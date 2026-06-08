"""Curated provider and provider-catalog seed data for Phase 8."""

from __future__ import annotations

from typing import TypedDict

from macro_foundry.enums import ProviderType


class ProviderSeed(TypedDict, total=False):
    """Seed payload for providers."""

    name: str
    alt_name: list[str]
    type: ProviderType
    homepage_url: str
    doc_url: str
    base_url: str
    credentials_ref: str
    notes: str
    is_active: bool


class ProviderCatalogSeed(TypedDict, total=False):
    """Seed payload for provider catalogs."""

    provider_name: str
    name: str
    catalog_url: str
    doc_url: str
    notes: str
    is_placeholder: bool


PROVIDERS: list[ProviderSeed] = [
    {
        "name": "World Bank",
        "type": ProviderType.INTERNATIONAL_ORGANIZATION,
        "homepage_url": "https://data.worldbank.org/",
        "doc_url": "https://datahelpdesk.worldbank.org/knowledgebase/topics/125589-developer-information",
        "base_url": "https://api.worldbank.org/v2/",
        "notes": "Default Phase 8 seed for World Bank data surfaces.",
        "is_active": True,
    },
    {
        "name": "OECD",
        "alt_name": ["Organisation for Economic Co-operation and Development"],
        "type": ProviderType.INTERNATIONAL_ORGANIZATION,
        "homepage_url": "https://www.oecd.org/",
        "doc_url": "https://data-explorer.oecd.org/",
        "notes": "Default Phase 8 seed for OECD data surfaces.",
        "is_active": True,
    },
    {
        "name": "International Monetary Fund",
        "alt_name": ["IMF"],
        "type": ProviderType.INTERNATIONAL_ORGANIZATION,
        "homepage_url": "https://www.imf.org/en/Data",
        "doc_url": "https://data.imf.org/en/Resource-Pages/IMF-API",
        "notes": "Default Phase 8 seed for IMF data surfaces.",
        "is_active": True,
    },
    {
        "name": "Bank for International Settlements",
        "alt_name": ["BIS"],
        "type": ProviderType.INTERNATIONAL_ORGANIZATION,
        "homepage_url": "https://www.bis.org/",
        "doc_url": "https://data.bis.org/",
        "notes": "Default Phase 8 seed for BIS data surfaces.",
        "is_active": True,
    },
    {
        "name": "USA FRED",
        "alt_name": ["Federal Reserve Economic Data"],
        "type": ProviderType.OFFICIAL,
        "homepage_url": "https://fred.stlouisfed.org/",
        "doc_url": "https://fred.stlouisfed.org/docs/api/fred/",
        "base_url": "https://api.stlouisfed.org/",
        "notes": "Country-prefixed provider name per Phase 8 convention.",
        "is_active": True,
    },
    {
        "name": "USA Bureau of Economic Analysis",
        "alt_name": ["BEA", "U.S. Bureau of Economic Analysis"],
        "type": ProviderType.OFFICIAL,
        "homepage_url": "https://www.bea.gov/data",
        "doc_url": "https://apps.bea.gov/API/signup/",
        "base_url": "https://apps.bea.gov/api/data",
        "notes": "Country-prefixed provider name per Phase 8 convention.",
        "is_active": True,
    },
    {
        "name": "HKG Census and Statistics Department",
        "alt_name": ["C&SD", "Hong Kong Census and Statistics Department"],
        "type": ProviderType.OFFICIAL,
        "homepage_url": "https://www.censtatd.gov.hk/en/",
        "doc_url": "https://www.censtatd.gov.hk/en/Interactive_Statistics.html",
        "notes": "Country-prefixed provider name per Phase 8 convention.",
        "is_active": True,
    },
    {
        "name": "HKG data.gov.hk",
        "alt_name": ["DATA.GOV.HK"],
        "type": ProviderType.OFFICIAL,
        "homepage_url": "https://data.gov.hk/en/",
        "doc_url": "https://data.gov.hk/en/help/api-spec",
        "notes": "Country-prefixed provider name per Phase 8 convention.",
        "is_active": True,
    },
    {
        "name": "JPN e-Stat",
        "alt_name": ["Portal Site of Official Statistics of Japan", "e-Stat"],
        "type": ProviderType.OFFICIAL,
        "homepage_url": "https://www.e-stat.go.jp/en",
        "doc_url": "https://www.e-stat.go.jp/en/developer",
        "base_url": "https://api.e-stat.go.jp/rest/3.0/app/",
        "notes": "Country-prefixed provider name per Phase 8 convention.",
        "is_active": True,
    },
    {
        "name": "Alpha Vantage",
        "type": ProviderType.VENDOR,
        "homepage_url": "https://www.alphavantage.co/",
        "doc_url": "https://www.alphavantage.co/documentation/",
        "base_url": "https://www.alphavantage.co/query",
        "is_active": True,
    },
    {
        "name": "Databento",
        "type": ProviderType.VENDOR,
        "homepage_url": "https://databento.com/",
        "doc_url": "https://databento.com/docs",
        "notes": "Market-data vendor included in the default Phase 8 provider seed set.",
        "is_active": True,
    },
]

PROVIDER_CATALOGS: list[ProviderCatalogSeed] = [
    {
        "provider_name": "World Bank",
        "name": "World Development Indicators",
        "catalog_url": "https://databank.worldbank.org/source/world-development-indicators",
        "doc_url": "https://datahelpdesk.worldbank.org/knowledgebase/articles/889392-about-the-indicators-api-documentation",
        "is_placeholder": False,
    },
    {
        "provider_name": "World Bank",
        "name": "Global Economic Monitor",
        "catalog_url": "https://databank.worldbank.org/source/global-economic-monitor-%28gem%29",
        "is_placeholder": False,
    },
    {
        "provider_name": "World Bank",
        "name": "International Debt Statistics",
        "catalog_url": "https://databank.worldbank.org/source/international-debt-statistics",
        "is_placeholder": False,
    },
    {
        "provider_name": "OECD",
        "name": "OECD default catalog",
        "catalog_url": "https://data-explorer.oecd.org/",
        "notes": "Placeholder catalog until specific OECD data namespaces are curated.",
        "is_placeholder": True,
    },
    {
        "provider_name": "International Monetary Fund",
        "name": "IMF default catalog",
        "catalog_url": "https://www.imf.org/en/data",
        "doc_url": "https://data.imf.org/en/Resource-Pages/IMF-API",
        "notes": "Placeholder catalog until specific IMF datasets are curated.",
        "is_placeholder": True,
    },
    {
        "provider_name": "Bank for International Settlements",
        "name": "BIS Data Portal",
        "catalog_url": "https://data.bis.org/",
        "is_placeholder": False,
    },
    {
        "provider_name": "USA FRED",
        "name": "FRED default catalog",
        "catalog_url": "https://fred.stlouisfed.org/",
        "doc_url": "https://fred.stlouisfed.org/docs/api/fred/",
        "notes": "Placeholder catalog for the unified FRED series namespace.",
        "is_placeholder": True,
    },
    {
        "provider_name": "USA Bureau of Economic Analysis",
        "name": "BEA default catalog",
        "catalog_url": "https://www.bea.gov/data",
        "doc_url": "https://apps.bea.gov/API/signup/",
        "notes": "Placeholder catalog until BEA account families are curated.",
        "is_placeholder": True,
    },
    {
        "provider_name": "HKG Census and Statistics Department",
        "name": "Common Interactive Data Dissemination Service",
        "catalog_url": "https://www.censtatd.gov.hk/en/Interactive_Statistics.html",
        "notes": "Current named dissemination surface under the C&SD Interactive Statistics umbrella.",
        "is_placeholder": False,
    },
    {
        "provider_name": "HKG data.gov.hk",
        "name": "Open Data Portal",
        "catalog_url": "https://data.gov.hk/en-datasets",
        "doc_url": "https://data.gov.hk/en/help/api-spec",
        "is_placeholder": False,
    },
    {
        "provider_name": "JPN e-Stat",
        "name": "e-Stat default catalog",
        "catalog_url": "https://www.e-stat.go.jp/en/stat-search/database",
        "doc_url": "https://www.e-stat.go.jp/en/developer",
        "notes": "Placeholder catalog for the unified e-Stat portal/API surface.",
        "is_placeholder": True,
    },
    {
        "provider_name": "Alpha Vantage",
        "name": "Alpha Vantage default catalog",
        "catalog_url": "https://www.alphavantage.co/",
        "doc_url": "https://www.alphavantage.co/documentation/",
        "is_placeholder": True,
    },
    {
        "provider_name": "Databento",
        "name": "Databento default catalog",
        "catalog_url": "https://databento.com/docs",
        "doc_url": "https://databento.com/docs",
        "is_placeholder": True,
    },
]

__all__ = ["PROVIDER_CATALOGS", "PROVIDERS", "ProviderCatalogSeed", "ProviderSeed"]
