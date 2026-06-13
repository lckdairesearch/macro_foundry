"""Concrete SQLAdmin model views."""

from macro_foundry.backend.admin.views.concept import ConceptAdmin
from macro_foundry.backend.admin.views.derived import DerivationInputAdmin, DerivedSeriesAdmin
from macro_foundry.backend.admin.views.geography import GeographyAdmin, GeographyMembershipAdmin
from macro_foundry.backend.admin.views.governance import ChangeProposalAdmin, ChangeProposalItemAdmin
from macro_foundry.backend.admin.views.ingestion import IngestionFeedAdmin, IngestionFeedMemberAdmin
from macro_foundry.backend.admin.views.observation import ObservationAdmin
from macro_foundry.backend.admin.views.provider import ProviderAdmin, ProviderCatalogAdmin, SeriesSourceAdmin
from macro_foundry.backend.admin.views.run_log import (
    ComputationRunLogAdmin,
    IngestionRunLogAdmin,
    IngestionRunLogMemberAdmin,
)
from macro_foundry.backend.admin.views.series import (
    SeriesAdmin,
    IndicatorAdmin,
    IndicatorVariantAdmin,
    SeriesHierarchyEdgeAdmin,
)
from macro_foundry.backend.admin.views.tag import ConceptTagAdmin, TagAdmin

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
    IndicatorAdmin,
    IndicatorVariantAdmin,
    SeriesHierarchyEdgeAdmin,
    ConceptTagAdmin,
    DerivedSeriesAdmin,
    DerivationInputAdmin,
    ObservationAdmin,
    IngestionRunLogAdmin,
    IngestionRunLogMemberAdmin,
    ComputationRunLogAdmin,
    ChangeProposalAdmin,
    ChangeProposalItemAdmin,
)

__all__ = ["ADMIN_VIEWS"]
