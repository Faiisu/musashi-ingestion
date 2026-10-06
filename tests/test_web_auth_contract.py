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

    def test_login_network_failure_offers_retry_without_persisting_password(self):
        self.assertIn('error.retryableLoginFailure = path === "/api/auth/login"', self.app)
        self.assertIn('const retryable=failure.retryableLoginFailure===true', self.app)
        self.assertIn('if (retryable) $("#password-input").value=password', self.app)
        self.assertIn('submit.childNodes[0].textContent=retryable?t("Retry sign in")+" ":t("Sign in")+" "', self.app)
        self.assertIn('$(retryable?"#password-input":"#username-input").focus()', self.app)
        self.assertIn('if (path === "/api/auth/login") throw new Error(t("Invalid username or password."))', self.app)

    def test_login_form_is_labeled_and_uses_password_manager_autofill(self):
        self.assertIn('for="username-input">Username</label>', self.html)
        self.assertIn('autocomplete="username"', self.html)
        self.assertIn('for="password-input">Password</label>', self.html)
        self.assertIn('autocomplete="current-password"', self.html)
        self.assertIn('id="login-error" class="field-error" role="alert"', self.html)
        self.assertIn('data-language-select aria-label="Language"', self.html)
        self.assertIn('<option value="en" lang="en">English</option>', self.html)
        self.assertIn('<option value="th" lang="th">ไทย</option>', self.html)


if __name__ == "__main__":
    unittest.main()
