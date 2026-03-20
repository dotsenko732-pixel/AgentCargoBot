"""Carrier-side handlers: vehicle management, cargo search with filters."""

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from agents.orchestrator import AgentOrchestrator
from bot.keyboards.main import (
    MAIN_MENU_CARRIER,
    cargo_interest_keyboard,
    city_keyboard,
    search_filter_keyboard,
    vehicle_type_keyboard,
)
from models.database import async_session
from models.entities import VehicleType
from services.cargo_service import (
    add_vehicle,
    delete_vehicle,
    get_active_cargos,
    get_user,
    get_user_vehicles,
    search_cargos,
)

logger = logging.getLogger(__name__)
router = Router()
orchestrator = AgentOrchestrator()


class AddVehicle(StatesGroup):
    waiting_type = State()
    waiting_weight = State()
    waiting_city = State()
    waiting_destination = State()


class SearchFilter(StatesGroup):
    waiting_origin = State()
    waiting_destination = State()
    waiting_weight = State()
    waiting_vtype = State()


# ── Find cargos (with filter options) ────────────────────────────────────


@router.message(F.text == "🚛 Найти грузы")
async def find_cargos(message: Message) -> None:
    async with async_session() as session:
        user = await get_user(session, message.from_user.id)
        if not user:
            await message.answer("Сначала зарегистрируйтесь: /start")
            return

    await message.answer(
        "🔍 <b>Поиск грузов</b>\n\nВыберите способ поиска:",
        parse_mode="HTML",
        reply_markup=search_filter_keyboard(),
    )


@router.callback_query(F.data == "filter_all")
async def on_filter_all(callback: CallbackQuery) -> None:
    await callback.answer()
    await _show_cargos(callback.message, cargos=None)


@router.callback_query(F.data == "filter_route")
async def on_filter_route(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SearchFilter.waiting_origin)
    await callback.message.answer(
        "🏙 Откуда? (город отправления, или «-» чтобы пропустить):",
        reply_markup=city_keyboard("search_origin"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("search_origin_"))
async def on_search_origin_city(callback: CallbackQuery, state: FSMContext) -> None:
    city = callback.data.replace("search_origin_", "")
    if city == "manual":
        await callback.message.answer("Введите город отправления:")
        await callback.answer()
        return
    await state.update_data(search_origin=city)
    await state.set_state(SearchFilter.waiting_destination)
    await callback.message.answer(
        "🏙 Куда? (город назначения, или «-» чтобы пропустить):",
        reply_markup=city_keyboard("search_dest"),
    )
    await callback.answer()


@router.message(SearchFilter.waiting_origin)
async def on_search_origin_text(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    origin = None if text == "-" else text
    await state.update_data(search_origin=origin)
    await state.set_state(SearchFilter.waiting_destination)
    await message.answer(
        "🏙 Куда? (город назначения, или «-» чтобы пропустить):",
        reply_markup=city_keyboard("search_dest"),
    )


@router.callback_query(F.data.startswith("search_dest_"))
async def on_search_dest_city(callback: CallbackQuery, state: FSMContext) -> None:
    city = callback.data.replace("search_dest_", "")
    if city == "manual":
        await callback.message.answer("Введите город назначения:")
        await callback.answer()
        return
    await state.update_data(search_dest=city)
    await _execute_search(callback.message, state)
    await callback.answer()


@router.message(SearchFilter.waiting_destination)
async def on_search_dest_text(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    dest = None if text == "-" else text
    await state.update_data(search_dest=dest)
    await _execute_search(message, state)


@router.callback_query(F.data == "filter_weight")
async def on_filter_weight(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SearchFilter.waiting_weight)
    await callback.message.answer(
        "⚖️ Максимальный вес груза (тонн)?\nНапример: 20"
    )
    await callback.answer()


@router.message(SearchFilter.waiting_weight)
async def on_search_weight(message: Message, state: FSMContext) -> None:
    try:
        weight = float(message.text.strip().replace(",", "."))
    except ValueError:
        await message.answer("Введите число.")
        return
    await state.update_data(search_weight=weight)
    await _execute_search(message, state)


@router.callback_query(F.data == "filter_vtype")
async def on_filter_vtype(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SearchFilter.waiting_vtype)
    await callback.message.answer(
        "🚛 Выберите тип кузова:",
        reply_markup=vehicle_type_keyboard("search_vtype"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("search_vtype_"))
async def on_search_vtype(callback: CallbackQuery, state: FSMContext) -> None:
    vtype = callback.data.replace("search_vtype_", "")
    await state.update_data(search_vtype=vtype if vtype != "any" else None)
    await _execute_search(callback.message, state)
    await callback.answer()


async def _execute_search(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()

    async with async_session() as session:
        cargos = await search_cargos(
            session,
            origin_city=data.get("search_origin"),
            destination_city=data.get("search_dest"),
            max_weight=data.get("search_weight"),
            vehicle_type=data.get("search_vtype"),
        )

    await _show_cargos(message, cargos)


async def _show_cargos(message: Message, cargos: list[dict] | None = None) -> None:
    if cargos is None:
        async with async_session() as session:
            cargos = await get_active_cargos(session)

    if not cargos:
        await message.answer(
            "🔍 Грузов по вашему запросу не найдено.",
            reply_markup=MAIN_MENU_CARRIER,
        )
        return

    await message.answer(
        f"📦 <b>Найдено грузов: {len(cargos)}</b>",
        parse_mode="HTML",
        reply_markup=MAIN_MENU_CARRIER,
    )
    for c in cargos[:10]:
        budget = _fmt_budget(c.get("budget_min"), c.get("budget_max"))
        text = (
            f"#{c['id']} <b>{c['title']}</b>\n"
            f"🏙 {c['origin_city']} → {c['destination_city']}\n"
            f"⚖️ {c['weight_tons']} т | 🚛 {c.get('vehicle_type_required') or 'любой'}\n"
            f"💰 {budget}\n"
            f"👤 {c['owner_name']} (⭐ {c['owner_rating']})"
        )
        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=cargo_interest_keyboard(c["id"]),
        )


# ── Add vehicle flow ───────────────────────────────────────────────────────


@router.message(F.text == "🅿️ Мои машины")
async def my_vehicles(message: Message) -> None:
    async with async_session() as session:
        user = await get_user(session, message.from_user.id)
        if not user:
            await message.answer("Сначала зарегистрируйтесь: /start")
            return
        vehicles = await get_user_vehicles(session, user.id)

    buttons = [
        [InlineKeyboardButton(text="➕ Добавить машину", callback_data="add_vehicle")]
    ]

    if not vehicles:
        await message.answer(
            "🅿️ У вас пока нет машин.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        )
        return

    lines = ["🅿️ <b>Ваши машины:</b>\n"]
    for v in vehicles:
        avail = "🟢" if v.is_available else "🔴"
        lines.append(
            f"{avail} #{v.id} {v.vehicle_type.value} | {v.max_weight_tons} т\n"
            f"  🏙 {v.current_city or '?'} → {v.destination_city or 'любое'}\n"
        )
        buttons.append(
            [InlineKeyboardButton(
                text=f"🗑 Удалить #{v.id}",
                callback_data=f"del_vehicle_{v.id}",
            )]
        )

    await message.answer(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(F.data == "add_vehicle")
async def start_add_vehicle(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddVehicle.waiting_type)
    await callback.message.answer(
        "🚛 Добавьте машину.\nВыберите тип кузова:",
        reply_markup=vehicle_type_keyboard("add_vtype"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("del_vehicle_"))
async def on_delete_vehicle(callback: CallbackQuery) -> None:
    vid = int(callback.data.replace("del_vehicle_", ""))
    async with async_session() as session:
        user = await get_user(session, callback.from_user.id)
        if not user:
            await callback.answer("Ошибка")
            return
        ok = await delete_vehicle(session, vid, user.id)
    if ok:
        await callback.message.answer(f"🗑 Машина #{vid} удалена.")
    else:
        await callback.message.answer("Не удалось удалить.")
    await callback.answer()


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
    await message.answer(
        "🏙 В каком городе сейчас машина?",
        reply_markup=city_keyboard("veh_city"),
    )


@router.callback_query(F.data.startswith("veh_city_"))
async def on_vehicle_city_btn(callback: CallbackQuery, state: FSMContext) -> None:
    city = callback.data.replace("veh_city_", "")
    if city == "manual":
        await callback.message.answer("Введите город:")
        await callback.answer()
        return
    await state.update_data(current_city=city)
    await state.set_state(AddVehicle.waiting_destination)
    await callback.message.answer(
        "🏙 Куда готовы ехать? (или «любой»):",
        reply_markup=city_keyboard("veh_dest"),
    )
    await callback.answer()


@router.message(AddVehicle.waiting_city)
async def on_vehicle_city(message: Message, state: FSMContext) -> None:
    await state.update_data(current_city=message.text.strip())
    await state.set_state(AddVehicle.waiting_destination)
    await message.answer(
        "🏙 Куда готовы ехать? (город назначения, или «любой»):",
        reply_markup=city_keyboard("veh_dest"),
    )


@router.callback_query(F.data.startswith("veh_dest_"))
async def on_vehicle_dest_btn(callback: CallbackQuery, state: FSMContext) -> None:
    city = callback.data.replace("veh_dest_", "")
    if city == "manual":
        await callback.message.answer("Введите город назначения (или «любой»):")
        await callback.answer()
        return
    await state.update_data(destination_override=city)
    await _save_vehicle(callback.message, state, city)
    await callback.answer()


@router.message(AddVehicle.waiting_destination)
async def on_vehicle_destination(message: Message, state: FSMContext) -> None:
    dest = message.text.strip()
    if dest.lower() in ("любой", "все", "любое"):
        dest = None
    await _save_vehicle(message, state, dest)


async def _save_vehicle(message: Message, state: FSMContext, dest: str | None) -> None:
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
        "AI автоматически подберёт грузы для вас!",
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
                lines = ["🎯 <b>AI нашёл подходящие грузы:</b>\n"]
                for m in matches[:5]:
                    lines.append(
                        f"  📦 <b>{m.get('carrier_name', 'Груз')}</b> "
                        f"— {m.get('score', 0)}%\n"
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
