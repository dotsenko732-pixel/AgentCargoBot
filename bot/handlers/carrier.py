"""Carrier-side handlers: vehicle management, cargo search."""

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from agents.orchestrator import AgentOrchestrator
from bot.keyboards.main import MAIN_MENU_CARRIER, vehicle_type_keyboard
from models.database import async_session
from models.entities import VehicleType
from services.cargo_service import add_vehicle, get_active_cargos, get_user

logger = logging.getLogger(__name__)
router = Router()
orchestrator = AgentOrchestrator()


class AddVehicle(StatesGroup):
    waiting_type = State()
    waiting_weight = State()
    waiting_city = State()
    waiting_destination = State()


# ── Find cargos (AI-powered search) ───────────────────────────────────────


@router.message(F.text == "🚛 Найти грузы")
async def find_cargos(message: Message) -> None:
    await message.answer("⏳ AI ищет подходящие грузы для вас...")

    async with async_session() as session:
        user = await get_user(session, message.from_user.id)
        if not user:
            await message.answer("Сначала зарегистрируйтесь: /start")
            return

        cargos = await get_active_cargos(session)

    if not cargos:
        await message.answer(
            "🔍 Активных грузов пока нет. Мы уведомим вас, когда появятся!",
            reply_markup=MAIN_MENU_CARRIER,
        )
        return

    # Format cargo list
    lines = [f"📦 <b>Доступные грузы ({len(cargos)}):</b>\n"]
    for c in cargos[:15]:
        budget = _fmt_budget(c.get("budget_min"), c.get("budget_max"))
        lines.append(
            f"  #{c['id']} <b>{c['title']}</b>\n"
            f"  🏙 {c['origin_city']} → {c['destination_city']}\n"
            f"  ⚖️ {c['weight_tons']} т | 🚛 {c.get('vehicle_type_required') or 'любой'}\n"
            f"  💰 {budget}\n"
            f"  👤 {c['owner_name']} (рейтинг {c['owner_rating']})\n"
        )

    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=MAIN_MENU_CARRIER)


# ── Add vehicle flow ───────────────────────────────────────────────────────


@router.message(F.text == "🅿️ Мои машины")
async def my_vehicles(message: Message, state: FSMContext) -> None:
    await state.set_state(AddVehicle.waiting_type)
    await message.answer(
        "🚛 Добавьте машину.\nВыберите тип кузова:",
        reply_markup=vehicle_type_keyboard("add_vtype"),
    )


@router.callback_query(F.data.startswith("add_vtype_"))
async def on_vehicle_type(callback: CallbackQuery, state: FSMContext) -> None:
    vtype_str = callback.data.replace("add_vtype_", "")
    if vtype_str == "any":
        vtype_str = "other"
    await state.update_data(vehicle_type=vtype_str)
    await state.set_state(AddVehicle.waiting_weight)
    await callback.message.answer("⚖️ Грузоподъёмность (тонн, например: 20):")
    await callback.answer()


@router.message(AddVehicle.waiting_weight)
async def on_vehicle_weight(message: Message, state: FSMContext) -> None:
    try:
        weight = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer("Введите число.")
        return
    await state.update_data(max_weight_tons=weight)
    await state.set_state(AddVehicle.waiting_city)
    await message.answer("🏙 В каком городе сейчас машина?")


@router.message(AddVehicle.waiting_city)
async def on_vehicle_city(message: Message, state: FSMContext) -> None:
    await state.update_data(current_city=message.text.strip())
    await state.set_state(AddVehicle.waiting_destination)
    await message.answer(
        "🏙 Куда готовы ехать? (город назначения, или «любой»):"
    )


@router.message(AddVehicle.waiting_destination)
async def on_vehicle_destination(message: Message, state: FSMContext) -> None:
    dest = message.text.strip()
    if dest.lower() in ("любой", "все", "любое"):
        dest = None
    data = await state.get_data()
    await state.clear()

    async with async_session() as session:
        user = await get_user(session, message.from_user.id)
        if not user:
            await message.answer("Сначала зарегистрируйтесь: /start")
            return

        vehicle = await add_vehicle(
            session,
            owner_id=user.id,
            vehicle_type=VehicleType(data["vehicle_type"]),
            max_weight_tons=data["max_weight_tons"],
            current_city=data["current_city"],
            destination_city=dest,
        )

    await message.answer(
        f"✅ Машина добавлена!\n"
        f"🚛 Тип: {data['vehicle_type']}\n"
        f"⚖️ Грузоподъёмность: {data['max_weight_tons']} т\n"
        f"🏙 {data['current_city']} → {dest or 'любое направление'}\n\n"
        "Теперь AI будет автоматически подбирать грузы для вас!",
        reply_markup=MAIN_MENU_CARRIER,
    )

    # Proactive matching
    try:
        async with async_session() as session:
            active_cargos = await get_active_cargos(session)

        if active_cargos:
            vehicle_data = {
                "id": vehicle.id,
                "vehicle_type": data["vehicle_type"],
                "max_weight_tons": data["max_weight_tons"],
                "current_city": data["current_city"],
                "destination_city": dest,
            }
            result = await orchestrator.process_carrier_available(
                vehicle_data, active_cargos
            )
            matches = result.get("matches", [])
            if matches:
                lines = ["🎯 <b>AI нашёл подходящие грузы для вашей машины:</b>\n"]
                for m in matches[:5]:
                    lines.append(
                        f"  📦 <b>{m.get('carrier_name', 'Груз')}</b> "
                        f"— совпадение {m.get('score', 0)}%\n"
                        f"  {m.get('reason', '')}\n"
                    )
                await message.answer("\n".join(lines), parse_mode="HTML")
    except Exception as e:
        logger.error("Proactive matching error: %s", e)


def _fmt_budget(bmin, bmax) -> str:
    if bmin is None and bmax is None:
        return "договорная"
    if bmin == bmax and bmin is not None:
        return f"{int(bmin)} сом"
    return f"{int(bmin or 0)}–{int(bmax or 0)} сом"
