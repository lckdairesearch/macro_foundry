"""Concrete SQLAdmin model views."""

from macro_foundry.backend.admin.views.concept import ConceptAdmin
from macro_foundry.backend.admin.views.derived import DerivationInputAdmin, DerivedSeriesAdmin
from macro_foundry.backend.admin.views.geography import GeographyAdmin, GeographyMembershipAdmin
from macro_foundry.backend.admin.views.governance import ChangeProposalAdmin, ChangeProposalItemAdmin
from macro_foundry.backend.admin.views.ingestion import IngestionFeedAdmin, IngestionFeedMemberAdmin
from macro_foundry.backend.admin.views.observation import ObservationAdmin
from macro_foundry.backend.admin.views.provider import ProviderAdmin, ProviderCatalogAdmin, SeriesSourceAdmin
from macro_foundry.backend.admin.views.run_log import ComputationRunLogAdmin, IngestionRunLogAdmin
from macro_foundry.backend.admin.views.series import (
    SeriesAdmin,
    SeriesFamilyAdmin,
    SeriesFamilyMemberAdmin,
    SeriesHierarchyEdgeAdmin,
)
from macro_foundry.backend.admin.views.tag import SeriesTagAdmin, TagAdmin

ADMIN_VIEWS = (
    GeographyAdmin,
    GeographyMembershipAdmin,
    ConceptAdmin,
    TagAdmin,
    ProviderAdmin,
    ProviderCatalogAdmin,
    SeriesSourceAdmin,
    IngestionFeedAdmin,
    IngestionFeedMemberAdmin,
    SeriesAdmin,
    SeriesFamilyAdmin,
    SeriesFamilyMemberAdmin,
    SeriesHierarchyEdgeAdmin,
    SeriesTagAdmin,
    DerivedSeriesAdmin,
    DerivationInputAdmin,
    ObservationAdmin,
    IngestionRunLogAdmin,
    ComputationRunLogAdmin,
    ChangeProposalAdmin,
    ChangeProposalItemAdmin,
)

__all__ = ["ADMIN_VIEWS"]
