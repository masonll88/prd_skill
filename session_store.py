"""Session storage abstractions and in-memory implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from schemas import SessionState


class SessionStore(ABC):
    """Abstract session storage interface."""

    @abstractmethod
    def create_session(self, session: SessionState) -> SessionState:
        """Persist a newly created session."""

    @abstractmethod
    def get_session(self, session_id: str) -> Optional[SessionState]:
        """Retrieve a session by id."""

    @abstractmethod
    def save_session(self, session: SessionState) -> SessionState:
        """Persist updates to an existing session."""


class InMemorySessionStore(SessionStore):
    """In-memory session storage implementation."""

    def __init__(self) -> None:
        self._sessions: dict[str, SessionState] = {}

    def create_session(self, session: SessionState) -> SessionState:
        self._sessions[session.session_id] = session.model_copy(deep=True)
        return session

    def get_session(self, session_id: str) -> Optional[SessionState]:
        session = self._sessions.get(session_id)
        return session.model_copy(deep=True) if session is not None else None

    def save_session(self, session: SessionState) -> SessionState:
        self._sessions[session.session_id] = session.model_copy(deep=True)
        return session
