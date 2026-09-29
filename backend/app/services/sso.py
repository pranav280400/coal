"""Government SSO via OpenID Connect (authorization code + PKCE).

Works with any standards-compliant OIDC provider: Parichay/MeriPehchaan (NIC),
Keycloak, Azure AD/Entra ID, Okta, etc. The ID token signature is verified
against the provider's JWKS; users are matched by verified email (or the stable
``sub`` claim once linked).
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

import anyio
import httpx
import jwt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import Forbidden, InvalidState, ServiceUnavailable
from app.core.redis import get_redis
from app.models import User
from app.models.enums import Role, UserStatus
from app.services.access import Principal
from app.services.events import record_event

_STATE_PREFIX = "cmg:sso:state:"
_discovery_cache: dict[str, Any] = {}
_jwks_clients: dict[str, jwt.PyJWKClient] = {}


def _require_enabled() -> None:
    s = get_settings()
    if not (s.sso_enabled and s.sso_issuer_url and s.sso_client_id):
        raise ServiceUnavailable("Single sign-on is not configured")


async def discovery() -> dict[str, Any]:
    s = get_settings()
    cached = _discovery_cache.get("doc")
    if cached and cached["expires"] > time.time():
        return cached["value"]
    url = s.sso_issuer_url.rstrip("/") + "/.well-known/openid-configuration"  # type: ignore[union-attr]
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        doc = resp.json()
    _discovery_cache["doc"] = {"value": doc, "expires": time.time() + 3600}
    return doc


async def build_authorize_url(return_to: str = "/dashboard") -> str:
    _require_enabled()
    s = get_settings()
    doc = await discovery()
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    safe_return = return_to if return_to.startswith("/") and not return_to.startswith("//") else "/"
    await get_redis().set(
        f"{_STATE_PREFIX}{state}",
        json.dumps({"nonce": nonce, "verifier": verifier, "return_to": safe_return}),
        ex=600,
    )
    params = {
        "response_type": "code",
        "client_id": s.sso_client_id,
        "redirect_uri": s.sso_redirect_uri,
        "scope": s.sso_scopes,
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return f"{doc['authorization_endpoint']}?{urlencode(params)}"


async def _verify_id_token(id_token: str, nonce: str, doc: dict[str, Any]) -> dict[str, Any]:
    s = get_settings()
    jwks_uri = doc["jwks_uri"]
    client = _jwks_clients.setdefault(jwks_uri, jwt.PyJWKClient(jwks_uri, cache_keys=True))
    signing_key = await anyio.to_thread.run_sync(client.get_signing_key_from_jwt, id_token)
    claims = jwt.decode(
        id_token,
        signing_key.key,
        algorithms=["RS256", "RS384", "RS512", "ES256", "ES384", "PS256"],
        audience=s.sso_client_id,
        issuer=doc["issuer"],
        options={"require": ["exp", "iat", "sub"]},
        leeway=60,
    )
    if claims.get("nonce") != nonce:
        raise Forbidden("SSO nonce mismatch")
    return claims


async def complete_login(session: AsyncSession, code: str, state: str) -> tuple[User, str]:
    """Exchange the authorization code and resolve the local user. Returns (user, return_to)."""
    _require_enabled()
    s = get_settings()
    raw = await get_redis().getdel(f"{_STATE_PREFIX}{state}")
    if not raw:
        raise InvalidState("SSO session expired or invalid state; please try again")
    saved = json.loads(raw)
    doc = await discovery()
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            doc["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": s.sso_redirect_uri,
                "client_id": s.sso_client_id,
                "client_secret": s.sso_client_secret.get_secret_value() if s.sso_client_secret else "",
                "code_verifier": saved["verifier"],
            },
            headers={"Accept": "application/json"},
        )
    if resp.status_code != 200:
        raise Forbidden("SSO provider rejected the login")
    tokens = resp.json()
    claims = await _verify_id_token(tokens["id_token"], saved["nonce"], doc)
    email = (claims.get("email") or "").lower()
    if claims.get("email_verified") is False:
        raise Forbidden("Your SSO email address is not verified")

    user = (await session.execute(select(User).where(User.sso_subject == claims["sub"]))).scalars().first()
    if user is None and email:
        user = (await session.execute(select(User).where(func.lower(User.email) == email))).scalars().first()
        if user is not None:
            user.sso_subject = claims["sub"]
    if user is None:
        domain = email.rsplit("@", 1)[-1] if "@" in email else ""
        if not (s.sso_auto_provision and email and (not s.sso_allowed_email_domains or domain in s.sso_allowed_email_domains)):
            raise Forbidden("No Lumen account is linked to this SSO identity. Request access first.")
        base_username = (claims.get("preferred_username") or email.split("@")[0])[:50]
        username = base_username
        suffix = 1
        while (await session.execute(select(User.id).where(User.username == username))).first():
            suffix += 1
            username = f"{base_username}{suffix}"
        user = User(
            username=username,
            email=email,
            full_name=claims.get("name") or username,
            role=Role(s.sso_default_role),
            # Auto-provisioned accounts still need an admin to scope them to a mine/subsidiary.
            status=UserStatus.PENDING if s.sso_default_role in ("mine_official", "contractor") else UserStatus.ACTIVE,
            sso_subject=claims["sub"],
        )
        session.add(user)
        await session.flush()
        record_event(session, "user.sso_provisioned", entity_type="user", entity_id=user.id, actor=None,
                     data={"issuer": doc["issuer"]})
    if user.status != UserStatus.ACTIVE:
        await session.commit()
        raise Forbidden("Your account is awaiting approval or disabled")
    user.last_login_at = datetime.now(UTC)
    record_event(session, "user.login", entity_type="user", entity_id=user.id, actor=Principal.from_user(user),
                 mine_id=user.mine_id, subsidiary_id=user.subsidiary_id, data={"method": "sso"})
    await session.commit()
    return user, saved["return_to"]
