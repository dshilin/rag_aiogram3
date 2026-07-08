import pytest

import requests

from src.llm.yandex_gpt import YandexGPTClient
from src.core.config import settings


class DummyResponse:
    def __init__(self, ok=True, status_code=200, text="", json_data=None):
        self.ok = ok
        self.status_code = status_code
        self.text = text
        self._json = json_data or {}

    def json(self):
        return self._json


def test_build_model_uri_variants(monkeypatch):
    # Проверяем, что мы можем вычислить URI из folder id
    monkeypatch.setattr(settings, "yandex_folder_id", "folder123")

    client = YandexGPTClient()
    assert client._build_model_uri() == "gpt://folder123/yandexgpt/latest"

    client2 = YandexGPTClient(model="yandexgpt-lite")
    assert client2._build_model_uri() == "gpt://folder123/yandexgpt-lite/latest"

    # если модель уже полный URI, он должен быть использован без изменений
    raw = "gpt://folder123/special-model/v1"
    client3 = YandexGPTClient(model=raw)
    assert client3._build_model_uri() == raw


def test_build_model_uri_fails_without_folder(monkeypatch):
    monkeypatch.setattr(settings, "yandex_folder_id", "")
    client = YandexGPTClient()
    with pytest.raises(ValueError):
        client._build_model_uri()


def test_ask_sends_correct_payload(monkeypatch):
    monkeypatch.setattr(settings, "yandex_folder_id", "folder123")
    # API-ключ сервисного аккаунта (AQVN...) → заголовок Api-Key, без обмена на IAM
    monkeypatch.setattr(settings, "yandex_api_key", "AQVN-test-key")

    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured['url'] = url
        captured['headers'] = headers
        captured['json'] = json
        return DummyResponse(
            ok=True,
            status_code=200,
            json_data={"result": {"alternatives": [{"message": {"text": "ok"}}]}}
        )

    monkeypatch.setattr(requests, "post", fake_post)

    client = YandexGPTClient(model="yandexgpt-lite")
    result = client.ask("hello")

    assert result == "ok"
    assert captured['json']['modelUri'] == "gpt://folder123/yandexgpt-lite/latest"
    assert captured['headers']['Authorization'] == "Api-Key AQVN-test-key"

    # проверяем, что явный URI сохраняется
    client2 = YandexGPTClient(model="gpt://folder123/custom/v2")
    result2 = client2.ask("hi")
    assert captured['json']['modelUri'] == "gpt://folder123/custom/v2"


def test_oauth_token_exchanged_for_iam(monkeypatch):
    monkeypatch.setattr(settings, "yandex_folder_id", "folder123")
    # OAuth-токен (y0_...) → сначала обмен на IAM-токен, затем Bearer
    monkeypatch.setattr(settings, "yandex_api_key", "y0_oauth_token")

    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(url)
        if "iam.api.cloud.yandex.net" in url:
            assert json == {"yandexPassportOauthToken": "y0_oauth_token"}
            return DummyResponse(ok=True, json_data={"iamToken": "t1.iam-token"})
        assert headers['Authorization'] == "Bearer t1.iam-token"
        return DummyResponse(
            ok=True,
            json_data={"result": {"alternatives": [{"message": {"text": "ok"}}]}}
        )

    monkeypatch.setattr(requests, "post", fake_post)

    client = YandexGPTClient()
    assert client.ask("hello") == "ok"
    assert calls[0].startswith("https://iam.api.cloud.yandex.net")

    # второй запрос использует кэшированный IAM-токен — обмена больше нет
    assert client.ask("again") == "ok"
    assert sum("iam.api.cloud.yandex.net" in c for c in calls) == 1


def test_ready_iam_token_used_directly(monkeypatch):
    monkeypatch.setattr(settings, "yandex_folder_id", "folder123")
    # Готовый IAM-токен (t1....) → Bearer как есть, без обмена
    monkeypatch.setattr(settings, "yandex_api_key", "t1.ready-token")

    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(url)
        assert headers['Authorization'] == "Bearer t1.ready-token"
        return DummyResponse(
            ok=True,
            json_data={"result": {"alternatives": [{"message": {"text": "ok"}}]}}
        )

    monkeypatch.setattr(requests, "post", fake_post)

    client = YandexGPTClient()
    assert client.ask("hello") == "ok"
    assert len(calls) == 1


def test_ask_reports_unconfigured(monkeypatch):
    # если folder id или api key отсутствуют, получаем предупреждение
    monkeypatch.setattr(settings, "yandex_folder_id", None)
    monkeypatch.setattr(settings, "yandex_api_key", None)
    client = YandexGPTClient()
    reply = client.ask("foo")
    assert "не настроен" in reply
