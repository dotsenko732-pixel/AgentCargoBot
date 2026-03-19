"""Keyboard layouts for AgentCargoBot."""

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from models.entities import VehicleType

# ── Main menu ──────────────────────────────────────────────────────────────

MAIN_MENU_SHIPPER = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📦 Разместить груз")],
        [KeyboardButton(text="🔍 Мои грузы"), KeyboardButton(text="📊 Мои сделки")],
        [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="ℹ️ Помощь")],
    ],
    resize_keyboard=True,
)

MAIN_MENU_CARRIER = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🚛 Найти грузы")],
        [KeyboardButton(text="🅿️ Мои машины"), KeyboardButton(text="📊 Мои сделки")],
        [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="ℹ️ Помощь")],
    ],
    resize_keyboard=True,
)

# ── Role selection ─────────────────────────────────────────────────────────

ROLE_KEYBOARD = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="📦 Грузовладелец", callback_data="role_shipper")],
        [InlineKeyboardButton(text="🚛 Перевозчик", callback_data="role_carrier")],
        [InlineKeyboardButton(text="🔄 И то, и другое", callback_data="role_both")],
    ]
)

# ── Phone sharing ──────────────────────────────────────────────────────────

PHONE_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📱 Отправить номер телефона", request_contact=True)],
    ],
    resize_keyboard=True,
    one_time_keyboard=True,
)

# ── Vehicle type selection ─────────────────────────────────────────────────

VEHICLE_TYPE_LABELS = {
    VehicleType.TENT: "🏕 Тент",
    VehicleType.REF: "❄️ Рефрижератор",
    VehicleType.BOARD: "📐 Бортовой",
    VehicleType.CONTAINER: "📦 Контейнер",
    VehicleType.FLATBED: "🔲 Площадка",
    VehicleType.ISOTERM: "🌡 Изотерм",
    VehicleType.TANKER: "🛢 Цистерна",
    VehicleType.OTHER: "🔧 Другой",
}


def vehicle_type_keyboard(prefix: str = "vtype") -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for vtype, label in VEHICLE_TYPE_LABELS.items():
        row.append(
            InlineKeyboardButton(
                text=label, callback_data=f"{prefix}_{vtype.value}"
            )
        )
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append(
        [InlineKeyboardButton(text="Любой тип", callback_data=f"{prefix}_any")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ── Confirmation ───────────────────────────────────────────────────────────


def confirm_keyboard(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"{prefix}_yes"),
                InlineKeyboardButton(text="❌ Отмена", callback_data=f"{prefix}_no"),
            ]
        ]
    )


# ── Match results ──────────────────────────────────────────────────────────


def match_results_keyboard(matches: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for m in matches[:7]:
        vid = m.get("vehicle_id", 0)
        name = m.get("carrier_name", "N/A")
        score = m.get("score", 0)
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"🚛 {name} (совпадение {score}%)",
                    callback_data=f"select_carrier_{vid}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=buttons)
