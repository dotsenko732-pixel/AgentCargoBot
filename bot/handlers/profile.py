"""Profile, statistics, reviews, settings handlers."""

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.keyboards.main import profile_keyboard
from models.database import async_session
from services.cargo_service import (
    get_user,
    get_user_reviews_detailed,
    get_user_stats,
    update_user_company,
    update_user_name,
)
from services.payment_service import get_subscription_info

logger = logging.getLogger(__name__)
router = Router()

ROLE_LABELS = {
    "shipper": "📦 Грузовладелец",
    "carrier": "🚛 Перевозчик",
    "both": "🔄 Грузовладелец + Перевозчик",
}


class EditProfile(StatesGroup):
    waiting_company = State()
    waiting_name = State()


# ── Profile ───────────────────────────────────────────────────────────────


@router.message(F.text == "👤 Профиль")
async def show_profile(message: Message) -> None:
    async with async_session() as session:
        user = await get_user(session, message.from_user.id)

    if not user:
        await message.answer("Вы не зарегистрированы. Нажмите /start")
        return

    async with async_session() as session:
        sub_info = await get_subscription_info(session, user.id)

    PLAN_LABELS = {
        "free": "🆓 Бесплатный",
        "standard": "🥈 Стандарт",
        "business": "🥇 Бизнес",
    }

    verified = "✅ Верифицирован" if user.is_verified else "⚠️ Не верифицирован"
    stars = "⭐" * max(1, int(user.rating)) if user.rating > 0 else "нет оценок"
    company = f"\n🏢 Компания: {user.company_name}" if user.company_name else ""
    username = f"\n🔗 @{user.username}" if user.username else ""

    plan_label = PLAN_LABELS.get(sub_info.get("plan", "free"), "🆓 Бесплатный")
    sub_line = f"\n💎 Подписка: {plan_label}"
    if sub_info.get("active") and sub_info.get("until"):
        sub_line += f" (до {sub_info['until']})"

    limit = sub_info.get("cargos_limit")
    used = sub_info.get("cargos_used", 0)
    cargo_line = f"\n📦 Грузов в этом месяце: {used}" + (f"/{limit}" if limit else " (безлимит)")

    await message.answer(
        f"👤 <b>Ваш профиль</b>\n\n"
        f"Имя: <b>{user.full_name}</b>{username}{company}\n"
        f"📱 Телефон: {user.phone or 'не указан'}\n"
        f"Роль: {ROLE_LABELS.get(user.role.value, user.role.value)}\n"
        f"⭐ Рейтинг: {stars} ({user.rating:.1f})\n"
        f"📊 Сделок: {user.total_deals}\n"
        f"Статус: {verified}"
        f"{sub_line}{cargo_line}\n"
        f"📅 Регистрация: {str(user.created_at)[:10] if user.created_at else 'N/A'}",
        parse_mode="HTML",
        reply_markup=profile_keyboard(user.is_verified),
    )


# ── My reviews ────────────────────────────────────────────────────────────


@router.callback_query(F.data == "my_reviews")
async def show_my_reviews(callback: CallbackQuery) -> None:
    async with async_session() as session:
        user = await get_user(session, callback.from_user.id)
        if not user:
            await callback.answer("Ошибка")
            return
        reviews = await get_user_reviews_detailed(session, user.id)

    if not reviews:
        await callback.message.answer("У вас пока нет отзывов.")
        await callback.answer()
        return

    lines = ["⭐ <b>Ваши отзывы:</b>\n"]
    for r in reviews[:15]:
        stars = "⭐" * r["rating"]
        comment = r["comment"] or "без комментария"
        date = r["created_at"][:10] if r["created_at"] else ""
        lines.append(
            f"{stars} от <b>{r['author_name']}</b>\n"
            f"  {comment}\n"
            f"  <i>{date}</i>\n"
        )

    avg = sum(r["rating"] for r in reviews) / len(reviews)
    lines.append(f"\n📊 Средний рейтинг: <b>{avg:.1f}</b> ({len(reviews)} отзывов)")

    await callback.message.answer("\n".join(lines), parse_mode="HTML")
    await callback.answer()


# ── Statistics ────────────────────────────────────────────────────────────


@router.callback_query(F.data == "my_stats")
async def show_my_stats(callback: CallbackQuery) -> None:
    async with async_session() as session:
        user = await get_user(session, callback.from_user.id)
        if not user:
            await callback.answer("Ошибка")
            return
        stats = await get_user_stats(session, user.id)

    cargo_counts = stats["cargo_counts"]
    deal_counts = stats["deal_counts"]

    # Format cargo stats
    total_cargos = sum(cargo_counts.values())
    active_cargos = cargo_counts.get("active", 0)

    # Format deal stats
    total_deals_count = sum(deal_counts.values())
    confirmed = deal_counts.get("confirmed", 0)
    cancelled = deal_counts.get("cancelled", 0)

    # Success rate
    finished = confirmed + cancelled
    success_rate = f"{confirmed / finished * 100:.0f}%" if finished > 0 else "—"

    lines = [
        f"📊 <b>Ваша статистика</b>\n",
        f"📦 Грузов размещено: {total_cargos}",
        f"  🟢 Активных: {active_cargos}",
        f"",
        f"🤝 Сделок всего: {total_deals_count}",
        f"  ✅ Завершено: {confirmed}",
        f"  ❌ Отменено: {cancelled}",
        f"  📈 Успешность: {success_rate}",
        f"",
        f"🚛 Машин: {stats['vehicle_count']}",
        f"",
    ]

    if stats["revenue"] > 0:
        lines.append(f"💰 Заработано: <b>{int(stats['revenue'])} сом</b>")
    if stats["spent"] > 0:
        lines.append(f"💳 Потрачено: <b>{int(stats['spent'])} сом</b>")

    await callback.message.answer("\n".join(lines), parse_mode="HTML")
    await callback.answer()


# ── Edit company name ─────────────────────────────────────────────────────


@router.callback_query(F.data == "edit_company")
async def on_edit_company(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(EditProfile.waiting_company)
    await callback.message.answer(
        "🏢 Введите название вашей компании (или «-» чтобы удалить):"
    )
    await callback.answer()


@router.message(EditProfile.waiting_company)
async def on_company_entered(message: Message, state: FSMContext) -> None:
    await state.clear()
    company = message.text.strip()
    if company == "-":
        company = ""

    async with async_session() as session:
        await update_user_company(session, message.from_user.id, company or None)

    if company:
        await message.answer(f"✅ Компания обновлена: <b>{company}</b>", parse_mode="HTML")
    else:
        await message.answer("✅ Название компании удалено.")


# ── Edit name ─────────────────────────────────────────────────────────────


@router.callback_query(F.data == "edit_name")
async def on_edit_name(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(EditProfile.waiting_name)
    await callback.message.answer("✏️ Введите новое имя:")
    await callback.answer()


@router.message(EditProfile.waiting_name)
async def on_name_entered(message: Message, state: FSMContext) -> None:
    await state.clear()
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("Имя слишком короткое.")
        return

    async with async_session() as session:
        await update_user_name(session, message.from_user.id, name)

    await message.answer(f"✅ Имя обновлено: <b>{name}</b>", parse_mode="HTML")


# ── Verification request ─────────────────────────────────────────────────


@router.callback_query(F.data == "request_verify")
async def on_request_verify(callback: CallbackQuery) -> None:
    async with async_session() as session:
        user = await get_user(session, callback.from_user.id)

    if not user:
        await callback.answer("Ошибка")
        return

    if user.is_verified:
        await callback.message.answer("✅ Вы уже верифицированы!")
        await callback.answer()
        return

    await callback.message.answer(
        "📋 <b>Верификация аккаунта</b>\n\n"
        "Для верификации отправьте в @AgentCargoBot_support:\n\n"
        "1. Фото удостоверения личности\n"
        "2. Фото с документом в руке (селфи)\n"
        "3. Если вы перевозчик — фото тех. паспорта авто\n"
        "4. Если у вас компания — свидетельство о регистрации\n\n"
        "Верификация занимает до 24 часов.\n"
        "Верифицированные пользователи получают:\n"
        "✅ Значок доверия в профиле\n"
        "✅ Приоритет в подборе AI\n"
        "✅ Повышенный лимит заявок",
        parse_mode="HTML",
    )
    await callback.answer()


# ── Help ──────────────────────────────────────────────────────────────────


@router.message(F.text == "ℹ️ Помощь")
async def show_help(message: Message) -> None:
    await message.answer(
        "ℹ️ <b>AgentCargoBot — AI-биржа грузоперевозок</b>\n\n"
        "<b>Для грузовладельцев:</b>\n"
        "📦 Разместить груз — AI оценит цену и найдёт перевозчика\n"
        "🔍 Мои грузы — управление заявками, повтор в 1 клик\n\n"
        "<b>Для перевозчиков:</b>\n"
        "🚛 Найти грузы — поиск с фильтрами (маршрут, вес, кузов)\n"
        "💰 Предложить цену — своя цена за перевозку\n"
        "🅿️ Мои машины — AI подберёт грузы автоматически\n\n"
        "<b>Сделки и торг:</b>\n"
        "📊 Мои сделки — управление, встречные предложения\n"
        "💰 Встречная цена — если цена не устраивает\n"
        "⚠️ Спор — если что-то пошло не так\n\n"
        "<b>AI-агенты:</b>\n"
        "🎯 Agent-Matcher — подбор за 15 секунд\n"
        "💰 Agent-Pricer — справедливая цена рынка\n"
        "🛡 Agent-Risk — проверка надёжности\n\n"
        "<b>Тарифы:</b>\n"
        "🆓 Бесплатный — 3 груза/мес, базовый поиск\n"
        "🥈 Стандарт (990 сом/мес) — безлимит, AI-подбор, приоритет\n"
        "🥇 Бизнес (2990 сом/мес) — всё + аналитика, VIP, API\n"
        "🚀 Продвижение груза — 150 сом (топ на 24ч)\n"
        "✅ Верификация — 500 сом (зелёная галочка)\n\n"
        "<b>Профиль:</b>\n"
        "👤 Профиль — статистика, отзывы, подписка\n"
        "💎 Подписка — управление тарифом\n"
        "💳 Платежи — история операций\n\n"
        "Поддержка: @AgentCargoBot_support",
        parse_mode="HTML",
    )
