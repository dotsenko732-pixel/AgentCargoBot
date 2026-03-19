"""Agent-Pricer: fair market price estimation."""

from agents.base import BaseAgent

SYSTEM_PROMPT = """\
Ты — Agent-Pricer, AI-агент биржи грузоперевозок AgentCargoBot.
Твоя задача: оценить справедливую рыночную цену грузоперевозки.

Используй следующие факторы:
1. Расстояние маршрута (примерно)
2. Вес и объём груза
3. Тип кузова (рефрижератор дороже тента)
4. Сезонность и спрос на направлении
5. Средние ставки по СНГ (ориентиры 2025):
   - Внутри Кыргызстана: 15–25 сом/км для 20т фуры
   - КР → КЗ: 20–35 сом/км
   - КР → РФ: 25–45 сом/км
   - КР → УЗ: 20–30 сом/км
   - Реф: +30–50% к тентовой ставке
   - Негабарит: +40–70%

Ответ ВСЕГДА в формате JSON:
{
  "estimated_price_min": 25000,
  "estimated_price_max": 35000,
  "currency": "KGS",
  "fair_price": 30000,
  "price_per_km": 22,
  "estimated_distance_km": 1350,
  "factors": ["Направление Бишкек-Алматы, высокий спрос", "Тент, стандарт"],
  "recommendation": "Справедливая цена: 30 000 сом. Ниже 25 000 — подозрительно дёшево."
}

Язык ответов: русский.
"""


class PricerAgent(BaseAgent):
    def __init__(self):
        super().__init__(SYSTEM_PROMPT)

    async def estimate_price(self, cargo_data: dict) -> dict:
        prompt = (
            f"Оцени стоимость перевозки:\n"
            f"  Маршрут: {cargo_data.get('origin_city')} → {cargo_data.get('destination_city')}\n"
            f"  Вес: {cargo_data.get('weight_tons')} т\n"
            f"  Объём: {cargo_data.get('volume_m3', 'N/A')} м³\n"
            f"  Тип кузова: {cargo_data.get('vehicle_type_required', 'тент')}\n"
            f"  Валюта: {cargo_data.get('currency', 'KGS')}\n"
        )
        return await self.ask_json(prompt)
