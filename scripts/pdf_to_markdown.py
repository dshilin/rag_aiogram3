"""
Утилита для конвертации PDF файлов в Markdown

Использование:
    python scripts/pdf_to_markdown.py [--input-dir INPUT_DIR] [--output-dir OUTPUT_DIR]

Аргументы:
    --input-dir   Директория с PDF файлами (по умолчанию: data/documents/pdf_docs)
    --output-dir  Директория для сохранения Markdown (по умолчанию: data/documents/md_docs)
"""

import argparse
import sys
from pathlib import Path

import fitz  # PyMuPDF
from loguru import logger


def setup_logging():
    """Настроить логирование"""
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO",
    )


def pdf_to_markdown(pdf_path: Path) -> str:
    """
    Конвертировать PDF файл в Markdown формат
    
    Args:
        pdf_path: Путь к PDF файлу
        
    Returns:
        Текст в формате Markdown
    """
    logger.info(f"Обработка файла: {pdf_path.name}")
    
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        logger.error(f"Ошибка открытия файла {pdf_path.name}: {e}")
        return ""
    
    markdown_content = []
    
    for page_num, page in enumerate(doc, 1):
        logger.debug(f"  Страница {page_num}/{len(doc)}")
        
        # Добавляем заголовок страницы
        markdown_content.append(f"<!-- Page {page_num} -->\n")
        
        # Получаем текст с страницы
        text = page.get_text("text")
        
        if text.strip():
            # Очищаем текст и добавляем в markdown
            lines = text.split('\n')
            cleaned_lines = []
            
            for line in lines:
                stripped = line.strip()
                if stripped:
                    cleaned_lines.append(stripped)
                elif cleaned_lines:  # Сохраняем пустые строки только между блоками текста
                    cleaned_lines.append('')
            
            markdown_content.append('\n'.join(cleaned_lines))
        
        # Проверяем наличие изображений
        image_list = page.get_images(full=True)
        if image_list:
            markdown_content.append(f"\n*[{len(image_list)} изображений на странице {page_num}]*\n")
    
    doc.close()
    
    return '\n\n'.join(markdown_content)


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
            markdown_text = pdf_to_markdown(pdf_file)
            
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
