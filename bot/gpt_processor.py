import asyncio
import logging
import random
from typing import List, Sequence

from openai import OpenAI

from config.settings import SETTINGS


LOGGER = logging.getLogger(__name__)


BATCH_TASK_EXTRACTION_PROMPT = """
Ты - ассистент для анализа диалога между разработческой студией и клиентами.
Твоя задача: проанализировать все сообщения клиентов за последний час и извлечь из них конкретные задачи или запросы на разработку.

Правила:
1. Анализируй ВЕСЬ контекст диалога, не каждое сообщение отдельно
2. Извлекай только четкие задачи и технические требования
3. Игнорируй благодарности, приветствия и общую переписку
4. Объединяй связанные задачи в одну, если они касаются одной функции
5. Каждую задачу формулируй кратко и ясно
6. Если задач нет - ответь "Нет задач"

Формат ответа - список задач, каждая с новой строки:
- Задача 1
- Задача 2
- Задача 3

Сообщения клиентов за последний час:
{messages_context}

Извлеченные задачи:
"""


def _parse_tasks_from_output(text: str) -> List[str]:
    lines = [line.strip("- ") for line in text.splitlines() if line.strip()]
    if not lines:
        return []
    if any("нет задач" in line.lower() for line in lines):
        return []
    return [line for line in lines if line]


def _create_openai_client() -> OpenAI:
    return OpenAI(api_key=SETTINGS.openai_api_key)


async def process_messages_batch_with_gpt(messages_list: Sequence[dict], timeout_seconds: int = 60) -> List[str]:
    client = _create_openai_client()
    # Prepare prompt
    from utils.formatters import format_messages_for_processing

    messages_context = format_messages_for_processing(messages_list)
    prompt = BATCH_TASK_EXTRACTION_PROMPT.format(messages_context=messages_context)

    async def _call_api_with_retry() -> str:
        max_attempts = 5
        base_delay = 1.5
        for attempt in range(1, max_attempts + 1):
            try:
                from config.settings import SETTINGS
                LOGGER.info("Calling OpenAI %s for batch processing, attempt %s", SETTINGS.gpt_model, attempt)
                # OpenAI v1.3.0 sync client; run in thread to respect asyncio
                def _sync_call() -> str:
                    resp = client.chat.completions.create(
                        model=SETTINGS.gpt_model,
                        messages=[
                            {"role": "system", "content": "Ты эксперт по извлечению задач."},
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0.2,
                    )
                    return resp.choices[0].message.content or ""

                content = await asyncio.to_thread(_sync_call)
                return content
            except Exception as exc:
                LOGGER.warning("OpenAI API error on attempt %s: %s", attempt, exc)
                if attempt == max_attempts:
                    raise
                # Exponential backoff with jitter
                delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                await asyncio.sleep(delay)

    content = await asyncio.wait_for(_call_api_with_retry(), timeout=timeout_seconds)
    tasks = _parse_tasks_from_output(content)
    LOGGER.info("Parsed %s tasks from GPT output", len(tasks))
    return tasks


