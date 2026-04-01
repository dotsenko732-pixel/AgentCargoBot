"""Payment, subscription, and admin handlers with Telegram Payments."""

import logging

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)

from bot.keyboards.main import (
    admin_keyboard,
    payment_confirm_keyboard,
    subscription_keyboard,
)
from config import settings
from models.database import async_session
from models.entities import PaymentType, SubscriptionPlan
from services.cargo_service import get_user
from services.payment_service import (
    activate_subscription,
    complete_payment,
    create_payment,
    get_platform_revenue,
    get_subscription_info,
    get_user_payments,
    process_paid_verification,
    promote_cargo,
)

logger = logging.getLogger(__name__)
router = Router()

# Admin telegram IDs — add your own ID here
ADMIN_IDS: set[int] = set()

PLAN_LABELS = {
    "free": "🆓 Бесплатный",
    "standard": "🥈 Стандарт",
    "business": "🥇 Бизнес",
}

PLAN_FEATURES = {
    "free": "3 груза/мес, базовый поиск",
    "standard": "Безлимит грузов, AI-подбор, приоритет, уведомления",
    "business": "Всё из Стандарт + аналитика цен, VIP-значок, API-доступ",
}


# ── Subscription info ────────────────────────────────────────────────────────


@router.callback_query(F.data == "my_subscription")
async def show_subscription(callback: CallbackQuery) -> None:
    async with async_session() as session:
        user = await get_user(session, callback.from_user.id)
        if not user:
            await callback.answer("Ошибка")
            return
        sub_info = await get_subscription_info(session, user.id)

    plan = sub_info["plan"]
    plan_label = PLAN_LABELS.get(plan, plan)
    features = PLAN_FEATURES.get(plan, "")

    lines = [
        f"💎 <b>Ваша подписка</b>\n",
        f"Тариф: {plan_label}",
        f"Возможности: {features}",
    ]

    if sub_info["active"]:
        lines.append(f"Активна до: <b>{sub_info['until']}</b>")
    elif plan != "free":
        lines.append("Подписка истекла")

    limit = sub_info["cargos_limit"]
    used = sub_info["cargos_used"]
    if limit is not None:
        lines.append(f"\n📦 Грузов в этом месяце: {used}/{limit}")
    else:
        lines.append(f"\n📦 Грузов в этом месяце: {used} (безлимит)")

    lines.append("\n<b>Доступные тарифы:</b>")
    lines.append("🥈 <b>Стандарт</b> — 990 сом/мес")
    lines.append("  Безлимит грузов, AI-подбор, приоритет")
    lines.append("🥇 <b>Бизнес</b> — 2990 сом/мес")
    lines.append("  Всё + аналитика, VIP, API")

    await callback.message.answer(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=subscription_keyboard(plan),
    )
    await callback.answer()


# ── Buy subscription ─────────────────────────────────────────────────────────


@router.callback_query(F.data.startswith("buy_sub_"))
async def on_buy_subscription(callback: CallbackQuery) -> None:
    plan_str = callback.data.replace("buy_sub_", "")

    if plan_str == "standard":
        price = settings.standard_price_kgs
        label = "Стандарт"
    elif plan_str == "business":
        price = settings.business_price_kgs
        label = "Бизнес"
    else:
        await callback.answer("Неизвестный тариф")
        return

    if settings.payment_provider_token:
        # Use Telegram Payments
        await callback.message.answer_invoice(
            title=f"Подписка «{label}»",
            description=f"Тариф «{label}» на 30 дней. {PLAN_FEATURES.get(plan_str, '')}",
            payload=f"sub_{plan_str}",
            provider_token=settings.payment_provider_token,
            currency="KGS",
            prices=[LabeledPrice(label=f"Подписка {label}", amount=price * 100)],
            start_parameter=f"sub-{plan_str}",
        )
    else:
        # Fallback: manual confirmation (for testing / pre-launch)
        async with async_session() as session:
            user = await get_user(session, callback.from_user.id)
            if not user:
                await callback.answer("Ошибка")
                return
            payment = await create_payment(
                session,
                user_id=user.id,
                payment_type=PaymentType.SUBSCRIPTION,
                amount=price,
                description=f"Подписка {label}",
            )

        await callback.message.answer(
            f"💳 <b>Оплата подписки «{label}»</b>\n\n"
            f"Сумма: <b>{price} сом</b>\n\n"
            f"Для оплаты переведите {price} сом на:\n"
            f"📱 Mbank / O!Деньги / ЭЛСОМ: +996XXXXXXXXX\n"
            f"Комментарий: <code>PAY-{payment.id}</code>\n\n"
            f"После оплаты нажмите кнопку ниже:",
            parse_mode="HTML",
            reply_markup=payment_confirm_keyboard(f"sub_{plan_str}", payment.id),
        )
    await callback.answer()


# ── Buy verification ─────────────────────────────────────────────────────────


@router.callback_query(F.data == "buy_verification")
async def on_buy_verification(callback: CallbackQuery) -> None:
    price = settings.verify_price_kgs

    if settings.payment_provider_token:
        await callback.message.answer_invoice(
            title="Верификация аккаунта",
            description="Верификация + зелёная галочка + приоритет в AI-подборе",
            payload="verification",
            provider_token=settings.payment_provider_token,
            currency="KGS",
            prices=[LabeledPrice(label="Верификация", amount=price * 100)],
            start_parameter="verification",
        )
    else:
        async with async_session() as session:
            user = await get_user(session, callback.from_user.id)
            if not user:
                await callback.answer("Ошибка")
                return
            if user.is_verified:
                await callback.message.answer("Вы уже верифицированы!")
                await callback.answer()
                return
            payment = await create_payment(
                session,
                user_id=user.id,
                payment_type=PaymentType.VERIFICATION,
                amount=price,
                description="Верификация аккаунта",
            )

        await callback.message.answer(
            f"✅ <b>Верификация аккаунта</b>\n\n"
            f"Сумма: <b>{price} сом</b>\n\n"
            f"Что вы получите:\n"
            f"  ✅ Зелёная галочка в профиле\n"
            f"  ✅ Приоритет в AI-подборе\n"
            f"  ✅ Повышенное доверие клиентов\n\n"
            f"Переведите {price} сом на:\n"
            f"📱 Mbank / O!Деньги / ЭЛСОМ: +996XXXXXXXXX\n"
            f"Комментарий: <code>PAY-{payment.id}</code>\n\n"
            f"После оплаты нажмите кнопку:",
            parse_mode="HTML",
            reply_markup=payment_confirm_keyboard("verification", payment.id),
        )
    await callback.answer()


# ── Promote cargo ────────────────────────────────────────────────────────────


@router.callback_query(F.data.startswith("promote_cargo_"))
async def on_promote_cargo(callback: CallbackQuery) -> None:
    cargo_id = int(callback.data.replace("promote_cargo_", ""))
    price = settings.promo_price_kgs

    if settings.payment_provider_token:
        await callback.message.answer_invoice(
            title=f"Продвижение груза #{cargo_id}",
            description="Поднять груз в топ выдачи на 24 часа",
            payload=f"promo_{cargo_id}",
            provider_token=settings.payment_provider_token,
            currency="KGS",
            prices=[LabeledPrice(label="Продвижение", amount=price * 100)],
            start_parameter=f"promo-{cargo_id}",
        )
    else:
        async with async_session() as session:
            user = await get_user(session, callback.from_user.id)
            if not user:
                await callback.answer("Ошибка")
                return
            payment = await create_payment(
                session,
                user_id=user.id,
                payment_type=PaymentType.PROMO_BOOST,
                amount=price,
                description=f"Продвижение груза #{cargo_id}",
                reference_id=cargo_id,
            )

        await callback.message.answer(
            f"🚀 <b>Продвижение груза #{cargo_id}</b>\n\n"
            f"Сумма: <b>{price} сом</b>\n"
            f"Ваш груз будет в топе 24 часа.\n\n"
            f"Переведите {price} сом:\n"
            f"Комментарий: <code>PAY-{payment.id}</code>\n\n"
            f"После оплаты нажмите кнопку:",
            parse_mode="HTML",
            reply_markup=payment_confirm_keyboard(f"promo_{cargo_id}", payment.id),
        )
    await callback.answer()


# ── Manual payment confirmation (fallback without provider) ──────────────────


@router.callback_query(F.data.startswith("pay_confirm_"))
async def on_manual_pay_confirm(callback: CallbackQuery) -> None:
    """Handle manual payment confirmation (pre-launch / testing mode)."""
    data = callback.data.replace("pay_confirm_", "")
    # Format: type_refid_paymentid  →  e.g. "sub_standard_5" or "promo_12_5"
    parts = data.rsplit("_", 1)
    if len(parts) != 2:
        await callback.answer("Ошибка данных")
        return
    action, payment_id_str = parts[0], parts[1]
    payment_id = int(payment_id_str)

    async with async_session() as session:
        user = await get_user(session, callback.from_user.id)
        if not user:
            await callback.answer("Ошибка")
            return

        payment = await complete_payment(session, payment_id)
        if not payment:
            await callback.message.answer("Платёж не найден.")
            await callback.answer()
            return

        # Process based on type
        if action.startswith("sub_"):
            plan_str = action.replace("sub_", "")
            plan = SubscriptionPlan(plan_str)
            await activate_subscription(session, user.id, plan)
            await callback.message.answer(
                f"🎉 <b>Подписка «{PLAN_LABELS.get(plan_str, plan_str)}» активирована!</b>\n\n"
                f"Действует 30 дней. Спасибо за доверие!",
                parse_mode="HTML",
            )
        elif action == "verification":
            await process_paid_verification(session, user.id)
            await callback.message.answer(
                "✅ <b>Аккаунт верифицирован!</b>\n\n"
                "Теперь у вас есть значок доверия и приоритет в подборе.",
                parse_mode="HTML",
            )
        elif action.startswith("promo_"):
            cargo_id = int(action.replace("promo_", ""))
            await promote_cargo(session, cargo_id, user.id)
            await callback.message.answer(
                f"🚀 <b>Груз #{cargo_id} поднят в топ!</b>\n\n"
                f"Будет в топе выдачи 24 часа.",
                parse_mode="HTML",
            )

    await callback.answer()


@router.callback_query(F.data == "pay_cancel")
async def on_pay_cancel(callback: CallbackQuery) -> None:
    await callback.message.answer("❌ Оплата отменена.")
    await callback.answer()


# ── Telegram Payments: pre-checkout + successful payment ─────────────────────


@router.pre_checkout_query()
async def on_pre_checkout(pre_checkout: PreCheckoutQuery) -> None:
    """Always approve pre-checkout (validation happens at invoice creation)."""
    await pre_checkout.answer(ok=True)


@router.message(F.successful_payment)
async def on_successful_payment(message: Message) -> None:
    """Process successful Telegram Payment."""
    payment = message.successful_payment
    payload = payment.invoice_payload

    async with async_session() as session:
        user = await get_user(session, message.from_user.id)
        if not user:
            return

        if payload.startswith("sub_"):
            plan_str = payload.replace("sub_", "")
            plan = SubscriptionPlan(plan_str)
            await activate_subscription(session, user.id, plan)
            await create_payment(
                session,
                user_id=user.id,
                payment_type=PaymentType.SUBSCRIPTION,
                amount=payment.total_amount / 100,
                currency=payment.currency,
                description=f"Подписка {plan_str}",
                telegram_payment_id=payment.telegram_payment_charge_id,
            )
            # Mark as completed immediately
            from services.payment_service import complete_payment as cp
            payments = await get_user_payments(session, user.id, limit=1)
            if payments:
                await cp(session, payments[0].id, payment.telegram_payment_charge_id)

            await message.answer(
                f"🎉 <b>Подписка «{PLAN_LABELS.get(plan_str, plan_str)}» активирована!</b>\n"
                f"Действует 30 дней.",
                parse_mode="HTML",
            )

        elif payload == "verification":
            await process_paid_verification(session, user.id)
            await create_payment(
                session, user_id=user.id,
                payment_type=PaymentType.VERIFICATION,
                amount=payment.total_amount / 100,
                telegram_payment_id=payment.telegram_payment_charge_id,
            )
            await message.answer(
                "✅ <b>Аккаунт верифицирован!</b>",
                parse_mode="HTML",
            )

        elif payload.startswith("promo_"):
            cargo_id = int(payload.replace("promo_", ""))
            await promote_cargo(session, cargo_id, user.id)
            await create_payment(
                session, user_id=user.id,
                payment_type=PaymentType.PROMO_BOOST,
                amount=payment.total_amount / 100,
                reference_id=cargo_id,
                telegram_payment_id=payment.telegram_payment_charge_id,
            )
            await message.answer(
                f"🚀 <b>Груз #{cargo_id} в топе 24 часа!</b>",
                parse_mode="HTML",
            )


# ── Payment history ──────────────────────────────────────────────────────────


@router.callback_query(F.data == "payment_history")
async def show_payment_history(callback: CallbackQuery) -> None:
    async with async_session() as session:
        user = await get_user(session, callback.from_user.id)
        if not user:
            await callback.answer("Ошибка")
            return
        payments = await get_user_payments(session, user.id)

    if not payments:
        await callback.message.answer("💳 У вас пока нет платежей.")
        await callback.answer()
        return

    TYPE_LABELS = {
        "subscription": "💎 Подписка",
        "promo_boost": "🚀 Продвижение",
        "verification": "✅ Верификация",
        "commission": "📊 Комиссия",
    }
    STATUS_LABELS = {
        "pending": "⏳",
        "completed": "✅",
        "refunded": "🔄",
        "failed": "❌",
    }

    lines = ["💳 <b>История платежей:</b>\n"]
    for p in payments[:15]:
        type_label = TYPE_LABELS.get(p.payment_type.value, p.payment_type.value)
        status_icon = STATUS_LABELS.get(p.status.value, "")
        date = str(p.created_at)[:10] if p.created_at else ""
        lines.append(
            f"{status_icon} {type_label} — <b>{int(p.amount)} {p.currency}</b>\n"
            f"  {p.description or ''} | {date}"
        )

    await callback.message.answer("\n".join(lines), parse_mode="HTML")
    await callback.answer()


# ── Admin panel ──────────────────────────────────────────────────────────────


@router.message(F.text == "/admin")
async def admin_panel(message: Message) -> None:
    if ADMIN_IDS and message.from_user.id not in ADMIN_IDS:
        return

    async with async_session() as session:
        from sqlalchemy import func as sa_func, select
        from models.entities import Deal, DealStatus, Payment, PaymentStatus, User

        # User stats
        total_users = (await session.execute(
            select(sa_func.count()).select_from(User)
        )).scalar() or 0

        # Subscription stats
        paid_users = (await session.execute(
            select(sa_func.count()).select_from(User).where(
                User.subscription_plan != SubscriptionPlan.FREE
            )
        )).scalar() or 0

        verified_users = (await session.execute(
            select(sa_func.count()).select_from(User).where(User.is_verified.is_(True))
        )).scalar() or 0

        # Deal stats
        total_deals = (await session.execute(
            select(sa_func.count()).select_from(Deal)
        )).scalar() or 0

        confirmed_deals = (await session.execute(
            select(sa_func.count()).select_from(Deal).where(
                Deal.status == DealStatus.CONFIRMED
            )
        )).scalar() or 0

        deal_volume = (await session.execute(
            select(sa_func.coalesce(sa_func.sum(Deal.agreed_price), 0)).where(
                Deal.status == DealStatus.CONFIRMED
            )
        )).scalar() or 0

        # Revenue
        total_revenue = (await session.execute(
            select(sa_func.coalesce(sa_func.sum(Payment.amount), 0)).where(
                Payment.status == PaymentStatus.COMPLETED
            )
        )).scalar() or 0

        commission_revenue = (await session.execute(
            select(sa_func.coalesce(sa_func.sum(Payment.amount), 0)).where(
                Payment.status == PaymentStatus.COMPLETED,
                Payment.payment_type == PaymentType.COMMISSION,
            )
        )).scalar() or 0

        sub_revenue = (await session.execute(
            select(sa_func.coalesce(sa_func.sum(Payment.amount), 0)).where(
                Payment.status == PaymentStatus.COMPLETED,
                Payment.payment_type == PaymentType.SUBSCRIPTION,
            )
        )).scalar() or 0

    await message.answer(
        f"🔧 <b>ADMIN — AgentCargoBot</b>\n\n"
        f"<b>Пользователи:</b>\n"
        f"  👥 Всего: {total_users}\n"
        f"  💎 Платных: {paid_users}\n"
        f"  ✅ Верифицированных: {verified_users}\n\n"
        f"<b>Сделки:</b>\n"
        f"  🤝 Всего: {total_deals}\n"
        f"  ✅ Завершено: {confirmed_deals}\n"
        f"  💰 Объём: {int(deal_volume):,} сом\n\n"
        f"<b>Доходы платформы:</b>\n"
        f"  💰 Всего: <b>{int(total_revenue):,} сом</b>\n"
        f"  📊 Комиссии: {int(commission_revenue):,} сом\n"
        f"  💎 Подписки: {int(sub_revenue):,} сом\n\n"
        f"Комиссия: {settings.commission_rate * 100:.0f}%\n"
        f"Стандарт: {settings.standard_price_kgs} сом/мес\n"
        f"Бизнес: {settings.business_price_kgs} сом/мес",
        parse_mode="HTML",
        reply_markup=admin_keyboard(),
    )


@router.callback_query(F.data == "admin_revenue")
async def admin_revenue_detail(callback: CallbackQuery) -> None:
    if ADMIN_IDS and callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Нет доступа")
        return

    async with async_session() as session:
        revenue = await get_platform_revenue(session)

    lines = ["💰 <b>Детализация доходов:</b>\n"]
    TYPE_LABELS = {
        "subscription": "💎 Подписки",
        "promo_boost": "🚀 Продвижение",
        "verification": "✅ Верификация",
        "commission": "📊 Комиссии",
    }
    total = 0
    for ptype, data in revenue.items():
        label = TYPE_LABELS.get(ptype, ptype)
        lines.append(f"{label}: <b>{int(data['total']):,} сом</b> ({data['count']} шт)")
        total += data["total"]

    lines.append(f"\n<b>Итого: {int(total):,} сом</b>")

    await callback.message.answer("\n".join(lines), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_users")
async def admin_users_detail(callback: CallbackQuery) -> None:
    if ADMIN_IDS and callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Нет доступа")
        return

    async with async_session() as session:
        from sqlalchemy import func as sa_func, select
        from models.entities import User

        stmt = (
            select(User.subscription_plan, sa_func.count())
            .group_by(User.subscription_plan)
        )
        result = await session.execute(stmt)
        plan_counts = dict(result.all())

        # Latest users
        stmt = select(User).order_by(User.created_at.desc()).limit(10)
        result = await session.execute(stmt)
        latest = list(result.scalars().all())

    lines = ["👥 <b>Пользователи по тарифам:</b>\n"]
    for plan, count in plan_counts.items():
        label = PLAN_LABELS.get(plan.value if hasattr(plan, 'value') else plan, str(plan))
        lines.append(f"  {label}: {count}")

    lines.append("\n<b>Последние регистрации:</b>")
    for u in latest[:10]:
        verified = "✅" if u.is_verified else ""
        date = str(u.created_at)[:10] if u.created_at else ""
        lines.append(f"  {u.full_name} {verified} — {date}")

    await callback.message.answer("\n".join(lines), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_deals")
async def admin_deals_detail(callback: CallbackQuery) -> None:
    if ADMIN_IDS and callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Нет доступа")
        return

    async with async_session() as session:
        from sqlalchemy import func as sa_func, select
        from models.entities import Deal

        stmt = (
            select(Deal.status, sa_func.count(), sa_func.coalesce(sa_func.sum(Deal.agreed_price), 0))
            .group_by(Deal.status)
        )
        result = await session.execute(stmt)
        rows = result.all()

    DEAL_LABELS = {
        "proposed": "📩 Предложены",
        "accepted": "✅ Приняты",
        "in_transit": "🚛 В пути",
        "delivered": "📦 Доставлены",
        "confirmed": "🤝 Завершены",
        "disputed": "⚠️ Споры",
        "cancelled": "❌ Отменены",
    }

    lines = ["📊 <b>Сделки по статусам:</b>\n"]
    total_count = 0
    total_volume = 0
    for status, count, volume in rows:
        s = status.value if hasattr(status, 'value') else status
        label = DEAL_LABELS.get(s, s)
        lines.append(f"  {label}: {count} шт | {int(volume):,} сом")
        total_count += count
        total_volume += volume

    lines.append(f"\n<b>Итого: {total_count} сделок, {int(total_volume):,} сом</b>")

    await callback.message.answer("\n".join(lines), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_refresh")
async def admin_refresh(callback: CallbackQuery) -> None:
    await callback.answer("Обновлено")
    # Re-trigger admin panel
    await admin_panel(callback.message)
