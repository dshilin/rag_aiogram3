from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Telegram Bot
    bot_token: str

    # LLM
    openai_api_key: str | None = None

    # RAG Settings
    embedding_model: str = "all-MiniLM-L6-v2"
    chunk_size: int = 500
    chunk_overlap: int = 50
    top_k: int = 3

    # Vector Store
    chroma_db_path: str = "./data/embeddings"  # Путь для хранения FAISS индекса

    # Logging
    log_level: str = "INFO"


settings = Settings()
