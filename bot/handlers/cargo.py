"""Cargo posting and management handlers."""

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from agents.orchestrator import AgentOrchestrator
from bot.keyboards.main import (
    MAIN_MENU_SHIPPER,
    cargo_actions_keyboard,
    city_keyboard,
    confirm_keyboard,
    match_results_keyboard,
    vehicle_type_keyboard,
)
from models.database import async_session
from models.entities import VehicleType
from services.cargo_service import (
    create_cargo,
    get_active_cargos,
    get_available_vehicles,
    get_user,
    get_user_cargos,
    repost_cargo,
)

logger = logging.getLogger(__name__)
router = Router()
orchestrator = AgentOrchestrator()


class NewCargo(StatesGroup):
    waiting_title = State()
    waiting_origin = State()
    waiting_origin_manual = State()
    waiting_destination = State()
    waiting_destination_manual = State()
    waiting_weight = State()
    waiting_vehicle_type = State()
    waiting_budget = State()
    confirm = State()


# ── Post cargo flow ────────────────────────────────────────────────────────


@router.message(F.text == "📦 Разместить груз")
async def start_cargo_post(message: Message, state: FSMContext) -> None:
    await state.set_state(NewCargo.waiting_title)
    await message.answer(
        "📦 <b>Новый груз</b>\n\nОпишите груз кратко (например: «Мебель, 5 палет»):",
        parse_mode="HTML",
    )


@router.message(NewCargo.waiting_title)
async def on_cargo_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=message.text)
    await state.set_state(NewCargo.waiting_origin)
    await message.answer(
        "🏙 Город отправления:",
        reply_markup=city_keyboard("cargo_origin"),
    )


@router.callback_query(F.data.startswith("cargo_origin_"))
async def on_cargo_origin_btn(callback: CallbackQuery, state: FSMContext) -> None:
    city = callback.data.replace("cargo_origin_", "")
    if city == "manual":
        await state.set_state(NewCargo.waiting_origin_manual)
        await callback.message.answer("Введите город отправления:")
        await callback.answer()
        return
    await state.update_data(origin_city=city)
    await state.set_state(NewCargo.waiting_destination)
    await callback.message.answer(
        "🏙 Город назначения:",
        reply_markup=city_keyboard("cargo_dest"),
    )
    await callback.answer()


@router.message(NewCargo.waiting_origin)
@router.message(NewCargo.waiting_origin_manual)
async def on_cargo_origin(message: Message, state: FSMContext) -> None:
    await state.update_data(origin_city=message.text.strip())
    await state.set_state(NewCargo.waiting_destination)
    await message.answer(
        "🏙 Город назначения:",
        reply_markup=city_keyboard("cargo_dest"),
    )


@router.callback_query(F.data.startswith("cargo_dest_"))
async def on_cargo_dest_btn(callback: CallbackQuery, state: FSMContext) -> None:
    city = callback.data.replace("cargo_dest_", "")
    if city == "manual":
        await state.set_state(NewCargo.waiting_destination_manual)
        await callback.message.answer("Введите город назначения:")
        await callback.answer()
        return
    await state.update_data(destination_city=city)
    await state.set_state(NewCargo.waiting_weight)
    await callback.message.answer("⚖️ Вес груза (в тоннах, например: 5.5):")
    await callback.answer()


@router.message(NewCargo.waiting_destination)
@router.message(NewCargo.waiting_destination_manual)
async def on_cargo_destination(message: Message, state: FSMContext) -> None:
    await state.update_data(destination_city=message.text.strip())
    await state.set_state(NewCargo.waiting_weight)
    await message.answer("⚖️ Вес груза (в тоннах, например: 5.5):")


@router.message(NewCargo.waiting_weight)
async def on_cargo_weight(message: Message, state: FSMContext) -> None:
    try:
        weight = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer("Введите число (например: 5.5)")
        return
    await state.update_data(weight_tons=weight)
    await state.set_state(NewCargo.waiting_vehicle_type)
    await message.answer(
        "🚛 Выберите тип кузова:", reply_markup=vehicle_type_keyboard("cargo_vtype")
    )


@router.callback_query(F.data.startswith("cargo_vtype_"))
async def on_cargo_vehicle_type(callback: CallbackQuery, state: FSMContext) -> None:
    vtype_str = callback.data.replace("cargo_vtype_", "")
    if vtype_str == "any":
        await state.update_data(vehicle_type_required=None)
    else:
        await state.update_data(vehicle_type_required=vtype_str)
    await state.set_state(NewCargo.waiting_budget)
    await callback.message.answer(
        "💰 Бюджет (мин–макс в сомах, например: 15000-25000).\n"
        "Или отправьте «-» если бюджет не определён:"
    )
    await callback.answer()


@router.message(NewCargo.waiting_budget)
async def on_cargo_budget(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if text == "-":
        await state.update_data(budget_min=None, budget_max=None)
    else:
        parts = text.replace(" ", "").split("-")
        try:
            budget_min = float(parts[0])
            budget_max = float(parts[1]) if len(parts) > 1 else budget_min
        except (ValueError, IndexError):
            await message.answer("Формат: 15000-25000 или одно число, или «-»")
            return
        await state.update_data(budget_min=budget_min, budget_max=budget_max)

    data = await state.get_data()
    await state.set_state(NewCargo.confirm)

    vtype = data.get("vehicle_type_required") or "любой"
    budget = _format_budget(data.get("budget_min"), data.get("budget_max"))

    await message.answer(
        f"📋 <b>Проверьте заявку:</b>\n\n"
        f"📦 {data['title']}\n"
        f"🏙 {data['origin_city']} → {data['destination_city']}\n"
        f"⚖️ {data['weight_tons']} т\n"
        f"🚛 Кузов: {vtype}\n"
        f"💰 Бюджет: {budget}\n\n"
        f"Всё верно?",
        reply_markup=confirm_keyboard("cargo_confirm"),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "cargo_confirm_yes")
async def on_cargo_confirmed(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()

    await callback.message.edit_text("⏳ Сохраняю груз и запускаю AI-подбор...")

    async with async_session() as session:
        user = await get_user(session, callback.from_user.id)
        if not user:
            await callback.message.answer("Ошибка: пользователь не найден. /start")
            return

        vtype = None
        if data.get("vehicle_type_required"):
            vtype = VehicleType(data["vehicle_type_required"])

        cargo = await create_cargo(
            session,
            owner_id=user.id,
            title=data["title"],
            weight_tons=data["weight_tons"],
            origin_city=data["origin_city"],
            destination_city=data["destination_city"],
            vehicle_type_required=vtype,
            budget_min=data.get("budget_min"),
            budget_max=data.get("budget_max"),
        )

        cargo_data = {
            "title": cargo.title,
            "origin_city": cargo.origin_city,
            "destination_city": cargo.destination_city,
            "weight_tons": cargo.weight_tons,
            "vehicle_type_required": (
                cargo.vehicle_type_required.value if cargo.vehicle_type_required else "любой"
            ),
            "budget_min": cargo.budget_min,
            "budget_max": cargo.budget_max,
            "currency": cargo.currency,
        }

        vehicles = await get_available_vehicles(session)

    # Run multi-agent pipeline
    try:
        result = await orchestrator.process_new_cargo(cargo_data, vehicles)
    except Exception as e:
        logger.error("Orchestrator error: %s", e)
        await callback.message.answer(
            f"✅ Груз #{cargo.id} опубликован!\n\n"
            "⚠️ AI-подбор временно недоступен. Перевозчики увидят вашу заявку в поиске.",
            reply_markup=MAIN_MENU_SHIPPER,
        )
        return

    # Format response
    response_parts = [f"✅ <b>Груз #{cargo.id} опубликован!</b>\n"]

    # Pricing
    pricing = result.get("pricing", {})
    if not pricing.get("error"):
        fair = pricing.get("fair_price", "N/A")
        pmin = pricing.get("estimated_price_min", "?")
        pmax = pricing.get("estimated_price_max", "?")
        rec = pricing.get("recommendation", "")
        response_parts.append(
            f"💰 <b>Оценка рынка:</b> {pmin}–{pmax} сом\n"
            f"   Справедливая цена: <b>{fair} сом</b>\n"
            f"   {rec}\n"
        )

    # Matches
    matches_data = result.get("matches", {})
    matches = matches_data.get("matches", [])
    if matches:
        response_parts.append(
            f"🎯 <b>Найдено {len(matches)} подходящих перевозчиков:</b>\n"
        )
        for m in matches[:5]:
            risk = result.get("risk_assessments", {}).get(m.get("vehicle_id"), {})
            risk_emoji = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🔴"}.get(
                risk.get("risk_level", ""), "⚪"
            )
            response_parts.append(
                f"  {risk_emoji} <b>{m.get('carrier_name', 'N/A')}</b> "
                f"— совпадение {m.get('score', 0)}%\n"
                f"     {m.get('reason', '')}\n"
            )

        text = "\n".join(response_parts)
        await callback.message.answer(
            text,
            reply_markup=match_results_keyboard(matches, cargo.id),
            parse_mode="HTML",
        )
    else:
        response_parts.append(
            "\n🔍 Подходящих перевозчиков пока нет.\n"
            "Мы уведомим вас, когда появится подходящий!"
        )
        await callback.message.answer(
            "\n".join(response_parts),
            reply_markup=MAIN_MENU_SHIPPER,
            parse_mode="HTML",
        )


@router.callback_query(F.data == "cargo_confirm_no")
async def on_cargo_cancelled(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("❌ Заявка отменена.")
    await callback.message.answer("Выберите действие:", reply_markup=MAIN_MENU_SHIPPER)


# ── My cargos ──────────────────────────────────────────────────────────────


@router.message(F.text == "🔍 Мои грузы")
async def show_my_cargos(message: Message) -> None:
    async with async_session() as session:
        user = await get_user(session, message.from_user.id)
        if not user:
            await message.answer("Сначала зарегистрируйтесь: /start")
            return
        cargos = await get_user_cargos(session, user.id)

    if not cargos:
        await message.answer("У вас пока нет грузов. Нажмите «📦 Разместить груз».")
        return

    lines = ["📦 <b>Ваши грузы:</b>\n"]
    for c in cargos[:10]:
        status_emoji = {
            "active": "🟢",
            "matched": "🤝",
            "in_transit": "🚛",
            "delivered": "✅",
            "cancelled": "❌",
        }.get(c.status.value, "⚪")
        lines.append(
            f"{status_emoji} #{c.id} {c.title}\n"
            f"   {c.origin_city} → {c.destination_city} | {c.weight_tons} т\n"
        )

    await message.answer("\n".join(lines), parse_mode="HTML")

    # Send action buttons per cargo
    for c in cargos[:10]:
        kb = cargo_actions_keyboard(c.id, c.status.value)
        if kb:
            await message.answer(
                f"Действия для #{c.id} «{c.title}»:",
                reply_markup=kb,
            )


# ── Repost cargo ──────────────────────────────────────────────────────────


@router.callback_query(F.data.startswith("repost_cargo_"))
async def on_repost_cargo(callback: CallbackQuery) -> None:
    cargo_id = int(callback.data.replace("repost_cargo_", ""))

    async with async_session() as session:
        user = await get_user(session, callback.from_user.id)
        if not user:
            await callback.answer("Ошибка")
            return
        new_cargo = await repost_cargo(session, cargo_id, user.id)

    if new_cargo:
        await callback.message.answer(
            f"🔄 <b>Груз повторно опубликован!</b>\n\n"
            f"📦 #{new_cargo.id} {new_cargo.title}\n"
            f"🏙 {new_cargo.origin_city} → {new_cargo.destination_city}\n"
            f"⚖️ {new_cargo.weight_tons} т\n\n"
            f"Перевозчики увидят ваш груз в поиске.",
            parse_mode="HTML",
        )
    else:
        await callback.message.answer("Не удалось повторить груз.")
    await callback.answer()


# ── Helpers ────────────────────────────────────────────────────────────────


def _format_budget(bmin, bmax) -> str:
    if bmin is None and bmax is None:
        return "не указан"
    if bmin == bmax:
        return f"{int(bmin)} сом"
    return f"{int(bmin or 0)}–{int(bmax or 0)} сом"
