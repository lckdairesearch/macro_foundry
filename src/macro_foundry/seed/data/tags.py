"""Curated tag seed data: the topical taxonomy (ADR 0022 §3)."""

from __future__ import annotations

# (code, name) — `code` is the UPPERCASE canonical key, `name` is display text.
TAGS: list[tuple[str, str]] = [
    ("PRICES", "Prices"),
    ("MONETARY_BANKING", "Monetary and Banking Variables"),
    ("POPULATION_LABOR", "Population and Labor Market"),
    ("PRODUCTION_BUSINESS_ACTIVITY", "Production and Business Activity"),
    ("RETAIL_CONSUMPTION", "Retail and Consumption"),
    ("NATIONAL_ACCOUNTS", "National Accounts"),
    ("GOVERNMENT_FISCAL", "Government and Fiscal"),
    ("INTERNATIONAL", "International"),
    ("FINANCIAL_INDICATORS", "Financial Indicators"),
    ("OTHER", "Others"),
]

__all__ = ["TAGS"]
