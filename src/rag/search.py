"""
Скрипт поиска по векторной базе с выводом цитат и источников

Использование:
    python -m src.rag.search "Ваш вопрос"
    
Выводит релевантные цитаты с указанием:
- Источника (имя файла)
- Страницы
- Счета схожести
"""

import sys
from pathlib import Path
from typing import Optional

from loguru import logger

from src.rag.service import RAGService, ChunkResult


def setup_logging():
    """Настройка логирования"""
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO",
    )


def format_citation(result: ChunkResult, rank: int) -> str:
    """
    Форматировать результат поиска как цитату для пользователя

    Args:
        result: Результат поиска
        rank: Порядковый номер в выдаче

    Returns:
        Форматированная строка с цитатой
    """
    lines = [
        f"\n{'─' * 60}",
        f"📌 **Результат #{rank}** (релевантность: {result.score:.4f})",
        f"",
        f"📚 **Источник**: `{result.source}`",
        f"📑 **Страница**: {result.page}",
        f"🆔 **ID чанка**: `{result.chunk_id}`",
        f"",
        f"💬 **Цитата**:",
        f"> {result.content}",
    ]
    return "\n".join(lines)


def format_citations_short(results: list[ChunkResult]) -> str:
    """
    Краткий формат результатов (для Telegram)

    Args:
        results: Список результатов поиска

    Returns:
        Форматированный ответ
    """
    if not results:
        return "❌ Ничего не найдено по вашему запросу."

    lines = [
        f"🔍 **Найдено результатов: {len(results)}**",
        f"",
    ]

    for i, result in enumerate(results, 1):
        preview = result.content[:150] + "..." if len(result.content) > 150 else result.content
        lines.extend([
            f"**{i}.** {result.source} (стр. {result.page})",
            f"> {preview}",
            f"",
        ])

    lines.append(f"{'─' * 60}")
    lines.append("ℹ️ Используйте `--full` для просмотра полных цитат")

    return "\n".join(lines)


def search_query(
    query: str,
    rag_service: RAGService,
    top_k: int = 5,
    score_threshold: float = 0.0,
    verbose: bool = False,
) -> list[ChunkResult]:
    """
    Выполнить поиск по векторной базе

    Args:
        query: Запрос пользователя
        rag_service: RAG сервис
        top_k: Количество результатов
        score_threshold: Порог схожести
        verbose: Показывать подробную информацию

    Returns:
        Список результатов поиска
    """
    logger.info(f"Поиск: {query}")
    logger.info(f"Параметры: top_k={top_k}, threshold={score_threshold}")

    results = rag_service.query_with_metadata(
        query,
        top_k=top_k,
        score_threshold=score_threshold,
    )

    if not results:
        logger.warning("Ничего не найдено")
        return []

    logger.success(f"Найдено {len(results)} результатов")

    if verbose:
        logger.info("=" * 60)
        for i, result in enumerate(results, 1):
            logger.info(format_citation(result, i))
        logger.info("=" * 60)

    return results


def interactive_search(rag_service: RAGService, top_k: int = 5):
    """
    Интерактивный режим поиска

    Args:
        rag_service: RAG сервис
        top_k: Количество результатов по умолчанию
    """
    print("\n" + "=" * 60)
    print("🔍 Интерактивный поиск по векторной базе")
    print("=" * 60)
    print("Команды:")
    print("  quit, exit, q - выход")
    print("  k=N - изменить количество результатов (например, k=10)")
    print("  t=N - изменить порог схожести (например, t=0.5)")
    print("=" * 60)
    print()

    current_top_k = top_k
    current_threshold = 0.0

    while True:
        try:
            query = input("Ваш вопрос> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nПоиск завершен")
            break

        if not query:
            continue

        # Проверка на команды
        query_lower = query.lower()
        
        if query_lower in ('quit', 'exit', 'q', 'выход'):
            print("Выход из интерактивного режима")
            break

        # Команда изменения top_k
        if query_lower.startswith('k='):
            try:
                current_top_k = int(query[2:])
                print(f"✓ Количество результатов: {current_top_k}")
            except ValueError:
                print("✗ Ошибка: укажите число (например, k=10)")
            continue

        # Команда изменения threshold
        if query_lower.startswith('t='):
            try:
                current_threshold = float(query[2:])
                print(f"✓ Порог схожести: {current_threshold}")
            except ValueError:
                print("✗ Ошибка: укажите число (например, t=0.5)")
            continue

        # Обычный поиск
        results = search_query(
            query,
            rag_service,
            top_k=current_top_k,
            score_threshold=current_threshold,
            verbose=False,
        )

        if results:
            # Вывод в кратком формате
            print(format_citations_short(results))
            
            # Предлагаем показать детали
            show_full = input("\nПоказать полные цитаты? (y/n)> ").strip().lower()
            if show_full == 'y':
                for i, result in enumerate(results, 1):
                    print(format_citation(result, i))
                print()


def main():
    """CLI для поиска по векторной базе"""
    import argparse

    setup_logging()

    parser = argparse.ArgumentParser(
        description="Поиск по векторной базе с цитатами и источниками",
    )
    parser.add_argument(
        "query",
        type=str,
        nargs="?",
        help="Запрос для поиска",
    )
    parser.add_argument(
        "--top-k", "-k",
        type=int,
        default=5,
        help="Количество результатов (по умолчанию: 5)",
    )
    parser.add_argument(
        "--threshold", "-t",
        type=float,
        default=0.0,
        help="Порог схожести (по умолчанию: 0.0)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Показывать подробную информацию",
    )
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Интерактивный режим поиска",
    )
    parser.add_argument(
        "--short", "-s",
        action="store_true",
        help="Краткий формат вывода (для Telegram)",
    )

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("RAG Search Engine")
    logger.info("=" * 60)

    # Инициализация RAG сервиса
    try:
        rag_service = RAGService()
        doc_count = rag_service.get_document_count()
        logger.info(f"Документов в базе: {doc_count}")
        
        if doc_count == 0:
            logger.error("Векторная база пуста! Сначала добавьте документы.")
            logger.info("Используйте: python -m src.rag.chunker --input-dir data/documents")
            return 1
            
    except Exception as e:
        logger.error(f"Ошибка инициализации RAG: {e}")
        return 1

    # Интерактивный режим
    if args.interactive:
        interactive_search(rag_service, top_k=args.top_k)
        return 0

    # Единичный запрос
    if args.query:
        results = search_query(
            args.query,
            rag_service,
            top_k=args.top_k,
            score_threshold=args.threshold,
            verbose=args.verbose,
        )

        if not results:
            print("\n❌ Ничего не найдено")
            return 1

        if args.short:
            # Краткий формат для Telegram
            print(format_citations_short(results))
        else:
            # Подробный формат
            print("\n" + "=" * 60)
            print("📊 РЕЗУЛЬТАТЫ ПОИСКА")
            print("=" * 60)
            
            for i, result in enumerate(results, 1):
                print(format_citation(result, i))
            
            print("\n" + "=" * 60)
    else:
        # Нет запроса и не интерактивный режим
        logger.info("Укажите запрос или используйте --interactive для интерактивного режима")
        parser.print_help()

    return 0


if __name__ == "__main__":
    sys.exit(main())
