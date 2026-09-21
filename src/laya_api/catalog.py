"""Public model names, aliases, and how they map onto Laya checkpoints."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelCard:
    name: str
    description: str
    release_date: str
    checkpoint: str | None
    listed: bool = True


# checkpoint=None means the hosted Router picks english vs multilingual vs typed-decisions.
MODELS: dict[str, ModelCard] = {
    "laya-latest": ModelCard(
        name="laya-latest",
        description="Recommended. Routes each request to the best Laya checkpoint (English, multilingual, or typed-decisions).",
        release_date="2026-09-20",
        checkpoint=None,
    ),
    "laya": ModelCard(
        name="laya",
        description="English checkpoint: ModernBERT-large, 421M, 512 context.",
        release_date="2026-09-20",
        checkpoint="english",
    ),
    "laya-multilingual": ModelCard(
        name="laya-multilingual",
        description="Multilingual checkpoint: mmBERT-base, 322M, 1024 context, 100+ languages.",
        release_date="2026-09-20",
        checkpoint="multilingual",
    ),
    "laya-typed-decisions": ModelCard(
        name="laya-typed-decisions",
        description="Fine-tuned on typed-decisions workflows (invoices, security, support, agent traces).",
        release_date="2026-09-20",
        checkpoint="typed-decisions",
    ),
}

_ALIASES = {
    "router": "laya-latest",
    "laya-router": "laya-latest",
    "latest": "laya-latest",
    "english": "laya",
    "laya-english": "laya",
    "en": "laya",
    "multilingual": "laya-multilingual",
    "multi": "laya-multilingual",
    "ml": "laya-multilingual",
    "typed": "laya-typed-decisions",
    "typed-decisions": "laya-typed-decisions",
    "typed_decisions": "laya-typed-decisions",
}

CHECKPOINT_TO_PUBLIC = {
    "english": "laya",
    "multilingual": "laya-multilingual",
    "typed-decisions": "laya-typed-decisions",
}


class UnknownModelError(ValueError):
    pass


def resolve_model(name: str) -> ModelCard:
    key = (name or "").strip()
    if not key:
        raise UnknownModelError("model is required")
    canonical = _ALIASES.get(key.lower(), key)
    card = MODELS.get(canonical) or MODELS.get(canonical.lower())
    if card is None:
        known = ", ".join(MODELS)
        raise UnknownModelError(f"unknown model {name!r}; choose one of: {known}")
    return card


def listed_models() -> list[ModelCard]:
    return [card for card in MODELS.values() if card.listed]
