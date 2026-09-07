"""Opt-in real analyzer diagnostic on historical source; never a bid-ready E2E.

Model modes do not fetch sources or run database, Telegram or sales opportunities.
Explicit source-check uses existing bounded RSS/public enrichment; package is local.
Uses the existing analyzer, quality functions and persistent budget adapter.
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import hmac
import json
import logging
from dataclasses import asdict
from datetime import datetime
from dotenv import dotenv_values

from ops import issue20_live_e2e as live
from gmail_agent.digest_parser import DigestJobCandidate, enrich_candidate_scope
from gmail_agent.email_analyzer import analyze_candidate, repair_analysis, JobAnalysis
from gmail_agent.email_analyzer import MAX_MODEL_OUTPUT_TOKENS, OpportunityWireOutput
from gmail_agent.project_identity import freelancehunt_project_stable_key
from gmail_agent.quality_gate import (
    apply_validation, approved_evidence_text, compose_application_owned_proposal,
    final_composed_proposal_errors, is_proposal_ready, validate_analysis,
    contains_unsupported_case_or_capability_claim, _language_matches,
)

SOURCE_PATH = live.ARTIFACT_DIR / "next_live_candidate_scope.json"
COPY_PATH = live.ARTIFACT_DIR / "contract_historical_real_snapshot.json"
REPORT_PATH = live.ARTIFACT_DIR / "contract_snapshot_model_report.json"
EXPECTED_URL = "https://freelancehunt.com/project/stvorennya-korotkih-reels-dlya-tovaru/1651774.html"
FRESHNESS_ERRORS = {"live_status_not_active_biddable", "live_status_not_fresh"}
# Repair can fix formatting/grounding of existing data, never missing source facts.
REPAIRABLE = {
    "ask_source_perspective_mismatch",
    "analysis_evidence_not_source_grounded", "invalid_evidence_case_id",
    "recommended_price_missing_amount_or_currency", "recommended_price_not_full_string_canonical",
    "realistic_timeline_missing_or_unparseable", "realistic_timeline_not_full_string_canonical",
    "proposal_language_mismatch", "proposal_not_project_specific", "proposal_not_concise",
    "next_action_must_be_exactly_one", "more_than_one_clarification_question",
    "ask_has_price", "ask_has_timeline", "ask_has_proposal",
    "clarification_language_mismatch", "proposal_contains_unapproved_capability_claim",
    "structured_field_contains_unapproved_capability_claim",
    "missing_delivery_risk", "missing_client_payment_risk", "missing_estimated_effort",
}


def save(path, value):
    live._write_json(path, json.loads(json.dumps(value, ensure_ascii=False, default=str)))


def load_source():
    if not SOURCE_PATH.is_file() or SOURCE_PATH.is_symlink():
        raise RuntimeError("historical source file missing or linked")
    source = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    if source["project_id"] != "1651774" or any(
        source[k] != EXPECTED_URL for k in ("url", "full_text_source_url")
    ):
        raise RuntimeError("historical source identity mismatch")
    description = " ".join(source["full_description"].split())
    if not description or len(description) > 16000:
        raise RuntimeError("historical full description is absent or exceeds bound")
    if not hmac.compare_digest(hashlib.sha256(description.encode()).hexdigest(), source["full_text_sha256"]):
        raise RuntimeError("historical full-text integrity mismatch")
    for field in ("full_text_fetched_at", "verified_at", "rss_fetched_at", "rss_feed_timestamp"):
        live._scope_timestamp(source[field], field)
    if source["description_completeness"] != "FULL" or source["source_kind"] != "PUBLIC_PAGE_VERIFIED":
        raise RuntimeError("saved source is not documented full public text")
    if source["manual_scope_assessment"] is not True or not source["manual_scope_assessment_basis"]:
        raise RuntimeError("historical manual scope provenance is absent")
    if source["source_budget_status"] != "NOT_SPECIFIED" or source["source_budget"] or source["source_budget_currency"]:
        raise RuntimeError("unexpected historical source budget")
    diagnostic = {
        "SOURCE_MODE": "HISTORICAL_REAL_SNAPSHOT",
        "CURRENT_SOURCE_FRESHNESS": "NOT_VERIFIED",
        "CURRENT_ACTIONABILITY": "BLOCKED",
        "original_snapshot": source,
        "hash_verifies": "integrity only; completeness and sufficiency retain historical manual provenance",
        "candidate_title_source": "verbatim first sentence of full_description; original RSS title not retained in this snapshot",
    }
    candidate = DigestJobCandidate(
        source_email_id="rss:1651774", platform="Freelancehunt",
        title=description.split(". ", 1)[0] + ".", description=description,
        budget="", budget_currency="", url=EXPECTED_URL, category="",
        received_at=live._scope_timestamp(source["rss_fetched_at"], "rss_fetched_at"),
        stable_key=freelancehunt_project_stable_key(EXPECTED_URL), project_id="1651774",
        discovery_source="rss", event_type="PROJECT_FEED",
        feed_fetched_at=live._scope_timestamp(source["rss_fetched_at"], "rss_fetched_at"),
        source_feed_timestamp=live._scope_timestamp(source["rss_feed_timestamp"], "rss_feed_timestamp"),
    )
    candidate = enrich_candidate_scope(
        candidate, description=description, source_kind=source["source_kind"],
        main_text_completeness=source["description_completeness"],
        materials_status=source["materials_status"], scope_sufficiency=source["scope_sufficiency"],
    )
    return diagnostic, candidate


def supplemental_content_errors(analysis):
    errors = []
    if analysis.commercial_decision == "ASK" and not _language_matches(analysis.language, analysis.clarification_question):
        errors.append("clarification_language_mismatch")
    if analysis.proposal_draft and contains_unsupported_case_or_capability_claim(analysis.proposal_draft):
        errors.append("proposal_contains_unapproved_capability_claim")
    return errors


def inspect_analysis(analysis, *, repair_count=0):
    validation = validate_analysis(analysis)
    composed = compose_application_owned_proposal(analysis) if analysis.proposal_draft else ""
    final_errors = list(final_composed_proposal_errors(analysis, composed)) if composed else []
    # Preserve the complete gate unchanged; the diagnostic grouping cannot authorize action.
    content_errors = [e for e in validation.errors if e not in FRESHNESS_ERRORS]
    supplemental = supplemental_content_errors(analysis)
    content_errors = list(dict.fromkeys(content_errors + supplemental))
    guarded = apply_validation(copy.deepcopy(analysis), validation, repair_count=repair_count)
    schema_errors = []
    if analysis.analysis_succeeded:
        replay = json.loads(live.COMPLETION_REPLAY_PATH.read_text(encoding="utf-8"))
        try:
            raw = json.loads(replay["content"])
            if not isinstance(raw, dict) or set(raw) != {"analysis"}:
                schema_errors.append("strict_schema_field_set_mismatch")
            OpportunityWireOutput.model_validate(raw)
        except (ValueError, TypeError):
            schema_errors.append("raw_response_schema_validation_failed")
    else:
        schema_errors.append("provider_or_parser_failed")
    return {
        "analysis_before_gate": asdict(analysis),
        "schema_errors": schema_errors,
        "numeric_metadata": {k: getattr(analysis, k) for k in (
            "score", "fit_score", "score_valid", "fit_score_valid", "score_state", "fit_score_state", "score_raw", "fit_score_raw")},
        "approved_evidence_clause": approved_evidence_text(analysis.evidence_case_id, analysis.language),
        "historical_diagnostic_composed_draft": composed,
        "final_composition_errors": final_errors,
        "content_validation_errors": content_errors,
        "supplemental_content_errors": supplemental,
        "full_readiness_validation": asdict(validation),
        "analysis_after_gate": asdict(guarded),
        "application_proposal_ready": is_proposal_ready(guarded),
    }


async def run(mode):
    diagnostic, candidate = load_source()
    ledger = live._load_ledger()
    expected_count = live.STEP_BASELINE_CALLS + int(mode == "repair")
    if len(ledger["calls"]) != expected_count:
        raise RuntimeError("persistent ledger differs from authorized diagnostic baseline; no request made")
    reserves = sum(c["upper_bound_usd"] for c in ledger["calls"])
    if reserves > live.MAX_USD or live.STEP_CALL_CEILING != 8:
        raise RuntimeError("budget contract mismatch")
    key = live._load_private_key()
    sdk = live._make_live_client(key, capture_requests=mode != "preflight")
    try:
        if not hmac.compare_digest(sdk.api_key, str(dotenv_values(live.ENV_PATH).get("OPENAI_API_KEY") or "").strip()):
            raise RuntimeError("SDK key mismatch")
        if sdk.max_retries != 0:
            raise RuntimeError("SDK retries must be zero")
        print(json.dumps({"key_matches_env_file": True, "source_text_hash": diagnostic["original_snapshot"]["full_text_sha256"],
            "source_fetched_at": diagnostic["original_snapshot"]["full_text_fetched_at"],
            "source_mode": diagnostic["SOURCE_MODE"], "calls_before": len(ledger["calls"]),
            "reserved_usd": reserves, "output_token_cap": MAX_MODEL_OUTPUT_TOKENS,
            "two_call_max_with_history_usd": round(reserves + 2 * 0.01992, 8)}), flush=True)
        if mode == "preflight":
            return
        save(COPY_PATH, diagnostic)
        # Only diagnostic artifact destinations change; budget, prompts and guards do not.
        live.REPORT_PATH = live.ARTIFACT_DIR / "contract_snapshot_provider_failure.json"
        live.COMPLETION_REPLAY_PATH = live.ARTIFACT_DIR / "contract_snapshot_completion.json"
        live._SOURCE_REVISION_FILES = (*live._SOURCE_REVISION_FILES, "optidigital-agent/ops/issue20_snapshot_diagnostic.py")
        client = live.BudgetedOpenAIClient(sdk)
        attempts = []
        if mode == "repair":
            previous = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
            save(live.ARTIFACT_DIR / "contract_snapshot_initial_report.json", previous)
            attempts = previous["attempts"]
            if ledger["calls"][-1].get("status") != "COMPLETED":
                raise RuntimeError("repair forbidden after provider failure")
            original = JobAnalysis(**attempts[-1]["analysis_before_gate"])
            supplemental = supplemental_content_errors(original)
            errors = list(dict.fromkeys(attempts[-1]["content_validation_errors"] + supplemental))
            if not errors or not set(errors).issubset(REPAIRABLE):
                raise RuntimeError("errors require factual/manual review rather than an authorized model repair")
            manual_path = live.ARTIFACT_DIR / "contract_manual_repair_review.json"
            manual_review = None
            if manual_path.is_file():
                manual_review = json.loads(manual_path.read_text(encoding="utf-8"))
                if (manual_review["ledger_sequence"] != ledger["calls"][-1]["sequence"]
                    or manual_review["project_id"] != diagnostic["original_snapshot"]["project_id"]
                    or manual_review["source_text_sha256"] != diagnostic["original_snapshot"]["full_text_sha256"]):
                    raise RuntimeError("manual content review is not bound to this source/completion")
                errors.extend(manual_review["repair_errors"])
            data = attempts[-1]["analysis_before_gate"]
            for name in ("received_at", "source_publication_at", "source_feed_timestamp", "feed_fetched_at", "first_seen_at", "live_status_checked_at", "quality_checked_at"):
                if data.get(name):
                    data[name] = datetime.fromisoformat(data[name])
            save(live.ARTIFACT_DIR / "contract_snapshot_repair_plan.json", {
                "initial_gate_unchanged": attempts[-1]["full_readiness_validation"],
                "manual_content_review": manual_review,
                "supplemental_review_errors": supplemental, "targeted_errors": errors,
                "not_repair_targets": sorted(FRESHNESS_ERRORS),
                "basis": "Correct only identified response-content defects using the real source and registry. Missing facts and current live status remain unknown. No predetermined decision, score, price or timeline.",
            })
            analysis = await repair_analysis(JobAnalysis(**data), errors, client=client, model=live.MODEL)
        else:
            analysis = await analyze_candidate(candidate, client=client, model=live.MODEL)
        # Defaults remain UNKNOWN / false / no current check. No fabricated active proof.
        inspected = inspect_analysis(analysis, repair_count=int(mode == "repair"))
        attempts.append(inspected)
        ledger_after = live._load_ledger()
        calls = ledger_after["calls"][live.STEP_BASELINE_CALLS:]
        failed = next((c for c in calls if c["status"] == "FAILED"), None)
        checks_ok = (analysis.analysis_succeeded and not inspected["schema_errors"]
                     and not inspected["content_validation_errors"] and not inspected["final_composition_errors"])
        report = {
            "MODEL_ON_REAL_SNAPSHOT": "PASS" if checks_ok else "FAIL",
            "LIVE_MODEL_E2E": "NOT_RUN", "CURRENT_BID_READY": "NO",
            "issue_status": "IMPLEMENTED_WITH_VALIDATION_BLOCKERS",
            "ACCOUNT_IDENTITY": "NOT_VERIFIED", "BILLING": "NOT_VERIFIED", "KEY_USE_AUTHORIZATION": "EXPLICIT",
            "source": diagnostic, "source_revision": live._source_revision(),
            "attempts": attempts, "model_calls": calls,
            "repair_calls": max(0, len(calls)-1),
            "ledger_calls": len(ledger_after["calls"]),
            "ledger_reserved_total_usd": round(sum(c["upper_bound_usd"] for c in ledger_after["calls"]), 8),
            "component_known_estimated_cost_usd": round(sum(c.get("actual_estimated_usd") or 0 for c in calls if c.get("api_usage") == "RETURNED"), 8) if all(c.get("api_usage") == "RETURNED" for c in calls) else "UNKNOWN",
            "api_failure": live._failure_report(failed, ledger_after) if failed else None,
            "excluded_stages": ["discovery refresh", "live status refresh", "PostgreSQL", "Telegram renderer", "5A opportunity", "external delivery"],
        }
        save(REPORT_PATH, report)
        print(json.dumps({k:report[k] for k in ("MODEL_ON_REAL_SNAPSHOT", "LIVE_MODEL_E2E", "CURRENT_BID_READY", "ledger_calls", "repair_calls", "ledger_reserved_total_usd")}), flush=True)
    finally:
        await sdk.close()


async def refresh_source_availability():
    """One public-source check; do not relabel or overwrite historical data."""
    from dataclasses import replace
    from gmail_agent.freelancehunt_discovery import FreelancehuntFeedClient, FreelancehuntPublicScopeClient
    from gmail_agent.live_status import FreelancehuntLiveStatusChecker
    _, historical = load_source()
    candidate = replace(historical, description="", description_completeness="PARTIAL",
        scope_enrichment_source="", scope_enrichment_sha256="", materials_status="UNKNOWN",
        scope_sufficiency="UNKNOWN")
    result = {"project_id": "1651774", "model_calls": 0, "historical_source_unchanged": True}
    try:
        batch = await FreelancehuntFeedClient(max_items=10).fetch()
        result["rss_checked_at"] = batch.fetched_at
        result["rss_sample_count"] = len(batch.candidates)
        match = next((c for c in batch.candidates if c.project_id == "1651774"), None)
        result["in_current_ten_item_sample"] = match is not None
        if match:
            candidate = match
    except Exception as exc:
        result["rss_error_type"] = type(exc).__name__
    async with FreelancehuntLiveStatusChecker() as checker:
        async def fetch(url):
            page = await checker.fetch_public_page(url)
            result["public_http_status"] = page.status_code
            return page
        candidate = await FreelancehuntPublicScopeClient(page_fetcher=fetch).enrich(candidate)
        result["current_description_completeness"] = candidate.description_completeness
        if candidate.description_completeness == "FULL":
            result["current_candidate"] = asdict(candidate)
            result["live_status"] = asdict(await checker.check(candidate.url))
    result["checked_at"] = live._utc_iso()
    result["selected_path"] = "A_REVIEW_CURRENT_SCOPE" if candidate.description_completeness == "FULL" else "B_HISTORICAL_REAL_SNAPSHOT"
    save(live.ARTIFACT_DIR / "contract_source_availability.json", result)
    print(json.dumps(result, default=str), flush=True)


def package_review():
    """Explicit allowlist only: no env, OAuth, pgdata, logs or network."""
    import difflib
    import subprocess
    import zipfile
    root = live.REPO_ROOT
    target = live.ARTIFACT_DIR / "review_package_20260907_ask_contract"
    if target.exists():
        raise RuntimeError("review package exists; refuse blind overwrite")
    secret = live._load_private_key()
    source_paths = [
        "gmail_agent/email_analyzer.py", "gmail_agent/quality_gate.py", "gmail_agent/processor.py",
        "ops/issue20_live_e2e.py", "ops/issue20_snapshot_diagnostic.py",
        "gmail_agent/tests/test_issue20_decision_first.py", "gmail_agent/tests/test_issue20_live_runner.py",
        "gmail_agent/tests/test_issue20_ask_contract.py",
        "gmail_agent/tests/fixtures/issue20_real_ask/completion_3.json",
        "gmail_agent/tests/fixtures/issue20_real_ask/completion_4.json",
    ]
    report_names = [
        "ASK_CONTRACT_IMPLEMENTATION_REPORT.md", "contract_pre_live_review.md",
        "contract_source_availability.json", "contract_historical_real_snapshot.json",
        "contract_manual_repair_review.json", "contract_snapshot_repair_plan.json",
        "contract_snapshot_initial_report.json", "contract_snapshot_model_report.json",
        "contract_request_5.json", "contract_request_6.json",
        "live_completion_replay_5.json", "live_completion_replay_6.json",
    ]
    files = {"source/" + p: (live.AGENT_ROOT / p).read_bytes() for p in source_paths}
    files.update({"evidence/" + p: (live.ARTIFACT_DIR / p).read_bytes() for p in report_names})
    incremental = []
    for p in source_paths[:5]:
        before = live.ARTIFACT_DIR / "ask_fix_before" / p.rsplit("/", 1)[-1]
        incremental.extend(difflib.unified_diff(before.read_text(encoding="utf-8").splitlines(True),
            (live.AGENT_ROOT / p).read_text(encoding="utf-8").splitlines(True),
            fromfile="before/" + p, tofile="after/" + p))
    files["incremental_contract.diff"] = "".join(incremental).encode("utf-8")
    files["issue20_tracked_context.diff"] = subprocess.run(
        ["git", "diff", "--no-ext-diff", "HEAD", "--", "optidigital-agent"],
        cwd=root, check=True, capture_output=True).stdout
    for name, content in files.items():
        if secret.encode() in content or any(part in {".env", "pgdata", "oauth", "logs"} for part in name.split("/")):
            raise RuntimeError("review package privacy check failed")
    target.mkdir()
    manifest = {}
    for name, content in files.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        manifest[name] = hashlib.sha256(content).hexdigest()
    save(target / "manifest.json", {"file_sha256": manifest,
        "actual_key_absent": True, "allowlist_only": True,
        "no_secret_file_or_private_log_included": True})
    archive = target.with_suffix(".zip")
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(target.rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(target))
    print(json.dumps({"review_package": str(archive), "file_count": len(files) + 1,
        "privacy_check": "PASS", "model_calls": 0}))


def replay_saved_gate():
    """Re-evaluate saved parsing only; no SDK, key loading, network or ledger writes."""
    original_bytes = REPORT_PATH.read_bytes()
    ledger_bytes = live.LEDGER_PATH.read_bytes()
    original = json.loads(original_bytes)
    live.COMPLETION_REPLAY_PATH = live.ARTIFACT_DIR / "contract_snapshot_completion.json"
    live._SOURCE_REVISION_FILES = (*live._SOURCE_REVISION_FILES, "optidigital-agent/ops/issue20_snapshot_diagnostic.py")
    analysis = JobAnalysis(**original["attempts"][-1]["analysis_before_gate"])
    inspected = inspect_analysis(analysis, repair_count=original["repair_calls"])
    before = original["attempts"][-1]["full_readiness_validation"]
    after = inspected["full_readiness_validation"]
    assert before["status"] == after["status"] and list(before["errors"]) == list(after["errors"])
    assert not inspected["application_proposal_ready"]
    assert inspected["analysis_after_gate"]["quality_repair_count"] == 1
    assert REPORT_PATH.read_bytes() == original_bytes
    assert live.LEDGER_PATH.read_bytes() == ledger_bytes
    save(live.ARTIFACT_DIR / "contract_snapshot_offline_replay.json", {
        "mode": "OFFLINE_REPLAY_OF_SAVED_PARSED_COMPLETION",
        "new_model_calls": 0, "original_report_unchanged": True, "ledger_unchanged": True,
        "correction": "Pass the recorded repair count to apply_validation; no gate status/errors changed.",
        "MODEL_ON_REAL_SNAPSHOT": original["MODEL_ON_REAL_SNAPSHOT"],
        "LIVE_MODEL_E2E": "NOT_RUN", "CURRENT_BID_READY": "NO",
        "executed_live_source_revision": original["source_revision"],
        "offline_replay_source_revision": live._source_revision(), "result": inspected,
    })
    print(json.dumps({"offline_replay": "PASS", "new_model_calls": 0,
        "gate_status_and_errors_unchanged": True, "quality_repair_count": 1}))


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("preflight", "run", "repair", "replay", "source-check", "package"))
    args = parser.parse_args()
    if args.mode == "package":
        package_review()
    elif args.mode == "source-check":
        asyncio.run(refresh_source_availability())
    elif args.mode == "replay":
        replay_saved_gate()
    else:
        asyncio.run(run(args.mode))
