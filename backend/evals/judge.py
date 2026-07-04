"""LLM-as-judge: absolute rubric scoring of one answer to one question.

The judge sees only (question, answer) — never which arm produced it, never
another arm's answer — so arms are compared through independent absolute
scores, not a head-to-head that leaks position bias. Temperature 0; strict
JSON out; a parse failure returns score None rather than a fabricated number.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

_RUBRIC = (
    "You are grading one answer to one question, alone, on an absolute scale. "
    "Score 0-10:\n"
    "- Correctness (0-4): are the claims, numbers, and reasoning right? A wrong "
    "core recommendation or wrong arithmetic caps this at 1.\n"
    "- Completeness (0-3): does it address every part the question actually "
    "asked (all named constraints/sub-questions)?\n"
    "- Decisiveness & practicality (0-3): does it commit to a concrete, usable "
    "recommendation with the load-bearing reasoning, instead of hedging or "
    "listing options?\n"
    "Length is NOT quality: do not reward padding; a short, correct, decisive "
    "answer scores high.\n\n"
    'Reply with ONLY a JSON object: {"score": <0-10>, "justification": "<one or '
    'two sentences>"}'
)

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


@dataclass
class Judgment:
    score: float | None
    justification: str


def parse_judgment(text: str) -> Judgment:
    match = _JSON_RE.search(text)
    if not match:
        return Judgment(None, f"unparseable: {text[:120]}")
    try:
        data = json.loads(match.group(0))
        score = float(data["score"])
    except Exception:
        return Judgment(None, f"unparseable: {text[:120]}")
    return Judgment(
        max(0.0, min(10.0, score)), str(data.get("justification", ""))[:400]
    )


async def judge_answer(llm, question: str, answer: str) -> Judgment:
    """Score one answer with the shared rubric. `llm` is any BaseChatModel
    (tests pass a fake; the CLI passes ChatGroq at temperature 0)."""
    if not answer.strip():
        return Judgment(0.0, "empty answer")
    prompt = (
        f"{_RUBRIC}\n\n"
        f"QUESTION:\n{question}\n\n"
        f"ANSWER TO GRADE:\n{answer}"
    )
    resp = await llm.ainvoke([{"role": "system", "content": prompt}])
    return parse_judgment(resp.content.strip())
