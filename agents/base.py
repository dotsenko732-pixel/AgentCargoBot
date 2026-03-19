"""Base agent with Claude API integration."""

import json
import logging

import anthropic

from config import settings

logger = logging.getLogger(__name__)


class BaseAgent:
    """Base class for all AI agents."""

    def __init__(self, system_prompt: str):
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.system_prompt = system_prompt

    async def ask(self, user_message: str) -> str:
        try:
            response = await self.client.messages.create(
                model=settings.claude_model,
                max_tokens=settings.claude_max_tokens,
                system=self.system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            return response.content[0].text
        except Exception as e:
            logger.error("Agent error: %s", e)
            return f"Ошибка агента: {e}"

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
