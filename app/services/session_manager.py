"""Session management for conversation persistence."""

import logging
import uuid
from typing import Optional
from datetime import datetime, timedelta
from collections import defaultdict
from app.models import ConversationMessage

logger = logging.getLogger(__name__)


class SessionManager:
    """
    Manages conversation sessions with in-memory storage.

    For MVP: Simple in-memory dictionary storage
    For Production: Replace with Redis, PostgreSQL, or similar
    """

    def __init__(self, session_ttl_minutes: int = 60):
        """
        Initialize session manager.

        Args:
            session_ttl_minutes: Time-to-live for inactive sessions (default 60 minutes)
        """
        self._sessions: dict[str, list[ConversationMessage]] = {}
        self._session_metadata: dict[str, dict] = {}
        self._ttl_minutes = session_ttl_minutes

        logger.info(f"SessionManager initialized with TTL={session_ttl_minutes} minutes")

    def create_session(self, project_id: str) -> str:
        """
        Create a new session.

        Args:
            project_id: Project identifier

        Returns:
            New session ID (UUID)
        """
        session_id = str(uuid.uuid4())
        self._sessions[session_id] = []
        self._session_metadata[session_id] = {
            "project_id": project_id,
            "created_at": datetime.now(),
            "last_accessed": datetime.now(),
        }

        logger.info(f"Created new session {session_id} for project {project_id}")
        return session_id

    def get_or_create_session(self, session_id: Optional[str], project_id: str) -> str:
        """
        Get existing session or create new one.

        Args:
            session_id: Optional existing session ID
            project_id: Project identifier

        Returns:
            Session ID (existing or new)
        """
        if session_id and self.session_exists(session_id):
            # Validate project_id matches
            metadata = self._session_metadata.get(session_id, {})
            if metadata.get("project_id") == project_id:
                self._update_last_accessed(session_id)
                return session_id
            else:
                logger.warning(
                    f"Session {session_id} belongs to different project. Creating new session."
                )

        # Create new session
        return self.create_session(project_id)

    def session_exists(self, session_id: str) -> bool:
        """Check if session exists and is not expired."""
        if session_id not in self._sessions:
            return False

        # Check expiration
        metadata = self._session_metadata.get(session_id, {})
        last_accessed = metadata.get("last_accessed")

        if last_accessed:
            age = datetime.now() - last_accessed
            if age > timedelta(minutes=self._ttl_minutes):
                logger.info(f"Session {session_id} expired (age: {age})")
                self._cleanup_session(session_id)
                return False

        return True

    def add_message(self, session_id: str, message: ConversationMessage) -> None:
        """
        Add a message to the conversation history.

        Args:
            session_id: Session identifier
            message: ConversationMessage to add
        """
        if not self.session_exists(session_id):
            logger.warning(f"Attempted to add message to non-existent session {session_id}")
            return

        self._sessions[session_id].append(message)
        self._update_last_accessed(session_id)

        logger.debug(
            f"Added {message.role} message to session {session_id} "
            f"(total messages: {len(self._sessions[session_id])})"
        )

    def get_conversation_history(
        self,
        session_id: str,
        max_messages: Optional[int] = None
    ) -> list[ConversationMessage]:
        """
        Get conversation history for a session.

        Args:
            session_id: Session identifier
            max_messages: Maximum number of recent messages to return (None = all)

        Returns:
            List of conversation messages (chronological order)
        """
        if not self.session_exists(session_id):
            logger.warning(f"Attempted to get history for non-existent session {session_id}")
            return []

        messages = self._sessions[session_id]

        if max_messages is not None and max_messages > 0:
            messages = messages[-max_messages:]

        self._update_last_accessed(session_id)
        return messages

    def clear_session(self, session_id: str) -> bool:
        """
        Clear all messages in a session.

        Args:
            session_id: Session identifier

        Returns:
            True if session was cleared, False if session doesn't exist
        """
        if not self.session_exists(session_id):
            return False

        self._sessions[session_id] = []
        self._update_last_accessed(session_id)

        logger.info(f"Cleared session {session_id}")
        return True

    def delete_session(self, session_id: str) -> bool:
        """
        Delete a session completely.

        Args:
            session_id: Session identifier

        Returns:
            True if session was deleted, False if session doesn't exist
        """
        if session_id not in self._sessions:
            return False

        self._cleanup_session(session_id)
        logger.info(f"Deleted session {session_id}")
        return True

    def get_session_metadata(self, session_id: str) -> Optional[dict]:
        """
        Get metadata for a session.

        Args:
            session_id: Session identifier

        Returns:
            Metadata dictionary or None if session doesn't exist
        """
        if not self.session_exists(session_id):
            return None

        return self._session_metadata.get(session_id, {}).copy()

    def cleanup_expired_sessions(self) -> int:
        """
        Clean up all expired sessions.

        Returns:
            Number of sessions cleaned up
        """
        now = datetime.now()
        expired_sessions = []

        for session_id, metadata in self._session_metadata.items():
            last_accessed = metadata.get("last_accessed")
            if last_accessed:
                age = now - last_accessed
                if age > timedelta(minutes=self._ttl_minutes):
                    expired_sessions.append(session_id)

        for session_id in expired_sessions:
            self._cleanup_session(session_id)

        if expired_sessions:
            logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")

        return len(expired_sessions)

    def get_active_session_count(self) -> int:
        """Get count of active (non-expired) sessions."""
        return len(self._sessions)

    def _update_last_accessed(self, session_id: str) -> None:
        """Update last accessed timestamp for a session."""
        if session_id in self._session_metadata:
            self._session_metadata[session_id]["last_accessed"] = datetime.now()

    def _cleanup_session(self, session_id: str) -> None:
        """Remove session from storage."""
        self._sessions.pop(session_id, None)
        self._session_metadata.pop(session_id, None)


# Global singleton instance
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """
    Get the global session manager instance.

    Returns:
        SessionManager singleton
    """
    global _session_manager

    if _session_manager is None:
        _session_manager = SessionManager(session_ttl_minutes=60)

    return _session_manager
