"""Conversation layer of the AI assistant: instant answers, follow-ups, suggestion parsing."""

from app.ai import assistant
from app.core.config import get_settings

S = get_settings()


def _ask(msg, history=(), hindi=False, live=None):
    return assistant.instant_answer(msg, list(history), hindi=hindi, first_name="Ravi", settings=S, live=live)


def test_greeting_is_instant():
    a = _ask("Hello")
    assert a and "Ravi" in a.text and a.suggestions


def test_sla_answer_uses_configured_deadline():
    a = _ask("How long do I have to fix a critical violation?")
    assert a and a.topic == "sla" and f"{S.sla_critical_hours} hours" in a.text


def test_follow_up_inherits_previous_topic():
    history = [{"role": "user", "content": "How long do I have to fix a critical violation?"},
               {"role": "assistant", "content": "A critical violation must have..."}]
    a = _ask("What about a high one?", history)
    assert a and a.topic == "sla" and f"{S.sla_high_hours} hours" in a.text


def test_hindi_sla_answer():
    a = _ask("गंभीर उल्लंघन को ठीक करने का समय कितने घंटे है?", hindi=True)
    assert a and "घंटे" in a.text


def test_open_question_goes_to_model():
    assert _ask("What are the ventilation standards for underground coal mines?") is None


def test_retrieval_query_carries_context_for_follow_ups():
    history = [{"role": "user", "content": "What is the PM10 limit near coal mines?"}]
    q = assistant.retrieval_query("and for noise at night?", history)
    assert "PM10" in q and "noise" in q


def test_live_counts_answer():
    live = {"kpis": {"open_violations": 8, "critical_violations": 2}}
    a = _ask("How many open violations do I have?", live=live)
    assert a and "8 open violations" in a.text


def test_follow_up_marker_is_hidden_and_parsed():
    sp = assistant.FollowUpSplitter()
    shown = ""
    for tok in ["A critical ", "violation needs a fix", " within 4 hours.\n", "FOLLOW", "-UPS: What if it is missed", "? | Who verifies the fix?"]:
        shown += sp.feed(tok)
    shown += sp.flush()
    assert "FOLLOW" not in shown and shown.startswith("A critical violation")
    assert sp.follow_ups() == ["What if it is missed?", "Who verifies the fix?"]


def test_answer_without_marker_streams_everything():
    sp = assistant.FollowUpSplitter()
    shown = "".join(sp.feed(t) for t in ["Short ", "answer ", "here."]) + sp.flush()
    assert shown == "Short answer here." and sp.follow_ups() == []


def test_environment_limit_answer_is_instant_and_correct():
    a = _ask("What is the PM10 limit for coal mines and what should I do if a reading is above it?")
    assert a and a.topic == "environment" and "100 µg/m³" in a.text and "NAAQS 2009" in a.text


def test_noise_at_night_follow_up():
    history = [{"role": "user", "content": "What is the PM10 limit for coal mines?"}]
    a = _ask("and for noise at night?", history)
    assert a and "70 dB(A)" in a.text and "75" not in a.text


def test_how_to_answer():
    a = _ask("How do I report a violation?")
    assert a and a.topic == "violation" and "Report violation" in a.text


def test_prompt_is_compact():
    hits = [{"title": f"Doc {i}", "text": "x" * 2000} for i in range(3)]
    msgs = assistant.build_messages(question="q", hits=hits, history=[], name="Ravi", role="Mine Manager",
                                    mine="Kalinga", policy="p", live="l", hindi=False)
    assert sum(len(m["content"]) for m in msgs) < 2600
