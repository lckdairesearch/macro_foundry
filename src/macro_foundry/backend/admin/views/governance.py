"""SQLAdmin views for governance models."""

from macro_foundry.backend.admin._base import BaseModelView, datetime_widget_args, json_widget_args, relation_formatter
from macro_foundry.models import ChangeProposal, ChangeProposalItem


class ChangeProposalAdmin(BaseModelView, model=ChangeProposal):
    name = "Change proposal"
    name_plural = "Change proposals"
    category = "Governance"
    category_icon = "ti ti-shield-check"
    column_list = [
        ChangeProposal.title,
        ChangeProposal.proposal_type,
        ChangeProposal.status,
        ChangeProposal.requested_by,
        ChangeProposal.risk_level,
        ChangeProposal.superseded_by_proposal,
        ChangeProposal.updated_at,
    ]
    column_searchable_list = [ChangeProposal.title, ChangeProposal.created_by_agent, ChangeProposal.user_prompt]
    column_filters = [
        ChangeProposal.proposal_type,
        ChangeProposal.status,
        ChangeProposal.requested_by,
        ChangeProposal.risk_level,
    ]
    column_sortable_list = [ChangeProposal.title, ChangeProposal.updated_at]
    column_default_sort = [(ChangeProposal.updated_at, True)]
    column_formatters = {
        ChangeProposal.superseded_by_proposal: relation_formatter("superseded_by_proposal"),
    }
    form_columns = [
        ChangeProposal.title,
        ChangeProposal.proposal_type,
        ChangeProposal.status,
        ChangeProposal.requested_by,
        ChangeProposal.created_by_agent,
        ChangeProposal.user_prompt,
        ChangeProposal.rationale,
        ChangeProposal.risk_level,
        ChangeProposal.review_notes,
        ChangeProposal.approved_by,
        ChangeProposal.approved_at,
        ChangeProposal.applied_at,
        ChangeProposal.superseded_by_proposal,
    ]
    form_widget_args = datetime_widget_args("approved_at", "applied_at")


class ChangeProposalItemAdmin(BaseModelView, model=ChangeProposalItem):
    name = "Change proposal item"
    name_plural = "Change proposal items"
    category = "Governance"
    category_icon = "ti ti-shield-check"
    column_list = [
        ChangeProposalItem.proposal,
        ChangeProposalItem.item_type,
        ChangeProposalItem.target_type,
        ChangeProposalItem.action,
        ChangeProposalItem.validation_status,
        ChangeProposalItem.updated_at,
    ]
    column_searchable_list = [ChangeProposalItem.target_ref, ChangeProposalItem.diff_summary, "proposal.title"]
    column_filters = [
        ChangeProposalItem.item_type,
        ChangeProposalItem.target_type,
        ChangeProposalItem.action,
        ChangeProposalItem.validation_status,
    ]
    column_sortable_list = [ChangeProposalItem.updated_at]
    column_default_sort = [(ChangeProposalItem.updated_at, True)]
    column_formatters = {ChangeProposalItem.proposal: relation_formatter("proposal")}
    form_columns = [
        ChangeProposalItem.proposal,
        ChangeProposalItem.item_type,
        ChangeProposalItem.target_type,
        ChangeProposalItem.action,
        ChangeProposalItem.target_id,
        ChangeProposalItem.target_ref,
        ChangeProposalItem.proposed_data,
        ChangeProposalItem.diff_summary,
        ChangeProposalItem.validation_status,
        ChangeProposalItem.validation_notes,
    ]
    form_widget_args = json_widget_args("proposed_data")


__all__ = ["ChangeProposalAdmin", "ChangeProposalItemAdmin"]
