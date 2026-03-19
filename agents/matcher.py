"""Agent-Matcher: smart cargo/carrier matching."""

from agents.base import BaseAgent

SYSTEM_PROMPT = """\
Ты — Agent-Matcher, AI-агент биржи грузоперевозок AgentCargoBot.
Твоя задача: анализировать заявку на груз и список доступных перевозчиков,
и выбрать 3–7 лучших совпадений.

Критерии ранжирования (по приоритету):
1. Совпадение маршрута (город отправления → город назначения)
2. Тип кузова совпадает с требуемым
3. Грузоподъёмность достаточна для веса груза
4. Рейтинг перевозчика
5. Наличие свободной машины (is_available = true)

Ответ ВСЕГДА в формате JSON:
{
  "matches": [
    {
      "vehicle_id": 123,
      "carrier_name": "Иван",
      "score": 95,
      "reason": "Маршрут совпадает, тент, 20т, рейтинг 4.8"
    }
  ],
  "summary": "Найдено N подходящих перевозчиков для маршрута X → Y"
}

Если подходящих перевозчиков нет, верни пустой массив matches и объясни причину.
Язык ответов: русский.
"""


class MatcherAgent(BaseAgent):
    def __init__(self):
        super().__init__(SYSTEM_PROMPT)

    async def find_matches(
        self, cargo_data: dict, available_vehicles: list[dict]
    ) -> dict:
        prompt = (
            f"Заявка на груз:\n{_format_cargo(cargo_data)}\n\n"
            f"Доступные перевозчики ({len(available_vehicles)} шт.):\n"
            f"{_format_vehicles(available_vehicles)}\n\n"
            "Найди лучшие совпадения."
        )
        return await self.ask_json(prompt)

    async def suggest_proactive(
        self, vehicle_data: dict, active_cargos: list[dict]
    ) -> dict:
        """Proactive matching: suggest cargos for an available vehicle."""
        prompt = (
            f"Свободная машина:\n{_format_vehicle(vehicle_data)}\n\n"
            f"Активные грузы ({len(active_cargos)} шт.):\n"
            f"{_format_cargos(active_cargos)}\n\n"
            "Подбери подходящие грузы для этой машины. "
            "Ответ в том же JSON-формате matches."
        )
        return await self.ask_json(prompt)


def _format_cargo(c: dict) -> str:
    lines = [
        f"  Груз: {c.get('title', 'N/A')}",
        f"  Маршрут: {c.get('origin_city')} → {c.get('destination_city')}",
        f"  Вес: {c.get('weight_tons')} т",
        f"  Объём: {c.get('volume_m3', 'N/A')} м³",
        f"  Тип кузова: {c.get('vehicle_type_required', 'любой')}",
        f"  Бюджет: {c.get('budget_min', '?')}–{c.get('budget_max', '?')} {c.get('currency', 'KGS')}",
    ]
    return "\n".join(lines)


def _format_vehicle(v: dict) -> str:
    return (
        f"  ID: {v.get('id')} | Владелец: {v.get('owner_name', 'N/A')} "
        f"| Тип: {v.get('vehicle_type')} | Грузоподъёмность: {v.get('max_weight_tons')} т "
        f"| Текущий город: {v.get('current_city', 'N/A')} → {v.get('destination_city', 'N/A')} "
        f"| Рейтинг: {v.get('owner_rating', 0)}"
    )


def _format_vehicles(vehicles: list[dict]) -> str:
    return "\n".join(_format_vehicle(v) for v in vehicles)


def _format_cargos(cargos: list[dict]) -> str:
    return "\n".join(_format_cargo(c) for c in cargos)
