"""Start, registration, and onboarding handlers."""

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.keyboards.main import (
    MAIN_MENU_BOTH,
    MAIN_MENU_CARRIER,
    MAIN_MENU_SHIPPER,
    PHONE_KEYBOARD,
    ROLE_KEYBOARD,
)
from models.database import async_session
from models.entities import UserRole
from services.cargo_service import get_or_create_user, get_user, update_user_phone, update_user_role

logger = logging.getLogger(__name__)
router = Router()


class Registration(StatesGroup):
    waiting_role = State()
    waiting_phone = State()


WELCOME_TEXT = (
    "🚛 <b>AgentCargoBot</b> — первая AI-биржа грузоперевозок в СНГ!\n\n"
    "Здесь искусственный интеллект:\n"
    "• Подбирает идеальных перевозчиков за 15 секунд\n"
    "• Оценивает справедливую цену рынка\n"
    "• Проверяет надёжность перевозчика\n\n"
    "Для начала — выберите вашу роль:"
)


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    async with async_session() as session:
        user = await get_or_create_user(
            session,
            telegram_id=message.from_user.id,
            full_name=message.from_user.full_name,
            username=message.from_user.username,
        )

    if user.phone:
        menu = _get_menu(user.role)
        await message.answer(
            f"С возвращением, <b>{user.full_name}</b>! 👋",
            reply_markup=menu,
            parse_mode="HTML",
        )
        return

    await state.set_state(Registration.waiting_role)
    await message.answer(WELCOME_TEXT, reply_markup=ROLE_KEYBOARD, parse_mode="HTML")


@router.callback_query(F.data.startswith("role_"))
async def on_role_selected(callback: CallbackQuery, state: FSMContext) -> None:
    role_map = {
        "role_shipper": UserRole.SHIPPER,
        "role_carrier": UserRole.CARRIER,
        "role_both": UserRole.BOTH,
    }
    role = role_map.get(callback.data)
    if not role:
        await callback.answer("Неизвестная роль")
        return

    async with async_session() as session:
        await update_user_role(session, callback.from_user.id, role)

    await state.set_state(Registration.waiting_phone)
    await callback.message.answer(
        "📱 Отправьте ваш номер телефона для связи:",
        reply_markup=PHONE_KEYBOARD,
    )
    await callback.answer()


@router.message(Registration.waiting_phone, F.contact)
async def on_phone_shared(message: Message, state: FSMContext) -> None:
    phone = message.contact.phone_number
    async with async_session() as session:
        user = await update_user_phone(session, message.from_user.id, phone)

    await state.clear()
    menu = _get_menu(user.role)
    await message.answer(
        f"✅ Регистрация завершена!\n"
        f"Роль: <b>{_role_label(user.role)}</b>\n"
        f"Телефон: {phone}",
        reply_markup=menu,
        parse_mode="HTML",
    )
    # Send onboarding
    await _send_onboarding(message, user.role)


@router.message(Registration.waiting_phone)
async def on_phone_text(message: Message, state: FSMContext) -> None:
    text = message.text or ""
    text = text.strip().replace(" ", "").replace("-", "")
    if len(text) >= 9 and (text.startswith("+") or text[0].isdigit()):
        async with async_session() as session:
            user = await update_user_phone(session, message.from_user.id, text)
        await state.clear()
        menu = _get_menu(user.role)
        await message.answer(
            f"✅ Регистрация завершена!\nРоль: <b>{_role_label(user.role)}</b>\n"
            f"Телефон: {text}",
            reply_markup=menu,
            parse_mode="HTML",
        )
        await _send_onboarding(message, user.role)
    else:
        await message.answer(
            "Пожалуйста, отправьте корректный номер телефона или нажмите кнопку ниже.",
            reply_markup=PHONE_KEYBOARD,
        )


async def _send_onboarding(message: Message, role: UserRole) -> None:
    """Send role-specific onboarding tutorial."""
    if role in (UserRole.SHIPPER, UserRole.BOTH):
        await message.answer(
            "📖 <b>Быстрый старт для грузовладельца:</b>\n\n"
            "<b>Шаг 1.</b> Нажмите «📦 Разместить груз»\n"
            "Опишите груз, маршрут, вес и бюджет.\n\n"
            "<b>Шаг 2.</b> AI подберёт перевозчиков\n"
            "Вы увидите оценку рынка, список перевозчиков и их надёжность.\n\n"
            "<b>Шаг 3.</b> Выберите перевозчика и предложите цену\n"
            "Перевозчик получит уведомление и может принять, отклонить или предложить встречную цену.\n\n"
            "<b>Шаг 4.</b> Следите за сделкой в «📊 Мои сделки»\n"
            "Статусы: предложена → принята → в пути → доставлено → завершена.\n\n"
            "💡 <b>Совет:</b> заполните профиль и название компании — это повышает доверие!",
            parse_mode="HTML",
        )

    if role in (UserRole.CARRIER, UserRole.BOTH):
        await message.answer(
            "📖 <b>Быстрый старт для перевозчика:</b>\n\n"
            "<b>Шаг 1.</b> Добавьте машину в «🅿️ Мои машины»\n"
            "AI автоматически начнёт подбирать грузы.\n\n"
            "<b>Шаг 2.</b> Ищите грузы в «🚛 Найти грузы»\n"
            "Фильтруйте по маршруту, весу или типу кузова.\n\n"
            "<b>Шаг 3.</b> Откликнитесь или предложите свою цену\n"
            "Кнопка «💰 Предложить цену» — ваше ценовое предложение.\n"
            "Кнопка «📩 Откликнуться» — просто выразить интерес.\n\n"
            "<b>Шаг 4.</b> Управляйте сделками в «📊 Мои сделки»\n"
            "Принимайте, торгуйтесь, отмечайте доставку.\n\n"
            "💡 <b>Совет:</b> пройдите верификацию в профиле — это даёт приоритет в AI-подборе!",
            parse_mode="HTML",
        )


def _get_menu(role: UserRole):
    if role == UserRole.CARRIER:
        return MAIN_MENU_CARRIER
    if role == UserRole.BOTH:
        return MAIN_MENU_BOTH
    return MAIN_MENU_SHIPPER


def _role_label(role: UserRole) -> str:
    return {
        UserRole.SHIPPER: "📦 Грузовладелец",
        UserRole.CARRIER: "🚛 Перевозчик",
        UserRole.BOTH: "🔄 Грузовладелец + Перевозчик",
    }.get(role, str(role))
