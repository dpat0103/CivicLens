"""
Generation providers.

The model only ever sees the explanatory path, and only ever sees retrieved
context. The system prompt below forbids introducing numbers that are not
present in that context, but the prompt is a second line of defence, not the
first. The first is that questions asking for numbers never reach here at all.

`ExtractiveLLM` is the zero-configuration fallback. It stitches together the
retrieved chunks without a model, so the endpoint degrades to something
honest and still cited rather than erroring when no API key is set. It is
also what the test suite runs against, which keeps assertions deterministic.
"""
from __future__ import annotations

import os
import re
from typing import Protocol

SYSTEM_PROMPT = """You are the CivicLens data assistant. You explain public \
statistics about New Jersey municipalities.

Rules:
1. Use only the facts in CONTEXT. Never introduce a number, date, place or \
trend that is not there.
2. If CONTEXT does not answer the question, say so in one sentence. Do not \
guess or fill gaps from general knowledge.
3. If CONTEXT is marked simulated, say the figures are demonstration data.
4. Answer in 2 to 4 sentences. Lead with the direct answer, then at most one \
sentence of context. Do not restate the question, do not list every figure \
you were given, and do not add a closing summary.
5. Write plainly. No preamble like "Based on the data provided".
6. Do not invent citations. Sources are attached by the interface."""


class LLMProvider(Protocol):
    name: str

    def generate(self, system: str, user: str) -> str:
        ...


class ExtractiveLLM:
    """Zero-configuration fallback with no model behind it.

    The previous version concatenated whole retrieved passages, which
    produced walls of text nobody read: a fact card lists every indicator
    for a municipality, and two of them stitched together is thirty numbers
    with no answer in sight.

    This version selects sentences instead. It scores each sentence in the
    retrieved context against the question's own terms and returns only the
    best few, in their original order. That is genuinely extractive
    summarisation rather than a dump, it cannot state anything that was not
    retrieved, and it is deterministic, which is what keeps the eval suite
    reproducible.
    """

    name = "extractive"
    MAX_SENTENCES = 3

    def generate(self, system: str, user: str) -> str:
        context = user.split("CONTEXT:", 1)[-1].split("QUESTION:", 1)[0].strip()
        question = user.split("QUESTION:", 1)[-1].strip()
        if not context:
            return "No data held that answers that question."

        sentences: list[str] = []
        for passage in context.split("\n---\n"):
            for raw in re.split(r"(?<=[.!?])\s+", passage.strip()):
                cleaned = raw.strip()
                if len(cleaned) > 15:
                    sentences.append(cleaned)
        if not sentences:
            return "No data held that answers that question."

        question_lower = question.lower()
        terms = {t for t in re.findall(r"[a-z]{4,}", question_lower)}
        # A "why" question wants the sentence that gives a reason, and term
        # overlap alone does not find it: asking why two towns share an
        # employment figure scores highest on the sentence that restates
        # that they do. Cue phrases are the standard extractive-QA fix, and
        # they pick out the sentence that actually explains.
        wants_reason = question_lower.strip().startswith(("why", "how come"))
        CUES = ("because", "since", "cannot", "opaque", "deliberate",
                "rather than", "reason", "expected", "tradeoff", "so that",
                "which means", "therefore")

        scored = []
        for index, sentence in enumerate(sentences):
            lowered = sentence.lower()
            words = set(re.findall(r"[a-z]{4,}", lowered))
            overlap = len(terms & words)
            # Prefer sentences carrying a figure, since the question is
            # nearly always about one.
            has_number = 1 if re.search(r"\d", sentence) else 0
            cue_bonus = 3 if wants_reason and any(c in lowered for c in CUES) else 0
            scored.append((overlap * 2 + has_number + cue_bonus, -index, index, sentence))

        scored.sort(reverse=True)
        chosen = sorted(scored[: self.MAX_SENTENCES], key=lambda item: item[2])
        return " ".join(sentence for *_, sentence in chosen)


class AnthropicLLM:
    name = "anthropic"

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6"):
        if not api_key:
            raise ValueError("AnthropicLLM requires ANTHROPIC_API_KEY")
        self.api_key = api_key
        self.model = model

    def generate(self, system: str, user: str) -> str:
        import requests

        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": self.model,
                "max_tokens": 350,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
            timeout=60,
        )
        resp.raise_for_status()
        blocks = resp.json().get("content", [])
        return "\n".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()


def get_llm() -> LLMProvider:
    provider = os.getenv("LLM_PROVIDER", "extractive").lower()
    if provider == "anthropic":
        return AnthropicLLM(
            os.getenv("ANTHROPIC_API_KEY", ""),
            os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
        )
    if provider == "extractive":
        return ExtractiveLLM()
    raise ValueError(f"Unknown LLM_PROVIDER '{provider}'")