"""Local-only Gmail read-only OAuth helper with mailbox identity gating."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def _client_config(credentials_path: str) -> dict:
    from_env = os.getenv("GMAIL_CREDENTIALS_JSON", "").strip()
    if from_env:
        try:
            return json.loads(from_env)
        except json.JSONDecodeError as exc:
            raise RuntimeError("GMAIL_CREDENTIALS_JSON is invalid JSON") from exc
    path = Path(credentials_path)
    if not path.exists():
        raise RuntimeError(f"credentials file not found: {credentials_path}")
    return json.loads(path.read_text(encoding="utf-8"))


def run_oauth(
    credentials_path: str,
    token_path: str,
    expected_account: str,
    *,
    open_browser: bool = True,
) -> str:
    """Authorize, verify users.getProfile, then and only then persist the token."""

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError(
            "Missing Gmail OAuth dependencies; install project requirements"
        ) from exc

    expected = (expected_account or "").strip().casefold()
    if not expected or "@" not in expected:
        raise RuntimeError("--expected-account is required and must be an email address")

    flow = InstalledAppFlow.from_client_config(_client_config(credentials_path), SCOPES)
    # Always force the account chooser. Reusing an unrelated signed-in Google
    # session must not silently create a token for the wrong mailbox.
    creds = flow.run_local_server(
        port=0,
        open_browser=open_browser,
        prompt="select_account",
    )
    service = build("gmail", "v1", credentials=creds)
    profile = service.users().getProfile(userId="me").execute()
    observed = str(profile.get("emailAddress", "")).strip().casefold()
    if observed != expected:
        raise RuntimeError(
            "Gmail OAuth mailbox mismatch; token was not written. "
            "Repeat authorization with the approved adult-owned account."
        )

    target = Path(token_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(creds.to_json(), encoding="utf-8")
    return observed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate and verify a local Gmail readonly OAuth token."
    )
    parser.add_argument("--credentials", default="credentials.json")
    parser.add_argument("--token", default="gmail_token.json")
    parser.add_argument(
        "--expected-account",
        default=os.getenv("GMAIL_EXPECTED_ACCOUNT", ""),
        help="Exact approved adult-owned mailbox (or GMAIL_EXPECTED_ACCOUNT)",
    )
    parser.add_argument(
        "--no-open-browser",
        action="store_true",
        help="Print the authorization URL without opening the system browser",
    )
    args = parser.parse_args()
    try:
        verified = run_oauth(
            args.credentials,
            args.token,
            args.expected_account,
            open_browser=not args.no_open_browser,
        )
    except Exception as exc:
        print(f"OAuth failed closed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    from .gmail_provider import mask_email_address

    print(f"OAuth identity verified: {mask_email_address(verified)}")
    print(f"Token stored locally in ignored path: {Path(args.token).resolve()}")


if __name__ == "__main__":
    main()
