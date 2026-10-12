"""Versioned USD price table, with file and in-process overrides."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from importlib.resources import files
from pathlib import Path

from agentcost.errors import PriceError


@dataclass(frozen=True, slots=True)
class ModelPrice:
    """USD per 1,000,000 tokens."""

    input_per_million: Decimal
    output_per_million: Decimal


@dataclass(frozen=True, slots=True)
class PriceTable:
    """Snapshot of model prices.

    Lookup is exact, then the longest table key that is a hyphen or dot prefix
    of the requested id. ``gpt-4o-mini-2024-07-18`` matches ``gpt-4o-mini``
    rather than ``gpt-4o``.
    """

    version: str
    currency: str
    models: Mapping[str, ModelPrice]

    def __post_init__(self) -> None:
        object.__setattr__(self, "models", dict(self.models))

    @classmethod
    def bundled(cls) -> PriceTable:
        text = files("agentcost").joinpath("data/prices.json").read_text(encoding="utf-8")
        return cls.from_json(text)

    @classmethod
    def load(cls, path: str | Path) -> PriceTable:
        file = Path(path)
        try:
            text = file.read_text(encoding="utf-8")
        except OSError as exc:
            raise PriceError(f"cannot read price file {file}: {exc}") from exc
        try:
            return cls.from_json(text)
        except PriceError as exc:
            raise PriceError(f"{file}: {exc}") from exc

    @classmethod
    def from_json(cls, text: str) -> PriceTable:
        try:
            data = json.loads(text, parse_float=Decimal)
        except json.JSONDecodeError as exc:
            raise PriceError(f"invalid price JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise PriceError("price file must be a JSON object")
        version = data.get("version")
        currency = data.get("currency")
        raw_models = data.get("models")
        if not isinstance(version, str) or not version:
            raise PriceError("price file is missing a version string")
        if not isinstance(currency, str) or not currency:
            raise PriceError("price file is missing a currency string")
        if not isinstance(raw_models, dict) or not raw_models:
            raise PriceError("price file is missing a models object")
        models: dict[str, ModelPrice] = {}
        for name, spec in raw_models.items():
            if not isinstance(name, str) or not name:
                raise PriceError("model names must be non-empty strings")
            if not isinstance(spec, dict) or "input" not in spec or "output" not in spec:
                raise PriceError(f"model {name!r} needs input and output prices")
            models[name] = _price(name, spec["input"], spec["output"])
        return cls(version=version, currency=currency, models=models)

    def lookup(self, model: str) -> ModelPrice | None:
        exact = self.models.get(model)
        if exact is not None:
            return exact
        best_key = ""
        best: ModelPrice | None = None
        for key, price in self.models.items():
            if model.startswith(key + "-") or model.startswith(key + "."):
                if len(key) > len(best_key):
                    best_key = key
                    best = price
        return best

    def merge(self, other: PriceTable) -> PriceTable:
        if other.currency != self.currency:
            raise PriceError(f"cannot merge {other.currency} prices into a {self.currency} table")
        models = dict(self.models)
        models.update(other.models)
        version = (
            self.version if other.version == self.version else f"{self.version}+{other.version}"
        )
        return PriceTable(version=version, currency=self.currency, models=models)

    def override(self, models: Mapping[str, ModelPrice]) -> PriceTable:
        merged = dict(self.models)
        for name, price in models.items():
            if price.input_per_million < 0 or price.output_per_million < 0:
                raise PriceError(f"model {name!r} has a negative price")
            merged[name] = price
        return PriceTable(
            version=f"{self.version}+override",
            currency=self.currency,
            models=merged,
        )


def _price(name: str, raw_input: object, raw_output: object) -> ModelPrice:
    try:
        input_price = Decimal(str(raw_input))
        output_price = Decimal(str(raw_output))
    except Exception as exc:
        raise PriceError(f"model {name!r} has a non-numeric price") from exc
    if input_price < 0 or output_price < 0:
        raise PriceError(f"model {name!r} has a negative price")
    return ModelPrice(input_per_million=input_price, output_per_million=output_price)
