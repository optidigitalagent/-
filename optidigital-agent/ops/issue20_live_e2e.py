"""Bounded live-model E2E for issue #20.

This runner is intentionally non-production: it reads one private local env
file, one public Freelancehunt RSS candidate, an isolated PostgreSQL URL and a
fake Telegram transport.  Its durable ledger makes the eight-call/$1 allowance
survive process restarts.  It has no platform-write or real Telegram path.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
from dotenv import dotenv_values
from openai import AsyncOpenAI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


AGENT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = AGENT_ROOT.parent
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))
ENV_PATH = AGENT_ROOT / ".env.issue20.local"
ARTIFACT_DIR = REPO_ROOT / "artifacts" / "private" / "issue20"
LEDGER_PATH = ARTIFACT_DIR / "live_model_budget.json"
REPORT_PATH = ARTIFACT_DIR / "live_e2e_report.json"
COMPLETION_REPLAY_PATH = ARTIFACT_DIR / "live_completion_replay.json"
MODEL = "gpt-4o-mini"
MAX_CALLS = 8
STEP_BASELINE_CALLS = 6
STEP_CALL_CEILING = 8
OFFICIAL_COMPLETION_ENDPOINT = "https://api.openai.com/v1/chat/completions"
MAX_USD = 1.0
INPUT_USD_PER_MILLION = 0.15
OUTPUT_USD_PER_MILLION = 0.60
PRICING_SOURCE = "https://developers.openai.com/api/docs/models/gpt-4o-mini"
PIPELINE_STAGE = "openai.chat.completions.create"
ISOLATED_DATABASE_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
ISOLATED_DATABASE_PORT = 55432
ISOLATED_DATABASE_NAME = "issue20e2e"

_RATE_LIMIT_HEADERS = (
    "x-ratelimit-limit-requests",
    "x-ratelimit-remaining-requests",
    "x-ratelimit-reset-requests",
    "x-ratelimit-limit-tokens",
    "x-ratelimit-remaining-tokens",
    "x-ratelimit-reset-tokens",
)
_SOURCE_REVISION_FILES = (
    "optidigital-agent/ops/issue20_live_e2e.py",
    "optidigital-agent/gmail_agent/digest_parser.py",
    "optidigital-agent/gmail_agent/email_analyzer.py",
    "optidigital-agent/gmail_agent/quality_gate.py",
    "optidigital-agent/gmail_agent/processor.py",
    "optidigital-agent/gmail_agent/storage.py",
    "optidigital-agent/gmail_agent/gmail_provider.py",
    "optidigital-agent/gmail_agent/freelancehunt_discovery.py",
    "optidigital-agent/gmail_agent/telegram_notifier.py",
    "optidigital-agent/gmail_agent/sales_closer.py",
    "optidigital-agent/db/models.py",
)

def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_private_key() -> str:
    if not ENV_PATH.is_file() or ENV_PATH.is_symlink():
        raise RuntimeError("private env file is absent or is not a regular file")
    value = str(dotenv_values(ENV_PATH).get("OPENAI_API_KEY") or "").strip()
    if not value:
        raise RuntimeError("OPENAI_API_KEY is absent in the confirmed env file")
    return value


def _make_live_client(key: str, *, capture_requests: bool = False) -> AsyncOpenAI:
    """Constrain the actual outbound request, retaining configured org/project IDs."""
    metadata: dict[str, Any] = {}

    async def guard(request: httpx.Request) -> None:
        if request.method != "POST" or str(request.url) != OFFICIAL_COMPLETION_ENDPOINT:
            raise RuntimeError("live runner refuses a non-official completion endpoint")
        if capture_requests:
            # Explicit diagnostic-only capture for the approved public source.
            # No HTTP headers, credentials or SDK configuration are serialized.
            sequence = len(_load_ledger()["calls"])
            body = json.loads(request.content)
            _write_json(ARTIFACT_DIR / f"contract_request_{sequence}.json", {
                "endpoint": OFFICIAL_COMPLETION_ENDPOINT,
                "capture": "ACTUAL_SERIALIZED_SDK_BODY_BEFORE_DISPATCH",
                "body": {k: body[k] for k in ("model", "messages", "response_format", "temperature", "max_tokens") if k in body},
            })

    async def observe(response: httpx.Response) -> None:
        metadata.clear()
        metadata["http_status"] = response.status_code
        for name in ("x-request-id", "openai-organization"):
            value = response.headers.get(name)
            if value:
                metadata[name] = _bounded_safe_text(value, limit=200)

    transport = httpx.AsyncHTTPTransport(retries=0, verify=True)
    http_client = httpx.AsyncClient(
        transport=transport, follow_redirects=False, trust_env=False,
        timeout=60.0, event_hooks={"request": [guard], "response": [observe]},
    )
    client = AsyncOpenAI(api_key=key, max_retries=0, http_client=http_client)
    if str(client.base_url) != "https://api.openai.com/v1/":
        raise RuntimeError("configured API base URL is not the official endpoint")
    client._issue20_response_metadata = metadata
    return client


def _validate_isolated_database_url(value: str) -> str:
    """Accept only the dedicated loopback issue-20 database contract."""

    try:
        parsed = urlsplit(str(value or ""))
        database_name = parsed.path.removeprefix("/")
        valid = (
            parsed.scheme == "postgresql+asyncpg"
            and parsed.hostname in ISOLATED_DATABASE_HOSTS
            and parsed.port == ISOLATED_DATABASE_PORT
            and database_name == ISOLATED_DATABASE_NAME
            and parsed.username == "issue20e2e"
            and parsed.password is None
            and not parsed.query
            and not parsed.fragment
        )
    except (TypeError, ValueError):
        valid = False
    if not valid:
        raise RuntimeError(
            "database URL must target the dedicated loopback issue20e2e database"
        )
    return value


def _scope_timestamp(value: Any, name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.utcoffset() is None:
        raise RuntimeError(f"{name} must include a timezone offset")
    return parsed.astimezone(timezone.utc)


def _load_verified_candidate_scope(path_value: str) -> dict[str, Any]:
    """Load a bounded, private source snapshot for one current real candidate."""

    candidate_path = Path(str(path_value or ""))
    if not candidate_path.is_file() or candidate_path.is_symlink():
        raise RuntimeError("verified scope file is absent or is not a regular file")
    resolved = candidate_path.resolve(strict=True)
    try:
        resolved.relative_to(ARTIFACT_DIR.resolve())
    except ValueError as exc:
        raise RuntimeError("verified scope file must stay under artifacts/private/issue20") from exc
    if resolved.stat().st_size > 64_000:
        raise RuntimeError("verified scope file exceeds the bounded size")
    try:
        value = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("verified scope file is not valid UTF-8 JSON") from exc
    required = {
        "project_id",
        "url",
        "full_description",
        "verified_at",
        "description_completeness",
        "materials_status",
        "scope_sufficiency",
        "source_kind",
        "rss_source_url",
        "rss_source_identity",
        "rss_fetched_at",
        "rss_feed_timestamp",
        "rss_entry_sha256",
        "rss_budget",
        "rss_budget_currency",
        "full_text_source_url",
        "full_text_fetched_at",
        "full_text_sha256",
        "source_budget",
        "source_budget_currency",
        "source_budget_status",
        "source_budget_source",
        "materials_evidence",
        "scope_sufficiency_basis",
        "remaining_unknowns",
        "manual_scope_assessment",
        "manual_scope_assessment_basis",
        "live_status",
        "live_status_biddable",
        "live_status_source",
        "live_status_checked_at",
        "live_status_evidence",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise RuntimeError("verified scope file has an unexpected field set")
    list_value = value["remaining_unknowns"]
    if not isinstance(list_value, list) or any(
        not isinstance(item, str) or not item.strip() or len(item) > 500
        for item in list_value
    ):
        raise RuntimeError("remaining_unknowns must be a bounded string list")
    if not isinstance(value["manual_scope_assessment"], bool):
        raise RuntimeError("manual_scope_assessment must be boolean")
    if value["live_status_biddable"] is not True:
        raise RuntimeError("verified scope must record biddable=true")
    snapshot: dict[str, Any] = {
        key: str(value[key] or "").strip()
        for key in required
        if key not in {
            "remaining_unknowns",
            "manual_scope_assessment",
            "live_status_biddable",
        }
    }
    snapshot["remaining_unknowns"] = [item.strip() for item in list_value]
    snapshot["manual_scope_assessment"] = value["manual_scope_assessment"]
    snapshot["live_status_biddable"] = True
    project_id = snapshot["project_id"]
    if not project_id.isdecimal():
        raise RuntimeError("verified scope project_id must be numeric")
    parsed_url = urlsplit(snapshot["url"])
    if (
        parsed_url.scheme != "https"
        or parsed_url.hostname not in {"freelancehunt.com", "www.freelancehunt.com"}
        or parsed_url.username is not None
        or parsed_url.password is not None
        or parsed_url.port not in {None, 443}
        or parsed_url.query
        or parsed_url.fragment
        or not parsed_url.path.endswith(f"/{project_id}.html")
    ):
        raise RuntimeError("verified scope URL is not a safe matching Freelancehunt URL")
    description = " ".join(snapshot["full_description"].split())
    if not description or len(description) > 16_000:
        raise RuntimeError("verified scope description is absent or exceeds the bound")
    snapshot["full_description"] = description
    expected_full_hash = hashlib.sha256(description.encode("utf-8")).hexdigest()
    if not hmac.compare_digest(snapshot["full_text_sha256"], expected_full_hash):
        raise RuntimeError("verified full-text hash does not match normalized text")
    if not re.fullmatch(r"[0-9a-f]{64}", snapshot["rss_entry_sha256"]):
        raise RuntimeError("RSS entry hash is not lowercase SHA-256")
    if snapshot["rss_source_url"] != "https://freelancehunt.com/projects.rss":
        raise RuntimeError("verified scope must use the official repository RSS URL")
    if project_id not in snapshot["rss_source_identity"]:
        raise RuntimeError("RSS source identity is not bound to project_id")
    if snapshot["source_kind"] != "PUBLIC_PAGE_VERIFIED":
        raise RuntimeError("live scope source must be PUBLIC_PAGE_VERIFIED")
    if snapshot["description_completeness"] != "FULL":
        raise RuntimeError("live scope main text must be verified FULL")
    full_text_url = urlsplit(snapshot["full_text_source_url"])
    if (
        full_text_url.scheme != "https"
        or full_text_url.hostname not in {"freelancehunt.com", "www.freelancehunt.com"}
        or full_text_url.username is not None
        or full_text_url.password is not None
        or full_text_url.port not in {None, 443}
        or full_text_url.query
        or full_text_url.fragment
        or not full_text_url.path.endswith(f"/{project_id}.html")
    ):
        raise RuntimeError("full-text source URL is not a safe matching project URL")
    materials = snapshot["materials_status"]
    sufficiency = snapshot["scope_sufficiency"]
    if materials not in {
        "NOT_REFERENCED",
        "AVAILABLE",
        "UNAVAILABLE_SCOPE_RELEVANT",
        "UNAVAILABLE_EXECUTION_INPUTS_ONLY",
    }:
        raise RuntimeError("verified scope materials_status is unsupported")
    if sufficiency not in {
        "INSUFFICIENT_FOR_FIXED_TERMS",
        "SUFFICIENT_FOR_FIXED_TERMS",
    }:
        raise RuntimeError("verified scope sufficiency is unsupported")
    if (
        materials == "UNAVAILABLE_SCOPE_RELEVANT"
        and sufficiency != "INSUFFICIENT_FOR_FIXED_TERMS"
    ):
        raise RuntimeError("scope-relevant unavailable materials cannot authorize terms")
    if (
        materials == "UNAVAILABLE_EXECUTION_INPUTS_ONLY"
        and sufficiency != "SUFFICIENT_FOR_FIXED_TERMS"
    ):
        raise RuntimeError("execution-input-only status requires sufficient main scope")
    if snapshot["source_budget_status"] not in {"PROVIDED", "NOT_SPECIFIED"}:
        raise RuntimeError("source budget status is unsupported")
    if snapshot["source_budget_status"] == "PROVIDED" and not (
        snapshot["source_budget"] and snapshot["source_budget_currency"]
    ):
        raise RuntimeError("provided source budget requires value and currency")
    if snapshot["source_budget_status"] == "PROVIDED" and snapshot[
        "source_budget_source"
    ] not in {"RSS_CANDIDATE", "PUBLIC_PAGE_DESCRIPTION"}:
        raise RuntimeError("provided source budget requires an approved source")
    if snapshot["source_budget_status"] == "NOT_SPECIFIED" and (
        snapshot["source_budget"]
        or snapshot["source_budget_currency"]
        or snapshot["source_budget_source"] != "NOT_SPECIFIED"
    ):
        raise RuntimeError("unspecified source budget cannot contain team terms")
    if snapshot["live_status"] != "ACTIVE_BIDDABLE":
        raise RuntimeError("verified scope must record ACTIVE_BIDDABLE")
    for name in (
        "verified_at",
        "rss_fetched_at",
        "rss_feed_timestamp",
        "full_text_fetched_at",
        "live_status_checked_at",
    ):
        _scope_timestamp(snapshot[name], name)
    live_checked_at = _scope_timestamp(
        snapshot["live_status_checked_at"], "live_status_checked_at"
    )
    age_seconds = (datetime.now(timezone.utc) - live_checked_at).total_seconds()
    if age_seconds < -300 or age_seconds > 900:
        raise RuntimeError("snapshot live status is not fresh enough for dispatch")
    if not snapshot["scope_sufficiency_basis"]:
        raise RuntimeError("scope sufficiency basis is required")
    if snapshot["manual_scope_assessment"] and not snapshot[
        "manual_scope_assessment_basis"
    ]:
        raise RuntimeError("manual scope assessment basis is required")
    return snapshot


def _load_ledger() -> dict[str, Any]:
    if not LEDGER_PATH.exists():
        return {
            "version": 1,
            "model": MODEL,
            "max_calls": MAX_CALLS,
            "max_usd": MAX_USD,
            "sdk_max_retries": 0,
            "pricing": {
                "checked_at": _utc_iso(),
                "source": PRICING_SOURCE,
                "input_usd_per_million": INPUT_USD_PER_MILLION,
                "output_usd_per_million": OUTPUT_USD_PER_MILLION,
            },
            "calls": [],
        }
    value = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    if value.get("model") != MODEL or value.get("max_calls") != MAX_CALLS:
        raise RuntimeError("existing live-model ledger contract does not match this runner")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _usage_value(usage: Any, name: str) -> int | None:
    value = getattr(usage, name, None)
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else None


def _bounded_safe_text(value: Any, *, limit: int = 500) -> str:
    """Redact credential-shaped material and bound one diagnostic string."""

    text = " ".join(str(value or "").split())
    if not text:
        return ""
    text = re.sub(
        r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+",
        "Bearer [REDACTED]",
        text,
    )
    text = re.sub(r"(?i)\bsk-[A-Za-z0-9_-]{8,}", "[REDACTED_KEY]", text)
    text = re.sub(
        r"(?i)\b(api[_-]?key|token|authorization|cookie|password)\s*[=:]\s*[^\s,;]+",
        r"\1=[REDACTED]",
        text,
    )

    def sanitize_url(match: re.Match[str]) -> str:
        return _safe_endpoint(match.group(0)) or "[REDACTED_URL]"

    text = re.sub(r"https?://[^\s]+", sanitize_url, text, flags=re.IGNORECASE)
    return text[: max(0, limit)]


def _safe_endpoint(value: Any) -> str:
    """Keep only scheme, hostname, optional port and path from an HTTP URL."""

    try:
        parsed = urlsplit(str(value or ""))
        if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
            return ""
        hostname = parsed.hostname
        if ":" in hostname and not hostname.startswith("["):
            hostname = f"[{hostname}]"
        port = parsed.port
        netloc = f"{hostname}:{port}" if port is not None else hostname
        return urlunsplit((parsed.scheme.casefold(), netloc, parsed.path or "/", "", ""))
    except (TypeError, ValueError):
        return ""


def _mapping_value(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return None


def _safe_error_diagnostics(
    exc: Exception,
    *,
    requested_model: str,
    pipeline_stage: str,
) -> dict[str, Any]:
    """Extract only the explicitly allowed provider diagnostic fields."""

    diagnostic: dict[str, Any] = {
        "exception_class": type(exc).__name__,
        "requested_model": requested_model,
        "pipeline_stage": pipeline_stage,
    }
    response = getattr(exc, "response", None)
    status = getattr(exc, "status_code", None)
    if not isinstance(status, int):
        status = getattr(response, "status_code", None)
    if isinstance(status, int):
        diagnostic["http_status"] = status

    body = getattr(exc, "body", None)
    error_object = _mapping_value(body, "error")
    if not isinstance(error_object, dict):
        error_object = body if isinstance(body, dict) else {}
    error_code = getattr(exc, "code", None) or error_object.get("code")
    error_type = getattr(exc, "type", None) or error_object.get("type")
    error_message = error_object.get("message") or getattr(exc, "message", None)
    if isinstance(error_code, str) and error_code.strip():
        diagnostic["error_code"] = _bounded_safe_text(error_code, limit=120)
    if isinstance(error_type, str) and error_type.strip():
        diagnostic["error_type"] = _bounded_safe_text(error_type, limit=120)
    safe_message = _bounded_safe_text(error_message)
    if safe_message:
        diagnostic["error_message"] = safe_message

    headers = getattr(response, "headers", None)
    request_id = getattr(exc, "request_id", None)
    if not request_id and headers is not None:
        request_id = headers.get("x-request-id")
    if isinstance(request_id, str) and request_id.strip():
        diagnostic["request_id"] = _bounded_safe_text(request_id, limit=200)
    if headers is not None:
        organization = headers.get("openai-organization")
        if organization:
            diagnostic["response_openai_organization"] = _bounded_safe_text(
                organization, limit=200
            )
        retry_after = headers.get("retry-after")
        if retry_after is not None:
            safe_retry = _bounded_safe_text(retry_after, limit=100)
            if safe_retry:
                diagnostic["retry_after"] = safe_retry
        rate_headers = {
            name: _bounded_safe_text(headers.get(name), limit=100)
            for name in _RATE_LIMIT_HEADERS
            if headers.get(name) is not None
        }
        rate_headers = {key: value for key, value in rate_headers.items() if value}
        if rate_headers:
            diagnostic["rate_limit_headers"] = rate_headers

    request = getattr(exc, "request", None) or getattr(response, "request", None)
    method = getattr(request, "method", None)
    if isinstance(method, str) and method.strip():
        diagnostic["method"] = method.strip().upper()[:20]
    endpoint = _safe_endpoint(getattr(request, "url", None))
    if endpoint:
        diagnostic["endpoint"] = endpoint
    return diagnostic


def _git_text(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


def _source_revision() -> dict[str, Any]:
    """Return reproducible, secret-free source identity for the local run."""

    revision: dict[str, Any] = {"files": {}}
    try:
        revision["head"] = _git_text("rev-parse", "HEAD")
        revision["dirty"] = bool(_git_text("status", "--porcelain=v1"))
    except (OSError, subprocess.SubprocessError):
        revision["dirty"] = True
    file_hashes: dict[str, str] = {}
    for relative in _SOURCE_REVISION_FILES:
        path = REPO_ROOT / relative
        if path.is_file() and not path.is_symlink():
            file_hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    revision["files"] = file_hashes
    combined = json.dumps(file_hashes, sort_keys=True, separators=(",", ":"))
    revision["source_sha256"] = hashlib.sha256(combined.encode("utf-8")).hexdigest()
    return revision


def _failure_report(record: dict[str, Any], ledger: dict[str, Any]) -> dict[str, Any]:
    diagnostic_keys = {
        "exception_class",
        "http_status",
        "error_code",
        "error_type",
        "error_message",
        "request_id",
        "retry_after",
        "rate_limit_headers",
        "method",
        "endpoint",
        "requested_model",
        "pipeline_stage",
        "response_openai_organization",
    }
    return {
        "status": "FAILED",
        "account_identity": "NOT_VERIFIED",
        "key_use_authorization": "EXPLICIT",
        "started_at": record["started_at"],
        "finished_at": record.get("finished_at"),
        "pipeline_stage": record.get("pipeline_stage"),
        "source_revision": record.get("source_revision") or _source_revision(),
        "model": {
            "requested": record.get("requested_model"),
            "calls_total_persistent": len(ledger.get("calls", [])),
            "calls_this_authorized_step": max(0, len(ledger.get("calls", [])) - STEP_BASELINE_CALLS),
            "api_usage": "NOT_RETURNED",
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
            "actual_cost": "UNKNOWN",
            "actual_cost_usd": None,
            "billing": "NOT_VERIFIED",
            "reserved_upper_bound_usd": record.get("upper_bound_usd"),
            "reserved_total_upper_bound_usd": round(sum(float(c["upper_bound_usd"]) for c in ledger.get("calls", [])), 8),
            "pricing_source": PRICING_SOURCE,
        },
        "error": {key: record[key] for key in diagnostic_keys if key in record},
    }


def _write_failure_report(record: dict[str, Any], ledger: dict[str, Any]) -> None:
    _write_json(REPORT_PATH, _failure_report(record, ledger))


def _new_failed_provider_call(
    ledger: dict[str, Any], initial_call_count: int
) -> dict[str, Any] | None:
    calls = ledger.get("calls")
    if not isinstance(calls, list) or len(calls) <= initial_call_count:
        return None
    latest = calls[-1]
    if not isinstance(latest, dict) or latest.get("status") != "FAILED":
        return None
    return latest


class BudgetedCompletions:
    def __init__(self, inner: Any, *, pipeline_stage: str = PIPELINE_STAGE,
                 response_metadata: dict[str, Any] | None = None,
                 enforce_targeted_repair: bool = False) -> None:
        self._inner = inner
        self._pipeline_stage = pipeline_stage
        self._response_metadata = response_metadata
        self._enforce_targeted_repair = enforce_targeted_repair

    async def create(self, **kwargs: Any) -> Any:
        requested_model = str(kwargs.get("model") or "")
        if requested_model != MODEL:
            raise RuntimeError("live runner refuses an unapproved model")
        ledger = _load_ledger()
        calls = ledger["calls"]
        if len(calls) >= MAX_CALLS:
            raise RuntimeError("live-model call limit exhausted")
        if len(calls) >= STEP_CALL_CEILING:
            raise RuntimeError("issue-20 current-step two-call allowance exhausted")
        if any(
            item.get("sequence", 0) > STEP_BASELINE_CALLS and item.get("status") in {"FAILED", "RESERVED"}
            for item in calls
        ):
            raise RuntimeError("current step is closed after an API/transport failure")
        if self._enforce_targeted_repair and len(calls) > STEP_BASELINE_CALLS:
            prompt = str(kwargs.get("messages", [{}])[-1].get("content", ""))
            if (calls[-1].get("status") != "COMPLETED"
                    or not calls[-1].get("completion_received")
                    or "QUALITY REPAIR" not in prompt or "Validation errors:" not in prompt):
                raise RuntimeError("second call requires a received completion and targeted validation repair")

        # One UTF-8 byte per token is deliberately conservative. Include the
        # schema and messages, then charge the full configured output ceiling.
        request_bytes = len(
            json.dumps(kwargs, ensure_ascii=False, default=str).encode("utf-8")
        )
        output_cap = int(kwargs.get("max_tokens") or 0)
        if not 0 < output_cap <= 1600 or request_bytes + output_cap > 128_000:
            raise RuntimeError("request exceeds the approved token limits")
        upper_bound = (
            request_bytes * INPUT_USD_PER_MILLION
            + output_cap * OUTPUT_USD_PER_MILLION
        ) / 1_000_000
        reserved_total = sum(float(item["upper_bound_usd"]) for item in calls)
        if reserved_total + upper_bound > MAX_USD:
            raise RuntimeError("next live-model request may exceed the remaining cost limit")

        record = {
            "sequence": len(calls) + 1,
            "started_at": _utc_iso(),
            "requested_model": requested_model,
            "sdk_max_retries": 0,
            "input_token_upper_bound": request_bytes,
            "output_token_cap": output_cap,
            "upper_bound_usd": round(upper_bound, 8),
            "status": "RESERVED",
            "api_usage": "NOT_RETURNED",
            "actual_cost": "UNKNOWN",
            "billing": "NOT_VERIFIED",
            "pipeline_stage": self._pipeline_stage,
            "source_revision": _source_revision(),
        }
        calls.append(record)
        _write_json(LEDGER_PATH, ledger)
        try:
            response = await self._inner.create(**kwargs)
        except Exception as exc:
            record["status"] = "FAILED"
            record["finished_at"] = _utc_iso()
            record.update(
                _safe_error_diagnostics(
                    exc,
                    requested_model=requested_model,
                    pipeline_stage=self._pipeline_stage,
                )
            )
            # Persistence diagnostics are secondary: neither a ledger nor a
            # report write failure may replace the provider exception.
            try:
                _write_json(LEDGER_PATH, ledger)
            except Exception:
                pass
            try:
                _write_failure_report(record, ledger)
            except Exception:
                pass
            raise

        usage = getattr(response, "usage", None)
        prompt_tokens = _usage_value(usage, "prompt_tokens")
        completion_tokens = _usage_value(usage, "completion_tokens")
        total_tokens = _usage_value(usage, "total_tokens")
        actual_cost = (
            (
                prompt_tokens * INPUT_USD_PER_MILLION
                + completion_tokens * OUTPUT_USD_PER_MILLION
            )
            / 1_000_000
            if prompt_tokens is not None and completion_tokens is not None
            else None
        )
        model_value = getattr(response, "model", "")
        record.update(
            status="COMPLETED",
            finished_at=_utc_iso(),
            actual_model=(model_value if isinstance(model_value, str) else requested_model),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            api_usage=("RETURNED" if actual_cost is not None else "NOT_RETURNED"),
            actual_cost=("ESTIMATED_FROM_USAGE" if actual_cost is not None else "UNKNOWN"),
            actual_estimated_usd=(round(actual_cost, 8) if actual_cost is not None else None),
        )
        record["request_id"] = _bounded_safe_text(getattr(response, "_request_id", ""), limit=200)
        if self._response_metadata:
            record["http_status"] = self._response_metadata.get("http_status")
            record["request_id"] = self._response_metadata.get("x-request-id", record["request_id"])
            if self._response_metadata.get("openai-organization"):
                record["response_openai_organization"] = self._response_metadata["openai-organization"]
        _write_json(LEDGER_PATH, ledger)
        choices = getattr(response, "choices", None)
        first_choice = choices[0] if isinstance(choices, list) and choices else None
        message = getattr(first_choice, "message", None)
        content = getattr(message, "content", None)
        record["completion_received"] = isinstance(content, str) and bool(content.strip())
        _write_json(LEDGER_PATH, ledger)
        replay = {
            "saved_at": _utc_iso(),
            "requested_model": requested_model,
            "actual_model": record.get("actual_model"),
            "finish_reason": getattr(first_choice, "finish_reason", None),
            "content": content if isinstance(content, str) else "",
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            },
            "source_revision": record["source_revision"],
            "ledger_sequence": record["sequence"],
        }
        _write_json(COMPLETION_REPLAY_PATH, replay)
        _write_json(COMPLETION_REPLAY_PATH.with_name(f"live_completion_replay_{record['sequence']}.json"), replay)
        return response


class BudgetedOpenAIClient:
    def __init__(self, inner: AsyncOpenAI) -> None:
        self.chat = SimpleNamespace(
            completions=BudgetedCompletions(
                inner.chat.completions,
                response_metadata=getattr(inner, "_issue20_response_metadata", None),
                enforce_targeted_repair=True,
            )
        )


@dataclass
class FakeTelegramTransport:
    messages: list[str]

    async def send_message(self, *, chat_id: int, text: str, **_: Any) -> Any:
        if chat_id != -20:
            raise RuntimeError("fake transport refuses unexpected chat ID")
        self.messages.append(text)
        return SimpleNamespace(message_id=len(self.messages))


async def _prepare_isolated_schema(
    engine: Any, base: Any, migrations: list[str] | tuple[str, ...]
) -> None:
    """Create missing tables and apply the application's additive migrations."""

    async with engine.begin() as connection:
        await connection.run_sync(base.metadata.create_all)
        for statement in migrations:
            await connection.execute(text(statement))


def _outcome_checks(
    reloaded: Any,
    *,
    proposal_ready: bool,
    rendered: list[str],
    telegram_messages: list[str],
    opportunity: Any | None,
) -> dict[str, bool]:
    """Validate the truthful downstream state for TAKE, ASK or SKIP."""

    decision = str(reloaded.commercial_decision or "").upper()
    expected_quality = {
        "TAKE": {"VALID", "REPAIRED"},
        "ASK": {"NEEDS_CLARIFICATION"},
        "SKIP": {"NON_EXECUTABLE"},
    }
    expected_status = {
        "TAKE": {"sent", "sales_tracking_pending"},
        "ASK": {"needs_clarification"},
        "SKIP": {"skipped"},
    }
    is_take = decision == "TAKE"
    no_offer_terms = not (
        reloaded.proposal_draft
        or reloaded.recommended_price
        or reloaded.realistic_timeline
        or reloaded.proposal_content_sha256
        or reloaded.proposal_version
    )
    sales_state_matches = (
        bool(
            opportunity
            and opportunity.proposal_version == reloaded.proposal_version
            and opportunity.proposal_content_sha256
            == reloaded.proposal_content_sha256
        )
        if is_take
        else opportunity is None
    )
    return {
        "decision_supported": decision in expected_quality,
        "quality_state_matches_decision": (
            reloaded.analysis_quality_status in expected_quality.get(decision, set())
        ),
        "offer_state_matches_decision": (
            proposal_ready and bool(reloaded.proposal_content_sha256)
            if is_take
            else (not proposal_ready and no_offer_terms)
        ),
        "terminal_status_matches_decision": (
            reloaded.status in expected_status.get(decision, set())
        ),
        "telegram_fake_transport_used": bool(telegram_messages),
        "real_renderer_matches_transport": rendered == telegram_messages,
        "sales_5a_state_matches_decision": sales_state_matches,
    }


async def _main(
    database_url: str,
    *,
    delivery_mode: str,
    verified_scope_file: str,
) -> int:
    database_url = _validate_isolated_database_url(database_url)
    if delivery_mode != "disabled":
        raise RuntimeError("external delivery must be explicitly disabled")
    scope_snapshot = _load_verified_candidate_scope(verified_scope_file)
    ledger_before = _load_ledger()
    initial_call_count = len(ledger_before["calls"])
    if initial_call_count != STEP_BASELINE_CALLS:
        raise RuntimeError("persistent ledger is outside the approved issue-20 history")
    key = _load_private_key()
    # Satisfy import-time application settings with isolated, non-production
    # values. The real key remains only in the explicitly constructed client.
    os.environ["DATABASE_URL"] = database_url
    os.environ["TELEGRAM_TOKEN"] = "issue20-fake-transport-token"
    os.environ["TELEGRAM_CHAT_ID"] = "-20"
    # Import application modules only after the runner has validated its local
    # boundaries. None of these imports starts the production bot/scheduler.
    from db.models import Base, _MIGRATIONS
    from gmail_agent.freelancehunt_discovery import (
        FreelancehuntFeedClient,
        enrich_candidate_scope,
        rss_candidate_sha256,
    )
    from gmail_agent.live_status import FreelancehuntLiveStatusChecker
    from gmail_agent.processor import GmailJobProcessor
    from gmail_agent.quality_gate import is_proposal_ready
    from gmail_agent.sales_closer import opportunity_id_for
    from gmail_agent.sales_storage import PostgresSalesRepository
    from gmail_agent.storage import PostgresGmailRepository
    from gmail_agent.telegram_notifier import format_job_card_parts

    openai_inner = _make_live_client(key)
    client = BudgetedOpenAIClient(openai_inner)
    batch = await FreelancehuntFeedClient(timeout_seconds=8, max_items=50).fetch()
    source = next(
        (
            candidate
            for candidate in batch.candidates
            if candidate.project_id == scope_snapshot["project_id"]
        ),
        None,
    )
    if source is None:
        raise RuntimeError("verified real project is absent from the current official RSS")
    if source.url != scope_snapshot["url"]:
        raise RuntimeError("current RSS canonical URL no longer matches the snapshot")
    if rss_candidate_sha256(source) != scope_snapshot["rss_entry_sha256"]:
        raise RuntimeError("current RSS candidate facts no longer match the snapshot")
    if (
        source.budget != scope_snapshot["rss_budget"]
        or source.budget_currency != scope_snapshot["rss_budget_currency"]
    ):
        raise RuntimeError("current RSS budget/currency no longer match the snapshot")
    candidate = enrich_candidate_scope(
        source,
        description=scope_snapshot["full_description"],
        source_kind=scope_snapshot["source_kind"],
        main_text_completeness=scope_snapshot["description_completeness"],
        materials_status=scope_snapshot["materials_status"],
        scope_sufficiency=scope_snapshot["scope_sufficiency"],
    )
    if scope_snapshot["source_budget_status"] == "PROVIDED":
        candidate = replace(
            candidate,
            budget=scope_snapshot["source_budget"],
            budget_currency=scope_snapshot["source_budget_currency"],
        )

    engine = create_async_engine(database_url, echo=False)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        await _prepare_isolated_schema(engine, Base, _MIGRATIONS)
        repository = PostgresGmailRepository(sessions)
        transport = FakeTelegramTransport([])

        async def mark_as_processed(_: str) -> None:
            return None

        processor = GmailJobProcessor(
            provider=SimpleNamespace(mark_as_processed=mark_as_processed),
            bot=transport,
            chat_id=-20,
            min_score=0.0,
            repository=repository,
            max_cards_per_scan=1,
            digest_enabled=True,
            openai_client=client,
            live_status_checker=FreelancehuntLiveStatusChecker(),
        )
        stats = await processor.run_candidates(
            [candidate],
            trigger="issue20_live_e2e",
            source_alias="official-public-rss+verified-page",
            source_candidates_found=1,
        )
        reloaded = await PostgresGmailRepository(sessions).get_job(candidate.stable_key)
        if reloaded is None:
            failed_ledger = _load_ledger()
            failed_call = _new_failed_provider_call(
                failed_ledger, initial_call_count
            )
            if failed_call is not None:
                failure = _failure_report(failed_call, failed_ledger)
                _write_json(REPORT_PATH, failure)
                print(json.dumps(failure, ensure_ascii=False, indent=2))
                return 1
            raise RuntimeError("positive candidate was not persisted")
        rendered = format_job_card_parts(GmailJobProcessor._analysis_from_job(reloaded))
        opportunity_id = opportunity_id_for(
            reloaded.project_id, reloaded.url or "", reloaded.stable_key
        )
        opportunity = await PostgresSalesRepository(sessions).get_opportunity(opportunity_id)
        ledger = _load_ledger()
        usage_records = [
            item
            for item in ledger["calls"]
            if item.get("api_usage") == "RETURNED"
            or (
                isinstance(item.get("prompt_tokens"), int)
                and isinstance(item.get("completion_tokens"), int)
                and item.get("status") == "COMPLETED"
            )
        ]
        usage_missing = len(usage_records) != len(ledger["calls"])
        known_actual_costs = [
            float(item["actual_estimated_usd"])
            for item in usage_records
            if isinstance(item.get("actual_estimated_usd"), (int, float))
        ]
        checks = _outcome_checks(
            reloaded,
            proposal_ready=is_proposal_ready(reloaded),
            rendered=rendered,
            telegram_messages=transport.messages,
            opportunity=opportunity,
        )
        report = {
            "status": "PASSED" if all(checks.values()) else "FAILED",
            "account_identity": "NOT_VERIFIED",
            "key_use_authorization": "EXPLICIT",
            "finished_at": _utc_iso(),
            "source_revision": _source_revision(),
            "source": {
                "project_id": candidate.project_id,
                "url": candidate.url,
                "budget": candidate.budget,
                "budget_currency": candidate.budget_currency,
                "discovery_source": candidate.discovery_source,
                "description_completeness": candidate.description_completeness,
                "materials_status": candidate.materials_status,
                "scope_sufficiency": candidate.scope_sufficiency,
                "scope_enrichment_source": candidate.scope_enrichment_source,
                "scope_enrichment_sha256": candidate.scope_enrichment_sha256,
                "rss_source_url": scope_snapshot["rss_source_url"],
                "rss_source_identity": scope_snapshot["rss_source_identity"],
                "rss_fetched_at": scope_snapshot["rss_fetched_at"],
                "rss_entry_sha256": scope_snapshot["rss_entry_sha256"],
                "rss_budget": scope_snapshot["rss_budget"],
                "rss_budget_currency": scope_snapshot["rss_budget_currency"],
                "full_text_source_url": scope_snapshot["full_text_source_url"],
                "full_text_fetched_at": scope_snapshot["full_text_fetched_at"],
                "full_text_sha256": scope_snapshot["full_text_sha256"],
                "source_budget_status": scope_snapshot["source_budget_status"],
                "source_budget_source": scope_snapshot["source_budget_source"],
                "materials_evidence": scope_snapshot["materials_evidence"],
                "scope_sufficiency_basis": scope_snapshot[
                    "scope_sufficiency_basis"
                ],
                "remaining_unknowns": scope_snapshot["remaining_unknowns"],
                "manual_scope_assessment": scope_snapshot[
                    "manual_scope_assessment"
                ],
                "manual_scope_assessment_basis": scope_snapshot[
                    "manual_scope_assessment_basis"
                ],
                "snapshot_live_status": scope_snapshot["live_status"],
                "snapshot_live_status_checked_at": scope_snapshot[
                    "live_status_checked_at"
                ],
            },
            "model": {
                "requested": MODEL,
                "actual": reloaded.provider_model,
                "provider_outcome": reloaded.provider_outcome,
                "finish_reason": reloaded.provider_finish_reason,
                "calls_total_persistent": len(ledger["calls"]),
                "calls_this_success_path": stats.ai_analyzed + stats.repair_calls,
                "calls_this_runner_invocation": len(ledger["calls"])
                - initial_call_count,
                "calls_this_authorized_step": max(0, len(ledger["calls"]) - STEP_BASELINE_CALLS),
                "current_step_call_ceiling": STEP_CALL_CEILING,
                "api_usage": "PARTIAL" if usage_missing else "RETURNED",
                "prompt_tokens_total_known": sum(
                    int(item.get("prompt_tokens") or 0) for item in usage_records
                ),
                "completion_tokens_total_known": sum(
                    int(item.get("completion_tokens") or 0) for item in usage_records
                ),
                "total_tokens_known": sum(
                    int(item.get("total_tokens") or 0) for item in usage_records
                ),
                "usage_not_returned_calls": len(ledger["calls"]) - len(usage_records),
                "actual_cost": "UNKNOWN" if usage_missing else "ESTIMATED_FROM_USAGE",
                "actual_cost_usd": (
                    None if usage_missing else round(sum(known_actual_costs), 8)
                ),
                "billing": "NOT_VERIFIED",
                "reserved_upper_bound_usd": round(
                    sum(item["upper_bound_usd"] for item in ledger["calls"]), 8
                ),
                "pricing_source": PRICING_SOURCE,
            },
            "decision": reloaded.commercial_decision,
            "score": reloaded.score,
            "fit_score": reloaded.fit_score,
            "live_status": reloaded.live_status,
            "model_calls": ledger["calls"][STEP_BASELINE_CALLS:],
            "decision_reason": reloaded.decision_reason,
            "quality_status": reloaded.analysis_quality_status,
            "quality_errors": json.loads(reloaded.quality_errors or "[]"),
            "repair_count": reloaded.quality_repair_count,
            "proposal": reloaded.proposal_draft,
            "recommended_price": reloaded.recommended_price,
            "realistic_timeline": reloaded.realistic_timeline,
            "proposal_version": reloaded.proposal_version,
            "proposal_content_sha256": reloaded.proposal_content_sha256,
            "opportunity_id": opportunity_id if opportunity else "",
            "checks": checks,
            "telegram_messages": transport.messages,
        }
        _write_json(REPORT_PATH, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["status"] == "PASSED" else 2
    finally:
        await engine.dispose()
        await openai_inner.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--database-url",
        default=os.getenv("ISSUE20_DATABASE_URL", ""),
        help="isolated postgresql+asyncpg URL (never production)",
    )
    parser.add_argument(
        "--external-delivery",
        required=True,
        choices=("disabled",),
        help="mandatory safety acknowledgement; this runner uses only fake Telegram",
    )
    parser.add_argument(
        "--verified-scope-file",
        required=True,
        help="private verified candidate snapshot under artifacts/private/issue20",
    )
    args = parser.parse_args()
    database_url = _validate_isolated_database_url(args.database_url)
    return asyncio.run(
        _main(
            database_url,
            delivery_mode=args.external_delivery,
            verified_scope_file=args.verified_scope_file,
        )
    )


if __name__ == "__main__":
    sys.exit(main())
