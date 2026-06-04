"""Deduplication — tracks processed email IDs in a local JSON file."""

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_PATH = Path(__file__).parent / "processed_emails.json"


class EmailDedup:
    def __init__(self, storage_path: str | Path = _DEFAULT_PATH):
        self._path = Path(storage_path)
        self._processed: set[str] = self._load()

    def _load(self) -> set[str]:
        if self._path.exists():
            try:
                content = self._path.read_text(encoding="utf-8").strip()
                if not content:
                    return set()
                data = json.loads(content)
                return set(data.get("processed", []))
            except Exception:
                logger.exception("Failed to load dedup store from %s", self._path)
        return set()

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump({"processed": list(self._processed)}, f, indent=2)
        except Exception:
            logger.exception("Failed to save dedup store to %s", self._path)

    def is_processed(self, email_id: str) -> bool:
        return email_id in self._processed

    def mark_processed(self, email_id: str) -> None:
        self._processed.add(email_id)
        self._save()

    def mark_many(self, email_ids: list[str]) -> None:
        self._processed.update(email_ids)
        self._save()

    def count(self) -> int:
        return len(self._processed)

    def clear(self) -> None:
        """For tests only — reset state."""
        self._processed = set()
        if self._path.exists():
            self._path.unlink()
