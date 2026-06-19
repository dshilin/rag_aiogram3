from typing import Optional
from datetime import datetime


class SessionManager:
    def __init__(self, max_messages: int = 10):
        self._sessions: dict[int, list[dict]] = {}
        self._max_messages = max_messages

    def _get(self, user_id: int) -> list[dict]:
        if user_id not in self._sessions:
            self._sessions[user_id] = []
        return self._sessions[user_id]

    def add_message(self, user_id: int, role: str, content: str) -> None:
        msgs = self._get(user_id)
        msgs.append({"role": role, "content": content, "timestamp": datetime.now().isoformat()})
        if len(msgs) > self._max_messages:
            msgs[:] = msgs[-self._max_messages:]

    def get_history(self, user_id: int, limit: Optional[int] = None) -> list[dict]:
        msgs = self._get(user_id)
        if limit and limit > 0:
            return msgs[-limit:]
        return msgs[:]

    def start_new_session(self, user_id: int) -> None:
        self._sessions[user_id] = []

    def end_session(self, user_id: int) -> bool:
        return self._sessions.pop(user_id, None) is not None


session_manager = SessionManager(max_messages=10)
