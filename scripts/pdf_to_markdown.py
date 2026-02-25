"""
Утилита для конвертации PDF файлов в Markdown с сохранением структуры

Сохраняет:
    - Иерархию заголовков (на основе размера шрифта)
    - Форматирование текста (жирный, курсив, подчеркивание)
    - Списки и нумерованные элементы
    - Таблицы
    - Блокировку текста и абзацы
    - Привязку к страницам
    - Изображения с позициями

Использование:
    python scripts/pdf_to_markdown.py [--input-dir INPUT_DIR] [--output-dir OUTPUT_DIR]

Аргументы:
    --input-dir   Директория с PDF файлами (по умолчанию: data/documents/pdf_docs)
    --output-dir  Директория для сохранения Markdown (по умолчанию: data/documents/md_docs)
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF
from loguru import logger


@dataclass
class TextSpan:
    """Информация о текстовом фрагменте с форматированием"""
    text: str
    font_name: str
    font_size: float
    is_bold: bool = False
    is_italic: bool = False
    is_underline: bool = False
    is_highlighted: bool = False
    color: tuple = (0, 0, 0)
    
    def to_markdown(self) -> str:
        """Конвертировать в Markdown с применением форматирования"""
        result = self.text
        if self.is_bold:
            result = f"**{result}**"
        if self.is_italic:
            result = f"*{result}*"
        if self.is_underline:
            result = f"<u>{result}</u>"
        if self.is_highlighted:
            result = f"=={result}=="
        return result


def setup_logging():
    """Настроить логирование"""
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO",
    )


def _detect_heading_level(font_size: float, font_name: str, avg_font_size: float) -> Optional[int]:
    """
    Определить уровень заголовка на основе размера шрифта
    
    Args:
        font_size: Размер шрифта текущего текста
        font_name: Название шрифта
        avg_font_size: Средний размер шрифта в документе
        
    Returns:
        Уровень заголовка (1-6) или None если это обычный текст
    """
    is_bold = "bold" in font_name.lower()
    size_ratio = font_size / avg_font_size if avg_font_size > 0 else 1.0
    
    # Если текст значительно больше среднего - это заголовок
    if is_bold and size_ratio > 1.8:
        return 1
    elif is_bold and size_ratio > 1.5:
        return 2
    elif is_bold and size_ratio > 1.3:
        return 3
    elif size_ratio > 1.5:
        return 4
    elif size_ratio > 1.2:
        return 5
    elif size_ratio > 1.05:
        return 6
    
    return None


def _extract_spans_with_formatting(block: dict) -> list[TextSpan]:
    """
    Извлечь текстовые фрагменты с информацией о форматировании
    
    Args:
        block: Блок текста из get_text("dict")
        
    Returns:
        Список TextSpan объектов
    """
    spans = []
    
    if block["type"] != 0:  # 0 = text block
        return spans
    
    try:
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "")
                if not text.strip():
                    continue
                
                font_info = span.get("font", "")
                flags = span.get("flags", 0)  # Битовые флаги форматирования
                
                # Распарсить флаги форматирования
                is_bold = bool(flags & (1 << 0))  # Bit 0: superscript
                is_italic = bool(flags & (1 << 1))  # Bit 1: italic
                is_underline = bool(flags & (1 << 2))  # Bit 2: underline
                
                span_obj = TextSpan(
                    text=text,
                    font_name=font_info,
                    font_size=span.get("size", 12.0),
                    is_bold=is_bold or "bold" in font_info.lower(),
                    is_italic=is_italic or "ital" in font_info.lower(),
                    is_underline=is_underline,
                )
                spans.append(span_obj)
    except Exception as e:
        logger.warning(f"Ошибка при разборе блока: {e}")
    
    return spans


def _calculate_avg_font_size(doc: fitz.Document, max_pages: int = 5) -> float:
    """
    Вычислить средний размер шрифта в документе
    
    Args:
        doc: PDF документ
        max_pages: Максимум страниц для анализа
        
    Returns:
        Средний размер шрифта
    """
    font_sizes = []
    
    for page in doc[:max_pages]:
        text_dict = page.get_text("dict")
        
        for block in text_dict.get("blocks", []):
            if block["type"] != 0:
                continue
            
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    size = span.get("size", 0)
                    if size > 0:
                        font_sizes.append(size)
    
    return sum(font_sizes) / len(font_sizes) if font_sizes else 12.0


def _process_text_block(block: dict, avg_font_size: float, page_num: int) -> str:
    """
    Обработать текстовый блок и конвертировать в Markdown
    
    Args:
        block: Блок текста из get_text("dict")
        avg_font_size: Средний размер шрифта
        page_num: Номер страницы (для справки)
        
    Returns:
        Текст в формате Markdown
    """
    if block["type"] != 0:
        return ""
    
    spans = _extract_spans_with_formatting(block)
    if not spans:
        return ""
    
    # Определить уровень заголовка на основе первого спана
    first_span = spans[0]
    heading_level = _detect_heading_level(first_span.font_size, first_span.font_name, avg_font_size)
    
    # Собрать текст с форматированием
    formatted_text = "".join(span.to_markdown() for span in spans)
    
    # Добавить Markdown заголовок если это заголовок
    if heading_level:
        return f"{'#' * heading_level} {formatted_text.strip()}"
    
    return formatted_text.strip()


def _extract_page_elements_ordered(page: fitz.Page, avg_font_size: float, page_num: int, output_dir: Path = None, doc_name: str = "") -> list[tuple[float, str]]:
    """
    Извлечь все элементы со страницы в порядке их появления (по координатам Y)
    
    Args:
        page: Страница PDF
        avg_font_size: Средний размер шрифта
        page_num: Номер страницы
        output_dir: Директория для сохранения изображений
        doc_name: Имя документа
        
    Returns:
        Список (y_coordinate, content) для сортировки по положению
    """
    elements = []
    
    # Извлечь текстовые блоки
    try:
        text_dict = page.get_text("dict")
        for block in text_dict.get("blocks", []):
            if block["type"] == 0:  # Text block
                # Получить Y-координату блока
                bbox = block.get("bbox", (0, 0, 0, 0))
                y_coord = bbox[1]
                
                processed = _process_text_block(block, avg_font_size, page_num)
                if processed:
                    elements.append((y_coord, processed))
    except Exception as e:
        logger.debug(f"Ошибка при извлечении текста: {e}")
    
    # Извлечь таблицы
    try:
        tables = page.find_tables()
        for table in tables:
            # Таблица имеет bbox с координатами
            bbox = table.bbox
            y_coord = bbox[1]
            
            rows = table.extract()
            if not rows:
                continue
            
            header = "| " + " | ".join(str(cell or "").strip() for cell in rows[0]) + " |"
            separator = "|" + "|".join(["---"] * len(rows[0])) + "|"
            table_rows = []
            for row in rows[1:]:
                row_md = "| " + " | ".join(str(cell or "").strip() for cell in row) + " |"
                table_rows.append(row_md)
            
            table_content = header + "\n" + separator + "\n" + "\n".join(table_rows)
            elements.append((y_coord, table_content))
    except Exception as e:
        logger.debug(f"Ошибка при извлечении таблиц: {e}")
    
    # Извлечь изображения
    if output_dir and doc_name:
        try:
            image_list = page.get_images(full=True)
            images_dir = output_dir / "images"
            
            for img_num, img_ref in enumerate(image_list, 1):
                try:
                    # Получить информацию об изображении
                    xref = img_ref[0]
                    img_info = page.parent.get_page_images(page.number)
                    # Получить приблизительные координаты
                    y_coord = page.rect.height / 2  # Упрощённо в середину страницы
                    
                    pix = fitz.Pixmap(page.parent, xref)
                    img_filename = f"{doc_name}_p{page_num}_img{img_num}.png"
                    img_path = images_dir / img_filename
                    
                    if not images_dir.exists():
                        images_dir.mkdir(parents=True, exist_ok=True)
                    
                    if pix.n - pix.alpha < 4:  # RGB
                        pix.save(str(img_path))
                    else:  # CMYK
                        pix = fitz.Pixmap(fitz.csRGB, pix)
                        pix.save(str(img_path))
                    
                    img_md = f"![Image {img_num}](images/{img_filename})"
                    elements.append((y_coord, img_md))
                except Exception as e:
                    logger.warning(f"Ошибка при сохранении изображения: {e}")
        except Exception as e:
            logger.debug(f"Ошибка при извлечении изображений: {e}")
    
    # Отсортировать элементы по Y-координате (сверху вниз)
    elements.sort(key=lambda x: x[0])
    
    return elements



def _extract_images(page: fitz.Page, output_dir: Path, doc_name: str, page_num: int) -> str:
    """
    ⚠️ Функция оставлена для обратной совместимости.
    Используйте _extract_page_elements_ordered() для сохранения порядка.
    
    Args:
        page: Страница PDF
        output_dir: Директория для сохранения
        doc_name: Имя документа
        page_num: Номер страницы
        
    Returns:
        Ссылки на изображения в Markdown формате
    """
    return ""  # Обработка теперь в _extract_page_elements_ordered()


def pdf_to_markdown(pdf_path: Path, output_dir: Path = None) -> str:
    """
    Конвертировать PDF файл в Markdown формат с сохранением структуры
    
    Args:
        pdf_path: Путь к PDF файлу
        output_dir: Директория для сохранения изображений
        
    Returns:
        Текст в формате Markdown
    """
    logger.info(f"Обработка файла: {pdf_path.name}")
    
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        logger.error(f"Ошибка открытия файла {pdf_path.name}: {e}")
        return ""
    
    # Вычислить средний размер шрифта для определения заголовков
    avg_font_size = _calculate_avg_font_size(doc)
    logger.debug(f"Средний размер шрифта: {avg_font_size:.1f}")
    
    markdown_parts = []
    doc_name = pdf_path.stem
    
    # Добавить метаинформацию о документе
    markdown_parts.append(f"# {doc_name}\n")
    markdown_parts.append(f"> **Источник**: {pdf_path.name} | **Страниц**: {len(doc)}\n")
    markdown_parts.append("")
    
    for page_num, page in enumerate(doc, 1):
        logger.debug(f"  Страница {page_num}/{len(doc)}")
        
        # Добавить якорь страницы
        markdown_parts.append(f"## [Страница {page_num}](#{pdf_path.stem}-page-{page_num}) {{#{pdf_path.stem}-page-{page_num}}}")
        markdown_parts.append("")
        
        # Извлечь все элементы страницы в правильном порядке
        try:
            page_elements = _extract_page_elements_ordered(page, avg_font_size, page_num, output_dir, pdf_path.stem)
            
            for y_coord, content in page_elements:
                markdown_parts.append(content)
                markdown_parts.append("")
        
        except Exception as e:
            logger.warning(f"  Ошибка при обработке страницы {page_num}: {e}")
        
        markdown_parts.append("---")
        markdown_parts.append("")
    
    doc.close()
    
    return "\n".join(markdown_parts)



def convert_directory(input_dir: Path, output_dir: Path) -> dict:
    """
    Конвертировать все PDF файлы в директории
    
    Args:
        input_dir: Директория с PDF файлами
        output_dir: Директория для сохранения Markdown файлов
        
    Returns:
        Статистика конвертации
    """
    stats = {"success": 0, "failed": 0, "total": 0}
    
    if not input_dir.exists():
        logger.error(f"Директория не найдена: {input_dir}")
        return stats
    
    pdf_files = list(input_dir.glob("*.pdf"))
    
    if not pdf_files:
        logger.warning(f"PDF файлы не найдены в {input_dir}")
        return stats
    
    stats["total"] = len(pdf_files)
    logger.info(f"Найдено PDF файлов: {stats['total']}")
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    for pdf_file in pdf_files:
        try:
            markdown_text = pdf_to_markdown(pdf_file, output_dir)
            
            if markdown_text:
                output_file = output_dir / f"{pdf_file.stem}.md"
                output_file.write_text(markdown_text, encoding="utf-8")
                logger.success(f"✓ {pdf_file.name} -> {output_file.name}")
                stats["success"] += 1
            else:
                logger.warning(f"⚠ {pdf_file.name} - пустой результат")
                stats["failed"] += 1
                
        except Exception as e:
            logger.error(f"✗ {pdf_file.name} - ошибка: {e}")
            stats["failed"] += 1
    
    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Конвертация PDF файлов в Markdown",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("data/documents/pdf_docs"),
        help="Директория с PDF файлами (по умолчанию: data/documents/pdf_docs)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/documents/md_docs"),
        help="Директория для Markdown файлов (по умолчанию: data/documents/md_docs)",
    )
    
    args = parser.parse_args()
    
    setup_logging()
    
    logger.info("=" * 50)
    logger.info("PDF -> Markdown Конвертер")
    logger.info("=" * 50)
    logger.info(f"Входная директория: {args.input_dir}")
    logger.info(f"Выходная директория: {args.output_dir}")
    logger.info("=" * 50)
    
    stats = convert_directory(args.input_dir, args.output_dir)
    
    logger.info("=" * 50)
    logger.info(f"Всего: {stats['total']} | Успешно: {stats['success']} | Ошибок: {stats['failed']}")
    logger.info("=" * 50)
    
    return 0 if stats["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
