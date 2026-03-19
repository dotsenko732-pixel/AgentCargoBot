"""Database operations for cargos, vehicles, users, and deals."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.entities import (
    Cargo,
    CargoStatus,
    Deal,
    DealStatus,
    Review,
    User,
    UserRole,
    Vehicle,
    VehicleType,
)


# ── User operations ────────────────────────────────────────────────────────


async def get_or_create_user(
    session: AsyncSession,
    telegram_id: int,
    full_name: str,
    username: str | None = None,
) -> User:
    stmt = select(User).where(User.telegram_id == telegram_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if user:
        return user
    user = User(telegram_id=telegram_id, full_name=full_name, username=username)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def update_user_role(
    session: AsyncSession, telegram_id: int, role: UserRole
) -> User | None:
    stmt = select(User).where(User.telegram_id == telegram_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if user:
        user.role = role
        await session.commit()
        await session.refresh(user)
    return user


async def update_user_phone(
    session: AsyncSession, telegram_id: int, phone: str
) -> User | None:
    stmt = select(User).where(User.telegram_id == telegram_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if user:
        user.phone = phone
        await session.commit()
    return user


async def get_user(session: AsyncSession, telegram_id: int) -> User | None:
    stmt = select(User).where(User.telegram_id == telegram_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


# ── Vehicle operations ─────────────────────────────────────────────────────


async def add_vehicle(
    session: AsyncSession,
    owner_id: int,
    vehicle_type: VehicleType,
    max_weight_tons: float,
    max_volume_m3: float | None = None,
    current_city: str | None = None,
    destination_city: str | None = None,
) -> Vehicle:
    vehicle = Vehicle(
        owner_id=owner_id,
        vehicle_type=vehicle_type,
        max_weight_tons=max_weight_tons,
        max_volume_m3=max_volume_m3,
        current_city=current_city,
        destination_city=destination_city,
    )
    session.add(vehicle)
    await session.commit()
    await session.refresh(vehicle)
    return vehicle


async def get_available_vehicles(session: AsyncSession) -> list[dict]:
    stmt = (
        select(Vehicle, User)
        .join(User, Vehicle.owner_id == User.id)
        .where(Vehicle.is_available.is_(True))
    )
    result = await session.execute(stmt)
    vehicles = []
    for vehicle, user in result.all():
        vehicles.append(
            {
                "id": vehicle.id,
                "owner_name": user.full_name,
                "owner_rating": user.rating,
                "total_deals": user.total_deals,
                "is_verified": user.is_verified,
                "vehicle_type": vehicle.vehicle_type.value,
                "max_weight_tons": vehicle.max_weight_tons,
                "max_volume_m3": vehicle.max_volume_m3,
                "current_city": vehicle.current_city,
                "destination_city": vehicle.destination_city,
                "created_at": str(user.created_at) if user.created_at else "N/A",
            }
        )
    return vehicles


# ── Cargo operations ───────────────────────────────────────────────────────


async def create_cargo(
    session: AsyncSession,
    owner_id: int,
    title: str,
    weight_tons: float,
    origin_city: str,
    destination_city: str,
    vehicle_type_required: VehicleType | None = None,
    volume_m3: float | None = None,
    budget_min: float | None = None,
    budget_max: float | None = None,
    currency: str = "KGS",
    description: str | None = None,
    pickup_date: datetime | None = None,
    delivery_deadline: datetime | None = None,
) -> Cargo:
    cargo = Cargo(
        owner_id=owner_id,
        title=title,
        description=description,
        weight_tons=weight_tons,
        volume_m3=volume_m3,
        vehicle_type_required=vehicle_type_required,
        origin_city=origin_city,
        destination_city=destination_city,
        budget_min=budget_min,
        budget_max=budget_max,
        currency=currency,
        pickup_date=pickup_date,
        delivery_deadline=delivery_deadline,
    )
    session.add(cargo)
    await session.commit()
    await session.refresh(cargo)
    return cargo


async def get_active_cargos(session: AsyncSession) -> list[dict]:
    stmt = (
        select(Cargo, User)
        .join(User, Cargo.owner_id == User.id)
        .where(Cargo.status == CargoStatus.ACTIVE)
        .order_by(Cargo.created_at.desc())
    )
    result = await session.execute(stmt)
    cargos = []
    for cargo, user in result.all():
        cargos.append(
            {
                "id": cargo.id,
                "title": cargo.title,
                "description": cargo.description,
                "weight_tons": cargo.weight_tons,
                "volume_m3": cargo.volume_m3,
                "vehicle_type_required": (
                    cargo.vehicle_type_required.value
                    if cargo.vehicle_type_required
                    else None
                ),
                "origin_city": cargo.origin_city,
                "destination_city": cargo.destination_city,
                "budget_min": cargo.budget_min,
                "budget_max": cargo.budget_max,
                "currency": cargo.currency,
                "owner_name": user.full_name,
                "owner_rating": user.rating,
            }
        )
    return cargos


async def get_user_cargos(session: AsyncSession, owner_id: int) -> list[Cargo]:
    stmt = (
        select(Cargo)
        .where(Cargo.owner_id == owner_id)
        .order_by(Cargo.created_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


# ── Deal operations ────────────────────────────────────────────────────────


async def create_deal(
    session: AsyncSession,
    cargo_id: int,
    shipper_id: int,
    carrier_id: int,
    agreed_price: float,
    currency: str = "KGS",
) -> Deal:
    deal = Deal(
        cargo_id=cargo_id,
        shipper_id=shipper_id,
        carrier_id=carrier_id,
        agreed_price=agreed_price,
        currency=currency,
    )
    session.add(deal)
    # Update cargo status
    stmt = select(Cargo).where(Cargo.id == cargo_id)
    result = await session.execute(stmt)
    cargo = result.scalar_one_or_none()
    if cargo:
        cargo.status = CargoStatus.MATCHED
    await session.commit()
    await session.refresh(deal)
    return deal


# ── Review operations ──────────────────────────────────────────────────────


async def get_user_reviews(session: AsyncSession, user_id: int) -> list[dict]:
    stmt = select(Review).where(Review.target_id == user_id).order_by(
        Review.created_at.desc()
    )
    result = await session.execute(stmt)
    return [
        {"rating": r.rating, "comment": r.comment}
        for r in result.scalars().all()
    ]
