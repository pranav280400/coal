"""Conversation layer for the Lumen assistant.

Sits between the chat endpoint and the model to make the assistant feel fast and
helpful on modest (CPU-only) hardware:

* **Instant answers** for greetings and for questions the platform can answer from
  its own configuration or live data (deadlines, counts) — no model call at all.
* **Conversation memory**: short follow-ups ("what about a high one?") inherit the
  topic of the previous question, both for instant answers and for retrieval.
* **Compact prompts**: stable instructions first (so the model's prompt cache is
  reused across turns), then history, then the retrieved references + question.
* **Follow-up suggestions**: the model ends with a ``FOLLOW-UPS:`` line which is
  stripped from the streamed text and sent to the UI as chips; a topic-based list
  is used when the model forgets.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.core.config import Settings

# ------------------------------------------------------------------ language
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def wants_hindi(message: str, language: str | None) -> bool:
    if language == "hi":
        return True
    if language not in (None, "", "auto"):
        return False
    return bool(_DEVANAGARI.search(message))


# -------------------------------------------------------------------- topics
TOPIC_WORDS: dict[str, tuple[str, ...]] = {
    "sla": ("how long", "deadline", "time limit", "within how", "sla", "hours to", "days to", "समय", "कितने घंटे", "समय-सीमा"),
    "violation": ("violation", "breach", "non-compliance", "hazard", "उल्लंघन"),
    "action": ("corrective", "action", "fix", "सुधार"),
    "inspection": ("inspection", "inspect", "checklist", "निरीक्षण"),
    "compliance": ("compliance", "statutory", "obligation", "return", "due", "overdue", "अनुपालन"),
    "grievance": ("grievance", "complaint", "शिकायत"),
    "environment": ("pm10", "pm2.5", "dust", "air", "noise", "effluent", "water", "pollution", "environment", "पर्यावरण", "प्रदूषण"),
    "production": ("production", "despatch", "dispatch", "tonnes", "target", "overburden", "उत्पादन"),
    "contractor": ("contractor", "contract labour", "clra", "licence", "license", "ठेकेदार"),
    "attendance": ("attendance", "check-in", "shift", "उपस्थिति"),
    "risk": ("risk", "high-risk", "anomal", "repeated", "recurring", "जोखिम"),
}

FOLLOW_UP_CUES = ("what about", "how about", "and ", "also", "same for", "for a ", "for an ", "and for", "और", "उसके", "इसके")

SEVERITIES = {
    "critical": ("critical", "गंभीर"),
    "high": ("high", "major", "उच्च"),
    "medium": ("medium", "moderate", "मध्यम"),
    "low": ("low", "minor", "निम्न", "छोटा"),
}


def topic_of(text: str) -> str | None:
    t = text.lower()
    # SLA questions are about a *kind* of record, so check them first.
    if any(w in t for w in TOPIC_WORDS["sla"]) and any(w in t for w in TOPIC_WORDS["violation"] + TOPIC_WORDS["action"] + TOPIC_WORDS["grievance"] + ("fix",)):
        return "grievance_sla" if any(w in t for w in TOPIC_WORDS["grievance"]) else "sla"
    for name, words in TOPIC_WORDS.items():
        if name != "sla" and any(w in t for w in words):
            return name
    return None


def severity_in(text: str) -> str | None:
    t = text.lower()
    for sev, words in SEVERITIES.items():
        if any(re.search(rf"(^|\W){re.escape(w)}(\W|$)", t) for w in words):
            return sev
    return None


def is_follow_up(text: str) -> bool:
    t = text.strip().lower()
    return len(t.split()) <= 8 or t.startswith(FOLLOW_UP_CUES)


def last_user_message(history: list[dict[str, str]]) -> str | None:
    for m in reversed(history):
        if m["role"] == "user":
            return m["content"]
    return None


def resolve_topic(message: str, history: list[dict[str, str]]) -> str | None:
    """Topic of this turn; short follow-ups inherit the previous question's topic."""
    topic = topic_of(message)
    prev = last_user_message(history)
    if prev and is_follow_up(message):
        prev_topic = topic_of(prev)
        # "what about a high one?" after an SLA question stays an SLA question.
        if prev_topic in ("sla", "grievance_sla") and (topic in (None, "violation", "grievance") or severity_in(message)):
            return prev_topic
        return topic or prev_topic
    return topic


def retrieval_query(message: str, history: list[dict[str, str]]) -> str:
    """Give short follow-ups the context of the previous question for document search."""
    prev = last_user_message(history)
    if prev and is_follow_up(message):
        return f"{prev}\n{message}"
    return message


# -------------------------------------------------------------- suggestions
SUGGESTIONS_EN: dict[str, list[str]] = {
    "sla": ["What happens if the deadline is missed?", "How do I assign a corrective action?", "Which of my violations are close to escalation?"],
    "grievance_sla": ["Who can see an anonymous grievance?", "How do I raise a grievance?", "What happens when a grievance is escalated?"],
    "violation": ["How long do I have to fix a critical violation?", "Which mines have repeated violations?", "How do I report a violation?"],
    "action": ["Who verifies a corrective action?", "What evidence should I upload?", "What happens if an action is overdue?"],
    "inspection": ["What should a haul-road inspection check?", "How do I record an inspection offline?", "Summarise this month's inspection findings"],
    "compliance": ["Which statutory items are overdue?", "When are reminders sent?", "What happens when an item is overdue?"],
    "grievance": ["How long does a grievance take to resolve?", "Can I raise a grievance anonymously?", "Who resolves a grievance?"],
    "environment": ["What is the PM10 limit for coal mines?", "What happens when a reading is above the limit?", "Which mines had the most exceedances?"],
    "production": ["How is target achievement calculated?", "Which mines are below target?", "How do I file the monthly return?"],
    "contractor": ["What does the Contract Labour Act require?", "How is a contractor's compliance score worked out?", "How do I verify a contractor?"],
    "attendance": ["How do I record attendance without internet?", "Why is attendance geo-tagged?", "Where can I see today's attendance?"],
    "risk": ["Why is a mine marked high-risk?", "Which mines have repeated violations?", "How can a mine lower its risk score?"],
    None: ["How long do I have to fix a critical violation?", "Which statutory items are due soon?", "Which of my mines are high-risk?"],
}
SUGGESTIONS_HI: dict[str, list[str]] = {
    "sla": ["समय-सीमा चूकने पर क्या होता है?", "सुधारात्मक कार्रवाई कैसे सौंपें?", "मेरे कौन से उल्लंघन एस्केलेशन के करीब हैं?"],
    "grievance_sla": ["गुमनाम शिकायत कौन देख सकता है?", "शिकायत कैसे दर्ज करें?", "शिकायत आगे बढ़ने पर क्या होता है?"],
    None: ["गंभीर उल्लंघन को कितने समय में ठीक करना है?", "कौन से अनुपालन मद जल्द देय हैं?", "मेरी कौन सी खदानें उच्च जोखिम में हैं?"],
}


def suggestions_for(topic: str | None, hindi: bool) -> list[str]:
    if hindi:
        return SUGGESTIONS_HI.get(topic) or SUGGESTIONS_HI[None]
    return SUGGESTIONS_EN.get(topic) or SUGGESTIONS_EN[None]


# ----------------------------------------------------------- instant answers
@dataclass
class Instant:
    text: str
    topic: str | None
    suggestions: list[str] = field(default_factory=list)


_GREETING = re.compile(r"^\s*(hi|hello|hey|hii+|namaste|namaskar|good\s+(morning|afternoon|evening)|नमस्ते|नमस्कार|हेलो)\b[\s!.,]*\w{0,12}[\s!.]*$", re.I)
_THANKS = re.compile(r"^\s*(thanks|thank you|thx|ok(ay)? thanks|great,? thanks|धन्यवाद|शुक्रिया)\b.{0,20}$", re.I)
_HELP = re.compile(r"^\s*(help|what can you do|who are you|how can you help|आप क्या कर सकते हैं|मदद)\W*$", re.I)

_SEV_EN = {"critical": "Critical", "high": "High", "medium": "Medium", "low": "Low"}
_SEV_HI = {"critical": "गंभीर", "high": "उच्च", "medium": "मध्यम", "low": "निम्न"}
GRIEVANCE_SLA = {"critical": 24, "high": 72, "medium": 168, "low": 360}


def _hours(h: int, hindi: bool) -> str:
    if h % 24 == 0 and h >= 48:
        return f"{h // 24} दिन" if hindi else f"{h // 24} days"
    return f"{h} घंटे" if hindi else f"{h} hours"


def instant_answer(message: str, history: list[dict[str, str]], *, hindi: bool, first_name: str,
                   settings: Settings, live: dict[str, Any] | None) -> Instant | None:
    text = message.strip()
    if _GREETING.match(text):
        if hindi:
            body = (f"नमस्ते {first_name}! मैं ल्यूमेन सहायक हूँ। मैं इनमें मदद कर सकता हूँ:\n\n"
                    "- खनन नियम और वैधानिक दायित्व (CMR 2017, खान अधिनियम, पर्यावरण मानक)\n"
                    "- आपकी खदानों के उल्लंघन, निरीक्षण और समय-सीमाएँ\n"
                    "- ऐप में कोई काम कैसे करें\n\nआप क्या जानना चाहेंगे?")
        else:
            body = (f"Hello {first_name}! I'm the Lumen assistant. I can help you with:\n\n"
                    "- **Rules and obligations** — CMR 2017, the Mines Act, environmental limits\n"
                    "- **Your mines** — open violations, inspections and upcoming deadlines\n"
                    "- **Using Lumen** — how to report, assign, verify or file something\n\nWhat would you like to know?")
        return Instant(body, None, suggestions_for(None, hindi))
    if _THANKS.match(text):
        body = "आपका स्वागत है! कुछ और पूछना हो तो बताइए।" if hindi else "You're welcome! Is there anything else I can help you with?"
        prev_topic = topic_of(last_user_message(history) or "")
        return Instant(body, prev_topic, suggestions_for(prev_topic, hindi))
    if _HELP.match(text):
        return instant_answer("hello", history, hindi=hindi, first_name=first_name, settings=settings, live=live)

    topic = resolve_topic(text, history)
    if topic == "sla":
        sla = {"critical": settings.sla_critical_hours, "high": settings.sla_high_hours,
               "medium": settings.sla_medium_hours, "low": settings.sla_low_hours}
        sev = severity_in(text)
        esc_hi = (f"अगर समय पर कार्रवाई नहीं सौंपी गई, तो यह अपने-आप आगे बढ़ता है: स्तर 1 खदान प्रबंधन → स्तर 2 सहायक कंपनी → "
                  f"स्तर {settings.max_escalation_level} मुख्यालय।")
        esc_en = ("If no action is assigned in time, it escalates automatically: level 1 mine management → "
                  f"level 2 subsidiary → level {settings.max_escalation_level} head office.")
        if sev:
            if hindi:
                body = f"**{_SEV_HI[sev]}** उल्लंघन के लिए **{_hours(sla[sev], True)}** के भीतर सुधारात्मक कार्रवाई सौंपनी होती है।\n\n{esc_hi}"
            else:
                body = f"A **{_SEV_EN[sev].lower()}** violation must have a corrective action assigned within **{_hours(sla[sev], False)}**.\n\n{esc_en}"
        else:
            rows = "\n".join(f"| {(_SEV_HI if hindi else _SEV_EN)[k]} | {_hours(v, hindi)} |" for k, v in sla.items())
            head = "| गंभीरता | कार्रवाई सौंपने की समय-सीमा |\n|---|---|" if hindi else "| Severity | Assign a fix within |\n|---|---|"
            body = f"{head}\n{rows}\n\n{esc_hi if hindi else esc_en}"
        return Instant(body, "sla", suggestions_for("sla", hindi))
    if topic == "grievance_sla":
        sev = severity_in(text)
        if sev:
            body = (f"**{_SEV_HI[sev]}** प्राथमिकता की शिकायत **{_hours(GRIEVANCE_SLA[sev], True)}** में हल होनी चाहिए। समय-सीमा चूकने पर यह अपने-आप आगे बढ़ती है।"
                    if hindi else
                    f"A **{_SEV_EN[sev].lower()}**-priority grievance should be resolved within **{_hours(GRIEVANCE_SLA[sev], False)}**. "
                    "If that is missed it is escalated automatically, and the person who raised it confirms before it is closed.")
        else:
            rows = "\n".join(f"| {(_SEV_HI if hindi else _SEV_EN)[k]} | {_hours(v, hindi)} |" for k, v in GRIEVANCE_SLA.items())
            head = "| प्राथमिकता | हल करने की समय-सीमा |\n|---|---|" if hindi else "| Priority | Resolve within |\n|---|---|"
            body = f"{head}\n{rows}"
        return Instant(body, "grievance_sla", suggestions_for("grievance_sla", hindi))

    if topic == "environment" or any(w in f" {text.lower()} " for ws in _ENV_WORDS.values() for w in ws):
        env = env_answer(text, hindi)
        if env and not any(w in text.lower() for w in ("which mine", "most exceed", "how many", "trend")):
            return env
    how = howto_answer(text, hindi)
    if how:
        return how

    # Live counts for the user's own scope — straight from the dashboard snapshot.
    if live and not hindi:
        t = text.lower()
        k = live.get("kpis", {})
        asks_count = any(w in t for w in ("how many", "count", "number of", "list", "show", "which"))
        if asks_count and "violation" in t and "open" in t and "repeat" not in t:
            body = (f"You have **{k.get('open_violations', 0)} open violations**, "
                    f"of which **{k.get('critical_violations', 0)} are critical**. "
                    "Open the **Violations** page to see them, filter by mine or severity, and assign fixes.")
            return Instant(body, "violation", suggestions_for("violation", False))
        if ("deadline" in t or "due soon" in t or "upcoming" in t) and ("compliance" in t or "statutory" in t or "deadline" in t) and "how long" not in t:
            items = live.get("upcoming_deadlines") or []
            if not items:
                return Instant("Nothing is due soon — all statutory items in your scope are on schedule.", "compliance",
                               suggestions_for("compliance", False))
            lines = "\n".join(f"- **{d['title']}** — {d['mine_name']}, due {d['due_date']}" for d in items[:5])
            return Instant(f"Here are your nearest statutory deadlines:\n\n{lines}\n\nOpen **Compliance** to mark any of them complete.",
                           "compliance", suggestions_for("compliance", False))
        if ("high-risk" in t or "high risk" in t or "riskiest" in t) and "mine" in t and "why" not in t:
            mines = [m for m in live.get("high_risk_mines") or [] if m.get("risk_score") is not None]
            if mines:
                lines = "\n".join(f"- **{m['name']}** — risk score {m['risk_score']:.0f}/100" for m in mines[:5])
                return Instant(f"The mines with the highest predicted risk are:\n\n{lines}\n\n"
                               "See **Reports & Analytics → Risk scoring** for the reasons behind each score.",
                               "risk", suggestions_for("risk", False))
    return None


# ------------------------------------------------ environment limits (instant)
_ENV_WORDS = {
    "pm10": ("pm10", "pm 10", "pm-10"),
    "pm2_5": ("pm2.5", "pm 2.5", "pm2_5", "fine dust"),
    "so2": ("so2", "sulphur dioxide", "sulfur dioxide"),
    "no2": ("no2", "nitrogen dioxide"),
    "noise": ("noise", "sound", "decibel", "db(a)", "शोर"),
    "water_ph": ("ph ", " ph", "ph?", "acidity"),
    "water_tss": ("tss", "suspended solid"),
    "water_oil_grease": ("oil", "grease"),
    "water_cod": ("cod", "chemical oxygen"),
}
_ENV_ACTIONS = {
    "air": "Increase water sprinkling on haul roads and stockpiles, cover coal in transport, check dust extraction at crushers, and re-measure.",
    "noise": "Find the source (weighbridge, crushers, haul roads), service or enclose equipment, add barriers, limit night operations, and re-measure.",
    "water": "Route discharge through the effluent treatment plant or settling ponds, fix oil separators, stop the outflow until it is within limit, and re-test.",
}


def env_answer(text: str, hindi: bool) -> Instant | None:
    from app.models.enums import EnvParameter
    from app.services.operations import LIMITS

    t = f" {text.lower()} "
    found = [k for k, words in _ENV_WORDS.items() if any(w in t for w in words)]
    if not found or hindi:
        return None
    params: list[EnvParameter] = []
    for k in found:
        if k == "noise":
            if "night" in t:
                params.append(EnvParameter.NOISE_NIGHT)
            elif "day" in t:
                params.append(EnvParameter.NOISE_DAY)
            else:
                params += [EnvParameter.NOISE_DAY, EnvParameter.NOISE_NIGHT]
        else:
            params.append(EnvParameter(k))
    lines, groups = [], []
    for prm in params:
        lim = LIMITS[prm]
        rng = f"{lim.limit_min}–{lim.limit_max} {lim.unit}" if lim.limit_min is not None else f"{lim.limit_max:g} {lim.unit}"
        lines.append(f"- **{lim.label}**: {'between ' if lim.limit_min is not None else 'at most '}{rng} — {lim.standard}")
        if lim.group not in groups:
            groups.append(lim.group)
    body = "The permissible limit" + ("s are" if len(lines) > 1 else " is") + ":\n\n" + "\n".join(lines)
    body += ("\n\nIf a reading is above the limit, record it on the **Environment** page — Lumen opens an environment "
             "violation automatically so a fix is assigned within the deadline.\n\n**What to do:** "
             + " ".join(_ENV_ACTIONS[g] for g in groups))
    return Instant(body, "environment", suggestions_for("environment", False))


# ------------------------------------------------------ "how do I…" (instant)
_HOWTO = [
    (("report", "log", "raise", "record", "add"), ("violation", "hazard", "unsafe", "incident"),
     "To report a violation:\n\n1. Open **Violations → Report violation** (on a phone, tap **+** → *Report a violation*).\n"
     "2. Choose the mine, describe what you saw and add photos — the location is captured automatically.\n"
     "3. Submit. Lumen suggests a severity; an official confirms it, and the fixing deadline starts.\n\n"
     "It works without internet — the report is sent when the signal returns.", "violation"),
    (("assign", "give", "allocate"), ("action", "fix", "corrective"),
     "To assign a corrective action:\n\n1. Open the violation from **Violations**.\n2. Click **Assign corrective action**, "
     "pick the person and a deadline, and describe the fix.\n3. The assignee uploads evidence when done; someone else then "
     "verifies it before the violation closes.", "action"),
    (("record", "do", "start", "new", "conduct", "add"), ("inspection",),
     "To record an inspection:\n\n1. Go to **Inspections → New inspection** (or **+** on a phone).\n2. Pick the mine and "
     "inspection type, work through the checklist and add photos.\n3. Submit — the GPS location and time are attached, and "
     "any hazards found can be turned into violations.", "inspection"),
    (("raise", "file", "submit", "make", "register", "lodge"), ("grievance", "complaint"),
     "To raise a grievance:\n\n1. Open **Grievances → Raise grievance** (or **+** on a phone).\n2. Choose the mine, category and "
     "priority, and describe the problem. Tick *Raise anonymously* if you prefer — only administrators can then see who raised it.\n"
     "3. It is assigned an owner and a deadline; you confirm and rate the resolution before it is closed.", "grievance"),
    (("mark", "complete", "close", "finish", "update"), ("compliance", "statutory", "obligation", "return item"),
     "To mark a statutory item complete: open **Compliance**, click the item, choose **Record completion**, add notes and upload "
     "the evidence document. Recurring items automatically roll forward to their next due date.", "compliance"),
    (("file", "submit", "enter", "record"), ("production", "monthly return", "despatch"),
     "To file the monthly production return: open **Production → Record monthly return**, choose the mine and month, and "
     "enter target, coal produced, despatched, overburden and closing stock. Re-entering a month corrects it.", "production"),
    (("record", "enter", "add", "submit"), ("reading", "air quality", "effluent", "monitoring"),
     "To record an environmental reading: open **Environment → Record reading**, pick the mine and parameter, enter the value, "
     "station and time. A value above the legal limit opens a violation automatically.", "environment"),
    (("switch", "change", "use", "set"), ("hindi", "language", "english"),
     "Use the **EN / हि** switch in your profile menu (top-right on a computer, **Menu** on a phone). Your choice is remembered.", None),
    (("reset", "forgot", "change"), ("password",),
     "Use **Forgot Password?** on the sign-in page to get a reset link, or change it any time under **Settings → Change password**.", None),
]


def howto_answer(text: str, hindi: bool) -> Instant | None:
    t = text.lower()
    if hindi or not any(w in t for w in ("how", "where", "steps", "procedure", "can i", "way to")):
        return None
    for verbs, nouns, body, topic in _HOWTO:
        if any(n in t for n in nouns) and any(v in t for v in verbs):
            return Instant(body, topic, suggestions_for(topic, False))
    return None


# ---------------------------------------------------------------- LLM prompt
# Identical for every user and every question, so the model keeps it in its prompt cache.
SYSTEM = """You are the Lumen assistant, a friendly expert on Indian coal-mine compliance and the Lumen app.
Answer rules:
- Direct answer first (1-2 sentences), then short bullets only if useful. Under 100 words. Plain language.
- Use only facts from ATTACHED FILE, REFERENCE, USER DATA and APP RULES; cite references like [1]. If unsure, say so and \
suggest the mine safety officer or DGMS. Never invent rule numbers or limits.
- If you need a missing detail (which mine, period, activity), ask ONE short question instead of guessing.
- Last line exactly: FOLLOW-UPS: <short question> | <short question>
APP RULES:
{policy}"""


def build_messages(*, question: str, hits: list[dict[str, Any]], history: list[dict[str, str]], name: str,
                   role: str, mine: str | None, policy: str, live: str, hindi: bool,
                   files: list[tuple[str, str]] | None = None) -> list[dict[str, str]]:
    language = ("Reply in simple Hindi (Devanagari); keep regulation names as they are."
                if hindi else "Reply in the user's language.")
    user_ctx = (f"USER: {name}, {role}{', ' + mine if mine else ''}. Today {date.today().isoformat()}. {language}\n"
                f"USER DATA:\n{live}")
    msgs: list[dict[str, str]] = [{"role": "system", "content": SYSTEM.format(policy=policy)},
                                  {"role": "system", "content": user_ctx}]
    for m in history[-4:]:
        msgs.append({"role": m["role"], "content": m["content"][:320]})
    refs = "\n".join(f"[{i + 1}] {h['title']}: {h['text'][:330].strip()}" for i, h in enumerate(hits[:2])) or "(none)"
    attached = "".join(f"ATTACHED FILE \"{name}\" (relevant part):\n{text}\n\n" for name, text in files or [])
    msgs.append({"role": "user", "content": f"{attached}REFERENCE:\n{refs}\n\nQUESTION: {question}"})
    return msgs


# ------------------------------------------------------------ stream filter
_MARKER = re.compile(r"\n?[ \t]*[*_#>-]*[ \t]*follow[- ]?ups?(?:\s+questions?)?[ \t]*[*_]*[ \t]*:", re.I)
_HOLD = 24  # characters kept back so a marker split across tokens is never shown


class FollowUpSplitter:
    """Streams answer text while silently capturing the trailing FOLLOW-UPS line."""

    def __init__(self) -> None:
        self.pending = ""
        self.tail = ""
        self.capturing = False

    def feed(self, token: str) -> str:
        if self.capturing:
            self.tail += token
            return ""
        self.pending += token
        m = _MARKER.search(self.pending)
        if m:
            out, self.tail = self.pending[: m.start()], self.pending[m.end():]
            self.pending, self.capturing = "", True
            return out
        if len(self.pending) > _HOLD:
            out, self.pending = self.pending[:-_HOLD], self.pending[-_HOLD:]
            return out
        return ""

    def flush(self) -> str:
        out, self.pending = ("" if self.capturing else self.pending), ""
        return out

    def follow_ups(self) -> list[str]:
        parts = re.split(r"\s*\|\s*|\n+\s*(?:[-*•]|\d+[.)])?\s*", self.tail.strip())
        clean = []
        for p in parts:
            p = p.strip(" -*•\"'`")
            if 6 <= len(p) <= 120 and p not in clean:
                clean.append(p if p.endswith("?") else p.rstrip(".") + "?")
        return clean[:3]
