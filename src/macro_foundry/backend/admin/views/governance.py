"""SQLAdmin views for governance models."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqladmin import action
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from macro_foundry.backend.admin._base import BaseModelView, datetime_widget_args, json_widget_args, relation_formatter
from macro_foundry.enums import ValidationStatus
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

    @action(
        "mark-applied",
        label="Mark applied",
        confirmation_message="Mark selected items as applied_by_operator?",
        add_in_list=True,
        add_in_detail=False,
    )
    async def mark_applied(self, request: Request) -> Response:
        pks_raw = request.query_params.get("pks", "")
        pk_list = [pk.strip() for pk in pks_raw.split(",") if pk.strip()]

        async with self.session_maker() as session:
            now = datetime.now(timezone.utc)
            for pk in pk_list:
                result = await session.execute(
                    select(ChangeProposalItem).where(ChangeProposalItem.id == pk)
                )
                item = result.scalar_one_or_none()
                if item is None or item.validation_status != ValidationStatus.PENDING_HUMAN_APPLY:
                    continue
                item.validation_status = ValidationStatus.APPLIED_BY_OPERATOR
                result_proposal = await session.execute(
                    select(ChangeProposal).where(ChangeProposal.id == item.proposal_id)
                )
                proposal = result_proposal.scalar_one_or_none()
                if proposal is not None:
                    proposal.applied_at = now
            await session.commit()

        return RedirectResponse(
            url=f"/admin/{self.identity}/list",
            status_code=303,
        )


__all__ = ["ChangeProposalAdmin", "ChangeProposalItemAdmin"]
