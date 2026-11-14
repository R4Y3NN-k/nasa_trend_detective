# SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team
"""Plain-language summary and next-question suggestions, written by Gemini from numbers the app computed.

The model never sees raw data and may not add numbers: every number in its text must already be in the
facts we send, and every suggested question must be one of ours. Anything else falls back to a template.

Needs GEMINI_API_KEY (free key from Google AI Studio) in the environment or .env. Optional GEMINI_MODEL
(default below). Without a key, or if Gemini fails, the template text is used and the app still works.

Contract:
    explain(facts: dict, questions: dict) -> {"summary": str, "next": [question_id], "source": "gemini"|"template"}
"""
from __future__ import annotations

import json
import os
import re

import requests

from td import cache

DEFAULT_MODEL = "gemini-flash-lite-latest"  # alias to the newest Flash-Lite; fast and on the free tier
API = "https://generativelanguage.googleapis.com/v1beta"
TIMEOUT = 25
NUMBER = re.compile(r"[-+−]?\d+(?:[.,]\d+)?")

PROMPT = """You explain climate trend results to high-school students, farmers and curious adults.
Use ONLY the facts in the JSON below. Rules:
- 2 to 4 short sentences, plain words, no jargon (no "p-value", "OLS", "Mann-Kendall", "anomaly").
- Do not write any number that is not written exactly the same way in the facts. Round nothing, compute nothing.
- Say what changed, how sure we are (tier: significant = confident, suggestive = possible, none = no clear trend),
  and, ONLY if a cross_check is present, what it says about a second NASA dataset. If there is no cross_check, or its
  state is "single", do not mention other datasets or agreement at all.
- If the quick_scan shows another variable changing, you may mention it in one short sentence, always with its
  certainty word: tier significant = "clearly", suggestive = "possibly". Never mention a variable whose tier is none
  as changing.
- Never claim a cause. No filler sentences. End with exactly: "This shows a change, not its cause."
- Then pick 1 to 3 follow-up questions from "available_questions" (by id). They are listed most relevant for this
  climate first (e.g. snow and frost for a cold climate, extreme heat and drying for a desert): keep that order,
  except you may move up one whose quick_scan shows a change. Do not pick the question already answered.
Return JSON: {{"summary": "...", "next": ["id", ...]}}

FACTS:
{facts}
"""


def _numbers(text: str) -> set[str]:
    return {n.replace("−", "-").replace(",", ".").lstrip("+-") for n in NUMBER.findall(text)}


def numbers_ok(summary: str, facts_text: str) -> bool:
    """True when every number in the summary also appears in the facts (sign and formatting aside)."""
    allowed = _numbers(facts_text)
    return all(n in allowed for n in _numbers(summary))


def claims_ok(summary: str, facts: dict) -> bool:
    """No cross-check claim the facts don't support (these have no numbers, so numbers_ok can't catch them)."""
    low = summary.lower()
    state = (facts.get("cross_check") or {}).get("state")
    if state != "agree" and re.search(r"\bagree", low):
        return False
    if state not in ("agree", "disagree") and re.search(r"dataset|second source|another source|satellite", low):
        return False
    return not re.search(r"\b(caus|because|due to|driven by|leads? to)\w*", low.replace("not its cause", ""))


def rank_next(facts: dict, questions: dict) -> list[str]:
    """The next most relevant questions for this climate (questions arrive ranked), skipping the one just answered."""
    current, done = facts.get("question_id"), facts.get("var_id")
    return [qid for qid, q in questions.items() if qid != current and q.get("primary") != done][:3]


def template(facts: dict, questions: dict) -> dict:
    """Deterministic fallback: the app's own verdict words."""
    parts = [facts.get("verdict", {}).get("headline", "")]
    cc = facts.get("cross_check") or {}
    if cc.get("headline") and cc.get("state") in ("agree", "disagree"):
        parts.append(cc["headline"])
    text = ". ".join(p.rstrip(".") for p in parts if p)
    return {"summary": (text + ". " if text else "") + "This shows a change, not its cause.",
            "next": rank_next(facts, questions), "source": "template"}


def _api_key() -> str | None:
    from td.giovanni import _load_env_file

    _load_env_file()
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


def _call_gemini(prompt: str, key: str) -> str:
    model = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}}
    resp = requests.post(f"{API}/models/{model}:generateContent", json=body, timeout=TIMEOUT,
                         headers={"x-goog-api-key": key})
    resp.raise_for_status()
    return resp.json()["candidates"][0]["content"]["parts"][0]["text"]


def explain(facts: dict, questions: dict) -> dict:
    fallback = template(facts, questions)
    key = _api_key()
    if not key:
        return {**fallback, "why_template": "No GEMINI_API_KEY set."}
    # A list, not a dict: sort_keys below would otherwise lose the climate ranking.
    facts = {**facts, "available_questions": [{"id": qid, "label": q.get("label", qid)} for qid, q in questions.items()]}
    facts_text = json.dumps(facts, ensure_ascii=False, sort_keys=True)
    ck = cache.make_key("gemini-explain", os.environ.get("GEMINI_MODEL", DEFAULT_MODEL), PROMPT, facts_text)
    hit = cache.get(ck)
    if hit is not None:
        return hit
    try:
        out = json.loads(_call_gemini(PROMPT.format(facts=facts_text), key))
        summary = str(out.get("summary", "")).strip()
        nxt = [q for q in out.get("next", []) if q in questions and q != facts.get("question_id")][:3]
    except Exception as exc:  # network, quota, bad JSON: never break the verdict
        return {**fallback, "why_template": f"Gemini unavailable ({type(exc).__name__})."}
    if not summary or not numbers_ok(summary, facts_text):
        return {**fallback, "why_template": "Gemini's text was rejected (it used a number the app did not compute)."}
    if not claims_ok(summary, facts):
        return {**fallback, "why_template": "Gemini's text was rejected (a claim about other datasets or causes "
                                            "that the app did not establish)."}
    result = {"summary": summary, "next": nxt or fallback["next"], "source": "gemini"}
    cache.put(ck, result)
    return result
