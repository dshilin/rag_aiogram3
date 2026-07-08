from typing import Optional
from datetime import datetime

# Ключ сессии: Telegram user_id (int) или веб-сессия ("web:<uuid>")
SessionKey = int | str


class SessionManager:
    def __init__(self, max_messages: int = 10):
        self._sessions: dict[SessionKey, list[dict]] = {}
        self._max_messages = max_messages

    def _get(self, user_id: SessionKey) -> list[dict]:
        if user_id not in self._sessions:
            self._sessions[user_id] = []
        return self._sessions[user_id]

    def add_message(self, user_id: SessionKey, role: str, content: str) -> None:
        msgs = self._get(user_id)
        msgs.append({"role": role, "content": content, "timestamp": datetime.now().isoformat()})
        if len(msgs) > self._max_messages:
            msgs[:] = msgs[-self._max_messages:]

    def get_history(self, user_id: SessionKey, limit: Optional[int] = None) -> list[dict]:
        msgs = self._get(user_id)
        if limit and limit > 0:
            return msgs[-limit:]
        return msgs[:]

    def start_new_session(self, user_id: SessionKey) -> None:
        self._sessions[user_id] = []

    def end_session(self, user_id: SessionKey) -> bool:
        return self._sessions.pop(user_id, None) is not None


session_manager = SessionManager(max_messages=10)
