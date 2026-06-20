"""Concrete SQLAdmin model views."""

from macro_foundry.backend.admin.views.category import CategoryAdmin, CategoryEdgeAdmin
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
    SeriesHierarchyEdgeAdmin,
)
from macro_foundry.backend.admin.views.source_group import SourceGroupAdmin, SourceGroupMemberAdmin

ADMIN_VIEWS = (
    CategoryAdmin,
    CategoryEdgeAdmin,
    GeographyAdmin,
    GeographyMembershipAdmin,
    ProviderAdmin,
    ProviderCatalogAdmin,
    SeriesSourceAdmin,
    SourceGroupAdmin,
    SourceGroupMemberAdmin,
    IngestionFeedAdmin,
    IngestionFeedMemberAdmin,
    SeriesAdmin,
    SeriesHierarchyEdgeAdmin,
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
