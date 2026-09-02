"""
Local-only OAuth2 helper — generates a Gmail token file for development.

Usage:
    python -m gmail_agent.oauth_local
    python -m gmail_agent.oauth_local --credentials credentials.json --token gmail_token_fh.json

NOT used on Railway. RealGmailProvider reads GMAIL_TOKEN_JSON env var in production.
"""

import argparse
import sys
from pathlib import Path


SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def run_oauth(credentials_path: str, token_path: str) -> None:
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print(
            "Missing dependency.\n"
            "Run: pip install google-auth-oauthlib",
            file=sys.stderr,
        )
        sys.exit(1)

    if not Path(credentials_path).exists():
        print(f"credentials file not found: {credentials_path}", file=sys.stderr)
        sys.exit(1)

    flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
    creds = flow.run_local_server(port=0)

    Path(token_path).write_text(creds.to_json(), encoding="utf-8")
    print(f"Token saved to {token_path}")
    print()
    print("To deploy on Railway, set this env var:")
    print(f"  GMAIL_TOKEN_JSON=$(cat {token_path})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Gmail OAuth2 token locally.")
    parser.add_argument(
        "--credentials",
        default="credentials.json",
        help="Path to OAuth2 credentials JSON file (default: credentials.json)",
    )
    parser.add_argument(
        "--token",
        default="gmail_token.json",
        help="Path to save the generated token JSON file (default: gmail_token.json)",
    )
    args = parser.parse_args()
    run_oauth(args.credentials, args.token)


if __name__ == "__main__":
    main()
