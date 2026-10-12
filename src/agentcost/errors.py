"""Errors raised by parsers, pricing, and comparison."""

from __future__ import annotations


class AgentCostError(Exception):
    """Base error for expected agentcost failures."""


class ParseError(AgentCostError):
    """A trace file is missing fields or is not valid JSON."""


class PriceError(AgentCostError):
    """A price table is invalid or a model cannot be priced."""


class CompareError(AgentCostError):
    """The requested A/B comparison cannot be computed."""
