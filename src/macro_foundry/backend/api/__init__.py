"""Registered API routers for the backend."""

from macro_foundry.backend.api.change_proposal_items import router as change_proposal_items_router
from macro_foundry.backend.api.change_proposals import router as change_proposals_router
from macro_foundry.backend.api.computation_run_logs import router as computation_run_logs_router
from macro_foundry.backend.api.concepts import router as concepts_router
from macro_foundry.backend.api.derivation_inputs import router as derivation_inputs_router
from macro_foundry.backend.api.derived_series import router as derived_series_router
from macro_foundry.backend.api.geographies import router as geographies_router
from macro_foundry.backend.api.geography_memberships import router as geography_memberships_router
from macro_foundry.backend.api.ingestion_feed_members import router as ingestion_feed_members_router
from macro_foundry.backend.api.ingestion_feeds import router as ingestion_feeds_router
from macro_foundry.backend.api.ingestion_run_logs import router as ingestion_run_logs_router
from macro_foundry.backend.api.observations import router as observations_router
from macro_foundry.backend.api.provider_catalogs import router as provider_catalogs_router
from macro_foundry.backend.api.providers import router as providers_router
from macro_foundry.backend.api.series import router as series_router
from macro_foundry.backend.api.series_families import router as series_families_router
from macro_foundry.backend.api.series_family_members import router as series_family_members_router
from macro_foundry.backend.api.series_hierarchy_edges import router as series_hierarchy_edges_router
from macro_foundry.backend.api.series_sources import router as series_sources_router
from macro_foundry.backend.api.series_tags import router as series_tags_router
from macro_foundry.backend.api.tags import router as tags_router

API_ROUTERS = (
    change_proposal_items_router,
    change_proposals_router,
    computation_run_logs_router,
    concepts_router,
    derivation_inputs_router,
    derived_series_router,
    geographies_router,
    geography_memberships_router,
    ingestion_feed_members_router,
    ingestion_feeds_router,
    ingestion_run_logs_router,
    observations_router,
    provider_catalogs_router,
    providers_router,
    series_router,
    series_families_router,
    series_family_members_router,
    series_hierarchy_edges_router,
    series_sources_router,
    series_tags_router,
    tags_router,
)

__all__ = ["API_ROUTERS"]
