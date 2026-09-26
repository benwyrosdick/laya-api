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
    runtime: str = "laya"


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

LEV_MODELS: dict[str, ModelCard] = {
    "lev-latest": ModelCard(
        name="lev-latest",
        description="Lev 350M on LiquidAI LFM2.5-350M. One forward pass, TypeSafe-shaped answers. Alias: jev-latest.",
        release_date="2026-09-22",
        checkpoint=None,
        runtime="lev",
    ),
}

_LEV_ALIASES = {
    "lev": "lev-latest",
    "latest": "lev-latest",
    "jev": "lev-latest",
    "jev-latest": "lev-latest",
}

KEV_MODELS: dict[str, ModelCard] = {
    "kev-latest": ModelCard(
        name="kev-latest",
        description="Kev on Qwen (default checkpoint jaredpalmer/kev-0.8b). Same question types as Jev. Set KEV_RUN to load 4b, 9b, or 27b.",
        release_date="2026-09-24",
        checkpoint=None,
        runtime="kev",
    ),
}

_KEV_ALIASES = {
    "kev": "kev-latest",
    "latest": "kev-latest",
    "kev-0.8b": "kev-latest",
    "kev-4b": "kev-latest",
    "kev-9b": "kev-latest",
    "kev-27b": "kev-latest",
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


def resolve_model(name: str, runtime: str = "laya") -> ModelCard:
    key = (name or "").strip()
    if not key:
        raise UnknownModelError("model is required")
    catalogs = {"laya": (MODELS, _ALIASES), "lev": (LEV_MODELS, _LEV_ALIASES), "kev": (KEV_MODELS, _KEV_ALIASES)}
    models, aliases = catalogs.get(runtime, catalogs["laya"])
    canonical = aliases.get(key.lower(), key)
    card = models.get(canonical) or models.get(canonical.lower())
    known = ", ".join(models)
    if card is None:
        raise UnknownModelError(f"unknown model {name!r}; choose one of: {known}")
    return card


def listed_models(runtime: str = "laya") -> list[ModelCard]:
    catalogs = {"laya": MODELS, "lev": LEV_MODELS, "kev": KEV_MODELS}
    catalog = catalogs.get(runtime, MODELS)
    return [card for card in catalog.values() if card.listed]
