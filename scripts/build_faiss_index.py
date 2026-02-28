"""
Скрипт для создания и обновления FAISS индекса чанков

Использует sentence-transformers для генерации эмбеддингов
и FAISS для векторного поиска.

Использование:
    python scripts/build_faiss_index.py [--chunks-dir CHUNKS_DIR] [--output-dir OUTPUT_DIR]

Аргументы:
    --chunks-dir      Директория с чанками (по умолчанию: data/documents/chunks_paragraphs)
    --output-dir      Директория для сохранения индекса (по умолчанию: data/embeddings)
    --model-name      Модель для эмбеддингов (по умолчанию: sentence-transformers/rubert-base-cased)
    --batch-size      Размер батча для генерации эмбеддингов (по умолчанию: 32)
"""

import argparse
import hashlib
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import faiss
import numpy as np
from loguru import logger
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()


@dataclass
class IndexMetadata:
    """Метаданные FAISS индекса"""
    model_name: str
    embedding_dim: int
    total_chunks: int
    created_at: str
    chunks_by_source: dict
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


def setup_logging():
    """Настроить логирование"""
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO",
    )


def load_chunks(chunks_dir: Path) -> list[dict]:
    """
    Загрузить все чанки из директории
    
    Args:
        chunks_dir: Директория с чанками
        
    Returns:
        Список чанков с метаданными
    """
    all_chunks = []
    
    if not chunks_dir.exists():
        logger.error(f"Директория не найдена: {chunks_dir}")
        return all_chunks
    
    # Ищем все директории с чанками
    doc_dirs = [d for d in chunks_dir.iterdir() if d.is_dir()]
    
    if not doc_dirs:
        logger.warning(f"Директории с чанками не найдены в {chunks_dir}")
        return all_chunks
    
    logger.info(f"Найдено документов: {len(doc_dirs)}")
    
    for doc_dir in doc_dirs:
        logger.info(f"Загрузка чанков из {doc_dir.name}...")
        
        # Читаем индекс документа
        index_file = doc_dir / "index.json"
        if not index_file.exists():
            logger.warning(f"  ⚠ {doc_dir.name}: нет index.json, пропускаем")
            continue
        
        try:
            doc_index = json.loads(index_file.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"  ✗ {doc_dir.name}: ошибка чтения index.json: {e}")
            continue
        
        # Загружаем каждый чанк
        chunk_count = 0
        for chunk_info in doc_index.get("paragraphs", []):
            chunk_id = chunk_info.get("chunk_id")
            if not chunk_id:
                continue
            
            chunk_file = doc_dir / f"{chunk_id}.json"
            if not chunk_file.exists():
                continue
            
            try:
                chunk_data = json.loads(chunk_file.read_text(encoding="utf-8"))
                all_chunks.append(chunk_data)
                chunk_count += 1
            except Exception as e:
                logger.debug(f"    Ошибка чтения {chunk_file.name}: {e}")
                continue
        
        logger.success(f"  ✓ {doc_dir.name}: {chunk_count} чанков")
    
    logger.info(f"Всего загружено чанков: {all_chunks}")
    return all_chunks


def generate_embeddings(
    chunks: list[dict],
    model: SentenceTransformer,
    batch_size: int = 32,
) -> np.ndarray:
    """
    Сгенерировать эмбеддинги для всех чанков
    
    Args:
        chunks: Список чанков
        model: Модель sentence-transformers
        batch_size: Размер батча
        
    Returns:
        Массив эмбеддингов
    """
    texts = [chunk["content"] for chunk in chunks]
    
    logger.info(f"Генерация эмбеддингов для {len(texts)} чанков...")
    logger.info(f"  Размер батча: {batch_size}")
    logger.info(f"  Модель: {model.get_sentence_embedding_dimension()} dim")
    
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    
    logger.success(f"  ✓ Сгенерировано {len(embeddings)} эмбеддингов")
    
    return embeddings


def create_faiss_index(
    embeddings: np.ndarray,
    use_ivf: bool = False,
    nlist: int = 100,
) -> faiss.Index:
    """
    Создать FAISS индекс
    
    Args:
        embeddings: Массив эмбеддингов
        use_ivf: Использовать IVF индекс (для больших данных)
        nlist: Количество кластеров для IVF
        
    Returns:
        FAISS индекс
    """
    dimension = embeddings.shape[1]
    num_vectors = len(embeddings)
    
    logger.info(f"Создание FAISS индекса...")
    logger.info(f"  Размерность: {dimension}")
    logger.info(f"  Количество векторов: {num_vectors}")
    
    # Выбираем тип индекса в зависимости от размера данных
    if use_ivf or num_vectors > 10000:
        # IVF индекс для больших данных
        logger.info(f"  Используем IVF индекс с {nlist} кластерами")
        quantizer = faiss.IndexFlatIP(dimension)  # Inner product для нормализованных векторов
        index = faiss.IndexIVFFlat(quantizer, dimension, nlist, faiss.METRIC_INNER_PRODUCT)
        
        # Обучаем индекс
        logger.info("  Обучение индекса...")
        index.train(embeddings)
        index.add(embeddings)
    else:
        # Простой индекс для небольших данных
        logger.info("  Используем IndexFlatIP (точный поиск)")
        index = faiss.IndexFlatIP(dimension)
        index.add(embeddings)
    
    logger.success(f"  ✓ Индекс создан")
    
    return index


def save_index(
    index: faiss.Index,
    chunks: list[dict],
    metadata: IndexMetadata,
    output_dir: Path,
):
    """
    Сохранить индекс и метаданные
    
    Args:
        index: FAISS индекс
        chunks: Список чанков
        metadata: Метаданные индекса
        output_dir: Директория для сохранения
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Сохраняем FAISS индекс
    index_path = output_dir / "faiss.index"
    faiss.write_index(index, str(index_path))
    logger.success(f"  ✓ FAISS индекс сохранён: {index_path}")
    
    # Сохраняем метаданные чанков (для маппинга ID -> контент)
    chunks_path = output_dir / "chunks_metadata.json"
    chunks_data = {
        "chunks": chunks,
        "id_mapping": {i: chunk["metadata"]["chunk_id"] for i, chunk in enumerate(chunks)},
    }
    chunks_path.write_text(
        json.dumps(chunks_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.success(f"  ✓ Метаданные чанков сохранены: {chunks_path}")
    
    # Сохраняем метаданные индекса
    metadata_path = output_dir / "index_metadata.json"
    metadata_path.write_text(metadata.to_json(), encoding="utf-8")
    logger.success(f"  ✓ Метаданные индекса сохранены: {metadata_path}")


def build_index(
    chunks_dir: Path,
    output_dir: Path,
    model_name: str = "sentence-transformers/rubert-base-cased",
    batch_size: int = 32,
    use_ivf: bool = False,
    nlist: int = 100,
) -> Optional[IndexMetadata]:
    """
    Построить FAISS индекс из чанков
    
    Args:
        chunks_dir: Директория с чанками
        output_dir: Директория для сохранения индекса
        model_name: Модель для эмбеддингов
        batch_size: Размер батча
        use_ivf: Использовать IVF индекс
        nlist: Количество кластеров для IVF
        
    Returns:
        Метаданные индекса или None при ошибке
    """
    # Загружаем чанки
    chunks = load_chunks(chunks_dir)
    
    if not chunks:
        logger.error("Нет чанков для индексации")
        return None
    
    # Считаем статистику по источникам
    chunks_by_source = {}
    for chunk in chunks:
        source = chunk.get("metadata", {}).get("source", "unknown")
        chunks_by_source[source] = chunks_by_source.get(source, 0) + 1
    
    # Загружаем модель
    logger.info(f"Загрузка модели: {model_name}")
    try:
        # Получаем токен HuggingFace из переменных окружения
        hf_token = os.getenv("HF_TOKEN")
        
        if hf_token:
            logger.info("Используем HF_TOKEN для аутентификации в HuggingFace")
            model = SentenceTransformer(model_name, token=hf_token)
        else:
            logger.warning("HF_TOKEN не найден. Попытка загрузки без аутентификации...")
            model = SentenceTransformer(model_name)
    except Exception as e:
        logger.error(f"Ошибка загрузки модели: {e}")
        logger.error("Убедитесь, что HF_TOKEN установлен в .env файле")
        return None
    
    # Генерируем эмбеддинги
    embeddings = generate_embeddings(chunks, model, batch_size)
    
    # Создаём FAISS индекс
    index = create_faiss_index(embeddings, use_ivf, nlist)
    
    # Создаём метаданные
    metadata = IndexMetadata(
        model_name=model_name,
        embedding_dim=embeddings.shape[1],
        total_chunks=len(chunks),
        created_at=datetime.now().isoformat(),
        chunks_by_source=chunks_by_source,
    )
    
    # Сохраняем
    save_index(index, chunks, metadata, output_dir)
    
    logger.info("=" * 60)
    logger.info(f"Индекс построен успешно!")
    logger.info(f"  Модель: {model_name}")
    logger.info(f"  Размерность: {embeddings.shape[1]}")
    logger.info(f"  Чанков: {len(chunks)}")
    logger.info(f"  Директория: {output_dir}")
    logger.info("=" * 60)
    
    return metadata


def search_index(
    query: str,
    index_dir: Path,
    top_k: int = 5,
) -> list[dict]:
    """
    Поиск по индексу
    
    Args:
        query: Поисковый запрос
        index_dir: Директория с индексом
        top_k: Количество результатов
        
    Returns:
        Список результатов поиска
    """
    # Загружаем индекс
    index_path = index_dir / "faiss.index"
    if not index_path.exists():
        logger.error(f"Индекс не найден: {index_path}")
        return []
    
    index = faiss.read_index(str(index_path))
    
    # Загружаем метаданные
    chunks_path = index_dir / "chunks_metadata.json"
    if not chunks_path.exists():
        logger.error(f"Метаданные не найдены: {chunks_path}")
        return []
    
    chunks_data = json.loads(chunks_path.read_text(encoding="utf-8"))
    chunks = chunks_data["chunks"]
    
    # Загружаем модель
    metadata_path = index_dir / "index_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    model_name = metadata["model_name"]
    
    logger.info(f"Загрузка модели: {model_name}")
    
    # Получаем токен HuggingFace из переменных окружения
    hf_token = os.getenv("HF_TOKEN")
    
    try:
        if hf_token:
            model = SentenceTransformer(model_name, token=hf_token)
        else:
            model = SentenceTransformer(model_name)
    except Exception as e:
        logger.error(f"Ошибка загрузки модели: {e}")
        return []
    
    # Генерируем эмбеддинг запроса
    logger.info(f"Поиск: {query}")
    query_embedding = model.encode(
        [query],
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    
    # Ищем
    scores, indices = index.search(query_embedding, top_k)
    
    # Формируем результаты
    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0 or idx >= len(chunks):
            continue
        
        chunk = chunks[idx]
        results.append({
            "content": chunk["content"],
            "metadata": chunk["metadata"],
            "score": float(score),
        })
    
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Создание FAISS индекса для чанков",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--chunks-dir",
        type=Path,
        default=Path("data/documents/chunks_paragraphs"),
        help="Директория с чанками (по умолчанию: data/documents/chunks_paragraphs)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/embeddings"),
        help="Директория для сохранения индекса (по умолчанию: data/embeddings)",
    )
    parser.add_argument(
        "--model-name",
        type=str,
        default="sentence-transformers/rubert-base-cased",
        help="Модель для эмбеддингов (по умолчанию: sentence-transformers/rubert-base-cased)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Размер батча (по умолчанию: 32)",
    )
    parser.add_argument(
        "--use-ivf",
        action="store_true",
        help="Использовать IVF индекс (для больших данных)",
    )
    parser.add_argument(
        "--nlist",
        type=int,
        default=100,
        help="Количество кластеров для IVF (по умолчанию: 100)",
    )
    parser.add_argument(
        "--search",
        type=str,
        help="Тестовый поиск по индексу",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Количество результатов поиска (по умолчанию: 5)",
    )
    
    args = parser.parse_args()
    
    setup_logging()
    
    # Проверяем наличие HF_TOKEN
    hf_token = os.getenv("HF_TOKEN")
    if hf_token:
        logger.info("HF_TOKEN найден в окружении")
    else:
        logger.warning("HF_TOKEN не найден в окружении")
    
    logger.info("=" * 60)
    logger.info("FAISS Index Builder")
    logger.info("=" * 60)
    logger.info(f"Директория с чанками: {args.chunks_dir}")
    logger.info(f"Директория индекса: {args.output_dir}")
    logger.info(f"Модель: {args.model_name}")
    logger.info(f"Размер батча: {args.batch_size}")
    logger.info(f"IVF: {args.use_ivf}")
    logger.info("=" * 60)
    
    if args.search:
        # Режим поиска
        results = search_index(args.search, args.output_dir, args.top_k)
        
        if results:
            logger.info(f"Найдено результатов: {len(results)}")
            logger.info("=" * 60)
            
            for i, result in enumerate(results, 1):
                logger.info(f"#{i} (score: {result['score']:.4f})")
                logger.info(f"  Источник: {result['metadata'].get('source')}")
                logger.info(f"  Страница: {result['metadata'].get('page')}")
                logger.info(f"  Текст: {result['content'][:200]}...")
                logger.info("-" * 60)
        else:
            logger.warning("Ничего не найдено")
    else:
        # Режим построения индекса
        metadata = build_index(
            args.chunks_dir,
            args.output_dir,
            args.model_name,
            args.batch_size,
            args.use_ivf,
            args.nlist,
        )
        
        return 0 if metadata else 1


if __name__ == "__main__":
    sys.exit(main())
