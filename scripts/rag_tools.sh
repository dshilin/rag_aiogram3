#!/usr/bin/env bash
# Скрипт разбиения PDF документов на чанки и поиска по векторной базе

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

print_header() {
    echo -e "${BLUE}============================================================${NC}"
    echo -e "${BLUE} $1${NC}"
    echo -e "${BLUE}============================================================${NC}"
}

print_usage() {
    echo ""
    print_header "RAG Tools"
    echo ""
    echo "Использование:"
    echo "  $0 chunk [OPTIONS]  - Разбиение документов на чанки"
    echo "  $0 search [OPTIONS] - Поиск по векторной базе"
    echo "  $0 full [OPTIONS]   - Разбиение + индексация + поиск"
    echo ""
    echo "Команды:"
    echo ""
    echo "  chunk - Разбиение PDF на чанки по абзацам"
    echo "    --input-dir DIR    Директория с PDF (по умолчанию: data/documents)"
    echo "    --output-dir DIR   Директория для чанков (по умолчанию: data/documents/chunks)"
    echo "    --no-save          Не сохранять чанки на диск"
    echo ""
    echo "  search - Поиск по векторной базе"
    echo "    --query TEXT       Запрос для поиска"
    echo "    --top-k N          Количество результатов (по умолчанию: 5)"
    echo "    --interactive      Интерактивный режим"
    echo ""
    echo "  full - Полный цикл: разбиение + индексация + поиск"
    echo "    --query TEXT       Запрос для поиска после индексации"
    echo "    --input-dir DIR    Директория с PDF"
    echo "    --clear            Очистить векторную базу перед индексацией"
    echo ""
    echo "Примеры:"
    echo "  $0 chunk                                    # Разбить все PDF в data/documents"
    echo "  $0 search --query \"Что такое RAG?\"         # Найти информацию о RAG"
    echo "  $0 search --interactive                     # Интерактивный поиск"
    echo "  $0 full --query \"Архитектура системы\"       # Полный цикл с поиском"
    echo ""
}

# Parse command
COMMAND="$1"
shift || true

case "$COMMAND" in
    chunk)
        print_header "Разбиение документов на чанки"
        python -m src.rag.chunker "$@"
        ;;
    
    search)
        print_header "Поиск по векторной базе"
        python -m src.rag.search "$@"
        ;;
    
    full)
        print_header "Полный цикл RAG"
        
        # Step 1: Chunking
        echo -e "${GREEN}[1/3] Разбиение документов на чанки...${NC}"
        python -m src.rag.chunker "$@"
        
        # Step 2: Indexing
        echo ""
        echo -e "${GREEN}[2/3] Индексация чанков в векторной базе...${NC}"
        python -m src.rag.chunk_loader --clear
        if [[ "$*" == *"--clear"* ]]; then
            # Already passed to chunker, remove for chunk_loader
            python -m src.rag.chunk_loader
        else
            python -m src.rag.chunk_loader
        fi
        
        # Step 3: Search
        echo ""
        echo -e "${GREEN}[3/3] Поиск...${NC}"
        # Extract query from arguments
        QUERY=""
        if [[ "$*" == *"--query"* ]]; then
            # Get the value after --query
            QUERY=$(echo "$@" | grep -oP '(?<=--query\s)[^ ]+' | head -1)
        fi
        
        if [[ -n "$QUERY" ]]; then
            python -m src.rag.search "$QUERY" --verbose
        else
            echo -e "${YELLOW}Запрос не указан. Пропускаем поиск.${NC}"
            echo "Добавьте --query \"ваш вопрос\" для поиска после индексации"
        fi
        ;;
    
    help|--help|-h|"")
        print_usage
        ;;
    
    *)
        echo -e "${RED}Неизвестная команда: $COMMAND${NC}"
        print_usage
        exit 1
        ;;
esac
