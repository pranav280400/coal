"""Operations CLI.

    python -m app.cli migrate              # alembic upgrade head (+ bootstrap admin, regulation library)
    python -m app.cli seed-demo            # demo/UAT dataset (refuses in production)
    python -m app.cli create-admin         # interactive/ENV-driven administrator creation
    python -m app.cli generate-secrets     # JWT secret, Fernet PII key, VAPID key pair, random passwords
    python -m app.cli verify-audit         # verify the audit hash chain
    python -m app.cli recompute-risk       # recompute risk scores + anomalies now (no Temporal needed)
    python -m app.cli reindex-knowledge    # (re)build the Qdrant RAG index from the regulation library
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import getpass
import json
import secrets
import sys

from alembic import command
from alembic.config import Config
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import dispose_engine, session_scope


def _alembic_upgrade() -> None:
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")


async def _bootstrap() -> None:
    from app.core.security import hash_password
    from app.models import User
    from app.models.enums import Role, UserStatus
    from app.seed.demo import seed_regulations
    from app.services.users import WeakPassword, ensure_strong

    s = get_settings()
    async with session_scope() as session:
        added = await seed_regulations(session)
        if added:
            print(f"regulation library: {added} provisions added")

    # Creating the first administrator is convenience, not a schema concern. The API,
    # worker and consumers all gate on `migrate` completing successfully, so a rejected
    # BOOTSTRAP_ADMIN_PASSWORD must not fail the job and strand the whole app tier —
    # report it loudly and let the operator fix it with `create-admin`.
    if s.bootstrap_admin_email and s.bootstrap_admin_password:
        try:
            async with session_scope() as session:
                exists = (await session.execute(select(User.id).where(User.role == Role.ADMIN))).first()
                if not exists:
                    ensure_strong(s.bootstrap_admin_password.get_secret_value())
                    session.add(User(username=s.bootstrap_admin_username, email=s.bootstrap_admin_email.lower(),
                                     full_name="System Administrator", role=Role.ADMIN, status=UserStatus.ACTIVE,
                                     password_hash=hash_password(s.bootstrap_admin_password.get_secret_value())))
                    print(f"bootstrap administrator '{s.bootstrap_admin_username}' created")
        except WeakPassword as exc:
            print(f"WARNING: no administrator created — BOOTSTRAP_ADMIN_PASSWORD rejected: {exc}")
            print("         Fix it in .env and re-run, or: python -m app.cli create-admin --username … --email …")
        except Exception as exc:
            print(f"WARNING: no administrator created ({type(exc).__name__}: {exc}); "
                  "use `python -m app.cli create-admin` once the stack is up")
    await dispose_engine()


def cmd_migrate(_: argparse.Namespace) -> None:
    _alembic_upgrade()
    asyncio.run(_bootstrap())
    print("database is up to date")


async def _seed(force: bool) -> None:
    from app.seed.demo import already_seeded, seed_demo
    from app.services import analytics

    s = get_settings()
    if s.is_production and not force:
        sys.exit("Refusing to load demo data in production (use --force if you really mean it).")
    async with session_scope() as session:
        present = await already_seeded(session)
        if not present:
            admin_pw = s.bootstrap_admin_password.get_secret_value() if s.bootstrap_admin_password else None
            summary = await seed_demo(session, admin_password=admin_pw)
    if present:
        print("demo data already present — skipping the core seed")
    else:
        print(json.dumps(summary, indent=2))
    await _seed_operations()
    if present:
        await dispose_engine()
        return
    # Post-seed analytics. Each step is independent: e.g. model training needs object storage,
    # but risk scoring falls back to the expert baseline without it.
    for label, step in (("training risk model", analytics.train_risk_model),
                        ("risk scores", analytics.recompute_risk),
                        ("anomalies", analytics.detect_all)):
        try:
            async with session_scope() as session:
                print(f"{label}:", json.dumps(await step(session), default=str))
        except Exception as exc:
            print(f"{label}: skipped ({type(exc).__name__}: {exc})")
    await dispose_engine()


async def _seed_operations() -> None:
    """Grievances, production returns and environmental readings (safe to re-run)."""
    from app.seed.operations import seed_operations

    async with session_scope() as session:
        print("operations:", json.dumps(await seed_operations(session), default=str))


def cmd_seed_operations(_: argparse.Namespace) -> None:
    async def run() -> None:
        await _seed_operations()
        await dispose_engine()

    asyncio.run(run())


def cmd_seed(args: argparse.Namespace) -> None:
    asyncio.run(_seed(args.force))


async def _create_admin(username: str, email: str, full_name: str, password: str) -> None:
    from app.core.security import hash_password
    from app.models import User
    from app.models.enums import Role, UserStatus
    from app.services.users import ensure_strong

    ensure_strong(password, username=username)
    async with session_scope() as session:
        session.add(User(username=username, email=email.lower(), full_name=full_name, role=Role.ADMIN,
                         status=UserStatus.ACTIVE, password_hash=hash_password(password)))
    await dispose_engine()
    print(f"administrator '{username}' created")


def cmd_create_admin(args: argparse.Namespace) -> None:
    password = args.password or getpass.getpass("Password: ")
    asyncio.run(_create_admin(args.username, args.email, args.full_name, password))


def cmd_generate_secrets(_: argparse.Namespace) -> None:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    raw_private = key.private_numbers().private_value.to_bytes(32, "big")
    raw_public = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)

    def b64(b: bytes) -> str:
        return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

    print("# Paste into .env (never commit this file)")
    print(f"JWT_SECRET_KEY={secrets.token_urlsafe(64)}")
    print(f"PII_ENCRYPTION_KEY={Fernet.generate_key().decode()}")
    print(f"VAPID_PUBLIC_KEY={b64(raw_public)}")
    print(f"VAPID_PRIVATE_KEY={b64(raw_private)}")
    print(f"POSTGRES_PASSWORD={secrets.token_urlsafe(24)}")
    print(f"REDIS_PASSWORD={secrets.token_urlsafe(24)}")
    print(f"QDRANT_API_KEY={secrets.token_urlsafe(32)}")
    print(f"LLM_API_KEY=sk-{secrets.token_urlsafe(32)}")
    print(f"VLLM_API_KEY={secrets.token_urlsafe(32)}")
    print(f"S3_SECRET_ACCESS_KEY={secrets.token_urlsafe(32)}")
    print(f"GRAFANA_ADMIN_PASSWORD={secrets.token_urlsafe(18)}")


async def _verify() -> None:
    from app.services.audit import verify_chain

    async with session_scope() as session:
        result = await verify_chain(session)
    await dispose_engine()
    print(json.dumps(result, default=str, indent=2))
    if not result["valid"]:
        sys.exit(2)


def cmd_verify(_: argparse.Namespace) -> None:
    asyncio.run(_verify())


async def _recompute() -> None:
    from app.services import analytics

    async with session_scope() as session:
        print(json.dumps(await analytics.recompute_risk(session), default=str))
    async with session_scope() as session:
        print(json.dumps(await analytics.detect_all(session), default=str))
    await dispose_engine()


def cmd_recompute(_: argparse.Namespace) -> None:
    asyncio.run(_recompute())


async def _reindex(force: bool) -> None:
    """Embed the regulation library into Qdrant without going through Temporal.

    Useful right after pointing the stack at a new inference backend: the nightly
    KnowledgeIndexWorkflow has not run yet, so the assistant would retrieve nothing.
    This duplicates the body of the ``index_regulations`` activity rather than calling
    it, because that function heartbeats into a Temporal activity context we are not in.
    """
    from sqlalchemy import select as _select

    from app.ai import vectorstore
    from app.models import Regulation

    s = get_settings()
    await vectorstore.ensure_collection()
    async with session_scope() as session:
        stmt = _select(Regulation)
        if not force:
            stmt = stmt.where(Regulation.is_embedded.is_(False))
        regs = (await session.execute(stmt)).scalars().all()
        total = len(regs)
        if not total:
            print("nothing to embed (use --force to re-embed the whole library)")
        for n, reg in enumerate(regs, 1):
            await vectorstore.upsert_source(
                source_type="regulation", source_id=str(reg.id),
                title=f"{reg.act} — {reg.section or reg.code}: {reg.title}",
                text=reg.text, category=reg.category.value,
                extra={"code": reg.code, "act": reg.act},
            )
            reg.is_embedded = True
            print(f"  [{n}/{total}] {reg.code}", flush=True)

    client = vectorstore.qdrant()
    info = await client.get_collection(s.qdrant_collection)
    print(json.dumps({"embedded_now": total, "collection": s.qdrant_collection,
                      "points": info.points_count, "vector_size": s.embedding_dim}, indent=2))
    await dispose_engine()


def cmd_reindex(args: argparse.Namespace) -> None:
    asyncio.run(_reindex(args.force))


def main() -> None:
    parser = argparse.ArgumentParser(prog="coalminegov")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate").set_defaults(fn=cmd_migrate)
    p = sub.add_parser("seed-demo")
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_seed)
    sub.add_parser("seed-operations").set_defaults(fn=cmd_seed_operations)
    p = sub.add_parser("create-admin")
    p.add_argument("--username", required=True)
    p.add_argument("--email", required=True)
    p.add_argument("--full-name", default="System Administrator")
    p.add_argument("--password", help="omit to be prompted (recommended)")
    p.set_defaults(fn=cmd_create_admin)
    sub.add_parser("generate-secrets").set_defaults(fn=cmd_generate_secrets)
    sub.add_parser("verify-audit").set_defaults(fn=cmd_verify)
    sub.add_parser("recompute-risk").set_defaults(fn=cmd_recompute)
    p = sub.add_parser("reindex-knowledge")
    p.add_argument("--force", action="store_true", help="re-embed everything, not just new rows")
    p.set_defaults(fn=cmd_reindex)
    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
