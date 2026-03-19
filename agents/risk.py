"""Agent-Risk: carrier verification and risk scoring."""

from agents.base import BaseAgent

SYSTEM_PROMPT = """\
Ты — Agent-Risk, AI-агент биржи грузоперевозок AgentCargoBot.
Твоя задача: оценить надёжность перевозчика и риски сделки.

Анализируй следующие данные:
1. Рейтинг перевозчика (0–5)
2. Количество завершённых сделок
3. Отзывы (текст и оценки)
4. Верификация аккаунта (документы проверены?)
5. Возраст аккаунта
6. Соответствие цены рыночной (слишком дёшево = подозрительно)

Уровни риска:
- LOW (зелёный): рейтинг > 4.0, 10+ сделок, верифицирован
- MEDIUM (жёлтый): рейтинг 3.0–4.0 или < 10 сделок или не верифицирован
- HIGH (красный): рейтинг < 3.0, или негативные отзывы, или новый аккаунт + низкая цена

Ответ ВСЕГДА в формате JSON:
{
  "risk_level": "LOW",
  "risk_score": 15,
  "factors": [
    {"factor": "Высокий рейтинг 4.7", "impact": "positive"},
    {"factor": "42 завершённые сделки", "impact": "positive"},
    {"factor": "Аккаунт верифицирован", "impact": "positive"}
  ],
  "recommendation": "Надёжный перевозчик. Рекомендуем к сотрудничеству.",
  "warnings": []
}

Язык ответов: русский.
"""


class RiskAgent(BaseAgent):
    def __init__(self):
        super().__init__(SYSTEM_PROMPT)

    async def assess_carrier(self, carrier_data: dict, reviews: list[dict]) -> dict:
        prompt = (
            f"Оцени надёжность перевозчика:\n"
            f"  Имя: {carrier_data.get('full_name')}\n"
            f"  Компания: {carrier_data.get('company_name', 'Частное лицо')}\n"
            f"  Рейтинг: {carrier_data.get('rating', 0)}\n"
            f"  Сделок: {carrier_data.get('total_deals', 0)}\n"
            f"  Верифицирован: {'Да' if carrier_data.get('is_verified') else 'Нет'}\n"
            f"  На платформе с: {carrier_data.get('created_at', 'N/A')}\n\n"
            f"Отзывы ({len(reviews)} шт.):\n"
        )
        for r in reviews[:10]:  # limit to 10 most recent
            prompt += f"  - Оценка {r.get('rating')}/5: {r.get('comment', 'Без комментария')}\n"

        if not reviews:
            prompt += "  Отзывов пока нет.\n"

        return await self.ask_json(prompt)

    async def assess_deal(
        self, carrier_data: dict, cargo_data: dict, proposed_price: float
    ) -> dict:
        prompt = (
            f"Оцени риски сделки:\n"
            f"  Перевозчик: {carrier_data.get('full_name')} "
            f"(рейтинг {carrier_data.get('rating', 0)}, "
            f"сделок {carrier_data.get('total_deals', 0)})\n"
            f"  Груз: {cargo_data.get('title')} "
            f"({cargo_data.get('origin_city')} → {cargo_data.get('destination_city')})\n"
            f"  Предложенная цена: {proposed_price} {cargo_data.get('currency', 'KGS')}\n"
            f"  Бюджет заказчика: {cargo_data.get('budget_min', '?')}–"
            f"{cargo_data.get('budget_max', '?')} {cargo_data.get('currency', 'KGS')}\n"
        )
        return await self.ask_json(prompt)
