"""Base agent with DeepSeek API integration (OpenAI-compatible)."""

import json
import logging

from openai import AsyncOpenAI

from config import settings

logger = logging.getLogger(__name__)


class BaseAgent:
    """Base class for all AI agents."""

    def __init__(self, system_prompt: str):
        self.client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )
        self.system_prompt = system_prompt

    async def ask(self, user_message: str) -> str:
        try:
            response = await self.client.chat.completions.create(
                model=settings.deepseek_model,
                max_tokens=settings.deepseek_max_tokens,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_message},
                ],
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error("Agent error: %s", e)
            raise

    async def ask_json(self, user_message: str) -> dict:
        raw = await self.ask(user_message)
        # Extract JSON from response (handle markdown code blocks)
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = lines[1:]  # skip ```json
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON from agent response: %s", raw[:200])
            return {"error": "parse_error", "raw": raw}
