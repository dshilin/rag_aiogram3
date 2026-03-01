"""
Конвертация PDF файлов в Markdown с сохранением структуры

Извлекает текст из PDF, сохраняя:
- Абзацы (разделение двойными новыми строками)
- Заголовки (Markdown заголовки)
- Разделы
- Номера страниц (маркеры <!-- Page X -->)
"""

import re
import sys
from pathlib import Path

import fitz  # PyMuPDF
from loguru import logger


def setup_logging():
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO",
    )


def extract_pages_from_pdf(pdf_path: Path) -> list[tuple[int, str]]:
    """
    Извлечь текст из PDF с разбивкой по страницам и абзацам

    Args:
        pdf_path: Путь к PDF файлу

    Returns:
        Список кортежей (номер_страницы, текст_страницы)
    """
    pages = []

    doc = fitz.open(pdf_path)

    for page_num in range(len(doc)):
        page = doc[page_num]
        # Используем "dict" для получения детальной информации о шрифтах и размерах
        text_dict = page.get_text("dict")
        
        # Собираем текстовые ЛИНИИ с координатами и информацией о шрифте
        # Это позволяет обнаруживать абзацы внутри больших текстовых блоков
        text_lines = []
        
        for block in text_dict.get("blocks", []):
            # Пропускаем изображения (block_type == 1)
            if block.get("type") == 1:
                continue

            if block.get("type") != 0:  # 0 = text block
                continue
                
            block_bbox = block.get("bbox", (0, 0, 0, 0))
            block_x0 = block_bbox[0]
            
            # Обрабатываем каждую линию в блоке отдельно
            for line in block.get("lines", []):
                line_bbox = line.get("bbox", (0, 0, 0, 0))
                y0, y1 = line_bbox[1], line_bbox[3]
                x0 = line_bbox[0]
                
                # Собираем текст из всех спанов в линии
                line_text_parts = []
                first_font = None
                first_size = None
                first_flags = 0
                
                for span in line.get("spans", []):
                    text = span.get("text", "").strip()
                    if text:
                        line_text_parts.append(text)
                        if first_font is None:
                            first_font = span.get("font", "")
                            first_size = span.get("size", 12.0)
                            first_flags = span.get("flags", 0)
                
                line_text = ' '.join(line_text_parts).strip()
                
                if line_text:
                    text_lines.append({
                        'y0': y0,
                        'y1': y1,
                        'x0': x0,
                        'text': line_text,
                        'font': first_font or '',
                        'size': first_size or 12.0,
                        'height': y1 - y0,
                        'flags': first_flags,
                        'block_x0': block_x0
                    })

        # Сортируем по вертикальной позиции (сверху вниз)
        text_lines.sort(key=lambda x: (x['y0'], x['x0']))

        # Вычисляем средний размер шрифта и высоту строки для этой страницы
        if text_lines:
            avg_font_size = sum(b['size'] for b in text_lines) / len(text_lines)
            avg_line_height = sum(b['height'] for b in text_lines) / len(text_lines)
        else:
            avg_font_size = 12.0
            avg_line_height = 14.0
        
        # Группируем линии в абзацы на основе нескольких критериев:
        # 1. Вертикальный промежуток между линиями
        # 2. Изменение шрифта/размера (заголовки)
        # 3. Выравнивание по левому краю
        # 4. Окончание предложения в предыдущей строке
        paragraphs = []
        
        if text_lines:
            current_para_lines = [text_lines[0]['text']]
            prev_line = text_lines[0]
            
            # Порог для нового абзаца: 1.3x от средней высоты строки
            # При avg_line_height ~15px это ~20px, что больше стандартного разрыва между
            # строками (~3px), но меньше разрыва между абзацами
            para_gap_threshold = avg_line_height * 1.3
            
            for i in range(1, len(text_lines)):
                curr_line = text_lines[i]
                
                # Вычисляем вертикальный промежуток между строками
                gap = curr_line['y0'] - prev_line['y1']
                
                # Проверяем несколько условий для нового абзаца:
                is_new_paragraph = False
                
                # 1. Большой вертикальный промежуток (основной критерий)
                if gap >= para_gap_threshold:
                    is_new_paragraph = True
                
                # 2. Значительное изменение размера шрифта (заголовок или подзаголовок)
                size_diff = abs(curr_line['size'] - prev_line['size'])
                if size_diff > 2.0:
                    is_new_paragraph = True
                
                # 3. Разное выравнивание (значительное изменение x0)
                # Учитываем только очень большие смещения (>150px), чтобы избежать ложных срабатываний
                # из-за разных текстовых блоков с небольшими отступами
                x_diff = abs(curr_line['x0'] - prev_line['x0'])
                if x_diff > 150:
                    is_new_paragraph = True
                
                # 4. Предыдущая строка заканчивается на точку, восклицательный или вопросительный знак
                # И есть заметный промежуток (больше высоты строки)
                prev_text = prev_line['text'].rstrip()
                prev_text_ends_with_punctuation = any(
                    prev_text.endswith(p)
                    for p in ['.', '!', '?']
                )
                # Создаём разрыв только если есть И окончание предложения И большой промежуток
                if prev_text_ends_with_punctuation and gap > avg_line_height:
                    is_new_paragraph = True
                
                # 5. Строка начинается с заглавной буквы после точки в предыдущей
                # и есть промежуток больше высоты строки
                curr_starts_with_cap = curr_line['text'][0].isupper() if curr_line['text'] else False
                if prev_text_ends_with_punctuation and curr_starts_with_cap and gap > avg_line_height:
                    is_new_paragraph = True
                
                if is_new_paragraph:
                    # Завершаем текущий абзац
                    paragraphs.append(' '.join(current_para_lines))
                    current_para_lines = [curr_line['text']]
                else:
                    # Продолжаем текущий абзац - соединяем строки пробелом
                    current_para_lines.append(curr_line['text'])
                
                prev_line = curr_line

            # Добавляем последний абзац
            if current_para_lines:
                paragraphs.append(' '.join(current_para_lines))

        # Формируем текст страницы - абзацы разделены двойными новыми строками
        page_text = '\n\n'.join(paragraphs)
        pages.append((page_num + 1, page_text))

    doc.close()

    return pages


def clean_text(text: str) -> str:
    """
    Очистить текст от лишних символов и нормализовать пробелы
    
    Сохраняет разрывы абзацев (двойные новые строки).
    """
    # Разделяем на абзацы по двойным новым строкам
    paragraphs = text.split('\n\n')
    
    cleaned_paragraphs = []
    for para in paragraphs:
        # Внутри абзаца убираем лишние пробелы и новые строки
        lines = []
        for line in para.split('\n'):
            cleaned = line.strip()
            if cleaned:
                lines.append(cleaned)
        
        # Собираем абзац обратно
        if lines:
            cleaned_paragraphs.append(' '.join(lines))
    
    # Соединяем абзацы двойными новыми строками
    return '\n\n'.join(cleaned_paragraphs)


def detect_headings(text: str) -> str:
    """
    Распознать заголовки и оформить их как Markdown заголовки

    Простая эвристика:
    - Короткие строки без точки в конце - возможные заголовки
    - Строки с номерами глав
    """
    lines = text.split('\n')
    result = []
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Пропускаем пустые строки
        if not line.strip():
            result.append('')
            i += 1
            continue
        
        # Проверка на заголовок главы (например, "Глава Первая", "Глава 1")
        if re.match(r'^глава\s+(первая|вторая|третья|четвертая|пятая|шестая|седьмая|восьмая|девятая|десятая|\d+)', line, re.IGNORECASE):
            result.append(f"# {line}")
            i += 1
            continue
        
        # Проверка на подзаголовок (короткая строка без точки в конце)
        if len(line) < 80 and not line.rstrip().endswith(('.', '!', '?', ':', ';', ',')):
            # Следующая строка не пустая и не продолжает предложение
            if i + 1 < len(lines) and lines[i + 1].strip():
                next_line = lines[i + 1]
                # Если следующая строка начинается с большой буквы или это короткий текст
                if len(line) < 50:
                    result.append(f"## {line}")
                    i += 1
                    continue
        
        result.append(line)
        i += 1
    
    return '\n'.join(result)


def format_paragraphs(text: str) -> str:
    """
    Форматировать текст с правильным разделением на абзацы
    
    Сохраняет существующие разрывы абзацев и нормализует их.
    """
    # Разделяем на абзацы по двойным новым строкам
    paragraphs = text.split('\n\n')
    
    formatted_paragraphs = []
    for para in paragraphs:
        para = para.strip()
        if para:
            # Проверяем, не является ли абзац служебным маркером
            if para.startswith('<!--') and para.endswith('-->'):
                formatted_paragraphs.append(para)
            else:
                formatted_paragraphs.append(para)
    
    # Соединяем абзацы двойными новыми строками
    return '\n\n'.join(formatted_paragraphs)


def convert_pdf_to_md(pdf_path: Path, output_path: Path) -> bool:
    """
    Конвертировать PDF в Markdown

    Args:
        pdf_path: Путь к PDF файлу
        output_path: Путь для сохранения MD файла

    Returns:
        True если успешно
    """
    logger.info(f"Конвертация: {pdf_path.name}")
    
    try:
        # Извлекаем текст по страницам
        pages = extract_pages_from_pdf(pdf_path)
        
        md_content = []
        
        for page_num, page_text in pages:
            # Добавляем маркер страницы
            md_content.append(f"<!-- Page {page_num} -->")
            md_content.append("")
            
            # Очищаем и форматируем текст
            cleaned = clean_text(page_text)
            formatted = format_paragraphs(cleaned)
            
            md_content.append(formatted)
            md_content.append("")
            md_content.append("")  # Дополнительный разделитель между страницами
        
        # Сохраняем результат
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text('\n'.join(md_content), encoding='utf-8')
        
        logger.success(f"  ✓ Сохранено: {output_path} ({len(pages)} страниц)")
        return True
        
    except Exception as e:
        logger.error(f"  ✗ Ошибка: {e}")
        return False


def convert_directory(input_dir: Path, output_dir: Path) -> dict:
    """
    Конвертировать все PDF из директории в Markdown

    Args:
        input_dir: Директория с PDF файлами
        output_dir: Директория для сохранения MD файлов

    Returns:
        Статистика конвертации
    """
    stats = {
        "success": 0,
        "failed": 0,
        "total_pages": 0,
    }
    
    if not input_dir.exists():
        logger.error(f"Директория не найдена: {input_dir}")
        return stats
    
    pdf_files = sorted(input_dir.glob("*.pdf"))
    
    if not pdf_files:
        logger.warning(f"PDF файлы не найдены: {input_dir}")
        return stats
    
    logger.info(f"Найдено PDF файлов: {len(pdf_files)}")
    logger.info("=" * 60)
    
    for pdf_path in pdf_files:
        if pdf_path.name.startswith('.'):
            continue
        
        # Формируем имя выходного файла
        md_filename = pdf_path.stem + ".md"
        md_path = output_dir / md_filename
        
        if convert_pdf_to_md(pdf_path, md_path):
            stats["success"] += 1
            
            # Считаем страницы
            try:
                doc = fitz.open(pdf_path)
                stats["total_pages"] += len(doc)
                doc.close()
            except Exception:
                pass
        else:
            stats["failed"] += 1
    
    logger.info("=" * 60)
    logger.info(f"Успешно: {stats['success']} | Ошибок: {stats['failed']}")
    logger.info(f"Всего страниц: {stats['total_pages']}")
    
    return stats


def main():
    """CLI для конвертации PDF в Markdown"""
    import argparse

    setup_logging()

    parser = argparse.ArgumentParser(
        description="Конвертация PDF файлов в Markdown с сохранением структуры",
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
        help="Директория для MD файлов (по умолчанию: data/documents/md_docs)",
    )

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("PDF to Markdown Converter")
    logger.info("=" * 60)
    logger.info(f"Входная директория: {args.input_dir}")
    logger.info(f"Выходная директория: {args.output_dir}")
    logger.info("=" * 60)

    stats = convert_directory(args.input_dir, args.output_dir)

    return 0


if __name__ == "__main__":
    sys.exit(main())
