"""DeepSeek LLM adapter via OpenAI-compatible SDK."""

from __future__ import annotations

import os

import structlog
from openai import OpenAI

from chill_agent.services.llm.base import LLMResult
from chill_agent.utils.retry import with_retry

logger = structlog.get_logger()


class DeepSeekClient:
    """Thin wrapper around DeepSeek API using the openai SDK."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-chat",
    ) -> None:
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    @with_retry(attempts=3, backoff=(2.0, 8.0, 30.0))
    def complete(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 1.0,
        json_mode: bool = False,
        max_tokens: int = 8192,
    ) -> LLMResult:
        kwargs: dict = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        logger.debug(
            "llm_request",
            model=self._model,
            temperature=temperature,
            json_mode=json_mode,
            prompt_chars=len(system) + len(user),
        )

        response = self._client.chat.completions.create(**kwargs)

        result = LLMResult(
            content=response.choices[0].message.content or "",
            input_tokens=response.usage.prompt_tokens if response.usage else 0,
            output_tokens=response.usage.completion_tokens if response.usage else 0,
            model=self._model,
        )

        logger.debug(
            "llm_response",
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            content_chars=len(result.content),
        )

        return result
