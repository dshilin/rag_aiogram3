"""
Скрипт разбиения документов на чанки по абзацам с сохранением метаданных

Разбивает PDF документы на чанки по абзацам, сохраняя:
- Источник (имя файла)
- Номер страницы (где начинается абзац)
- Уникальный ID чанка

Универсальное решение для абзацев, переходящих на следующую страницу:
- Абзац целиком относится к странице, где он НАЧИНАЕТСЯ
- Это предотвращает дублирование и сохраняет контекст
"""

import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF
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

    def format_for_display(self) -> str:
        """Форматировать для отображения"""
        return (
            f"[{self.chunk_id}] {self.source} (стр. {self.page})\n"
            f"{'─' * 50}\n{self.content}"
        )


@dataclass
class ChunkingStats:
    """Статистика разбиения"""
    total_pages: int = 0
    total_paragraphs: int = 0
    total_chunks: int = 0
    empty_pages: int = 0
    cross_page_paragraphs: int = 0  # Абзацы, начинающиеся на одной странице и продолжающиеся на другой
    files_processed: int = 0
    errors: list = field(default_factory=list)


class ParagraphChunker:
    """
    Разбиение текста на чанки по абзацам
    
    Стратегия для абзацев, переходящих между страницами:
    - Абзац целиком относится к странице, где он НАЧИНАЕТСЯ
    - Это сохраняет целостность мысли и предотвращает дублирование
    - При поиске пользователь получит полный абзац с указанием страницы начала
    """

    def __init__(
        self,
        min_paragraph_length: int = 10,
        merge_short_paragraphs: bool = True,
        merge_threshold: int = 50,
    ):
        """
        Args:
            min_paragraph_length: Минимальная длина абзаца (короткие игнорируются)
            merge_short_paragraphs: Объединять короткие абзацы с предыдущим
            merge_threshold: Порог для объединения (абзацы короче будут объединены)
        """
        self.min_paragraph_length = min_paragraph_length
        self.merge_short_paragraphs = merge_short_paragraphs
        self.merge_threshold = merge_threshold

    def extract_text_from_pdf(self, pdf_path: Path) -> list[tuple[int, str]]:
        """
        Извлечь текст из PDF с разбивкой по страницам

        Args:
            pdf_path: Путь к PDF файлу

        Returns:
            Список кортежей (номер_страницы, текст_страницы)
        """
        pages_text = []

        try:
            doc = fitz.open(pdf_path)
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text("text")
                # Нумерация страниц с 1 (как принято в документах)
                pages_text.append((page_num + 1, text))
            
            doc.close()
            
        except Exception as e:
            logger.error(f"Ошибка чтения PDF {pdf_path}: {e}")
            raise

        return pages_text

    def split_into_paragraphs(self, text: str) -> list[str]:
        """
        Разбить текст на абзацы

        Абзацем считается текст, разделенный двумя или более новыми строками,
        или одиночными новыми строками с отступами.
        """
        if not text.strip():
            return []

        # Разделяем по двойным новым строкам (основной разделитель абзацев)
        raw_paragraphs = text.split('\n\n')
        
        paragraphs = []
        for para in raw_paragraphs:
            # Очищаем и нормализуем
            cleaned = '\n'.join(
                line.strip() 
                for line in para.split('\n') 
                if line.strip()
            )
            
            if cleaned and len(cleaned) >= self.min_paragraph_length:
                paragraphs.append(cleaned)

        return paragraphs

    def chunk_pdf(self, pdf_path: Path) -> tuple[list[Chunk], ChunkingStats]:
        """
        Разбить PDF на чанки по абзацам

        Args:
            pdf_path: Путь к PDF файлу

        Returns:
            Кортеж (список чанков, статистика)
        """
        stats = ChunkingStats()
        chunks = []
        source_name = pdf_path.stem  # Имя файла без расширения
        global_paragraph_index = 0

        logger.info(f"Обработка файла: {pdf_path.name}")

        try:
            pages_text = self.extract_text_from_pdf(pdf_path)
            stats.total_pages = len(pages_text)

            # Словарь для отслеживания абзацев, продолжающихся со страницы на страницу
            continued_paragraphs: dict[int, str] = {}  # page -> remaining_text

            for page_num, page_text in pages_text:
                if not page_text.strip():
                    stats.empty_pages += 1
                    continue

                # Проверяем, есть ли продолжение с предыдущей страницы
                if continued_paragraphs.get(page_num):
                    # Это продолжение предыдущего абзаца
                    # Добавляем к первому абзацу текущей страницы
                    pass

                paragraphs = self.split_into_paragraphs(page_text)

                if not paragraphs:
                    stats.empty_pages += 1
                    continue

                for i, para in enumerate(paragraphs):
                    # Проверяем, является ли этот абзац продолжением предыдущего
                    is_continuation = (
                        i == 0 and 
                        page_num > 1 and 
                        continued_paragraphs.get(page_num - 1) is not None
                    )

                    if is_continuation:
                        stats.cross_page_paragraphs += 1
                        # Объединяем с предыдущим чанком (последний в списке)
                        if chunks and chunks[-1].page == page_num - 1:
                            prev_chunk = chunks[-1]
                            # Создаем обновленный чанк с объединенным контентом
                            merged_content = prev_chunk.content + " " + para
                            merged_chunk = Chunk(
                                content=merged_content,
                                source=prev_chunk.source,
                                page=prev_chunk.page,  # Оставляем страницу начала
                                chunk_id=prev_chunk.chunk_id,  # Сохраняем ID
                                paragraph_index=prev_chunk.paragraph_index,
                            )
                            chunks[-1] = merged_chunk
                            logger.debug(
                                f"  Стр. {page_num}: объединение с предыдущим абзацем "
                                f"(общая длина: {len(merged_content)} симв.)"
                            )
                        continue

                    # Проверяем, продолжается ли абзац на следующую страницу
                    # (последний абзац страницы без завершающего знака препинания)
                    continues_next = (
                        i == len(paragraphs) - 1 and
                        page_num < len(pages_text) and
                        not para.rstrip().endswith(('.', '!', '?', ':', ';'))
                    )

                    if continues_next:
                        continued_paragraphs[page_num] = para
                        logger.debug(
                            f"  Стр. {page_num}: абзац продолжается на след. страницу "
                            f"(длина: {len(para)} симв.)"
                        )

                    # Создаем чанк
                    chunk = Chunk(
                        content=para,
                        source=source_name,
                        page=page_num,
                        paragraph_index=global_paragraph_index,
                    )
                    chunks.append(chunk)
                    global_paragraph_index += 1
                    stats.total_paragraphs += 1

            stats.total_chunks = len(chunks)
            stats.files_processed += 1

            logger.info(
                f"  ✓ Обработано: {stats.total_pages} стр., "
                f"{stats.total_paragraphs} абзацев, "
                f"{stats.cross_page_paragraphs} межстраничных"
            )

        except Exception as e:
            stats.errors.append(f"{pdf_path.name}: {str(e)}")
            logger.error(f"Ошибка обработки {pdf_path.name}: {e}")
            raise

        return chunks, stats

    def chunk_directory(
        self,
        input_dir: Path,
        output_dir: Optional[Path] = None,
        glob_pattern: str = "*.pdf",
        save_chunks: bool = True,
    ) -> tuple[list[Chunk], ChunkingStats]:
        """
        Разбить все документы в директории на чанки

        Args:
            input_dir: Директория с документами
            output_dir: Директория для сохранения чанков (опционально)
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

        # Поиск файлов
        files = list(input_dir.glob(glob_pattern))
        
        # Также ищем в поддиректориях
        files.extend(input_dir.rglob(glob_pattern))
        files = list(set(files))  # Убираем дубликаты

        if not files:
            logger.warning(f"Файлы не найдены по паттерну: {glob_pattern}")
            return all_chunks, total_stats

        logger.info(f"Найдено файлов: {len(files)}")

        for file_path in files:
            if file_path.name.startswith('.'):
                continue

            try:
                chunks, stats = self.chunk_pdf(file_path)
                all_chunks.extend(chunks)

                # Обновляем общую статистику
                total_stats.total_pages += stats.total_pages
                total_stats.total_paragraphs += stats.total_paragraphs
                total_stats.total_chunks += stats.total_chunks
                total_stats.empty_pages += stats.empty_pages
                total_stats.cross_page_paragraphs += stats.cross_page_paragraphs
                total_stats.files_processed += 1
                total_stats.errors.extend(stats.errors)

                # Сохраняем чанки
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
        if total_stats.errors:
            logger.warning(f"Ошибок: {len(total_stats.errors)}")

        return all_chunks, total_stats

    def save_chunks(self, chunks: list[Chunk], output_dir: Path):
        """
        Сохранить чанки в JSON файлы

        Структура:
        output_dir/
          ├── index.json (общая информация)
          ├── chunk_000.json
          ├── chunk_001.json
          └── ...
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        # Сохраняем каждый чанк
        for i, chunk in enumerate(chunks):
            chunk_file = output_dir / f"chunk_{i:04d}.json"
            chunk_data = chunk.to_dict()
            chunk_file.write_text(
                json.dumps(chunk_data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )

        # Сохраняем индекс
        index_data = {
            "total_chunks": len(chunks),
            "source": chunks[0].source if chunks else "unknown",
            "pages": list(set(c.page for c in chunks)),
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


def create_chunker() -> ParagraphChunker:
    """Создать чанкер с настройками по умолчанию"""
    return ParagraphChunker(
        min_paragraph_length=10,
        merge_short_paragraphs=True,
        merge_threshold=50,
    )


def main():
    """CLI для разбиения документов на чанки"""
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
        description="Разбиение PDF документов на чанки по абзацам",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("data/documents"),
        help="Директория с PDF документами (по умолчанию: data/documents)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/documents/chunks"),
        help="Директория для сохранения чанков (по умолчанию: data/documents/chunks)",
    )
    parser.add_argument(
        "--pattern",
        type=str,
        default="*.pdf",
        help="Паттерн для поиска файлов (по умолчанию: *.pdf)",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Не сохранять чанки на диск (только статистика)",
    )
    parser.add_argument(
        "--preview",
        type=int,
        default=3,
        help="Показать N первых чанков для预览 (по умолчанию: 3)",
    )

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("PDF Paragraph Chunker")
    logger.info("=" * 60)
    logger.info(f"Входная директория: {args.input_dir}")
    logger.info(f"Выходная директория: {args.output_dir}")
    logger.info(f"Паттерн файлов: {args.pattern}")
    logger.info("=" * 60)

    # Создаем чанкер
    chunker = create_chunker()

    # Разбиваем документы
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
    logger.info(f"  Межстраничных абзацев: {stats.cross_page_paragraphs}")
    logger.info(f"  Пустых страниц: {stats.empty_pages}")
    logger.info(f"  Чанков создано: {stats.total_chunks}")
    
    if stats.errors:
        logger.warning(f"  Ошибки: {len(stats.errors)}")
        for error in stats.errors[:5]:
            logger.warning(f"    - {error}")

    # Превью чанков
    if chunks and args.preview > 0:
        logger.info("=" * 60)
        logger.info(f"Превью первых {min(args.preview, len(chunks))} чанков:")
        logger.info("=" * 60)
        
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
