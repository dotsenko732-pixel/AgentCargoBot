"""Profile and help handlers."""

from aiogram import F, Router
from aiogram.types import Message

from models.database import async_session
from services.cargo_service import get_user

router = Router()


@router.message(F.text == "👤 Профиль")
async def show_profile(message: Message) -> None:
    async with async_session() as session:
        user = await get_user(session, message.from_user.id)

    if not user:
        await message.answer("Вы не зарегистрированы. Нажмите /start")
        return

    verified = "✅ Верифицирован" if user.is_verified else "⚠️ Не верифицирован"
    await message.answer(
        f"👤 <b>Ваш профиль</b>\n\n"
        f"Имя: {user.full_name}\n"
        f"Телефон: {user.phone or 'не указан'}\n"
        f"Роль: {user.role.value}\n"
        f"Рейтинг: {'⭐' * int(user.rating)} ({user.rating:.1f})\n"
        f"Сделок: {user.total_deals}\n"
        f"Статус: {verified}\n",
        parse_mode="HTML",
    )


@router.message(F.text == "ℹ️ Помощь")
async def show_help(message: Message) -> None:
    await message.answer(
        "ℹ️ <b>AgentCargoBot — Помощь</b>\n\n"
        "<b>Для грузовладельцев:</b>\n"
        "• 📦 Разместить груз — создать заявку\n"
        "• 🔍 Мои грузы — посмотреть ваши заявки\n\n"
        "<b>Для перевозчиков:</b>\n"
        "• 🚛 Найти грузы — поиск грузов с AI\n"
        "• 🅿️ Мои машины — добавить транспорт\n\n"
        "<b>AI-агенты работают автоматически:</b>\n"
        "• 🎯 Agent-Matcher — подбор перевозчиков\n"
        "• 💰 Agent-Pricer — оценка справедливой цены\n"
        "• 🛡 Agent-Risk — проверка надёжности\n\n"
        "Вопросы? Пишите @AgentCargoBot_support",
        parse_mode="HTML",
    )
