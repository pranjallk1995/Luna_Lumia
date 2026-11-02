import os
import unittest
from unittest.mock import patch

from config import SSOConfig, UIConfig
from sso import LunaSingleSignOn

ENV = {
    "LUNA_SSO_URL": "https://auth.example.com",
    "LUNALUMIA_API_TOKEN": "x" * 32,
    "LUNALUMIA_ALLOWED_EMAILS": " Owner@Example.com ",
}


class AuthenticationTests(unittest.TestCase):
    def test_verified_allowlisted_email_is_required(self):
        auth = LunaSingleSignOn(frozenset({"owner@example.com"}), SSOConfig(public_url="https://auth.example.com"))
        self.assertTrue(auth.is_allowed({"email": "Owner@Example.com", "email_verified": True}))
        self.assertFalse(auth.is_allowed({"email": "owner@example.com", "email_verified": False}))
        self.assertFalse(auth.is_allowed({"email": "other@example.com", "email_verified": True}))

    def test_allowed_emails_are_normalized(self):
        with patch.dict(os.environ, ENV, clear=True):
            self.assertEqual(UIConfig.from_env().allowed_emails, frozenset({"owner@example.com"}))

    def test_settings_are_required(self):
        for name in ENV:
            env = {key: value for key, value in ENV.items() if key != name}
            with patch.dict(os.environ, env, clear=True), self.assertRaisesRegex(RuntimeError, name):
                UIConfig.from_env()

    def test_short_api_token_is_refused(self):
        with patch.dict(os.environ, {**ENV, "LUNALUMIA_API_TOKEN": "short"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "at least 32"):
                UIConfig.from_env()


if __name__ == "__main__":
    unittest.main()
