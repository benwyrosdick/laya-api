from __future__ import annotations

import json
import logging
import math
import re
import threading
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger("laya_api.engine")

from laya_api.catalog import CHECKPOINT_TO_PUBLIC, ModelCard
from laya_api.schemas import (
    Answer,
    ChoiceAnswer,
    NoulAnswer,
    Routing,
    ScoreAnswer,
    SystemOneResponse,
    Usage,
)


def flatten_state(state: Any) -> str:
    if isinstance(state, str):
        return state
    try:
        return json.dumps(state, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(state)


def public_model_name(checkpoint: str) -> str:
    return CHECKPOINT_TO_PUBLIC.get(checkpoint, checkpoint)


def _confidence(probs: list[float]) -> float:
    if not probs:
        return 0.0
    ordered = sorted(probs, reverse=True)
    top = ordered[0]
    gap = top - ordered[1] if len(ordered) > 1 else top
    entropy = -sum(p * math.log(p + 1e-12) for p in probs)
    max_ent = math.log(len(probs)) if len(probs) > 1 else 1.0
    return round(max(0.0, min(1.0, 0.5 * gap + 0.5 * (1 - entropy / max_ent))), 4)


class DecisionEngine(ABC):
    blocking_startup: bool = True

    @abstractmethod
    async def startup(self) -> None: ...

    @abstractmethod
    async def predict(self, state: Any, questions: dict[str, Any], card: ModelCard) -> SystemOneResponse: ...


class StubEngine(DecisionEngine):
    """Deterministic heuristic stand-in so the API can run without downloading Laya."""

    _urgent = re.compile(
        r"\b(asap|urgent|immediately|right now|today|emergency|down|outage|blocked|failing|deadline)\b",
        re.I,
    )
    _refund = re.compile(r"\b(refund|charged twice|duplicate|billed twice|money back)\b", re.I)
    _cancel = re.compile(r"\b(cancel|churn|leave|competitor|unsubscribe|won't use)\b", re.I)
    _angry = re.compile(r"\b(angry|furious|unacceptable|worst|lawsuit|outrage|hate)\b", re.I)
    _billing = re.compile(r"\b(invoice|charge|refund|billed|payment|stripe|payout|billing)\b", re.I)
    _tech = re.compile(r"\b(bug|outage|error|integration|api|crash|timeout|500|down)\b", re.I)
    _sales = re.compile(r"\b(pricing|upgrade|demo|plan|quote|enterprise)\b", re.I)

    async def startup(self) -> None:
        return None

    async def predict(self, state: Any, questions: dict[str, Any], card: ModelCard) -> SystemOneResponse:
        text = flatten_state(state)
        if card.runtime == "lev":
            answers = {qid: self._answer(text, q if isinstance(q, dict) else q.model_dump()) for qid, q in questions.items()}
            return SystemOneResponse(
                model=card.name,
                answers=answers,
                usage=Usage(input_tokens=max(1, len(text.split())), output_tokens=0),
                routing=None,
            )
        resolved_checkpoint = card.checkpoint or self._route_checkpoint(text)
        answers: dict[str, Answer] = {}
        for qid, question in questions.items():
            payload = question if isinstance(question, dict) else question.model_dump()
            answers[qid] = self._answer(text, payload)
        token_count = max(1, len(text.split()) + sum(len(flatten_state(q).split()) for q in questions.values()))
        return SystemOneResponse(
            model=public_model_name(resolved_checkpoint),
            answers=answers,
            usage=Usage(input_tokens=token_count, output_tokens=0),
            routing=Routing(
                model=resolved_checkpoint,
                repo="stub",
                reason="stub engine" if card.checkpoint else f"stub routed to {resolved_checkpoint}",
            ),
        )

    def _route_checkpoint(self, text: str) -> str:
        if re.search(r"[^\x00-\x7F]", text) and re.search(r"[^\W\d_]", text, re.UNICODE):
            non_ascii_letters = re.findall(r"[^\x00-\x7F]", text)
            if non_ascii_letters:
                return "multilingual"
        return "english"

    def _answer(self, text: str, question: dict[str, Any]) -> Answer:
        qtype = question["type"]
        if qtype == "noul":
            p = self._noul_probability(text, question)
            return NoulAnswer(noul=round(p, 4))
        if qtype == "choice":
            criteria = question.get("criteria") or {}
            keys = list(criteria.keys())
            scores = [self._option_score(text, key, criteria[key]) for key in keys]
            shifted = [math.exp(s) for s in scores]
            total = sum(shifted) or 1.0
            probs = [s / total for s in shifted]
            winner = keys[max(range(len(keys)), key=lambda i: probs[i])]
            return ChoiceAnswer(
                choice=winner,
                probabilities={k: round(p, 4) for k, p in zip(keys, probs)},
                confidence=_confidence(probs),
            )
        criteria = question.get("criteria") or []
        n = len(criteria)
        intensity = 0.2
        if self._urgent.search(text):
            intensity += 0.35
        if self._angry.search(text):
            intensity += 0.35
        if self._cancel.search(text):
            intensity += 0.15
        intensity = min(0.98, intensity)
        # Triangle around the expected level so the distribution is peaked, not one-hot.
        expected = intensity * (n - 1)
        probs = []
        for i in range(n):
            dist = abs(i - expected)
            probs.append(math.exp(-2.2 * dist))
        total = sum(probs)
        probs = [p / total for p in probs]
        score = sum(i * p for i, p in enumerate(probs))
        return ScoreAnswer(
            score=round(score, 4),
            legend={str(i): _legend_label(c) for i, c in enumerate(criteria)},
            probabilities={str(i): round(p, 4) for i, p in enumerate(probs)},
            confidence=_confidence(probs),
        )

    def _noul_probability(self, text: str, question: dict[str, Any]) -> float:
        blob = flatten_state(question.get("instructions", "")).lower() + " " + text.lower()
        p = 0.12
        if "urgent" in blob or "time" in blob or "deadline" in blob:
            p = 0.18 + (0.72 if self._urgent.search(text) else 0.08)
        if "refund" in blob:
            p = 0.82 if self._refund.search(text) else 0.08
        if "churn" in blob or "cancel" in blob or "leave" in blob:
            p = 0.78 if self._cancel.search(text) else 0.1
        if "spam" in blob:
            p = 0.12
        if "phish" in blob:
            p = 0.09
        if "jailbreak" in blob or "injection" in blob:
            p = 0.85 if re.search(r"ignore .{0,40}(instructions|rules)", text, re.I) else 0.07
        return min(0.98, max(0.02, p))

    def _option_score(self, text: str, key: str, description: Any) -> float:
        hay = text.lower()
        score = 0.15
        key_l = key.lower().replace("_", " ")
        if key_l in hay:
            score += 1.6
        desc = flatten_state(description).lower() if description is not None else ""
        for token in re.findall(r"[a-z0-9]{4,}", desc):
            if token in hay:
                score += 0.45
        if key_l in {"billing", "refund"} and self._billing.search(text):
            score += 1.4
        if key_l in {"technical", "technical help", "technical_help"} and self._tech.search(text):
            score += 1.4
        if key_l in {"sales"} and self._sales.search(text):
            score += 1.2
        if key_l in {"other"}:
            score += 0.05
        return score


def _legend_label(value: Any) -> str:
    if isinstance(value, str):
        return value
    return flatten_state(value)


class LayaEngine(DecisionEngine):
    blocking_startup = False

    def __init__(self, device: str | None, preload: bool) -> None:
        self.device = device or None
        self.preload = preload
        self._router = None
        self._lock = threading.Lock()

    async def startup(self) -> None:
        import asyncio

        await asyncio.to_thread(self._load)

    def _load(self) -> None:
        try:
            from laya import Router
        except ImportError as exc:
            raise RuntimeError(
                "ENGINE=laya requires the Laya package. Install with: pip install 'laya-api[engine]'"
            ) from exc
        kwargs: dict[str, Any] = {"preload": self.preload, "max_loaded": 3}
        if self.device:
            kwargs["device"] = self.device
        logger.info("Loading Laya Router device=%s preload=%s (CPU can take several minutes)", self.device, self.preload)
        self._router = Router(**kwargs)
        logger.info("Laya Router ready: %s", self._router)

    async def predict(self, state: Any, questions: dict[str, Any], card: ModelCard) -> SystemOneResponse:
        import asyncio

        if self._router is None:
            raise RuntimeError("Laya engine is not started")
        raw_questions = {
            qid: (q if isinstance(q, dict) else q.model_dump()) for qid, q in questions.items()
        }
        result = await asyncio.to_thread(self._predict_sync, state, raw_questions, card)
        return _from_laya_result(result, card)

    def _predict_sync(self, state: Any, questions: dict[str, Any], card: ModelCard) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        if card.checkpoint:
            kwargs["model"] = card.checkpoint
        with self._lock:
            return self._router.predict(state, questions, **kwargs)


def _from_laya_result(result: dict[str, Any], card: ModelCard) -> SystemOneResponse:
    routing_raw = result.get("routing") or {}
    checkpoint = routing_raw.get("model") or card.checkpoint or "english"
    answers: dict[str, Answer] = {}
    for qid, raw in (result.get("answers") or {}).items():
        answers[qid] = _public_answer(raw)
    usage_raw = result.get("usage") or {}
    routing = None
    if routing_raw:
        routing = Routing(
            model=str(routing_raw.get("model", checkpoint)),
            repo=routing_raw.get("repo"),
            reason=routing_raw.get("reason"),
            workflow=routing_raw.get("workflow"),
            detection=routing_raw.get("detection"),
        )
    return SystemOneResponse(
        model=public_model_name(str(checkpoint)),
        answers=answers,
        usage=Usage(
            input_tokens=int(usage_raw.get("input_tokens") or 0),
            output_tokens=int(usage_raw.get("output_tokens") or 0),
        ),
        routing=routing,
    )


def _public_answer(raw: dict[str, Any]) -> Answer:
    qtype = raw.get("type")
    if qtype == "choice":
        return ChoiceAnswer(
            choice=str(raw["choice"]),
            probabilities={str(k): float(v) for k, v in (raw.get("probabilities") or {}).items()},
            confidence=float(raw.get("confidence") or 0.0),
        )
    if qtype == "score":
        legend = raw.get("legend") or {}
        return ScoreAnswer(
            score=float(raw["score"]),
            legend={str(k): str(v) for k, v in legend.items()},
            probabilities={str(k): float(v) for k, v in (raw.get("probabilities") or {}).items()},
            confidence=float(raw.get("confidence") or 0.0),
        )
    return NoulAnswer(noul=float(raw["noul"]))


class LevEngine(DecisionEngine):
    """Lev 350M (LFM2.5) served in-process. Weights default to franckverrot/lev-350m."""

    blocking_startup = False

    def __init__(self, run: str, device: str | None) -> None:
        self.run = run or "franckverrot/lev-350m"
        self.device = device or None
        self._lock = threading.Lock()
        self._tok = None
        self._model = None
        self._temperature = 1.0

    async def startup(self) -> None:
        import asyncio

        await asyncio.to_thread(self._load)

    def _load(self) -> None:
        try:
            import torch
            from lev.evaluate import load, resolve_run
            from lev.serve import load_temperature
        except ImportError as exc:
            raise RuntimeError(
                "The lev runtime requires the lev package. Install with: pip install 'laya-api[lev]'"
            ) from exc
        run = resolve_run(self.run)
        if self.device:
            dev = self.device
        elif torch.cuda.is_available():
            dev = "cuda"
        else:
            dev = "cpu"
        logger.info("Loading Lev checkpoint %s on %s", self.run, dev)
        self._tok, self._model = load(run, dev)
        self._temperature, source = load_temperature(run)
        logger.info("Lev ready temperature=%.3f (%s)", self._temperature, source)

    async def predict(self, state: Any, questions: dict[str, Any], card: ModelCard) -> SystemOneResponse:
        import asyncio

        if self._model is None:
            raise RuntimeError("Lev engine is not started")
        raw_questions = {qid: (q if isinstance(q, dict) else q.model_dump()) for qid, q in questions.items()}
        return await asyncio.to_thread(self._predict_sync, state, raw_questions, card)

    def _predict_sync(self, state: Any, questions: dict[str, Any], card: ModelCard) -> SystemOneResponse:
        import torch
        from lev.api import SystemOneRequest as LevRequest
        from lev.api import output_tokens, to_answers, to_record

        req = LevRequest.model_validate({"state": state, "model": card.name, "questions": questions})
        record, meta = to_record(req)
        with self._lock:
            encoded = self._model.encode(self._tok, record, max_state=8192, max_branch=8192)
            with torch.no_grad():
                probs = [torch.softmax(z / self._temperature, -1).cpu().tolist() for z in self._model.forward(encoded)]
        answers = {qid: _public_answer(raw) for qid, raw in to_answers(probs, meta).items()}
        input_tokens = len(encoded["ids"])
        return SystemOneResponse(
            model=card.name,
            answers=answers,
            usage=Usage(input_tokens=input_tokens, output_tokens=output_tokens(self._tok, to_answers(probs, meta))),
            routing=None,
        )


def build_engine(kind: str, device: str | None, preload: bool, *, lev_run: str = "franckverrot/lev-350m") -> DecisionEngine:
    if kind in {"stub", "heuristic", "fake"}:
        return StubEngine()
    if kind in {"laya", "real"}:
        return LayaEngine(device=device, preload=preload)
    if kind == "lev":
        return LevEngine(run=lev_run, device=device)
    raise ValueError(f"unknown ENGINE {kind!r}; use 'stub', 'laya', or 'lev'")
