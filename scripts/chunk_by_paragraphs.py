"""
Скрипт для разделения Markdown документов на чанки по абзацам

Каждый чанк содержит один абзац с метаданными:
    - source: имя файла-источника
    - page: номер страницы, где начинается абзац
    - paragraph_index: порядковый номер абзаца в документе
    - chunk_id: уникальный идентификатор

Использование:
    python scripts/chunk_by_paragraphs.py [--input-dir INPUT_DIR] [--output-dir OUTPUT_DIR]

Аргументы:
    --input-dir   Директория с Markdown файлами (по умолчанию: data/documents/md_docs)
    --output-dir  Директория для чанков (по умолчанию: data/documents/chunks_paragraphs)
"""

import argparse
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from loguru import logger


@dataclass
class ParagraphMetadata:
    """Метаданные абзаца для RAG поиска"""
    chunk_id: str
    source: str
    page: int
    paragraph_index: int
    char_start: int
    char_end: int
    total_paragraphs: int

    def to_dict(self) -> dict:
        """Конвертировать в словарь"""
        return asdict(self)

    def to_json(self) -> str:
        """Конвертировать в JSON строку"""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict) -> "ParagraphMetadata":
        """Создать из словаря"""
        return cls(**data)


@dataclass
class ParagraphChunk:
    """Абзац документа с метаданными"""
    content: str
    metadata: ParagraphMetadata

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


def generate_chunk_id(source: str, page: int, para_index: int, content: str) -> str:
    """
    Сгенерировать уникальный ID для чанка

    Args:
        source: имя файла-источника
        page: номер страницы
        para_index: индекс абзаца
        content: содержимое абзаца

    Returns:
        Уникальный хеш-идентификатор
    """
    unique_string = f"{source}:{page}:{para_index}:{content[:100]}"
    return hashlib.md5(unique_string.encode("utf-8")).hexdigest()[:16]


def extract_paragraphs_with_pages(content: str) -> list[tuple[str, int, int, int]]:
    """
    Извлечь абзацы из Markdown контента с номерами страниц

    Поддерживаемые форматы маркеров страниц:
        - <!-- Page X -->

    Args:
        content: Markdown контент

    Returns:
        Список кортежей (paragraph_text, page_number, char_start, char_end)
    """
    paragraphs = []
    
    # Паттерн для маркеров страниц
    page_marker_pattern = re.compile(r"<!--\s*Page\s+(\d+)\s*-->", re.IGNORECASE)
    
    # Находим все маркеры страниц с их позициями
    page_markers = []
    for match in page_marker_pattern.finditer(content):
        page_num = int(match.group(1))
        page_markers.append((match.start(), match.end(), page_num))
    
    # Сортируем маркеры по позиции
    page_markers.sort(key=lambda x: x[0])
    
    # Функция для определения страницы по позиции
    def get_page_at_position(pos: int) -> int:
        """Определить номер страницы для данной позиции"""
        current_page = 1
        for marker_start, marker_end, page_num in page_markers:
            if pos >= marker_end:
                current_page = page_num
            elif pos >= marker_start:
                break
        return current_page
    
    # Разделяем контент на абзацы по двойным новым строкам
    # Но сначала удалим маркеры страниц из текста
    clean_content = page_marker_pattern.sub("", content)
    
    # Разделяем на абзацы
    raw_paragraphs = re.split(r'\n\s*\n', clean_content)
    
    # Обрабатываем каждый абзац
    current_pos = 0
    para_index = 0
    
    # Буфер для заголовков - накапливаем последовательные заголовки
    header_buffer = []
    header_start_pos = None
    
    for para in raw_paragraphs:
        para = para.strip()
        
        # Пропускаем пустые абзацы
        if not para:
            current_pos += len(para) + 2  # +2 для \n\n
            continue
        
        # Проверяем, является ли абзац заголовком
        is_header = para.startswith('#')
        
        if is_header:
            # Сохраняем заголовок в буфер
            if header_start_pos is None:
                header_start_pos = current_pos
            header_buffer.append(para)
            current_pos += len(para) + 2
            continue
        
        # Если это не заголовок, сначала обрабатываем накопленные заголовки
        if header_buffer:
            # Объединяем все заголовки в один
            combined_header = ' '.join(header_buffer)
            # Удаляем Markdown синтаксис заголовков (####)
            clean_header = re.sub(r'^#+\s*', '', combined_header)
            
            # Добавляем объединённый заголовок как абзац, если он достаточно длинный
            if len(clean_header) >= 20:
                char_start = header_start_pos
                char_end = header_start_pos + len(clean_header)
                page_num = get_page_at_position(char_start)
                paragraphs.append((clean_header, page_num, char_start, char_end))
            
            # Очищаем буфер заголовков
            header_buffer = []
            header_start_pos = None
        
        # Пропускаем очень короткие абзацы (< 20 символов)
        if len(para) < 20:
            current_pos += len(para) + 2
            continue
        
        # Находим позицию начала абзаца в оригинальном контенте
        char_start = current_pos
        char_end = current_pos + len(para)
        
        # Определяем страницу
        page_num = get_page_at_position(char_start)
        
        paragraphs.append((para, page_num, char_start, char_end))
        
        current_pos += len(para) + 2
        para_index += 1
    
    # Обрабатываем оставшиеся заголовки в конце документа
    if header_buffer:
        combined_header = ' '.join(header_buffer)
        clean_header = re.sub(r'^#+\s*', '', combined_header)
        
        if len(clean_header) >= 20:
            char_start = header_start_pos
            char_end = header_start_pos + len(clean_header)
            page_num = get_page_at_position(char_start)
            paragraphs.append((clean_header, page_num, char_start, char_end))
    
    return paragraphs


def chunk_markdown_by_paragraphs(content: str, source: str) -> list[ParagraphChunk]:
    """
    Разделить Markdown документ на абзацы с метаданными

    Args:
        content: Markdown контент
        source: Имя файла-источника

    Returns:
        Список ParagraphChunk объектов
    """
    chunks = []
    
    # Извлекаем абзацы с номерами страниц
    paragraphs = extract_paragraphs_with_pages(content)
    
    if not paragraphs:
        logger.warning(f"  ⚠ {source}: не найдено абзацев")
        return chunks
    
    for idx, (para_text, page_num, char_start, char_end) in enumerate(paragraphs):
        # Пропускаем очень короткие абзацы
        if len(para_text) < 10:
            continue
        
        chunk = ParagraphChunk(
            content=para_text,
            metadata=ParagraphMetadata(
                chunk_id=generate_chunk_id(source, page_num, idx, para_text),
                source=source,
                page=page_num,
                paragraph_index=idx,
                char_start=char_start,
                char_end=char_end,
                total_paragraphs=len(paragraphs),
            ),
        )
        chunks.append(chunk)
    
    return chunks


def process_file(file_path: Path, output_dir: Path) -> int:
    """
    Обработать один файл и сохранить чанки

    Args:
        file_path: Путь к файлу
        output_dir: Директория для сохранения чанков

    Returns:
        Количество созданных чанков
    """
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as e:
        logger.error(f"Ошибка чтения {file_path.name}: {e}")
        return 0
    
    source = file_path.stem
    chunks = chunk_markdown_by_paragraphs(content, source)
    
    if not chunks:
        logger.warning(f"  ⚠ {file_path.name}: не создано чанков")
        return 0
    
    # Создаем директорию для чанков этого документа
    doc_chunks_dir = output_dir / source
    doc_chunks_dir.mkdir(parents=True, exist_ok=True)
    
    # Сохраняем каждый абзац в отдельном JSON файле
    for chunk in chunks:
        chunk_file = doc_chunks_dir / f"{chunk.metadata.chunk_id}.json"
        chunk_file.write_text(chunk.to_json(), encoding="utf-8")
    
    # Сохраняем индекс документа
    index_data = {
        "source": source,
        "total_paragraphs": len(chunks),
        "paragraphs": [
            {
                "chunk_id": chunk.metadata.chunk_id,
                "page": chunk.metadata.page,
                "paragraph_index": chunk.metadata.paragraph_index,
                "char_start": chunk.metadata.char_start,
                "char_end": chunk.metadata.char_end,
            }
            for chunk in chunks
        ],
    }
    
    index_file = doc_chunks_dir / "index.json"
    index_file.write_text(
        json.dumps(index_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    
    logger.success(f"  ✓ {file_path.name}: {len(chunks)} абзацев")
    
    return len(chunks)


def process_directory(input_dir: Path, output_dir: Path) -> dict:
    """
    Обработать все Markdown файлы в директории

    Args:
        input_dir: Директория с Markdown файлами
        output_dir: Директория для чанков

    Returns:
        Статистика обработки
    """
    stats = {
        "files": 0,
        "paragraphs": 0,
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
            para_count = process_file(md_file, output_dir)
            stats["paragraphs"] += para_count
            if para_count == 0:
                stats["failed"] += 1
        except Exception as e:
            logger.error(f"  ✗ {md_file.name}: {e}")
            stats["failed"] += 1
    
    logger.info("=" * 60)
    logger.info(f"Файлов: {stats['files']} | Абзацев: {stats['paragraphs']} | Ошибок: {stats['failed']}")
    
    # Сохраняем общую статистику
    stats_file = output_dir / "processing_stats.json"
    stats_file.write_text(
        json.dumps(stats, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    
    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Разделение Markdown документов на абзацы",
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
        default=Path("data/documents/chunks_paragraphs"),
        help="Директория для чанков (по умолчанию: data/documents/chunks_paragraphs)",
    )
    
    args = parser.parse_args()
    
    setup_logging()
    
    logger.info("=" * 60)
    logger.info("Paragraph Chunker")
    logger.info("=" * 60)
    logger.info(f"Входная директория: {args.input_dir}")
    logger.info(f"Выходная директория: {args.output_dir}")
    logger.info("=" * 60)
    
    stats = process_directory(args.input_dir, args.output_dir)
    
    return 0 if stats["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
