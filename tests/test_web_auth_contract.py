"""Offline checks for the browser session-login contract."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "src" / "musashi_ingestion" / "web"


class WebAuthContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = (WEB / "app.js").read_text(encoding="utf-8")
        cls.html = (WEB / "index.html").read_text(encoding="utf-8")

    def test_login_restore_logout_and_csrf_use_same_origin_session_api(self):
        self.assertIn('fetch("/api/auth/session"', self.app)
        self.assertIn('api("/api/auth/login"', self.app)
        self.assertIn('api("/api/auth/logout"', self.app)
        self.assertIn('headers.set("X-CSRF-Token", state.csrfToken)', self.app)
        self.assertIn('credentials:"same-origin"', self.app)
        self.assertNotIn("Authorization", self.app)
        self.assertNotIn("Bearer ", self.app)

    def test_auth_failures_clear_page_state_without_replaying_mutations(self):
        self.assertIn('clearSessionState({showLogin:true})', self.app)
        self.assertIn('$("#page-content").replaceChildren()', self.app)
        self.assertIn('$("#password-input").value=""', self.app)
        self.assertIn("await refreshSessionAfterForbidden()", self.app)
        self.assertIn("The action was not repeated.", self.app)
        self.assertNotIn("localStorage", self.app)
        self.assertNotIn("sessionStorage", self.app)

    def test_login_form_is_labeled_and_uses_password_manager_autofill(self):
        self.assertIn('for="username-input">Username</label>', self.html)
        self.assertIn('autocomplete="username"', self.html)
        self.assertIn('for="password-input">Password</label>', self.html)
        self.assertIn('autocomplete="current-password"', self.html)
        self.assertIn('id="login-error" class="field-error" role="alert"', self.html)
        self.assertNotRegex(self.html, r"[\u0e00-\u0e7f]")


if __name__ == "__main__":
    unittest.main()
