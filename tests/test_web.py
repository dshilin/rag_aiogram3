import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, Mock
from src.web.router import router
from src.bot.classifier import QueryCategory
from fastapi import FastAPI

app = FastAPI()
app.include_router(router)


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_chat_greeting(client):
    """POST /api/chat with greeting returns greeting category"""
    with patch("src.web.router.classify_query", return_value=QueryCategory.GREETING):
        response = await client.post("/api/chat", json={
            "message": "Привет",
            "session_id": "test-session-1"
        })
        assert response.status_code == 200
        data = response.json()
        assert "reply" in data
        assert data["category"] == "greeting"
