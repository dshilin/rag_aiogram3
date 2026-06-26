"""
Разбиение Markdown документов на чанки с метаданными:

- Иерархия заголовков (# H1 → chapter, ## H2 → section)
- Определения (текст в «»)
- NA-концепты, ключевые слова
- Склейка коротких/резка длинных чанков по токенам
"""

import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from loguru import logger
from src.rag.concepts import NA_CONCEPTS
from src.utils.text import _extract_keywords
from src.utils.logging import setup_logging


@dataclass
class Chunk:
    content: str
    source: str
    chunk_id: str = ""
    book_title: str = ""
    part: str | None = None
    chapter: str | None = None
    section: str | None = None
    element_type: str = "main_text"
    element_number: int | None = None
    chunk_role: str = "body"
    definition_ref_id: str | None = None
    citation_label: str = "TBD"
    na_concepts: list = field(default_factory=list)
    keywords: list = field(default_factory=list)
    paragraph_index: int = 0
    page: int = 0

    def __post_init__(self):
        if not self.chunk_id:
            self.chunk_id = self._generate_id()

    def _generate_id(self) -> str:
        unique_str = f"{self.source}:{self.paragraph_index}:{self.content[:50]}"
        return hashlib.md5(unique_str.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "metadata": {
                "chunk_id": self.chunk_id,
                "source": self.source,
                "book_title": self.book_title,
                "part": self.part,
                "chapter": self.chapter,
                "section": self.section,
                "element_type": self.element_type,
                "element_number": self.element_number,
                "chunk_role": self.chunk_role,
                "definition_ref_id": self.definition_ref_id,
                "citation_label": self.citation_label,
                "na_concepts": self.na_concepts,
                "keywords": self.keywords,
                "paragraph_index": self.paragraph_index,
            }
        }


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
        min_chunk_tokens: int = 25,
        max_chunk_tokens: int = 130,
        overlap_ratio: float = 0,
    ):
        self.min_chunk_tokens = min_chunk_tokens
        self.max_chunk_tokens = max_chunk_tokens
        self.overlap_ratio = overlap_ratio

    @staticmethod
    def _detect_heading(text: str) -> tuple[str, str] | None:
        stripped = text.strip()
        for prefix, level in [("# ", "chapter"), ("## ", "section")]:
            if stripped.startswith(prefix):
                value = stripped[len(prefix):].strip()
                return (level, value)
        return None

    @staticmethod
    def _is_definition(text: str) -> bool:
        stripped = text.rstrip(".!?,")
        return text.startswith("«") and stripped.endswith("»")

    @staticmethod
    def _detect_na_concepts(text: str) -> list[str]:
        return [c for c in NA_CONCEPTS if c.lower() in text.lower()]

    @staticmethod
    def _classify_heading(chapter: str | None) -> tuple[str, int | None]:
        if not chapter:
            return ("main_text", None)
        chapter_lower = chapter.lower()
        if "шаг" in chapter_lower:
            for w in chapter_lower.split():
                if w.isdigit():
                    return ("step", int(w))
            return ("step", None)
        if "традици" in chapter_lower:
            for w in chapter_lower.split():
                if w.isdigit():
                    return ("tradition", int(w))
            return ("tradition", None)
        return ("main_text", None)

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

        paragraphs = []
        raw_blocks = re.split(r'\n\n+', text)

        for block in raw_blocks:
            lines = []
            for line in block.split('\n'):
                line = line.strip()
                if not line:
                    continue
                lines.append(line)

            if not lines:
                continue

            block_text = ' '.join(lines)
            if block_text.strip():
                paragraphs.append(block_text)

        return paragraphs

    def chunk_md(self, md_path: Path) -> tuple[list[Chunk], ChunkingStats]:
        stats = ChunkingStats()
        chunks = []
        source_name = md_path.stem
        global_paragraph_index = 0

        hierarchy = {
            "book_title": source_name,
            "part": None,
            "chapter": None,
            "section": None,
            "element_type": "main_text",
            "element_number": None,
        }

        logger.info(f"Обработка файла: {md_path.name}")

        try:
            text = md_path.read_text(encoding="utf-8")
            paragraphs = self.split_into_paragraphs(text)
            logger.debug(f"  Разбито на {len(paragraphs)} абзацев")
            stats.total_pages = 1

            current_definition_id: str | None = None

            for para in paragraphs:
                heading = self._detect_heading(para)
                if heading:
                    level, value = heading
                    logger.debug(f"  Заголовок [{level}]: {value}")
                    if level == "chapter":
                        hierarchy["chapter"] = value
                        hierarchy["section"] = None
                        hierarchy["element_type"], hierarchy["element_number"] = \
                            self._classify_heading(value)
                        logger.debug(f"  Иерархия: chapter={value}, type={hierarchy['element_type']}")
                        current_definition_id = None
                    elif level == "section":
                        hierarchy["section"] = value
                        logger.debug(f"  Иерархия: section={value}")
                    continue

                if para.strip().startswith("**Только сегодня:**"):
                    chunk = Chunk(
                        content=para,
                        source=source_name,
                        book_title=hierarchy["book_title"],
                        part=hierarchy["part"],
                        chapter=hierarchy["chapter"],
                        section=hierarchy["section"],
                        element_type=hierarchy["element_type"],
                        element_number=hierarchy["element_number"],
                        chunk_role="just_for_today",
                        definition_ref_id=current_definition_id,
                        citation_label=self._build_citation_label(hierarchy),
                        na_concepts=self._detect_na_concepts(para),
                        keywords=_extract_keywords(para),
                        paragraph_index=global_paragraph_index,
                    )
                    chunks.append(chunk)
                    global_paragraph_index += 1
                    continue

                if self._is_definition(para):
                    chunk_id = hashlib.md5(
                        (para[:100]).encode("utf-8")
                    ).hexdigest()[:16]
                    current_definition_id = chunk_id
                    logger.debug(f"  Определение: id={chunk_id}")
                    chunk = Chunk(
                        content=para,
                        source=source_name,
                        chunk_id=chunk_id,
                        book_title=hierarchy["book_title"],
                        part=hierarchy["part"],
                        chapter=hierarchy["chapter"],
                        section=hierarchy["section"],
                        element_type=hierarchy["element_type"],
                        element_number=hierarchy["element_number"],
                        chunk_role="definition",
                        definition_ref_id=chunk_id,
                        citation_label=self._build_citation_label(hierarchy),
                        na_concepts=self._detect_na_concepts(para),
                        keywords=_extract_keywords(para),
                        paragraph_index=global_paragraph_index,
                    )
                    chunks.append(chunk)
                    global_paragraph_index += 1
                    continue

                chunk = Chunk(
                    content=para,
                    source=source_name,
                    book_title=hierarchy["book_title"],
                    part=hierarchy["part"],
                    chapter=hierarchy["chapter"],
                    section=hierarchy["section"],
                    element_type=hierarchy["element_type"],
                    element_number=hierarchy["element_number"],
                    chunk_role="body",
                    definition_ref_id=current_definition_id,
                    citation_label=self._build_citation_label(hierarchy),
                    na_concepts=self._detect_na_concepts(para),
                    keywords=_extract_keywords(para),
                    paragraph_index=global_paragraph_index,
                )
                chunks.append(chunk)
                global_paragraph_index += 1

            stats.total_paragraphs = len(chunks)
            chunks = self._post_process(chunks)
            stats.total_chunks = len(chunks)
            stats.files_processed += 1

            logger.info(f"  ✓ Обработано: {stats.total_chunks} чанков")

        except Exception as e:
            stats.errors.append(f"{md_path.name}: {str(e)}")
            logger.error(f"Ошибка обработки {md_path.name}: {e}")
            raise

        return chunks, stats

    def _post_process(self, chunks: list[Chunk]) -> list[Chunk]:
        if not chunks:
            return chunks

        merged = [chunks[0]]
        merge_count = 0
        split_count = 0
        for chunk in chunks[1:]:
            prev_is_def = merged[-1].chunk_role in ("definition", "just_for_today")
            curr_is_def = chunk.chunk_role in ("definition", "just_for_today")

            if not prev_is_def and not curr_is_def and \
               self._estimate_tokens(merged[-1].content) < self.min_chunk_tokens:
                merged[-1].content += " " + chunk.content
                merged[-1].keywords = list(dict.fromkeys(merged[-1].keywords + chunk.keywords))
                merged[-1].na_concepts = list(dict.fromkeys(merged[-1].na_concepts + chunk.na_concepts))
                merge_count += 1
                continue

            if not curr_is_def and \
               self._estimate_tokens(chunk.content) > self.max_chunk_tokens:
                split = self._split_chunk(chunk)
                merged.extend(split)
                split_count += 1
                continue

            merged.append(chunk)

        if merge_count:
            logger.debug(f"  Склеено чанков: {merge_count}")
        if split_count:
            logger.debug(f"  Разрезано чанков: {split_count}")

        return merged

    def _split_chunk(self, chunk: Chunk) -> list[Chunk]:
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', chunk.content) if s.strip()]
        if len(sentences) < 2:
            return [chunk]

        parts = []
        current = []
        current_tokens = 0
        overlap_tokens = int(self.max_chunk_tokens * self.overlap_ratio)

        for sent in sentences:
            sent_tokens = self._estimate_tokens(sent)
            if current_tokens + sent_tokens > self.max_chunk_tokens and current:
                text = " ".join(current)
                new_chunk = Chunk(
                    content=text,
                    source=chunk.source,
                    book_title=chunk.book_title,
                    part=chunk.part,
                    chapter=chunk.chapter,
                    section=chunk.section,
                    element_type=chunk.element_type,
                    element_number=chunk.element_number,
                    chunk_role=chunk.chunk_role,
                    definition_ref_id=chunk.definition_ref_id,
                    citation_label=chunk.citation_label,
                    na_concepts=chunk.na_concepts,
                    keywords=chunk.keywords,
                    paragraph_index=chunk.paragraph_index,
                )
                parts.append(new_chunk)

                overlap = []
                overlap_tok = 0
                for s in reversed(current):
                    t = self._estimate_tokens(s)
                    if overlap_tok + t > overlap_tokens:
                        break
                    overlap.insert(0, s)
                    overlap_tok += t
                current = overlap
                current_tokens = overlap_tok

            current.append(sent)
            current_tokens += sent_tokens

        if current:
            text = " ".join(current)
            new_chunk = Chunk(
                content=text,
                source=chunk.source,
                book_title=chunk.book_title,
                part=chunk.part,
                chapter=chunk.chapter,
                section=chunk.section,
                element_type=chunk.element_type,
                element_number=chunk.element_number,
                chunk_role=chunk.chunk_role,
                definition_ref_id=chunk.definition_ref_id,
                citation_label=chunk.citation_label,
                na_concepts=chunk.na_concepts,
                keywords=chunk.keywords,
                paragraph_index=chunk.paragraph_index,
            )
            parts.append(new_chunk)

        return parts

    @staticmethod
    def _clean_heading(text: str) -> str:
        return re.sub(r'\s*#+\s*', ' ', text).strip()

    @staticmethod
    def _build_citation_label(hierarchy: dict) -> str:
        book = hierarchy.get("book_title", "")
        chapter = MarkdownChunker._clean_heading(hierarchy["chapter"]) if hierarchy.get("chapter") else None
        section = MarkdownChunker._clean_heading(hierarchy["section"]) if hierarchy.get("section") else None

        if book and chapter and book.endswith(chapter):
            return book

        parts = []
        if book:
            parts.append(book)
        if chapter:
            parts.append(f"Глава «{chapter}»")
        if section:
            if any(section.lower().startswith(p) for p in ("шаг", "глава", "традици", "книга")):
                parts.append(section)
            else:
                parts.append(f"Раздел «{section}»")
        return ", ".join(parts) if parts else book

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        return int(len(text.split()) * 1.3)

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

                total_stats.total_chunks += stats.total_chunks
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
            "chunks": [
                {
                    "file": f"chunk_{i:04d}.json",
                    "chunk_id": chunk.chunk_id,
                    "chunk_role": chunk.chunk_role,
                    "chapter": chunk.chapter,
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
            logger.info(f"  Роль: {chunk.chunk_role}")
            logger.info(f"  Длина: {len(chunk.content)} симв.")
            logger.info(f"  Текст: {chunk.content[:200]}...")

    return 0


if __name__ == "__main__":
    sys.exit(main())
