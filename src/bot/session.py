from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime
import asyncio


@dataclass
class Session:
    """Представляет одну сессию общения с пользователем"""
    user_id: int
    messages: list[dict] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def add_message(self, role: str, content: str) -> None:
        """Добавить сообщение в историю сессии"""
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        self.updated_at = datetime.now()
    
    def get_history(self, limit: Optional[int] = None) -> list[dict]:
        """Получить историю сообщений (последние N сообщений)"""
        if limit is None or limit <= 0:
            return self.messages.copy()
        return self.messages[-limit:].copy()
    
    def clear(self) -> None:
        """Очистить историю сессии"""
        self.messages.clear()
        self.updated_at = datetime.now()


class SessionManager:
    """Менеджер сессий для хранения истории сообщений пользователей"""
    
    def __init__(self, max_messages: int = 10, session_ttl: int = 3600):
        """
        Инициализация менеджера сессий
        
        Args:
            max_messages: Максимальное количество сообщений в истории сессии
            session_ttl: Время жизни сессии в секундах (0 = без ограничений)
        """
        self._sessions: dict[int, Session] = {}
        self._max_messages = max_messages
        self._session_ttl = session_ttl
    
    def get_session(self, user_id: int) -> Session:
        """
        Получить сессию пользователя
        
        Если сессии нет — создаёт новую
        """
        if user_id not in self._sessions:
            self._sessions[user_id] = Session(user_id=user_id)
        
        return self._sessions[user_id]
    
    def add_message(self, user_id: int, role: str, content: str) -> None:
        """Добавить сообщение в сессию пользователя"""
        session = self.get_session(user_id)
        session.add_message(role, content)
        
        # Ограничиваем количество сообщений
        if len(session.messages) > self._max_messages:
            session.messages = session.messages[-self._max_messages:]
    
    def get_history(self, user_id: int, limit: Optional[int] = None) -> list[dict]:
        """Получить историю сообщений пользователя"""
        session = self.get_session(user_id)
        return session.get_history(limit)
    
    def start_new_session(self, user_id: int) -> Session:
        """Начать новую сессию (очистить старую)"""
        self._sessions[user_id] = Session(user_id=user_id)
        return self._sessions[user_id]
    
    def end_session(self, user_id: int) -> bool:
        """
        Завершить сессию пользователя
        
        Returns:
            True если сессия была завершена, False если сессии не существовало
        """
        if user_id in self._sessions:
            del self._sessions[user_id]
            return True
        return False
    
    def has_session(self, user_id: int) -> bool:
        """Проверить, существует ли сессия у пользователя"""
        return user_id in self._sessions
    
    async def cleanup_expired(self) -> int:
        """
        Очистить просроченные сессии
        
        Returns:
            Количество удалённых сессий
        """
        if self._session_ttl <= 0:
            return 0
        
        now = datetime.now()
        expired = [
            user_id for user_id, session in self._sessions.items()
            if (now - session.updated_at).total_seconds() > self._session_ttl
        ]
        
        for user_id in expired:
            del self._sessions[user_id]
        
        return len(expired)
    
    async def start_cleanup_task(self, interval: int = 300) -> asyncio.Task:
        """
        Запустить фоновую задачу для очистки просроченных сессий
        
        Args:
            interval: Интервал очистки в секундах
        
        Returns:
            asyncio.Task для возможной отмены
        """
        async def cleanup_loop():
            while True:
                await asyncio.sleep(interval)
                await self.cleanup_expired()
        
        return asyncio.create_task(cleanup_loop())
    
    def get_stats(self) -> dict:
        """Получить статистику по сессиям"""
        now = datetime.now()
        active_count = 0
        if self._session_ttl > 0:
            active_count = sum(
                1 for s in self._sessions.values()
                if (now - s.updated_at).total_seconds() < self._session_ttl
            )
        else:
            active_count = len(self._sessions)
        
        return {
            "total_sessions": len(self._sessions),
            "active_sessions": active_count,
            "max_messages_per_session": self._max_messages,
            "session_ttl_seconds": self._session_ttl
        }


# Глобальный экземпляр менеджера сессий
session_manager = SessionManager(max_messages=10, session_ttl=0)
