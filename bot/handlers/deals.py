"""Deal management handlers: proposals, acceptance, status, reviews."""

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from agents.orchestrator import AgentOrchestrator
from models.database import async_session
from models.entities import DealStatus
from services.cargo_service import (
    cancel_cargo,
    create_deal,
    create_review,
    get_cargo_by_id,
    get_deal,
    get_user,
    get_user_by_id,
    get_user_deals,
    get_vehicle_with_owner,
    increment_total_deals,
    update_deal_status,
)

logger = logging.getLogger(__name__)
router = Router()
orchestrator = AgentOrchestrator()

DEAL_STATUS_LABELS = {
    "proposed": "📩 Предложена",
    "accepted": "✅ Принята",
    "in_transit": "🚛 В пути",
    "delivered": "📦 Доставлено",
    "confirmed": "🤝 Завершена",
    "disputed": "⚠️ Спор",
    "cancelled": "❌ Отменена",
}


class DealProposal(StatesGroup):
    waiting_price = State()


class ReviewFlow(StatesGroup):
    waiting_rating = State()
    waiting_comment = State()


# ── Select carrier from match results ──────────────────────────────────────


@router.callback_query(F.data.startswith("selcar_"))
async def on_select_carrier(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.replace("selcar_", "").split("_")
    if len(parts) != 2:
        await callback.answer("Ошибка данных")
        return
    cargo_id, vehicle_id = int(parts[0]), int(parts[1])

    async with async_session() as session:
        cargo = await get_cargo_by_id(session, cargo_id)
        veh_data = await get_vehicle_with_owner(session, vehicle_id)

    if not cargo or not veh_data:
        await callback.message.answer("Груз или перевозчик не найден.")
        await callback.answer()
        return

    vehicle, owner = veh_data

    # Run risk assessment
    risk_text = ""
    try:
        carrier_data = {
            "full_name": owner.full_name,
            "rating": owner.rating,
            "total_deals": owner.total_deals,
            "is_verified": owner.is_verified,
            "created_at": str(owner.created_at),
        }
        risk_result = await orchestrator.risk.assess_carrier(carrier_data, reviews=[])
        risk_level = risk_result.get("risk_level", "N/A")
        risk_emoji = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🔴"}.get(risk_level, "⚪")
        risk_text = (
            f"\n{risk_emoji} <b>Надёжность:</b> {risk_result.get('summary', risk_level)}\n"
        )
    except Exception as e:
        logger.error("Risk assessment error: %s", e)

    # Store deal context
    await state.update_data(deal_cargo_id=cargo_id, deal_vehicle_id=vehicle_id)
    await state.set_state(DealProposal.waiting_price)

    budget_hint = ""
    if cargo.budget_min or cargo.budget_max:
        bmin = int(cargo.budget_min or 0)
        bmax = int(cargo.budget_max or 0)
        budget_hint = f"\n💰 Ваш бюджет: {bmin}–{bmax} сом" if bmin != bmax else f"\n💰 Ваш бюджет: {bmin} сом"

    await callback.message.answer(
        f"🚛 <b>Перевозчик: {owner.full_name}</b>\n"
        f"⭐ Рейтинг: {owner.rating:.1f} | Сделок: {owner.total_deals}\n"
        f"🚛 {vehicle.vehicle_type.value} | {vehicle.max_weight_tons} т\n"
        f"🏙 {vehicle.current_city or '?'} → {vehicle.destination_city or 'любое'}"
        f"{risk_text}{budget_hint}\n\n"
        f"💰 Введите цену предложения (в сомах):",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(DealProposal.waiting_price)
async def on_deal_price_entered(message: Message, state: FSMContext) -> None:
    try:
        price = float(message.text.strip().replace(",", ".").replace(" ", ""))
        if price <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Введите корректную цену (число больше 0):")
        return

    data = await state.get_data()
    cargo_id = data["deal_cargo_id"]
    vehicle_id = data["deal_vehicle_id"]
    await state.clear()

    async with async_session() as session:
        user = await get_user(session, message.from_user.id)
        if not user:
            await message.answer("Ошибка. /start")
            return

        veh_data = await get_vehicle_with_owner(session, vehicle_id)
        if not veh_data:
            await message.answer("Перевозчик не найден.")
            return

        vehicle, carrier = veh_data

        deal = await create_deal(
            session,
            cargo_id=cargo_id,
            shipper_id=user.id,
            carrier_id=carrier.id,
            agreed_price=price,
        )

        cargo = await get_cargo_by_id(session, cargo_id)

    await message.answer(
        f"✅ <b>Сделка #{deal.id} создана!</b>\n\n"
        f"📦 {cargo.title}\n"
        f"🏙 {cargo.origin_city} → {cargo.destination_city}\n"
        f"💰 {int(price)} сом\n"
        f"🚛 Перевозчик: {carrier.full_name}\n\n"
        f"Ожидаем подтверждения от перевозчика.",
        parse_mode="HTML",
    )

    # Notify carrier
    try:
        await message.bot.send_message(
            carrier.telegram_id,
            f"📩 <b>Новое предложение сделки #{deal.id}!</b>\n\n"
            f"📦 {cargo.title}\n"
            f"🏙 {cargo.origin_city} → {cargo.destination_city}\n"
            f"⚖️ {cargo.weight_tons} т\n"
            f"💰 Цена: <b>{int(price)} сом</b>\n"
            f"👤 Заказчик: {user.full_name}\n\n"
            f"Примите или отклоните в разделе «📊 Мои сделки».",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Принять",
                        callback_data=f"accept_deal_{deal.id}",
                    ),
                    InlineKeyboardButton(
                        text="❌ Отклонить",
                        callback_data=f"reject_deal_{deal.id}",
                    ),
                ]
            ]),
        )
    except Exception as e:
        logger.error("Failed to notify carrier %s: %s", carrier.telegram_id, e)


@router.callback_query(F.data == "back_to_matches")
async def on_back_to_matches(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Используйте список перевозчиков выше.")
    await callback.answer()


# ── Carrier responds to cargo ─────────────────────────────────────────────


@router.callback_query(F.data.startswith("respond_cargo_"))
async def on_carrier_respond(callback: CallbackQuery) -> None:
    cargo_id = int(callback.data.replace("respond_cargo_", ""))

    async with async_session() as session:
        carrier = await get_user(session, callback.from_user.id)
        if not carrier:
            await callback.answer("Сначала зарегистрируйтесь: /start")
            return

        cargo = await get_cargo_by_id(session, cargo_id)
        if not cargo:
            await callback.message.answer("Груз не найден или уже неактивен.")
            await callback.answer()
            return

        shipper = await get_user_by_id(session, cargo.owner_id)

    # Notify shipper about carrier interest
    try:
        await callback.bot.send_message(
            shipper.telegram_id,
            f"🚛 <b>Перевозчик откликнулся на ваш груз!</b>\n\n"
            f"📦 {cargo.title}\n"
            f"🏙 {cargo.origin_city} → {cargo.destination_city}\n\n"
            f"👤 <b>{carrier.full_name}</b>\n"
            f"⭐ Рейтинг: {carrier.rating:.1f} | Сделок: {carrier.total_deals}\n"
            f"📱 {carrier.phone or 'нет телефона'}\n\n"
            f"Свяжитесь с перевозчиком или предложите сделку через «📊 Мои сделки».",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error("Failed to notify shipper %s: %s", shipper.telegram_id, e)

    await callback.message.answer(
        f"✅ Ваш отклик на груз «{cargo.title}» отправлен заказчику!\n"
        f"Ожидайте предложения сделки."
    )
    await callback.answer()


# ── My Deals ───────────────────────────────────────────────────────────────


@router.message(F.text == "📊 Мои сделки")
async def show_my_deals(message: Message) -> None:
    async with async_session() as session:
        user = await get_user(session, message.from_user.id)
        if not user:
            await message.answer("Сначала зарегистрируйтесь: /start")
            return
        deals = await get_user_deals(session, user.id)

    if not deals:
        await message.answer("У вас пока нет сделок.")
        return

    lines = ["📊 <b>Ваши сделки:</b>\n"]
    for d in deals[:15]:
        status_label = DEAL_STATUS_LABELS.get(d["status"], d["status"])
        role = "заказчик" if d["shipper_id"] == user.id else "перевозчик"
        lines.append(
            f"{status_label} <b>Сделка #{d['id']}</b> ({role})\n"
            f"  📦 {d['cargo_title']}\n"
            f"  🏙 {d['origin']} → {d['destination']}\n"
            f"  💰 {int(d['price'])} {d['currency']}\n"
        )

    # Add action buttons for active deals
    buttons = []
    for d in deals[:5]:
        if d["status"] == "proposed" and d["carrier_id"] == user.id:
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=f"✅ Принять #{d['id']}",
                        callback_data=f"accept_deal_{d['id']}",
                    ),
                    InlineKeyboardButton(
                        text=f"❌ Отклонить",
                        callback_data=f"reject_deal_{d['id']}",
                    ),
                ]
            )
        elif d["status"] == "accepted" and d["carrier_id"] == user.id:
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=f"🚛 Взял груз #{d['id']}",
                        callback_data=f"intransit_deal_{d['id']}",
                    )
                ]
            )
        elif d["status"] == "in_transit" and d["carrier_id"] == user.id:
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=f"📦 Доставлено #{d['id']}",
                        callback_data=f"delivered_deal_{d['id']}",
                    )
                ]
            )
        elif d["status"] == "delivered" and d["shipper_id"] == user.id:
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=f"🤝 Подтвердить #{d['id']}",
                        callback_data=f"confirm_deal_{d['id']}",
                    )
                ]
            )

    kb = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=kb)


# ── Deal status transitions ───────────────────────────────────────────────


@router.callback_query(F.data.startswith("accept_deal_"))
async def on_accept_deal(callback: CallbackQuery) -> None:
    deal_id = int(callback.data.replace("accept_deal_", ""))
    async with async_session() as session:
        deal = await update_deal_status(session, deal_id, DealStatus.ACCEPTED)
        if not deal:
            await callback.message.answer("Сделка не найдена.")
            await callback.answer()
            return
        cargo = await get_cargo_by_id(session, deal.cargo_id)
        shipper = await get_user_by_id(session, deal.shipper_id)

    await callback.message.answer(f"✅ Сделка #{deal_id} принята! Заберите груз.")
    await callback.answer()

    # Notify shipper
    if shipper:
        try:
            await callback.bot.send_message(
                shipper.telegram_id,
                f"✅ <b>Сделка #{deal_id} принята перевозчиком!</b>\n\n"
                f"📦 {cargo.title}\n"
                f"Перевозчик скоро заберёт груз.",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error("Notify shipper error: %s", e)


@router.callback_query(F.data.startswith("reject_deal_"))
async def on_reject_deal(callback: CallbackQuery) -> None:
    deal_id = int(callback.data.replace("reject_deal_", ""))
    async with async_session() as session:
        deal = await update_deal_status(session, deal_id, DealStatus.CANCELLED)
        if not deal:
            await callback.message.answer("Сделка не найдена.")
            await callback.answer()
            return
        shipper = await get_user_by_id(session, deal.shipper_id)

    await callback.message.answer(f"❌ Сделка #{deal_id} отклонена.")
    await callback.answer()

    # Notify shipper
    if shipper:
        try:
            await callback.bot.send_message(
                shipper.telegram_id,
                f"❌ <b>Сделка #{deal_id} отклонена перевозчиком.</b>\n"
                f"Попробуйте другого перевозчика.",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error("Notify shipper error: %s", e)


@router.callback_query(F.data.startswith("intransit_deal_"))
async def on_intransit_deal(callback: CallbackQuery) -> None:
    deal_id = int(callback.data.replace("intransit_deal_", ""))
    async with async_session() as session:
        deal = await update_deal_status(session, deal_id, DealStatus.IN_TRANSIT)
        if not deal:
            await callback.message.answer("Сделка не найдена.")
            await callback.answer()
            return
        cargo = await get_cargo_by_id(session, deal.cargo_id)
        shipper = await get_user_by_id(session, deal.shipper_id)

    await callback.message.answer(f"🚛 Сделка #{deal_id}: груз в пути!")
    await callback.answer()

    # Notify shipper
    if shipper:
        try:
            await callback.bot.send_message(
                shipper.telegram_id,
                f"🚛 <b>Сделка #{deal_id}: груз в пути!</b>\n\n"
                f"📦 {cargo.title}\n"
                f"🏙 {cargo.origin_city} → {cargo.destination_city}",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error("Notify shipper error: %s", e)


@router.callback_query(F.data.startswith("delivered_deal_"))
async def on_delivered_deal(callback: CallbackQuery) -> None:
    deal_id = int(callback.data.replace("delivered_deal_", ""))
    async with async_session() as session:
        deal = await update_deal_status(session, deal_id, DealStatus.DELIVERED)
        if not deal:
            await callback.message.answer("Сделка не найдена.")
            await callback.answer()
            return
        shipper = await get_user_by_id(session, deal.shipper_id)

    await callback.message.answer(
        f"📦 Сделка #{deal_id}: доставка отмечена.\n"
        f"Ожидаем подтверждения от заказчика."
    )
    await callback.answer()

    # Notify shipper to confirm
    if shipper:
        try:
            await callback.bot.send_message(
                shipper.telegram_id,
                f"📦 <b>Сделка #{deal_id}: перевозчик отметил доставку!</b>\n\n"
                f"Подтвердите получение груза:",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text=f"🤝 Подтвердить получение",
                        callback_data=f"confirm_deal_{deal_id}",
                    )]
                ]),
            )
        except Exception as e:
            logger.error("Notify shipper error: %s", e)


@router.callback_query(F.data.startswith("confirm_deal_"))
async def on_confirm_deal(callback: CallbackQuery, state: FSMContext) -> None:
    deal_id = int(callback.data.replace("confirm_deal_", ""))
    async with async_session() as session:
        deal = await update_deal_status(session, deal_id, DealStatus.CONFIRMED)
        if not deal:
            await callback.message.answer("Сделка не найдена.")
            await callback.answer()
            return
        # Increment deal counters
        await increment_total_deals(session, deal.shipper_id)
        await increment_total_deals(session, deal.carrier_id)
        carrier = await get_user_by_id(session, deal.carrier_id)

    await state.update_data(review_deal_id=deal_id, review_target_id=deal.carrier_id)
    await state.set_state(ReviewFlow.waiting_rating)
    await callback.message.answer(
        f"🤝 Сделка #{deal_id} завершена!\n\n"
        "Оцените перевозчика от 1 до 5:"
    )
    await callback.answer()

    # Notify carrier
    if carrier:
        try:
            await callback.bot.send_message(
                carrier.telegram_id,
                f"🤝 <b>Сделка #{deal_id} завершена!</b>\n"
                f"Заказчик подтвердил получение груза. Отличная работа!",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error("Notify carrier error: %s", e)


# ── Review flow ────────────────────────────────────────────────────────────


@router.message(ReviewFlow.waiting_rating)
async def on_review_rating(message: Message, state: FSMContext) -> None:
    try:
        rating = int(message.text.strip())
        if not 1 <= rating <= 5:
            raise ValueError
    except ValueError:
        await message.answer("Введите число от 1 до 5.")
        return
    await state.update_data(review_rating=rating)
    await state.set_state(ReviewFlow.waiting_comment)
    await message.answer("Напишите комментарий (или «-» чтобы пропустить):")


@router.message(ReviewFlow.waiting_comment)
async def on_review_comment(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()

    comment = message.text.strip() if message.text.strip() != "-" else None

    async with async_session() as session:
        user = await get_user(session, message.from_user.id)
        if not user:
            await message.answer("Ошибка. /start")
            return
        await create_review(
            session,
            author_id=user.id,
            target_id=data["review_target_id"],
            deal_id=data["review_deal_id"],
            rating=data["review_rating"],
            comment=comment,
        )

    stars = "⭐" * data["review_rating"]
    await message.answer(f"Спасибо за отзыв! {stars}")


# ── Cancel cargo ───────────────────────────────────────────────────────────


@router.callback_query(F.data.startswith("cancel_cargo_"))
async def on_cancel_cargo(callback: CallbackQuery) -> None:
    cargo_id = int(callback.data.replace("cancel_cargo_", ""))
    async with async_session() as session:
        user = await get_user(session, callback.from_user.id)
        if not user:
            await callback.answer("Ошибка")
            return
        ok = await cancel_cargo(session, cargo_id, user.id)
    if ok:
        await callback.message.answer(f"❌ Груз #{cargo_id} отменён.")
    else:
        await callback.message.answer("Не удалось отменить. Возможно, груз уже в работе.")
    await callback.answer()
