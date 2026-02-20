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

try:
    from loguru import logger
except Exception:
    import logging
    logging.basicConfig(
        stream=sys.stdout,
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
    )
    _logger = logging.getLogger("clean_markdown")

    class _SimpleLogger:
        def remove(self):
            return None

        def add(self, *args, **kwargs):
            return None

        def info(self, msg, *a, **k):
            _logger.info(msg)

        def warning(self, msg, *a, **k):
            _logger.warning(msg)

        def error(self, msg, *a, **k):
            _logger.error(msg)

        def success(self, msg, *a, **k):
            _logger.info(msg)

    logger = _SimpleLogger()


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
    consecutive_empty = 0

    # Проходим с индексом, чтобы смотреть вперед/назад для склеивания строк
    for idx, raw_line in enumerate(lines):
        # Сохраняем маркеры страниц (оставляем в каноническом виде)
        if raw_line.strip().startswith("<!-- Page"):
            match = re.search(r'Page\s*(\d+)', raw_line)
            if match:
                page_marker = f"<!-- Page {match.group(1)} -->"
                cleaned_lines.append(page_marker)
                cleaned_lines.append("")  # Пустая строка после маркера
                prev_line = ""
                consecutive_empty = 1
            continue

        stripped = raw_line.strip()

        # Пустые строки — сохраняем, но контролируем подряд идущие
        if not stripped:
            consecutive_empty += 1
            if consecutive_empty > 2:
                continue
            cleaned_lines.append("")
            prev_line = ""
            continue

        # Попытка склеить однословную строку с предыдущей, если это не маркер и предыдущая строка не пустая
        # Условие: текущая строка — одно слово (без пробелов), не маркированный пункт, и предыдущая реальная строка есть
        if " " not in stripped and cleaned_lines:
            last = cleaned_lines[-1]
            if last != "" and not isinstance(last, type(None)) and not last.strip().startswith("<!-- Page"):
                # Не склеивать с предыдущей строкой, если она похожа на запись оглавления (много точек + номер страницы)
                if re.search(r'\.{2,}\s*\d+\s*$', last):
                    # предыдущая строка похожа на запись в оглавлении — пропустить склейку
                    pass
                else:
                    # Исключаем явные маркеры списка/заголовков
                    if not re.match(r'^[\-\*\d\)\.]', stripped):
                        # Если предыдущая строка не заканчивается на точку/вопрос/воскл/двоиточие, то вероятно перенос в середине предложения
                        if not re.search(r'[\.\!\?\:\—\-]$', last.strip()):
                            # Если предыдущая строка заканчивается дефисом (перенос слова), склеиваем без пробела
                            if last.endswith("-") or last.endswith("‑"):
                                cleaned_lines[-1] = last.rstrip("-‑") + stripped
                            else:
                                cleaned_lines[-1] = last + " " + stripped
                            prev_line = cleaned_lines[-1]
                            consecutive_empty = 0
                            continue

        # Обычная очистка строки
        cleaned = clean_line(raw_line)
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
    dry_run = getattr(process_file, "dry_run", False)
    do_backup = getattr(process_file, "do_backup", True)

    if cleaned_size < original_size:
        reduction = ((original_size - cleaned_size) / original_size) * 100
        if dry_run:
            logger.info(f"(dry-run) ✓ {file_path.name}: {original_size} → {cleaned_size} символов (-{reduction:.1f}%)")
        else:
            # Создаём .bak резервную копию если нужно
            if do_backup:
                # file.md -> file.md.bak, если занято -> file.md.bak1, ...
                suffix = file_path.suffix + ".bak"
                backup_path = file_path.with_suffix(suffix)
                idx = 1
                while backup_path.exists():
                    backup_path = file_path.with_suffix(suffix + str(idx))
                    idx += 1
                try:
                    backup_path.write_bytes(file_path.read_bytes())
                    logger.info(f"Создана резервная копия: {backup_path.name}")
                except Exception as e:
                    logger.warning(f"Не удалось создать резервную копию {backup_path}: {e}")

            file_path.write_text(cleaned_content, encoding="utf-8")
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
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Не изменять файлы, только показать, что бы изменилось",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Не создавать резервные .bak копии перед перезаписью",
    )
    
    args = parser.parse_args()

    # Добавляем опции dry-run и backup в функцию process_file через атрибуты
    process_file.dry_run = False
    process_file.do_backup = True

    if args.dry_run:
        process_file.dry_run = True
    if args.no_backup:
        process_file.do_backup = False
    
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
