from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Telegram Bot
    bot_token: str

    # LLM - Выбор провайдера
    llm_provider: str = "yandex"  # 'yandex', 'vsegpt', и т.д.
    llm_model: str | None = None  # Модель (если None, используется модель по умолчанию)
    llm_temperature: float = 0.7
    llm_max_tokens: int = 300

    # LLM - OpenAI
    openai_api_key: str | None = None

    # LLM - YandexGPT
    yandex_folder_id: str | None = None
    yandex_api_key: str | None = None

    # LLM - VseGPT.ru
    vsegpt_api_key: str | None = None

    # RAG Settings
    embedding_model: str = "all-MiniLM-L6-v2"
    chunk_size: int = 500
    chunk_overlap: int = 50
    top_k: int = 3

    # Vector Store
    embeddings_db_path: str = "./data/embeddings"  # Путь для хранения FAISS индекса

    # Logging
    log_level: str = "DEBUG"  # Рекомендуется: DEBUG для разработки, INFO для продакшена


settings = Settings()
