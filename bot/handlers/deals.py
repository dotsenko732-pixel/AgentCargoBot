"""Deal management handlers: proposals, acceptance, status, reviews."""

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

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
    update_deal_status,
)

logger = logging.getLogger(__name__)
router = Router()

DEAL_STATUS_LABELS = {
    "proposed": "📩 Предложена",
    "accepted": "✅ Принята",
    "in_transit": "🚛 В пути",
    "delivered": "📦 Доставлено",
    "confirmed": "🤝 Завершена",
    "disputed": "⚠️ Спор",
    "cancelled": "❌ Отменена",
}


class ReviewFlow(StatesGroup):
    waiting_rating = State()
    waiting_comment = State()


# ── Select carrier from match results ──────────────────────────────────────


@router.callback_query(F.data.startswith("select_carrier_"))
async def on_select_carrier(callback: CallbackQuery) -> None:
    vehicle_id = callback.data.replace("select_carrier_", "")
    await callback.message.answer(
        f"🚛 Перевозчик (машина #{vehicle_id}) выбран!\n\n"
        "Хотите предложить сделку?",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="💰 Предложить сделку",
                        callback_data=f"propose_deal_{vehicle_id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🔙 Назад", callback_data="back_to_matches"
                    )
                ],
            ]
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "back_to_matches")
async def on_back_to_matches(callback: CallbackQuery) -> None:
    await callback.message.edit_text("Используйте список перевозчиков выше.")
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
                        text=f"✅ Принять сделку #{d['id']}",
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
        elif d["status"] == "in_transit" and d["shipper_id"] == user.id:
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=f"📦 Груз доставлен #{d['id']}",
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
    if deal:
        await callback.message.answer(f"✅ Сделка #{deal_id} принята! Заберите груз.")
    else:
        await callback.message.answer("Сделка не найдена.")
    await callback.answer()


@router.callback_query(F.data.startswith("reject_deal_"))
async def on_reject_deal(callback: CallbackQuery) -> None:
    deal_id = int(callback.data.replace("reject_deal_", ""))
    async with async_session() as session:
        deal = await update_deal_status(session, deal_id, DealStatus.CANCELLED)
    if deal:
        await callback.message.answer(f"❌ Сделка #{deal_id} отклонена.")
    else:
        await callback.message.answer("Сделка не найдена.")
    await callback.answer()


@router.callback_query(F.data.startswith("intransit_deal_"))
async def on_intransit_deal(callback: CallbackQuery) -> None:
    deal_id = int(callback.data.replace("intransit_deal_", ""))
    async with async_session() as session:
        deal = await update_deal_status(session, deal_id, DealStatus.IN_TRANSIT)
    if deal:
        await callback.message.answer(f"🚛 Сделка #{deal_id}: груз в пути!")
    else:
        await callback.message.answer("Сделка не найдена.")
    await callback.answer()


@router.callback_query(F.data.startswith("delivered_deal_"))
async def on_delivered_deal(callback: CallbackQuery) -> None:
    deal_id = int(callback.data.replace("delivered_deal_", ""))
    async with async_session() as session:
        deal = await update_deal_status(session, deal_id, DealStatus.DELIVERED)
    if deal:
        await callback.message.answer(
            f"📦 Сделка #{deal_id}: доставка отмечена. Подтвердите получение."
        )
    else:
        await callback.message.answer("Сделка не найдена.")
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_deal_"))
async def on_confirm_deal(callback: CallbackQuery, state: FSMContext) -> None:
    deal_id = int(callback.data.replace("confirm_deal_", ""))
    async with async_session() as session:
        deal = await update_deal_status(session, deal_id, DealStatus.CONFIRMED)
    if deal:
        await state.update_data(review_deal_id=deal_id, review_target_id=deal.carrier_id)
        await state.set_state(ReviewFlow.waiting_rating)
        await callback.message.answer(
            f"🤝 Сделка #{deal_id} завершена!\n\n"
            "Оцените перевозчика от 1 до 5:"
        )
    else:
        await callback.message.answer("Сделка не найдена.")
    await callback.answer()


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
