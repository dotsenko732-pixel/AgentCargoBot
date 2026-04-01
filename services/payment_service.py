"""Payment and subscription management service."""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.entities import (
    Cargo,
    Deal,
    DealStatus,
    Payment,
    PaymentStatus,
    PaymentType,
    SubscriptionPlan,
    User,
)


# ── Subscription checks ─────────────────────────────────────────────────────


def is_subscription_active(user: User) -> bool:
    """Check if user has an active paid subscription."""
    if user.subscription_plan == SubscriptionPlan.FREE:
        return False
    if user.subscription_until is None:
        return False
    return user.subscription_until > datetime.utcnow()


def get_cargo_limit(user: User) -> int | None:
    """Return monthly cargo limit. None = unlimited."""
    if is_subscription_active(user):
        return None  # unlimited for paid plans
    return settings.free_cargo_limit


def can_post_cargo(user: User) -> bool:
    """Check if user can post another cargo this month."""
    if is_subscription_active(user):
        return True
    _maybe_reset_month(user)
    return user.cargos_this_month < settings.free_cargo_limit


def _maybe_reset_month(user: User) -> None:
    """Reset monthly counter if new month started."""
    now = datetime.utcnow()
    if user.month_reset is None or user.month_reset.month != now.month or user.month_reset.year != now.year:
        user.cargos_this_month = 0
        user.month_reset = now


async def increment_cargo_count(session: AsyncSession, user: User) -> None:
    """Increment user's monthly cargo counter."""
    _maybe_reset_month(user)
    user.cargos_this_month += 1
    await session.commit()


# ── Subscription management ──────────────────────────────────────────────────


async def activate_subscription(
    session: AsyncSession,
    user_id: int,
    plan: SubscriptionPlan,
    months: int = 1,
) -> User | None:
    """Activate or extend a subscription."""
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        return None

    now = datetime.utcnow()
    # Extend if already active
    base = user.subscription_until if (user.subscription_until and user.subscription_until > now) else now
    user.subscription_plan = plan
    user.subscription_until = base + timedelta(days=30 * months)
    await session.commit()
    await session.refresh(user)
    return user


async def get_subscription_info(session: AsyncSession, user_id: int) -> dict:
    """Get user's subscription status."""
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        return {}

    active = is_subscription_active(user)
    _maybe_reset_month(user)

    return {
        "plan": user.subscription_plan.value,
        "active": active,
        "until": str(user.subscription_until)[:10] if user.subscription_until else None,
        "cargos_used": user.cargos_this_month,
        "cargos_limit": get_cargo_limit(user),
    }


# ── Commission ───────────────────────────────────────────────────────────────


def calculate_commission(deal_price: float) -> float:
    """Calculate platform commission for a deal."""
    return round(deal_price * settings.commission_rate, 2)


async def charge_commission(session: AsyncSession, deal_id: int) -> Payment | None:
    """Create a commission payment record when deal is confirmed."""
    stmt = select(Deal).where(Deal.id == deal_id)
    result = await session.execute(stmt)
    deal = result.scalar_one_or_none()
    if not deal or deal.commission_paid:
        return None

    commission = calculate_commission(deal.agreed_price)
    deal.commission_amount = commission
    deal.commission_paid = True

    payment = Payment(
        user_id=deal.carrier_id,
        payment_type=PaymentType.COMMISSION,
        amount=commission,
        currency=deal.currency,
        status=PaymentStatus.COMPLETED,
        description=f"Комиссия 2% со сделки #{deal_id}",
        reference_id=deal_id,
    )
    session.add(payment)
    await session.commit()
    await session.refresh(payment)
    return payment


# ── Cargo promotion ──────────────────────────────────────────────────────────


async def promote_cargo(
    session: AsyncSession, cargo_id: int, owner_id: int, hours: int = 24
) -> Cargo | None:
    """Boost a cargo listing to the top."""
    stmt = select(Cargo).where(Cargo.id == cargo_id, Cargo.owner_id == owner_id)
    result = await session.execute(stmt)
    cargo = result.scalar_one_or_none()
    if not cargo:
        return None

    cargo.is_promoted = True
    cargo.promoted_until = datetime.utcnow() + timedelta(hours=hours)
    await session.commit()
    await session.refresh(cargo)
    return cargo


# ── Payment records ──────────────────────────────────────────────────────────


async def create_payment(
    session: AsyncSession,
    user_id: int,
    payment_type: PaymentType,
    amount: float,
    currency: str = "KGS",
    description: str | None = None,
    reference_id: int | None = None,
    telegram_payment_id: str | None = None,
) -> Payment:
    """Create a payment record."""
    payment = Payment(
        user_id=user_id,
        payment_type=payment_type,
        amount=amount,
        currency=currency,
        status=PaymentStatus.PENDING,
        description=description,
        reference_id=reference_id,
        telegram_payment_id=telegram_payment_id,
    )
    session.add(payment)
    await session.commit()
    await session.refresh(payment)
    return payment


async def complete_payment(session: AsyncSession, payment_id: int, telegram_payment_id: str | None = None) -> Payment | None:
    """Mark payment as completed."""
    stmt = select(Payment).where(Payment.id == payment_id)
    result = await session.execute(stmt)
    payment = result.scalar_one_or_none()
    if not payment:
        return None
    payment.status = PaymentStatus.COMPLETED
    if telegram_payment_id:
        payment.telegram_payment_id = telegram_payment_id
    await session.commit()
    await session.refresh(payment)
    return payment


async def get_user_payments(session: AsyncSession, user_id: int, limit: int = 20) -> list[Payment]:
    """Get user's payment history."""
    stmt = (
        select(Payment)
        .where(Payment.user_id == user_id)
        .order_by(Payment.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


# ── Verification ─────────────────────────────────────────────────────────────


async def process_paid_verification(session: AsyncSession, user_id: int) -> User | None:
    """Mark user as verified after payment."""
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        return None
    user.is_verified = True
    await session.commit()
    await session.refresh(user)
    return user


# ── Revenue stats (admin) ───────────────────────────────────────────────────


async def get_platform_revenue(session: AsyncSession) -> dict:
    """Get total platform revenue by payment type."""
    from sqlalchemy import func as sa_func

    stmt = (
        select(Payment.payment_type, sa_func.sum(Payment.amount), sa_func.count())
        .where(Payment.status == PaymentStatus.COMPLETED)
        .group_by(Payment.payment_type)
    )
    result = await session.execute(stmt)
    data = {}
    for ptype, total, count in result.all():
        data[ptype.value] = {"total": float(total or 0), "count": count}
    return data
