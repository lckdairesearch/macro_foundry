"""Concrete SQLAdmin model views."""

from macro_foundry.backend.admin.views.concept import ConceptAdmin
from macro_foundry.backend.admin.views.derived import DerivationInputAdmin, DerivedSeriesAdmin
from macro_foundry.backend.admin.views.geography import GeographyAdmin, GeographyMembershipAdmin
from macro_foundry.backend.admin.views.governance import ChangeProposalAdmin, ChangeProposalItemAdmin
from macro_foundry.backend.admin.views.ingestion import IngestionFeedAdmin
from macro_foundry.backend.admin.views.observation import ObservationAdmin
from macro_foundry.backend.admin.views.provider import ProviderAdmin, ProviderCatalogAdmin, SeriesSourceAdmin
from macro_foundry.backend.admin.views.run_log import ComputationRunLogAdmin, IngestionRunLogAdmin
from macro_foundry.backend.admin.views.series import SeriesAdmin, SeriesFamilyAdmin, SeriesFamilyMemberAdmin
from macro_foundry.backend.admin.views.tag import SeriesTagAdmin, TagAdmin

ADMIN_VIEWS = (
    GeographyAdmin,
    GeographyMembershipAdmin,
    ConceptAdmin,
    TagAdmin,
    SeriesTagAdmin,
    ProviderAdmin,
    ProviderCatalogAdmin,
    SeriesAdmin,
    SeriesFamilyAdmin,
    SeriesFamilyMemberAdmin,
    SeriesSourceAdmin,
    ObservationAdmin,
    DerivedSeriesAdmin,
    DerivationInputAdmin,
    IngestionFeedAdmin,
    IngestionRunLogAdmin,
    ComputationRunLogAdmin,
    ChangeProposalAdmin,
    ChangeProposalItemAdmin,
)

__all__ = ["ADMIN_VIEWS"]
