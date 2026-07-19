"""Safe Gmail account identity diagnostics."""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gmail_agent.gmail_provider import RealGmailProvider


class TestGmailAccountProfile(unittest.IsolatedAsyncioTestCase):
    async def test_profile_reads_identity_and_inbox_label_only(self):
        service = MagicMock()
        service.users.return_value.getProfile.return_value.execute.return_value = {
            "emailAddress": "tijgadymg@gmail.com",
            "messagesTotal": 613,
            "threadsTotal": 584,
        }
        service.users.return_value.labels.return_value.get.return_value.execute.return_value = {
            "messagesTotal": 432,
        }

        provider = RealGmailProvider("credentials.json", "gmail_token.json")
        provider._service = service

        profile = await provider.get_account_profile()

        self.assertEqual(profile["email_address"], "tijgadymg@gmail.com")
        self.assertEqual(profile["messages_total"], 613)
        self.assertEqual(profile["threads_total"], 584)
        self.assertEqual(profile["inbox_messages_count"], 432)
        self.assertEqual(profile["oauth_status"], "OK")
        service.users.return_value.getProfile.assert_called_once_with(userId="me")
        service.users.return_value.labels.return_value.get.assert_called_once_with(
            userId="me", id="INBOX"
        )
        service.users.return_value.messages.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
