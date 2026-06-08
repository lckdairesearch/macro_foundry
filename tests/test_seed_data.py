"""Focused Phase 8 seed data coverage."""

from __future__ import annotations

from datetime import date

from macro_foundry.seed.data.geographies import BLOCS, COUNTRIES, SUBNATIONALS, SUBNATIONAL_REGIONS, WORLD
from macro_foundry.seed.data.memberships import GEOGRAPHY_MEMBERSHIPS
from macro_foundry.seed.data.providers import PROVIDER_CATALOGS, PROVIDERS
from macro_foundry.seed.data.tags import TAGS
from macro_foundry.seed.run import SeedTarget, parse_seed_targets


def test_country_seed_uses_full_iso_3166_alpha_3_set() -> None:
    assert len(COUNTRIES) == 249
    countries = {row["code"]: row for row in COUNTRIES}

    assert {"USA", "JPN", "HKG", "GBR"}.issubset(countries)
    assert countries["USA"]["alt_name"] == ["United States of America"]
    assert countries["HKG"]["name"] == "Hong Kong"
    assert countries["HKG"]["alt_name"] == [
        "Hong Kong Special Administrative Region of China",
    ]
    assert countries["ALA"]["name"] == "Åland Islands"
    assert countries["CUW"]["name"] == "Curaçao"
    assert countries["CIV"]["name"] == "Côte d'Ivoire"
    assert countries["STP"]["name"] == "São Tomé and Príncipe"
    assert countries["TUR"]["name"] == "Türkiye"


def test_curated_subnational_scope_matches_phase_8_decisions() -> None:
    us_codes = {row["code"] for row in SUBNATIONALS if row["code"].startswith("US-")}
    jp_subnationals = {
        row["code"]: row for row in SUBNATIONALS if row["code"].startswith("JP-")
    }
    jp_codes = set(jp_subnationals)
    jp_regions = {row["code"]: row for row in SUBNATIONAL_REGIONS}

    assert len(us_codes) == 51
    assert "US-DC" in us_codes
    assert len(jp_codes) == 47
    assert {row["code"] for row in SUBNATIONAL_REGIONS} == {
        "JP-HOKKAIDO",
        "JP-TOHOKU",
        "JP-KANTO",
        "JP-CHUBU",
        "JP-KINKI",
        "JP-CHUGOKU",
        "JP-SHIKOKU",
        "JP-KYUSHU-OKINAWA",
    }
    assert jp_subnationals["JP-13"]["alt_name"] == ["東京都"]
    assert jp_regions["JP-KINKI"]["alt_name"] == ["Kansai", "近畿", "関西"]


def test_japan_chiho_memberships_cover_all_prefectures() -> None:
    chiho_members = [
        membership
        for membership in GEOGRAPHY_MEMBERSHIPS
        if membership["group_code"].startswith("JP-")
    ]

    assert len(chiho_members) == 47
    assert {
        membership["member_code"]
        for membership in chiho_members
        if membership["group_code"] == "JP-KYUSHU-OKINAWA"
    } == {"JP-40", "JP-41", "JP-42", "JP-43", "JP-44", "JP-45", "JP-46", "JP-47"}


def test_eu_membership_seed_tracks_requested_history_window() -> None:
    eu_memberships = {
        membership["member_code"]: membership
        for membership in GEOGRAPHY_MEMBERSHIPS
        if membership["group_code"] == "EU"
    }

    assert eu_memberships["BGR"]["start_date"] == date(2007, 1, 1)
    assert eu_memberships["ROU"]["start_date"] == date(2007, 1, 1)
    assert eu_memberships["HRV"]["start_date"] == date(2013, 7, 1)
    assert eu_memberships["GBR"]["end_date"] == date(2020, 1, 31)


def test_bloc_membership_seed_tracks_2026_emu_and_mercosur_status() -> None:
    emu_memberships = {
        membership["member_code"]: membership
        for membership in GEOGRAPHY_MEMBERSHIPS
        if membership["group_code"] == "EMU"
    }
    mercosur_memberships = {
        membership["member_code"]: membership
        for membership in GEOGRAPHY_MEMBERSHIPS
        if membership["group_code"] == "MERCOSUR"
    }

    assert emu_memberships["BGR"]["start_date"] == date(2026, 1, 1)
    assert mercosur_memberships["VEN"]["end_date"] == date(2017, 8, 5)


def test_tags_match_normalized_subject_taxonomy() -> None:
    assert TAGS == [
        "national_accounts",
        "production_business_activity",
        "prices",
        "labor_population",
        "money_banking_finance",
        "international",
        "housing",
    ]


def test_default_provider_seed_set_matches_phase_8_scope() -> None:
    provider_names = {provider["name"] for provider in PROVIDERS}
    assert provider_names == {
        "World Bank",
        "OECD",
        "International Monetary Fund",
        "Bank for International Settlements",
        "USA FRED",
        "USA Bureau of Economic Analysis",
        "HKG Census and Statistics Department",
        "HKG data.gov.hk",
        "JPN e-Stat",
        "Alpha Vantage",
        "Databento",
    }
    assert any(catalog["name"] == "World Development Indicators" for catalog in PROVIDER_CATALOGS)
    assert any(catalog["name"] == "e-Stat default catalog" and catalog["is_placeholder"] for catalog in PROVIDER_CATALOGS)


def test_bloc_seed_includes_world_and_requested_exception() -> None:
    assert WORLD["code"] == "WLD"
    assert {bloc["code"] for bloc in BLOCS} >= {"AU", "ASEAN", "BRICS", "EFTA", "EMU", "EU", "G7", "G20", "MERCOSUR", "OECD"}


def test_seed_target_parser_accepts_repeated_cli_targets() -> None:
    assert parse_seed_targets(["geographies", "providers"]) == {
        SeedTarget.GEOGRAPHIES,
        SeedTarget.PROVIDERS,
    }
