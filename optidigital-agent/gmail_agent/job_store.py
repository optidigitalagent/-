"""Small persistent store for Gmail job analyses used by /reply_job."""

import json
import os
from pathlib import Path
from typing import Any


DEFAULT_STORE_PATH = Path(__file__).parent / "gmail_jobs.json"


def _store_path(path: str | Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    return Path(os.getenv("GMAIL_JOB_STORE_FILE", DEFAULT_STORE_PATH))


def _load(path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    target = _store_path(path)
    if not target.exists():
        return {}
    try:
        raw = target.read_text(encoding="utf-8").strip()
        if not raw:
            return {}
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        str(key): value
        for key, value in data.items()
        if isinstance(value, dict)
    }


def _save(data: dict[str, dict[str, Any]], path: str | Path | None = None) -> None:
    target = _store_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    tmp.replace(target)


def save_job(analysis: dict[str, Any], path: str | Path | None = None) -> None:
    email_id = str(analysis["email_id"])
    data = _load(path)
    data[email_id] = dict(analysis)
    _save(data, path)


def get_job(email_id: str, path: str | Path | None = None) -> dict[str, Any] | None:
    return _load(path).get(str(email_id))


def delete_job(email_id: str, path: str | Path | None = None) -> bool:
    data = _load(path)
    key = str(email_id)
    if key not in data:
        return False
    del data[key]
    _save(data, path)
    return True
