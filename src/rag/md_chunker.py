"""
Скрипт разбиения Markdown документов на чанки по абзацам

Разбивает MD файлы на чанки по абзацам, сохраняя:
- Источник (имя файла)
- Номер страницы (из маркеров <!-- Page X -->)
- Уникальный ID чанка

Стратегия для абзацев, переходящих на следующую страницу:
- Абзац целиком относится к странице, где он НАЧИНАЕТСЯ
"""

import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from loguru import logger


@dataclass
class Chunk:
    """Чанк текста с метаданными"""
    content: str
    source: str
    page: int
    chunk_id: str = ""
    paragraph_index: int = 0

    def __post_init__(self):
        if not self.chunk_id:
            self.chunk_id = self._generate_id()

    def _generate_id(self) -> str:
        """Генерация уникального ID на основе контента и метаданных"""
        unique_str = f"{self.source}:{self.page}:{self.paragraph_index}:{self.content[:50]}"
        return hashlib.md5(unique_str.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict:
        """Конвертировать в словарь для сохранения"""
        return {
            "content": self.content,
            "metadata": {
                "source": self.source,
                "page": self.page,
                "chunk_id": self.chunk_id,
                "paragraph_index": self.paragraph_index,
            }
        }

    def format_for_response(self) -> str:
        """Форматировать для ответа пользователю"""
        return (
            f"📄 **Источник**: {self.source}\n"
            f"📑 **Страница**: {self.page}\n"
            f"📝 **Текст**:\n{self.content}"
        )


@dataclass
class ChunkingStats:
    """Статистика разбиения"""
    total_pages: int = 0
    total_paragraphs: int = 0
    total_chunks: int = 0
    empty_pages: int = 0
    cross_page_paragraphs: int = 0
    files_processed: int = 0
    errors: list = field(default_factory=list)


class MarkdownChunker:
    """
    Разбиение Markdown документов на чанки по абзацам
    """

    def __init__(
        self,
        min_paragraph_length: int = 10,
        cross_page_merge: bool = True,
        merge_short_paragraphs: bool = True,
        merge_threshold: int = 50,
    ):
        self.min_paragraph_length = min_paragraph_length
        self.cross_page_merge = cross_page_merge
        self.merge_short_paragraphs = merge_short_paragraphs
        self.merge_threshold = merge_threshold

    def extract_pages_from_md(self, md_path: Path) -> list[tuple[int, str]]:
        content = md_path.read_text(encoding="utf-8")
        page_pattern = r'<!--\s*Page\s+(\d+)\s*-->'
        parts = re.split(page_pattern, content)

        pages = []

        if not re.search(page_pattern, content):
            if content.strip():
                pages.append((1, content))
            return pages

        i = 0
        if parts[0].strip():
            pages.append((1, parts[0]))
            i = 1
        else:
            i = 1

        while i < len(parts) - 1:
            page_num = int(parts[i])
            page_content = parts[i + 1]
            pages.append((page_num, page_content))
            i += 2

        return pages

    def split_into_paragraphs(self, text: str) -> list[str]:
        if not text.strip():
            return []

        text = re.sub(r'<!--\s*Page\s+\d+\s*-->', '', text)
        paragraphs = []
        raw_blocks = re.split(r'\n\n+', text)

        for block in raw_blocks:
            lines = []
            for line in block.split('\n'):
                line = line.strip()
                if not line:
                    continue
                if line.startswith('<!--') and line.endswith('-->'):
                    continue
                if re.match(r'^\*\[\d+\s+изображений?\s+на\s+странице\s+\d+\]\*$', line):
                    continue
                if re.match(r'^.*\.{3,}\d+$', line):
                    continue
                lines.append(line)

            if not lines:
                continue

            block_text = ' '.join(lines)
            if len(block_text) >= self.min_paragraph_length:
                paragraphs.append(block_text)

        return paragraphs

    def chunk_md(self, md_path: Path) -> tuple[list[Chunk], ChunkingStats]:
        stats = ChunkingStats()
        chunks = []
        source_name = md_path.stem
        global_paragraph_index = 0

        logger.info(f"Обработка файла: {md_path.name}")

        try:
            pages_text = self.extract_pages_from_md(md_path)
            stats.total_pages = len(pages_text)

            continued_paragraph: tuple[int, str] | None = None

            for page_num, page_text in pages_text:
                if not page_text.strip():
                    stats.empty_pages += 1
                    continue

                paragraphs = self.split_into_paragraphs(page_text)

                if not paragraphs:
                    stats.empty_pages += 1
                    continue

                if self.cross_page_merge and continued_paragraph is not None:
                    prev_page, prev_text = continued_paragraph
                    paragraphs[0] = prev_text + " " + paragraphs[0]
                    stats.cross_page_paragraphs += 1
                    continued_paragraph = None
                    chunk_page = prev_page
                else:
                    chunk_page = page_num

                if self.cross_page_merge and not any(paragraphs[-1].rstrip().endswith(c) for c in ('.', '!', '?', ':', ';', '»', '"')):
                    continued_paragraph = (chunk_page, paragraphs.pop())

                for para in paragraphs:
                    chunk = Chunk(
                        content=para,
                        source=source_name,
                        page=chunk_page,
                        paragraph_index=global_paragraph_index,
                    )
                    chunks.append(chunk)
                    global_paragraph_index += 1
                    stats.total_paragraphs += 1

            if self.cross_page_merge and continued_paragraph is not None:
                prev_page, prev_text = continued_paragraph
                chunk = Chunk(
                    content=prev_text,
                    source=source_name,
                    page=prev_page,
                    paragraph_index=global_paragraph_index,
                )
                chunks.append(chunk)
                global_paragraph_index += 1
                stats.total_paragraphs += 1

            if self.merge_short_paragraphs:
                merged = []
                for chunk in chunks:
                    if merged and len(chunk.content) < self.merge_threshold:
                        merged[-1] = Chunk(
                            content=merged[-1].content + " " + chunk.content,
                            source=merged[-1].source,
                            page=merged[-1].page,
                            paragraph_index=merged[-1].paragraph_index,
                        )
                    else:
                        merged.append(chunk)
                chunks = merged

            stats.total_chunks = len(chunks)
            stats.files_processed += 1

            logger.info(
                f"  ✓ Обработано: {stats.total_pages} стр., "
                f"{stats.total_paragraphs} абзацев"
            )

        except Exception as e:
            stats.errors.append(f"{md_path.name}: {str(e)}")
            logger.error(f"Ошибка обработки {md_path.name}: {e}")
            raise

        return chunks, stats

    def chunk_directory(
        self,
        input_dir: Path,
        output_dir: Optional[Path] = None,
        glob_pattern: str = "*.md",
        save_chunks: bool = True,
    ) -> tuple[list[Chunk], ChunkingStats]:
        """
        Разбить все документы в директории на чанки

        Args:
            input_dir: Директория с документами
            output_dir: Директория для сохранения чанков
            glob_pattern: Паттерн для поиска файлов
            save_chunks: Сохранять чанки на диск

        Returns:
            Кортеж (все чанки, общая статистика)
        """
        all_chunks = []
        total_stats = ChunkingStats()

        if not input_dir.exists():
            logger.error(f"Директория не найдена: {input_dir}")
            return all_chunks, total_stats

        files = sorted(input_dir.glob(glob_pattern))

        if not files:
            logger.warning(f"Файлы не найдены по паттерну: {glob_pattern}")
            return all_chunks, total_stats

        logger.info(f"Найдено файлов: {len(files)}")

        for file_path in files:
            if file_path.name.startswith('.'):
                continue

            try:
                chunks, stats = self.chunk_md(file_path)
                all_chunks.extend(chunks)

                total_stats.total_pages += stats.total_pages
                total_stats.total_paragraphs += stats.total_paragraphs
                total_stats.total_chunks += stats.total_chunks
                total_stats.empty_pages += stats.empty_pages
                total_stats.cross_page_paragraphs += stats.cross_page_paragraphs
                total_stats.files_processed += 1
                total_stats.errors.extend(stats.errors)

                if save_chunks and output_dir and chunks:
                    self.save_chunks(chunks, output_dir / file_path.stem)

            except Exception as e:
                logger.error(f"Пропущен файл {file_path.name}: {e}")
                total_stats.errors.append(f"{file_path.name}: {str(e)}")
                continue

        logger.info("=" * 60)
        logger.info(
            f"Всего: {total_stats.files_processed} файлов, "
            f"{total_stats.total_chunks} чанков"
        )

        return all_chunks, total_stats

    def save_chunks(self, chunks: list[Chunk], output_dir: Path):
        """
        Сохранить чанки в JSON файлы
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        for i, chunk in enumerate(chunks):
            chunk_file = output_dir / f"chunk_{i:04d}.json"
            chunk_data = chunk.to_dict()
            chunk_file.write_text(
                json.dumps(chunk_data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )

        index_data = {
            "total_chunks": len(chunks),
            "source": chunks[0].source if chunks else "unknown",
            "pages": sorted(list(set(c.page for c in chunks))),
            "chunks": [
                {
                    "file": f"chunk_{i:04d}.json",
                    "page": chunk.page,
                    "chunk_id": chunk.chunk_id,
                    "preview": chunk.content[:100] + "..." if len(chunk.content) > 100 else chunk.content,
                }
                for i, chunk in enumerate(chunks)
            ]
        }
        
        index_file = output_dir / "index.json"
        index_file.write_text(
            json.dumps(index_data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8"
        )

        logger.info(f"  Сохранено {len(chunks)} чанков в {output_dir}")


def main():
    """CLI для разбиения Markdown документов на чанки"""
    import argparse

    def setup_logging():
        logger.remove()
        logger.add(
            sys.stdout,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
            level="INFO",
        )

    setup_logging()

    parser = argparse.ArgumentParser(
        description="Разбиение Markdown документов на чанки по абзацам",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("data/documents/md_docs"),
        help="Директория с MD документами (по умолчанию: data/documents/md_docs)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/documents/chunks"),
        help="Директория для сохранения чанков",
    )
    parser.add_argument(
        "--pattern",
        type=str,
        default="*.md",
        help="Паттерн для поиска файлов (по умолчанию: *.md)",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Не сохранять чанки на диск",
    )
    parser.add_argument(
        "--preview",
        type=int,
        default=3,
        help="Показать N первых чанков",
    )

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Markdown Chunker")
    logger.info("=" * 60)
    logger.info(f"Входная директория: {args.input_dir}")
    logger.info(f"Выходная директория: {args.output_dir}")
    logger.info(f"Паттерн файлов: {args.pattern}")
    logger.info("=" * 60)

    chunker = MarkdownChunker()

    chunks, stats = chunker.chunk_directory(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        glob_pattern=args.pattern,
        save_chunks=not args.no_save,
    )

    logger.info("=" * 60)
    logger.info("Статистика:")
    logger.info(f"  Файлов обработано: {stats.files_processed}")
    logger.info(f"  Всего страниц: {stats.total_pages}")
    logger.info(f"  Всего абзацев: {stats.total_paragraphs}")
    logger.info(f"  Чанков создано: {stats.total_chunks}")
    
    if stats.errors:
        logger.warning(f"  Ошибки: {len(stats.errors)}")

    if chunks and args.preview > 0:
        logger.info("=" * 60)
        logger.info(f"Превью первых {min(args.preview, len(chunks))} чанков:")
        
        for i, chunk in enumerate(chunks[:args.preview]):
            logger.info(f"\n[Чанк {i+1}]")
            logger.info(f"  ID: {chunk.chunk_id}")
            logger.info(f"  Источник: {chunk.source}")
            logger.info(f"  Страница: {chunk.page}")
            logger.info(f"  Длина: {len(chunk.content)} симв.")
            logger.info(f"  Текст: {chunk.content[:200]}...")

    return 0


if __name__ == "__main__":
    sys.exit(main())
