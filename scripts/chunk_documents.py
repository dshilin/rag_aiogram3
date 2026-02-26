"""
Скрипт для разделения Markdown документов на чанки с метаданными

Сохраняет:
    - Номер страницы источника
    - Имя файла-источника
    - Позицию чанка в документе

Каждый чанк содержит метаданные для последующего поиска:
    - source: имя файла
    - page: номер страницы
    - chunk_id: уникальный идентификатор чанка
    - start_idx: позиция начала в документе

Использование:
    python scripts/chunk_documents.py [--input-dir INPUT_DIR] [--output-dir OUTPUT_DIR]

Аргументы:
    --input-dir   Директория с Markdown файлами (по умолчанию: data/documents/md_docs)
    --output-dir  Директория для чанков (по умолчанию: data/documents/chunks)
    --chunk-size  Размер чанка в символах (по умолчанию: 500)
    --overlap     Перекрытие между чанками (по умолчанию: 50)
"""

import argparse
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from loguru import logger


@dataclass
class ChunkMetadata:
    """Метаданные чанка для RAG поиска"""
    chunk_id: str
    source: str
    page: int
    chunk_index: int
    start_char: int
    end_char: int
    total_chunks: int

    def to_dict(self) -> dict:
        """Конвертировать в словарь"""
        return asdict(self)

    def to_json(self) -> str:
        """Конвертировать в JSON строку"""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict) -> "ChunkMetadata":
        """Создать из словаря"""
        return cls(**data)


@dataclass
class Chunk:
    """Чанк документа с метаданными"""
    content: str
    metadata: ChunkMetadata

    def to_dict(self) -> dict:
        """Конвертировать в словарь для сохранения"""
        return {
            "content": self.content,
            "metadata": self.metadata.to_dict(),
        }

    def to_json(self) -> str:
        """Конвертировать в JSON строку"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


def setup_logging():
    """Настроить логирование"""
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO",
    )


def generate_chunk_id(source: str, page: int, chunk_index: int, content: str) -> str:
    """
    Сгенерировать уникальный ID для чанка

    Args:
        source: имя файла-источника
        page: номер страницы
        chunk_index: индекс чанка
        content: содержимое чанка

    Returns:
        Уникальный хеш-идентификатор
    """
    unique_string = f"{source}:{page}:{chunk_index}:{content[:100]}"
    return hashlib.md5(unique_string.encode("utf-8")).hexdigest()[:16]


def extract_page_markers(content: str) -> list[tuple[int, int, str]]:
    """
    Извлечь маркеры страниц из Markdown контента

    Поддерживаемые форматы:
        - <!-- Page X -->
        - ## [Страница X](...)
        - <!-- Page X: source.pdf -->

    Args:
        content: Markdown контент

    Returns:
        Список кортежей (page_number, start_position, source_hint)
    """
    markers = []

    # Паттерн 1: <!-- Page X --> или <!-- Page X: source.pdf -->
    page_comment_pattern = re.compile(r"<!--\s*Page\s+(\d+)(?::\s*([^>]+?))?\s*-->", re.IGNORECASE)

    # Паттерн 2: ## [Страница X](...)
    page_header_pattern = re.compile(r"^##\s*\[?Страница\s+(\d+)\]?", re.IGNORECASE | re.MULTILINE)

    # Ищем комментарии
    for match in page_comment_pattern.finditer(content):
        page_num = int(match.group(1))
        source_hint = match.group(2).strip() if match.group(2) else ""
        markers.append((page_num, match.start(), source_hint))

    # Ищем заголовки
    for match in page_header_pattern.finditer(content):
        page_num = int(match.group(1))
        # Проверяем, нет ли уже маркера рядом
        existing = any(abs(pos - match.start()) < 50 for _, pos, _ in markers)
        if not existing:
            markers.append((page_num, match.start(), ""))

    # Сортируем по позиции
    markers.sort(key=lambda x: x[1])

    return markers


def split_by_sections(content: str, chunk_size: int, overlap: int) -> list[tuple[str, int, int]]:
    """
    Разделить контент на секции с учетом абзацев

    Args:
        content: Текст для разделения
        chunk_size: Размер чанка
        overlap: Перекрытие

    Returns:
        Список кортежей (chunk_text, start_pos, end_pos)
    """
    chunks = []
    start = 0
    content_len = len(content)

    while start < content_len:
        end = start + chunk_size

        # Если это последний чанк
        if end >= content_len:
            chunk_text = content[start:].strip()
            if chunk_text:
                chunks.append((chunk_text, start, content_len))
            break

        # Ищем ближайший разрыв строки или абзаца перед end
        chunk_text = content[start:end]

        # Пробуем найти разрыв абзаца (двойная newline)
        last_paragraph_break = chunk_text.rfind("\n\n")

        # Если нет разрыва абзаца, ищем одинарный newline
        if last_paragraph_break == -1:
            last_paragraph_break = chunk_text.rfind("\n")

        # Если нашли разрыв и он не слишком близко к началу
        if last_paragraph_break > chunk_size * 0.3:
            end = start + last_paragraph_break
            chunk_text = content[start:end].strip()
        else:
            chunk_text = chunk_text.strip()

        if chunk_text:
            chunks.append((chunk_text, start, end))

        # Двигаемся вперед с учетом overlap
        start = end - overlap if end > overlap else end

        # Защита от зацикливания
        if start >= content_len and len(chunks) == 0:
            chunk_text = content[:chunk_size].strip()
            if chunk_text:
                chunks.append((chunk_text, 0, min(chunk_size, content_len)))
            break

    return chunks


def chunk_markdown_document(
    content: str,
    source: str,
    chunk_size: int = 500,
    overlap: int = 50,
) -> list[Chunk]:
    """
    Разделить Markdown документ на чанки с метаданными

    Args:
        content: Markdown контент
        source: Имя файла-источника
        chunk_size: Размер чанка в символах
        overlap: Перекрытие между чанками

    Returns:
        Список Chunk объектов
    """
    chunks = []

    # Извлекаем маркеры страниц
    page_markers = extract_page_markers(content)

    if not page_markers:
        # Если нет маркеров страниц, обрабатываем как один документ
        logger.warning(f"  ⚠ {source}: не найдены маркеры страниц")
        text_chunks = split_by_sections(content, chunk_size, overlap)

        for idx, (chunk_text, start, end) in enumerate(text_chunks):
            chunk = Chunk(
                content=chunk_text,
                metadata=ChunkMetadata(
                    chunk_id=generate_chunk_id(source, 0, idx, chunk_text),
                    source=source,
                    page=0,
                    chunk_index=idx,
                    start_char=start,
                    end_char=end,
                    total_chunks=len(text_chunks),
                ),
            )
            chunks.append(chunk)

        return chunks

    # Разделяем контент по страницам
    for marker_idx, (page_num, marker_pos, _) in enumerate(page_markers):
        # Определяем конец текущей страницы
        if marker_idx + 1 < len(page_markers):
            next_page_pos = page_markers[marker_idx + 1][1]
            page_content = content[marker_pos:next_page_pos]
        else:
            page_content = content[marker_pos:]

        # Разделяем страницу на чанки
        text_chunks = split_by_sections(page_content, chunk_size, overlap)

        logger.debug(f"  Страница {page_num}: {len(text_chunks)} чанков")

        for idx, (chunk_text, start, end) in enumerate(text_chunks):
            # Пропускаем очень короткие чанки
            if len(chunk_text) < 20:
                continue

            # Вычисляем глобальный индекс чанка
            if marker_idx > 0:
                # Считаем количество чанков на предыдущих страницах
                global_chunk_index = sum(
                    len(split_by_sections(content[page_markers[i][1]:page_markers[i+1][1]], chunk_size, overlap))
                    for i in range(marker_idx)
                )
            else:
                global_chunk_index = 0

            chunk = Chunk(
                content=chunk_text,
                metadata=ChunkMetadata(
                    chunk_id=generate_chunk_id(source, page_num, idx, chunk_text),
                    source=source,
                    page=page_num,
                    chunk_index=idx,
                    start_char=start,
                    end_char=end,
                    total_chunks=len(text_chunks),
                ),
            )
            chunks.append(chunk)

    return chunks


def process_file(
    file_path: Path,
    output_dir: Path,
    chunk_size: int = 500,
    overlap: int = 50,
) -> int:
    """
    Обработать один файл и сохранить чанки

    Args:
        file_path: Путь к файлу
        output_dir: Директория для сохранения чанков
        chunk_size: Размер чанка
        overlap: Перекрытие

    Returns:
        Количество созданных чанков
    """
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as e:
        logger.error(f"Ошибка чтения {file_path.name}: {e}")
        return 0

    source = file_path.stem
    chunks = chunk_markdown_document(content, source, chunk_size, overlap)

    if not chunks:
        logger.warning(f"  ⚠ {file_path.name}: не создано чанков")
        return 0

    # Создаем директорию для чанков этого документа
    doc_chunks_dir = output_dir / source
    doc_chunks_dir.mkdir(parents=True, exist_ok=True)

    # Сохраняем каждый чанк в отдельном JSON файле
    for chunk in chunks:
        chunk_file = doc_chunks_dir / f"{chunk.metadata.chunk_id}.json"
        chunk_file.write_text(chunk.to_json(), encoding="utf-8")

    # Сохраняем индекс документа
    index_data = {
        "source": source,
        "total_chunks": len(chunks),
        "chunk_size": chunk_size,
        "overlap": overlap,
        "chunks": [
            {
                "chunk_id": chunk.metadata.chunk_id,
                "page": chunk.metadata.page,
                "chunk_index": chunk.metadata.chunk_index,
            }
            for chunk in chunks
        ],
    }

    index_file = doc_chunks_dir / "index.json"
    index_file.write_text(json.dumps(index_data, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.success(f"  ✓ {file_path.name}: {len(chunks)} чанков")

    return len(chunks)


def process_directory(
    input_dir: Path,
    output_dir: Path,
    chunk_size: int = 500,
    overlap: int = 50,
) -> dict:
    """
    Обработать все Markdown файлы в директории

    Args:
        input_dir: Директория с Markdown файлами
        output_dir: Директория для чанков
        chunk_size: Размер чанка
        overlap: Перекрытие

    Returns:
        Статистика обработки
    """
    stats = {
        "files": 0,
        "chunks": 0,
        "failed": 0,
    }

    if not input_dir.exists():
        logger.error(f"Директория не найдена: {input_dir}")
        return stats

    md_files = sorted(input_dir.glob("*.md"))

    if not md_files:
        logger.warning(f"Markdown файлы не найдены в {input_dir}")
        return stats

    stats["files"] = len(md_files)
    logger.info(f"Найдено Markdown файлов: {stats['files']}")
    logger.info("=" * 60)

    output_dir.mkdir(parents=True, exist_ok=True)

    for md_file in md_files:
        logger.info(f"Обработка: {md_file.name}")
        try:
            chunk_count = process_file(md_file, output_dir, chunk_size, overlap)
            stats["chunks"] += chunk_count
            if chunk_count == 0:
                stats["failed"] += 1
        except Exception as e:
            logger.error(f"  ✗ {md_file.name}: {e}")
            stats["failed"] += 1

    logger.info("=" * 60)
    logger.info(f"Файлов: {stats['files']} | Чанков: {stats['chunks']} | Ошибок: {stats['failed']}")

    # Сохраняем общую статистику
    stats_file = output_dir / "processing_stats.json"
    stats_file.write_text(
        json.dumps(stats, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return stats


def search_chunk_by_text(query: str, chunks_dir: Path) -> Optional[dict]:
    """
    Найти чанк по текстовому запросу (простой поиск)

    Args:
        query: Текст для поиска
        chunks_dir: Директория с чанками

    Returns:
        Метаданные найденного чанка или None
    """
    query_lower = query.lower()
    best_match = None
    best_score = 0

    for doc_dir in chunks_dir.iterdir():
        if not doc_dir.is_dir():
            continue

        for chunk_file in doc_dir.glob("*.json"):
            if chunk_file.name == "index.json":
                continue

            try:
                chunk_data = json.loads(chunk_file.read_text(encoding="utf-8"))
                content = chunk_data.get("content", "").lower()
                metadata = chunk_data.get("metadata", {})

                # Простой scoring: количество совпадений слов
                score = content.count(query_lower)

                if score > best_score:
                    best_score = score
                    best_match = {
                        "content": chunk_data.get("content", ""),
                        "metadata": metadata,
                        "score": score,
                        "file": str(chunk_file),
                    }
            except Exception as e:
                logger.debug(f"Ошибка чтения {chunk_file.name}: {e}")
                continue

    return best_match


def main():
    parser = argparse.ArgumentParser(
        description="Разделение Markdown документов на чанки",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("data/documents/md_docs"),
        help="Директория с Markdown файлами (по умолчанию: data/documents/md_docs)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/documents/chunks"),
        help="Директория для чанков (по умолчанию: data/documents/chunks)",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=500,
        help="Размер чанка в символах (по умолчанию: 500)",
    )
    parser.add_argument(
        "--overlap",
        type=int,
        default=50,
        help="Перекрытие между чанками (по умолчанию: 50)",
    )
    parser.add_argument(
        "--search",
        type=str,
        help="Тестовый поиск чанка по тексту",
    )

    args = parser.parse_args()

    setup_logging()

    logger.info("=" * 60)
    logger.info("Markdown Chunker")
    logger.info("=" * 60)
    logger.info(f"Входная директория: {args.input_dir}")
    logger.info(f"Выходная директория: {args.output_dir}")
    logger.info(f"Размер чанка: {args.chunk_size}")
    logger.info(f"Перекрытие: {args.overlap}")
    logger.info("=" * 60)

    if args.search:
        # Режим поиска
        logger.info(f"Поиск: {args.search}")
        result = search_chunk_by_text(args.search, args.output_dir)
        if result:
            logger.success(f"Найден чанк (score: {result['score']})")
            logger.info(f"Источник: {result['metadata'].get('source')}")
            logger.info(f"Страница: {result['metadata'].get('page')}")
            logger.info(f"Текст: {result['content'][:200]}...")
        else:
            logger.warning("Ничего не найдено")
    else:
        # Режим обработки
        stats = process_directory(
            args.input_dir,
            args.output_dir,
            args.chunk_size,
            args.overlap,
        )

        return 0 if stats["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
