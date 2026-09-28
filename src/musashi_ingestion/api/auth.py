"""In-memory browser sessions for the local operator account."""

from __future__ import annotations

from dataclasses import dataclass
import hmac
import secrets
import threading
import time


IDLE_SECONDS = 8 * 60 * 60
ABSOLUTE_SECONDS = 24 * 60 * 60
COOKIE_NAME = "musashi_session"


@dataclass
class Session:
    session_id: str
    csrf_token: str
    created_at: float
    last_seen_at: float


class SessionStore:
    """Validate credentials and keep opaque, restart-volatile sessions."""

    def __init__(self, username: str, password: str, *, clock=time.monotonic):
        if not username or not password:
            raise ValueError("OPERATOR_USERNAME and OPERATOR_PASSWORD must be nonempty")
        self.username = username.encode("utf-8")
        self.password = password.encode("utf-8")
        self.clock = clock
        self.sessions: dict[str, Session] = {}
        self.lock = threading.RLock()

    def credentials_valid(self, username: object, password: object) -> bool:
        if not isinstance(username, str) or not isinstance(password, str):
            return False
        user_ok = hmac.compare_digest(username.encode("utf-8"), self.username)
        password_ok = hmac.compare_digest(password.encode("utf-8"), self.password)
        return user_ok and password_ok

    def create(self) -> Session:
        now = self.clock()
        session = Session(secrets.token_urlsafe(32), secrets.token_urlsafe(32), now, now)
        with self.lock:
            self.sessions[session.session_id] = session
        return session

    def get(self, supplied_id: str | None, *, touch: bool = True) -> Session | None:
        if not supplied_id:
            return None
        # Compare opaque IDs in constant time, including on misses.
        with self.lock:
            matched = None
            for session_id, session in tuple(self.sessions.items()):
                if hmac.compare_digest(supplied_id.encode("utf-8"), session_id.encode("ascii")):
                    matched = session
            if matched is None:
                return None
            now = self.clock()
            if now - matched.last_seen_at >= IDLE_SECONDS or now - matched.created_at >= ABSOLUTE_SECONDS:
                self.sessions.pop(matched.session_id, None)
                return None
            if touch:
                matched.last_seen_at = now
            return matched

    def csrf_valid(self, session: Session, supplied: str | None) -> bool:
        with self.lock:
            return (self.sessions.get(session.session_id) is session and isinstance(supplied, str)
                    and hmac.compare_digest(supplied.encode("utf-8"), session.csrf_token.encode("ascii")))

    def touch(self, session: Session) -> None:
        with self.lock:
            if self.sessions.get(session.session_id) is session:
                session.last_seen_at = self.clock()

    def discard(self, session: Session) -> None:
        with self.lock:
            self.sessions.pop(session.session_id, None)
