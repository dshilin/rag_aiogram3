"""
Утилиты для загрузки чанков в RAG систему

Загружает чанки из JSON файлов, созданных скриптом chunk_documents.py,
и добавляет их в векторное хранилище с метаданными.
"""

import json
import sys
from pathlib import Path
from typing import Optional

from loguru import logger

from src.rag.service import RAGService


def load_chunks_from_directory(chunks_dir: Path) -> tuple[list[str], list[dict]]:
    """
    Загрузить все чанки из директории

    Args:
        chunks_dir: Директория с чанками (создана chunk_documents.py)

    Returns:
        Кортеж (список текстов, список метаданных)
    """
    texts = []
    metadatas = []

    if not chunks_dir.exists():
        logger.error(f"Директория не найдена: {chunks_dir}")
        return texts, metadatas

    # Проходим по всем поддиректориям (каждый документ)
    for doc_dir in chunks_dir.iterdir():
        if not doc_dir.is_dir():
            continue

        # Пропускаем служебные файлы
        if doc_dir.name.startswith("."):
            continue

        logger.info(f"Загрузка чанков из: {doc_dir.name}")

        # Загружаем каждый чанк
        for chunk_file in doc_dir.glob("*.json"):
            if chunk_file.name == "index.json":
                continue

            try:
                chunk_data = json.loads(chunk_file.read_text(encoding="utf-8"))

                content = chunk_data.get("content", "")
                metadata = chunk_data.get("metadata", {})

                if not content:
                    logger.warning(f"  ⚠ Пустой чанк: {chunk_file.name}")
                    continue

                texts.append(content)
                metadatas.append(metadata)

            except Exception as e:
                logger.error(f"  ✗ Ошибка чтения {chunk_file.name}: {e}")
                continue

    logger.info(f"Загружено чанков: {len(texts)}")

    return texts, metadatas


def index_chunks_directory(
    chunks_dir: Path,
    rag_service: RAGService,
    clear_existing: bool = False,
    batch_size: int = 100,
) -> dict:
    """
    Загрузить чанки в RAG систему

    Args:
        chunks_dir: Директория с чанками
        rag_service: RAG сервис для добавления документов
        clear_existing: Очистить существующий индекс перед загрузкой
        batch_size: Размер пакета для добавления

    Returns:
        Статистика индексации
    """
    stats = {
        "loaded": 0,
        "failed": 0,
        "total_texts": 0,
    }

    if clear_existing:
        logger.info("Очистка существующего индекса...")
        rag_service.clear()
        logger.info("Индекс очищен")

    texts, metadatas = load_chunks_from_directory(chunks_dir)

    if not texts:
        logger.warning("Чанки для загрузки не найдены")
        return stats

    stats["total_texts"] = len(texts)

    # Добавляем документами пакетами с прогресс баром
    total_batches = (len(texts) + batch_size - 1) // batch_size
    logger.info(f"Добавление {len(texts)} чанков ({total_batches} пакетов по {batch_size})...")

    try:
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i + batch_size]
            batch_metas = metadatas[i:i + batch_size]
            
            rag_service.add_documents(batch_texts, batch_metas)
            stats["loaded"] += len(batch_texts)
            
            current_batch = (i // batch_size) + 1
            logger.info(f"  Пакет {current_batch}/{total_batches} - добавлено {stats['loaded']}/{len(texts)} чанков")

        logger.success(f"✓ Добавлено {len(texts)} чанков в векторное хранилище")
    except Exception as e:
        logger.error(f"Ошибка добавления документов: {e}")
        stats["failed"] = len(texts) - stats["loaded"]

    return stats


def search_and_format(
    query: str,
    rag_service: RAGService,
    top_k: Optional[int] = None,
) -> str:
    """
    Выполнить поиск и форматировать результат для ответа пользователю

    Args:
        query: Запрос для поиска
        rag_service: RAG сервис
        top_k: Количество результатов

    Returns:
        Форматированный ответ с источниками
    """
    results = rag_service.query_with_metadata(query, top_k=top_k)

    if not results:
        return "❌ Ничего не найдено"

    response_parts = []
    response_parts.append(f"🔍 Найдено результатов: {len(results)}\n")

    for i, result in enumerate(results, 1):
        response_parts.append(f"{'─' * 40}")
        response_parts.append(f"**Результат {i}**")
        response_parts.append(result.format_for_response())
        response_parts.append("")

    return "\n".join(response_parts)


def main():
    """CLI для индексации чанков"""
    import argparse
    import sys

    from loguru import logger

    def setup_logging():
        logger.remove()
        logger.add(
            sys.stdout,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
            level="INFO",
        )

    setup_logging()

    parser = argparse.ArgumentParser(
        description="Загрузка чанков в RAG систему",
    )
    parser.add_argument(
        "--chunks-dir",
        type=Path,
        default=Path("data/documents/chunks"),
        help="Директория с чанками (по умолчанию: data/documents/chunks)",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Очистить существующий индекс перед загрузкой",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Размер пакета для добавления (по умолчанию: 100)",
    )
    parser.add_argument(
        "--search",
        type=str,
        help="Выполнить тестовый поиск после индексации",
    )

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("RAG Chunk Indexer")
    logger.info("=" * 60)
    logger.info(f"Директория с чанками: {args.chunks_dir}")
    logger.info(f"Очистка индекса: {args.clear}")
    logger.info(f"Размер пакета: {args.batch_size}")
    logger.info("=" * 60)

    # Создаем RAG сервис
    rag_service = RAGService()

    # Индексируем чанки
    stats = index_chunks_directory(args.chunks_dir, rag_service, args.clear, args.batch_size)

    logger.info("=" * 60)
    logger.info(f"Загружено: {stats['loaded']} | Ошибок: {stats['failed']}")
    logger.info("=" * 60)

    # Тестовый поиск
    if args.search:
        logger.info(f"Тестовый поиск: {args.search}")
        result = search_and_format(args.search, rag_service, top_k=3)
        logger.info(result)

    return 0


if __name__ == "__main__":
    sys.exit(main())
