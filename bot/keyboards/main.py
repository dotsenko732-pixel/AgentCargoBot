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

MAIN_MENU_BOTH = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📦 Разместить груз"), KeyboardButton(text="🚛 Найти грузы")],
        [KeyboardButton(text="🔍 Мои грузы"), KeyboardButton(text="🅿️ Мои машины")],
        [KeyboardButton(text="📊 Мои сделки")],
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


def match_results_keyboard(matches: list[dict], cargo_id: int = 0) -> InlineKeyboardMarkup:
    buttons = []
    for m in matches[:7]:
        vid = m.get("vehicle_id", 0)
        name = m.get("carrier_name", "N/A")
        score = m.get("score", 0)
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"🚛 {name} ({score}%)",
                    callback_data=f"selcar_{cargo_id}_{vid}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ── Carrier cargo actions ─────────────────────────────────────────────────


def cargo_interest_keyboard(cargo_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💰 Предложить цену",
                    callback_data=f"bid_cargo_{cargo_id}",
                ),
                InlineKeyboardButton(
                    text="📩 Откликнуться",
                    callback_data=f"respond_cargo_{cargo_id}",
                ),
            ]
        ]
    )


# ── Deal action buttons for carrier (accept / counter / reject) ──────────


def deal_response_keyboard(deal_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Принять",
                    callback_data=f"accept_deal_{deal_id}",
                ),
                InlineKeyboardButton(
                    text="💰 Встречная цена",
                    callback_data=f"counter_deal_{deal_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отклонить",
                    callback_data=f"reject_deal_{deal_id}",
                ),
            ],
        ]
    )


# ── Popular CIS cities ───────────────────────────────────────────────────


CIS_CITIES = [
    "Бишкек", "Ош", "Джалал-Абад", "Каракол", "Токмок",
    "Алматы", "Нур-Султан", "Шымкент", "Караганда",
    "Ташкент", "Самарканд",
    "Москва", "Новосибирск", "Екатеринбург", "Казань",
    "Душанбе", "Худжанд",
]


def city_keyboard(prefix: str) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for city in CIS_CITIES:
        row.append(
            InlineKeyboardButton(text=city, callback_data=f"{prefix}_{city}")
        )
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append(
        [InlineKeyboardButton(text="✏️ Ввести вручную", callback_data=f"{prefix}_manual")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ── Profile action buttons ────────────────────────────────────────────────


def profile_keyboard(is_verified: bool) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="⭐ Мои отзывы", callback_data="my_reviews"),
            InlineKeyboardButton(text="📊 Статистика", callback_data="my_stats"),
        ],
        [
            InlineKeyboardButton(text="🏢 Компания", callback_data="edit_company"),
            InlineKeyboardButton(text="✏️ Имя", callback_data="edit_name"),
        ],
    ]
    if not is_verified:
        buttons.append(
            [InlineKeyboardButton(
                text="✅ Запросить верификацию",
                callback_data="request_verify",
            )]
        )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ── Cargo repost button ──────────────────────────────────────────────────


def cargo_actions_keyboard(cargo_id: int, status: str) -> InlineKeyboardMarkup:
    buttons = []
    if status == "active":
        buttons.append(
            [InlineKeyboardButton(
                text=f"❌ Отменить #{cargo_id}",
                callback_data=f"cancel_cargo_{cargo_id}",
            )]
        )
    if status in ("delivered", "cancelled", "active"):
        buttons.append(
            [InlineKeyboardButton(
                text=f"🔄 Повторить #{cargo_id}",
                callback_data=f"repost_cargo_{cargo_id}",
            )]
        )
    return InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None


# ── Search filter keyboard ────────────────────────────────────────────────


def search_filter_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🏙 По маршруту", callback_data="filter_route"),
                InlineKeyboardButton(text="⚖️ По весу", callback_data="filter_weight"),
            ],
            [
                InlineKeyboardButton(text="🚛 По кузову", callback_data="filter_vtype"),
                InlineKeyboardButton(text="📋 Все грузы", callback_data="filter_all"),
            ],
        ]
    )
