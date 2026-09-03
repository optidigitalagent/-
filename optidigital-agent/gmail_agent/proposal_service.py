"""Single fail-closed contract for newly generated proposal text."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Awaitable, Callable

from .email_analyzer import JobAnalysis
from .quality_gate import (
    QualityStatus,
    QualityValidation,
    apply_validation,
    is_proposal_ready,
    validate_analysis,
)


class ProposalGenerationStatus(StrEnum):
    VALIDATED_PROPOSAL = "VALIDATED_PROPOSAL"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    NON_EXECUTABLE = "NON_EXECUTABLE"
    PROVIDER_RETRYABLE = "PROVIDER_RETRYABLE"
    LIVE_STATUS_BLOCKED = "LIVE_STATUS_BLOCKED"


@dataclass(frozen=True, slots=True)
class ProposalGenerationResult:
    status: str
    analysis: JobAnalysis
    validation_errors: tuple[str, ...] = ()
    repair_count: int = 0


LiveRefresh = Callable[[JobAnalysis], Awaitable[JobAnalysis | None]]
CandidateGenerator = Callable[
    [JobAnalysis, tuple[str, ...], str], Awaitable[str]
]
PersistProposal = Callable[[JobAnalysis, str], Awaitable[None]]


def _provider_failure(analysis: JobAnalysis) -> QualityValidation:
    from datetime import datetime, timezone

    return QualityValidation(
        status=QualityStatus.FAILED.value,
        errors=("proposal_provider_failed",),
        checked_at=datetime.now(timezone.utc),
        proposal_quality_score=0.0,
    )


async def generate_validate_and_persist_proposal(
    source: JobAnalysis,
    *,
    refresh_live_status: LiveRefresh,
    generate_candidate: CandidateGenerator,
    persist: PersistProposal,
) -> ProposalGenerationResult:
    """Generate, validate, repair at most once, version, and persist one draft."""

    refreshed = await refresh_live_status(replace(source))
    if refreshed is None:
        return ProposalGenerationResult(
            ProposalGenerationStatus.LIVE_STATUS_BLOCKED.value,
            source,
        )

    original_snapshot = refreshed.original_analysis_snapshot
    if not original_snapshot:
        from dataclasses import asdict

        original_snapshot = json.dumps(
            asdict(refreshed), ensure_ascii=False, default=str, sort_keys=True
        )

    candidate = (await generate_candidate(refreshed, (), "")).strip()
    if not candidate:
        failed = replace(refreshed, analysis_succeeded=False, proposal_draft="")
        failed.original_analysis_snapshot = original_snapshot
        validation = _provider_failure(failed)
        apply_validation(failed, validation)
        await persist(failed, "quality_retryable")
        return ProposalGenerationResult(
            ProposalGenerationStatus.PROVIDER_RETRYABLE.value,
            failed,
            validation.errors,
        )

    first = replace(
        refreshed,
        proposal_draft=candidate,
        proposal_version="",
        analysis_quality_status="",
        quality_errors="[]",
        quality_repair_count=0,
        original_analysis_snapshot=original_snapshot,
    )
    initial = validate_analysis(first)
    if initial.proposal_ready:
        apply_validation(first, initial)
        if not is_proposal_ready(first):
            await persist(first, "quality_manual_review")
            return ProposalGenerationResult(
                ProposalGenerationStatus.MANUAL_REVIEW.value,
                first,
                tuple(json.loads(first.quality_errors or "[]")),
            )
        first.qualified = True
        await persist(first, "queued")
        return ProposalGenerationResult(
            ProposalGenerationStatus.VALIDATED_PROPOSAL.value,
            first,
        )

    if initial.status == QualityStatus.NON_EXECUTABLE.value:
        apply_validation(first, initial)
        await persist(first, "quality_non_executable")
        return ProposalGenerationResult(
            ProposalGenerationStatus.NON_EXECUTABLE.value,
            first,
            initial.errors,
        )

    repaired_candidate = (
        await generate_candidate(first, initial.errors, candidate)
    ).strip()
    if not repaired_candidate:
        failed = replace(first, analysis_succeeded=False, proposal_draft="")
        validation = _provider_failure(failed)
        apply_validation(failed, validation, repair_count=1)
        await persist(failed, "quality_retryable")
        return ProposalGenerationResult(
            ProposalGenerationStatus.PROVIDER_RETRYABLE.value,
            failed,
            validation.errors,
            1,
        )

    repaired = replace(
        first,
        analysis_succeeded=True,
        proposal_draft=repaired_candidate,
        proposal_version="",
        analysis_quality_status="",
        quality_errors="[]",
    )
    second = validate_analysis(repaired, repaired=True)
    apply_validation(repaired, second, repair_count=1)
    if second.proposal_ready and is_proposal_ready(repaired):
        repaired.qualified = True
        await persist(repaired, "queued")
        return ProposalGenerationResult(
            ProposalGenerationStatus.VALIDATED_PROPOSAL.value,
            repaired,
            (),
            1,
        )

    status = (
        "quality_non_executable"
        if second.status == QualityStatus.NON_EXECUTABLE.value
        else "quality_manual_review"
    )
    await persist(repaired, status)
    return ProposalGenerationResult(
        ProposalGenerationStatus.MANUAL_REVIEW.value,
        repaired,
        second.errors,
        1,
    )
