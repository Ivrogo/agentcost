"""Versioned model price table."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from agentcost import ModelPrice, PriceError, PriceTable


def test_bundled_table_is_versioned_and_matches_dated_snapshots() -> None:
    table = PriceTable.bundled()
    assert table.version == "2026-10-29"
    assert table.currency == "USD"
    dated = table.lookup("gpt-4o-mini-2024-07-18")
    assert dated == ModelPrice(
        input_per_million=Decimal("0.15"),
        output_per_million=Decimal("0.60"),
        cache_read_per_million=Decimal("0.075"),
        source="https://developers.openai.com/api/docs/pricing",
        as_of="2026-10-29",
    )
    exact = table.lookup("gpt-4o")
    assert exact == ModelPrice(
        input_per_million=Decimal("2.50"),
        output_per_million=Decimal("10"),
        cache_read_per_million=Decimal("1.25"),
        source="https://developers.openai.com/api/docs/pricing",
        as_of="2026-10-29",
    )
    assert table.lookup("not-a-model") is None


def test_file_and_mapping_overrides_replace_matching_models(tmp_path: Path) -> None:
    override = tmp_path / "prices.json"
    override.write_text(
        """
        {
          "version": "lab-1",
          "currency": "USD",
          "models": {"gpt-4o-mini": {"input": 0.01, "output": 0.02}}
        }
        """,
        encoding="utf-8",
    )
    table = PriceTable.bundled().merge(PriceTable.load(override))
    assert table.lookup("gpt-4o-mini") == ModelPrice(
        input_per_million=Decimal("0.01"), output_per_million=Decimal("0.02")
    )
    # Unmentioned models stay on the bundled snapshot, cache price included.
    assert table.lookup("gpt-4o") == ModelPrice(
        input_per_million=Decimal("2.50"),
        output_per_million=Decimal("10"),
        cache_read_per_million=Decimal("1.25"),
        source="https://developers.openai.com/api/docs/pricing",
        as_of="2026-10-29",
    )
    replaced = table.override({"gpt-4o": ModelPrice(Decimal("9"), Decimal("9"))})
    assert replaced.lookup("gpt-4o") == ModelPrice(Decimal("9"), Decimal("9"))
    assert "override" in replaced.version


def test_negative_price_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(
        '{"version":"x","currency":"USD","models":{"m":{"input":-1,"output":1}}}',
        encoding="utf-8",
    )
    with pytest.raises(PriceError):
        PriceTable.load(path)
