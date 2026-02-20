"""
Утилита для очистки Markdown файлов от мусора

Сохраняет разметку по страницам (<!-- Page X -->), удаляет:
- Короткие строки (< 3 символов)
- Строки только из спецсимволов
- Повторяющиеся подряд строки
- Лишние пустые строки

Использование:
    python scripts/clean_markdown.py [--input-dir INPUT_DIR]

Аргументы:
    --input-dir   Директория с Markdown файлами (по умолчанию: data/documents/md_docs)
"""

import argparse
import re
import sys
from pathlib import Path

from loguru import logger


def setup_logging():
    """Настроить логирование"""
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO",
    )


def clean_line(line: str) -> str | None:
    """
    Очистить одну строку текста
    
    Returns:
        Очищенную строку или None, если строку нужно удалить
    """
    # Удаляем leading/trailing пробелы
    stripped = line.strip()
    
    # Пустые строки сохраняем (для разделения абзацев)
    if not stripped:
        return ""
    
    # Удаляем строки короче 2 символов (кроме маркеров страниц)
    if len(stripped) < 2 and not stripped.startswith("<!--"):
        return None
    
    # Удаляем строки, состоящие только из спецсимволов
    if re.match(r'^[^a-zA-Zа-яА-Я0-9]+$', stripped):
        return None
    
    # Удаляем изолированные символы (кроме маркеров страниц)
    if len(stripped) <= 3 and not stripped.startswith("<!--"):
        # Проверяем, не является ли это частью нумерации или маркированного списка
        if not re.match(r'^[\d\-\*\•]\.?$', stripped):
            return None
    
    return stripped


def clean_markdown_content(content: str) -> str:
    """
    Очистить Markdown контент от мусора
    
    Args:
        content: Исходный текст
        
    Returns:
        Очищенный текст
    """
    lines = content.split('\n')
    cleaned_lines = []
    prev_line = None
    page_marker = None
    consecutive_empty = 0
    
    for line in lines:
        # Сохраняем маркеры страниц
        if line.strip().startswith("<!-- Page"):
            # Извлекаем номер страницы
            match = re.search(r'Page\s*(\d+)', line)
            if match:
                page_marker = f"<!-- Page {match.group(1)} -->"
                cleaned_lines.append(page_marker)
                cleaned_lines.append("")  # Пустая строка после маркера
                prev_line = ""
                consecutive_empty = 1
            continue
        
        # Очищаем строку
        cleaned = clean_line(line)
        
        if cleaned is None:
            continue
        
        # Пропускаем дубликаты подряд идущих строк
        if cleaned == prev_line and cleaned != "":
            continue
        
        # Контролируем количество пустых строк подряд (максимум 2)
        if cleaned == "":
            consecutive_empty += 1
            if consecutive_empty > 2:
                continue
        else:
            consecutive_empty = 0
        
        cleaned_lines.append(cleaned)
        prev_line = cleaned
    
    # Удаляем лишние пустые строки в начале и конце
    while cleaned_lines and cleaned_lines[0] == "":
        cleaned_lines.pop(0)
    while cleaned_lines and cleaned_lines[-1] == "":
        cleaned_lines.pop()
    
    return '\n'.join(cleaned_lines)


def process_file(file_path: Path) -> tuple[int, int]:
    """
    Обработать один файл
    
    Args:
        file_path: Путь к файлу
        
    Returns:
        (исходный размер, новый размер) в символах
    """
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as e:
        logger.error(f"Ошибка чтения {file_path.name}: {e}")
        return 0, 0
    
    original_size = len(content)
    cleaned_content = clean_markdown_content(content)
    cleaned_size = len(cleaned_content)
    
    # Записываем только если есть изменения
    if cleaned_size < original_size:
        file_path.write_text(cleaned_content, encoding="utf-8")
        reduction = ((original_size - cleaned_size) / original_size) * 100
        logger.success(f"✓ {file_path.name}: {original_size} → {cleaned_size} символов (-{reduction:.1f}%)")
    else:
        logger.info(f"= {file_path.name}: без изменений")
    
    return original_size, cleaned_size


def clean_directory(input_dir: Path) -> dict:
    """
    Очистить все Markdown файлы в директории
    
    Args:
        input_dir: Директория с Markdown файлами
        
    Returns:
        Статистика обработки
    """
    stats = {
        "files": 0,
        "total_original": 0,
        "total_cleaned": 0,
        "skipped": 0,
    }
    
    if not input_dir.exists():
        logger.error(f"Директория не найдена: {input_dir}")
        return stats
    
    md_files = list(input_dir.glob("*.md"))
    
    if not md_files:
        logger.warning(f"Markdown файлы не найдены в {input_dir}")
        return stats
    
    stats["files"] = len(md_files)
    logger.info(f"Найдено Markdown файлов: {stats['files']}")
    logger.info("=" * 60)
    
    for md_file in md_files:
        original, cleaned = process_file(md_file)
        stats["total_original"] += original
        stats["total_cleaned"] += cleaned
        
        if cleaned == 0 and original == 0:
            stats["skipped"] += 1
    
    logger.info("=" * 60)
    
    total_reduction = 0
    if stats["total_original"] > 0:
        total_reduction = (
            (stats["total_original"] - stats["total_cleaned"]) / stats["total_original"]
        ) * 100
    
    logger.info(f"Всего: {stats['total_original']} → {stats['total_cleaned']} символов (-{total_reduction:.1f}%)")
    logger.info(f"Обработано: {stats['files'] - stats['skipped']} | Пропущено: {stats['skipped']}")
    
    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Очистка Markdown файлов от мусора",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("data/documents/md_docs"),
        help="Директория с Markdown файлами (по умолчанию: data/documents/md_docs)",
    )
    
    args = parser.parse_args()
    
    setup_logging()
    
    logger.info("=" * 60)
    logger.info("Markdown Cleaner")
    logger.info("=" * 60)
    logger.info(f"Директория: {args.input_dir}")
    logger.info("=" * 60)
    
    stats = clean_directory(args.input_dir)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
