# Logging System Documentation

## Overview

The enhanced logging system provides comprehensive tracking of:
- **All user messages** (with user ID and username)
- **Complete call flow** through the application
- **Request tracing** with unique IDs per conversation
- **Error tracking** with detailed context

## Log Level Recommendation

**Use `DEBUG` level** for the following reasons:

1. **User Message Tracking**: Every user message is logged with user ID and username
2. **Call Flow Tracing**: Complete visibility into function calls and execution order
3. **Request Correlation**: Each conversation gets a unique request ID for easy debugging
4. **Structured Output**: Logs are organized into separate files by category

## Log Files

All logs are stored in the `logs/` directory:

| File | Purpose | Retention |
|------|---------|-----------|
| `app_YYYY-MM-DD.log` | All application logs (DEBUG level) | 7 days |
| `errors_YYYY-MM-DD.log` | Error logs only | 30 days |
| `user_messages_YYYY-MM-DD.log` | User messages only | 30 days |
| `call_flow_YYYY-MM-DD.log` | Function call traces | 7 days |

## Features

### 1. Request ID Tracking

Each user interaction gets a unique request ID (8 characters):
```
2026-02-27 10:15:30 | INFO     | src.bot.handlers:handle_text:78 | a3f5d8e1 | USER [12345] @username: What is RAG?
2026-02-27 10:15:30 | DEBUG    | src.rag.service:query_with_metadata:165 | a3f5d8e1 | RAG query: 'What is RAG?...' top_k=3
```

### 2. Call Flow Tracing

Every function call is traced with entry/exit points:
```
2026-02-27 10:15:30 | DEBUG    | src.rag.service:add_documents:120 | a3f5d8e1 | [a3f5d8e1] ENTER → src.rag.service.RAGService.add_documents(...)
2026-02-27 10:15:31 | DEBUG    | src.rag.service:add_documents:134 | a3f5d8e1 | [a3f5d8e1] EXIT  ← src.rag.service:add_documents = Successfully added 1 documents
```

### 3. User Message Logging

All user messages are logged separately:
```
2026-02-27 10:15:30 | USER [12345] @username: What is RAG?
```

### 4. Error Tracking

Errors include full context and request ID:
```
2026-02-27 10:15:35 | ERROR    | src.llm.yandex_gpt:ask:145 | a3f5d8e1 | YandexGPT error 400: invalid model_uri
```

## Usage

### Decorator for Call Tracing

```python
from src.utils.logging import trace

@trace()  # Default: shows args and result
async def my_function(arg1, arg2):
    return result

@trace(show_args=False)  # Hide arguments
async def sensitive_function(secret_data):
    pass

@trace(show_result=False)  # Hide result
async def large_result_function():
    return "very long string..."
```

### Logging User Messages

```python
from src.utils.logging import log_user_message, log_call_flow

# Log user message
log_user_message(
    user_id=message.from_user.id,
    username=message.from_user.username,
    message_text=message.text
)

# Log call flow
log_call_flow("Custom message about execution flow")
```

### Request ID Management

```python
from src.utils.logging import generate_request_id, set_request_id, get_request_id

# Generate new request ID for each user interaction
request_id = generate_request_id()
set_request_id(request_id)

# Get current request ID (used automatically in logs)
current_id = get_request_id()
```

## Configuration

Set log level in `.env`:

```bash
# For development - full logging
LOG_LEVEL=DEBUG

# For production - less verbose
LOG_LEVEL=INFO
```

## Log Format

### Console (with colors):
```
2026-02-27 10:15:30 | INFO     | src.bot.handlers:handle_text:78 | a3f5d8e1 | User message received
```

### File:
```
2026-02-27 10:15:30 | INFO     | src.bot.handlers:handle_text:78 | a3f5d8e1 | User message received
```

## Example Log Output

```
2026-02-27 10:15:30 | INFO     | src.main:main:17 | b7c2e9f1 | Бот запускается...
2026-02-27 10:15:45 | INFO     | src.bot.handlers:handle_text:82 | a3f5d8e1 | USER [12345] @john_doe: What is RAG?
2026-02-27 10:15:45 | DEBUG    | src.bot.handlers:handle_text:85 | a3f5d8e1 | Processing text message from user 12345
2026-02-27 10:15:45 | DEBUG    | src.rag.service:query_with_metadata:165 | a3f5d8e1 | RAG query: 'What is RAG?...' top_k=3
2026-02-27 10:15:46 | DEBUG    | src.rag.service:query_with_metadata:188 | a3f5d8e1 | RAG query returned 3 results
2026-02-27 10:15:46 | DEBUG    | src.llm.yandex_gpt:ask:77 | a3f5d8e1 | YandexGPT request: 'What is RAG?...' with context=True
2026-02-27 10:15:47 | DEBUG    | src.llm.yandex_gpt:ask:134 | a3f5d8e1 | YandexGPT response received: 'RAG stands for...'
2026-02-27 10:15:47 | DEBUG    | src.bot.handlers:handle_text:108 | a3f5d8e1 | Sending response to user 12345
```

## Benefits

1. **Debugging**: Easy to trace issues with request IDs
2. **Audit Trail**: Complete record of all user interactions
3. **Performance Analysis**: Identify slow function calls
4. **Error Investigation**: Full context for every error
5. **User Analytics**: Track usage patterns via user_messages log
