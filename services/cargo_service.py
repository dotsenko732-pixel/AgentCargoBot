"""Database operations for cargos, vehicles, users, and deals."""

from datetime import datetime

from sqlalchemy import func as sa_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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


async def update_user_company(
    session: AsyncSession, telegram_id: int, company_name: str
) -> User | None:
    stmt = select(User).where(User.telegram_id == telegram_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if user:
        user.company_name = company_name
        await session.commit()
    return user


async def update_user_name(
    session: AsyncSession, telegram_id: int, full_name: str
) -> User | None:
    stmt = select(User).where(User.telegram_id == telegram_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if user:
        user.full_name = full_name
        await session.commit()
    return user


async def get_user_stats(session: AsyncSession, user_id: int) -> dict:
    """Aggregate stats for a user."""
    # Count cargos by status
    cargo_stmt = (
        select(Cargo.status, sa_func.count())
        .where(Cargo.owner_id == user_id)
        .group_by(Cargo.status)
    )
    cargo_result = await session.execute(cargo_stmt)
    cargo_counts = dict(cargo_result.all())

    # Count deals by status
    deal_stmt = (
        select(Deal.status, sa_func.count())
        .where((Deal.shipper_id == user_id) | (Deal.carrier_id == user_id))
        .group_by(Deal.status)
    )
    deal_result = await session.execute(deal_stmt)
    deal_counts = dict(deal_result.all())

    # Total revenue / spend
    revenue_stmt = (
        select(sa_func.coalesce(sa_func.sum(Deal.agreed_price), 0))
        .where(Deal.carrier_id == user_id)
        .where(Deal.status == DealStatus.CONFIRMED)
    )
    revenue = (await session.execute(revenue_stmt)).scalar() or 0

    spent_stmt = (
        select(sa_func.coalesce(sa_func.sum(Deal.agreed_price), 0))
        .where(Deal.shipper_id == user_id)
        .where(Deal.status == DealStatus.CONFIRMED)
    )
    spent = (await session.execute(spent_stmt)).scalar() or 0

    # Vehicle count
    vehicle_stmt = select(sa_func.count()).where(Vehicle.owner_id == user_id)
    vehicle_count = (await session.execute(vehicle_stmt)).scalar() or 0

    return {
        "cargo_counts": cargo_counts,
        "deal_counts": deal_counts,
        "revenue": revenue,
        "spent": spent,
        "vehicle_count": vehicle_count,
    }


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


async def repost_cargo(session: AsyncSession, cargo_id: int, owner_id: int) -> Cargo | None:
    """Clone an existing cargo as a new ACTIVE listing."""
    original = await get_cargo_by_id(session, cargo_id)
    if not original or original.owner_id != owner_id:
        return None
    new_cargo = Cargo(
        owner_id=owner_id,
        title=original.title,
        description=original.description,
        weight_tons=original.weight_tons,
        volume_m3=original.volume_m3,
        vehicle_type_required=original.vehicle_type_required,
        origin_city=original.origin_city,
        destination_city=original.destination_city,
        budget_min=original.budget_min,
        budget_max=original.budget_max,
        currency=original.currency,
    )
    session.add(new_cargo)
    await session.commit()
    await session.refresh(new_cargo)
    return new_cargo


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


async def search_cargos(
    session: AsyncSession,
    origin_city: str | None = None,
    destination_city: str | None = None,
    max_weight: float | None = None,
    vehicle_type: str | None = None,
) -> list[dict]:
    """Search active cargos with filters."""
    stmt = (
        select(Cargo, User)
        .join(User, Cargo.owner_id == User.id)
        .where(Cargo.status == CargoStatus.ACTIVE)
    )
    if origin_city:
        stmt = stmt.where(Cargo.origin_city.ilike(f"%{origin_city}%"))
    if destination_city:
        stmt = stmt.where(Cargo.destination_city.ilike(f"%{destination_city}%"))
    if max_weight:
        stmt = stmt.where(Cargo.weight_tons <= max_weight)
    if vehicle_type and vehicle_type != "any":
        stmt = stmt.where(Cargo.vehicle_type_required == VehicleType(vehicle_type))
    stmt = stmt.order_by(Cargo.created_at.desc())
    result = await session.execute(stmt)
    cargos = []
    for cargo, user in result.all():
        cargos.append(
            {
                "id": cargo.id,
                "title": cargo.title,
                "weight_tons": cargo.weight_tons,
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


async def update_deal_price(
    session: AsyncSession, deal_id: int, new_price: float
) -> Deal | None:
    """Update agreed price for counter-offer."""
    deal = await get_deal(session, deal_id)
    if deal:
        deal.agreed_price = new_price
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


async def get_user_reviews_detailed(session: AsyncSession, user_id: int) -> list[dict]:
    """Get reviews with author name."""
    stmt = (
        select(Review, User)
        .join(User, Review.author_id == User.id)
        .where(Review.target_id == user_id)
        .order_by(Review.created_at.desc())
    )
    result = await session.execute(stmt)
    reviews = []
    for review, author in result.all():
        reviews.append({
            "rating": review.rating,
            "comment": review.comment,
            "author_name": author.full_name,
            "created_at": str(review.created_at) if review.created_at else "",
        })
    return reviews


# ── Deal queries ───────────────────────────────────────────────────────────


async def get_user_deals(session: AsyncSession, user_id: int) -> list[dict]:
    """Get all deals where user is shipper or carrier."""
    stmt = (
        select(Deal, Cargo)
        .join(Cargo, Deal.cargo_id == Cargo.id)
        .where((Deal.shipper_id == user_id) | (Deal.carrier_id == user_id))
        .order_by(Deal.created_at.desc())
    )
    result = await session.execute(stmt)
    deals = []
    for deal, cargo in result.all():
        deals.append(
            {
                "id": deal.id,
                "cargo_id": deal.cargo_id,
                "cargo_title": cargo.title,
                "origin": cargo.origin_city,
                "destination": cargo.destination_city,
                "price": deal.agreed_price,
                "currency": deal.currency,
                "status": deal.status.value,
                "shipper_id": deal.shipper_id,
                "carrier_id": deal.carrier_id,
                "created_at": str(deal.created_at),
            }
        )
    return deals


async def get_deal(session: AsyncSession, deal_id: int) -> Deal | None:
    stmt = select(Deal).where(Deal.id == deal_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def update_deal_status(
    session: AsyncSession, deal_id: int, status: DealStatus
) -> Deal | None:
    deal = await get_deal(session, deal_id)
    if deal:
        deal.status = status
        # Sync cargo status with deal status
        stmt = select(Cargo).where(Cargo.id == deal.cargo_id)
        result = await session.execute(stmt)
        cargo = result.scalar_one_or_none()
        if cargo:
            if status == DealStatus.ACCEPTED:
                cargo.status = CargoStatus.MATCHED
            elif status == DealStatus.IN_TRANSIT:
                cargo.status = CargoStatus.IN_TRANSIT
            elif status in (DealStatus.DELIVERED, DealStatus.CONFIRMED):
                cargo.status = CargoStatus.DELIVERED
            elif status == DealStatus.CANCELLED:
                cargo.status = CargoStatus.ACTIVE
        await session.commit()
        await session.refresh(deal)
    return deal


async def cancel_cargo(session: AsyncSession, cargo_id: int, owner_id: int) -> bool:
    stmt = select(Cargo).where(Cargo.id == cargo_id, Cargo.owner_id == owner_id)
    result = await session.execute(stmt)
    cargo = result.scalar_one_or_none()
    if cargo and cargo.status == CargoStatus.ACTIVE:
        cargo.status = CargoStatus.CANCELLED
        await session.commit()
        return True
    return False


async def get_user_vehicles(session: AsyncSession, owner_id: int) -> list[Vehicle]:
    stmt = select(Vehicle).where(Vehicle.owner_id == owner_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def delete_vehicle(session: AsyncSession, vehicle_id: int, owner_id: int) -> bool:
    stmt = select(Vehicle).where(Vehicle.id == vehicle_id, Vehicle.owner_id == owner_id)
    result = await session.execute(stmt)
    vehicle = result.scalar_one_or_none()
    if vehicle:
        await session.delete(vehicle)
        await session.commit()
        return True
    return False


async def get_cargo_by_id(session: AsyncSession, cargo_id: int) -> Cargo | None:
    stmt = select(Cargo).where(Cargo.id == cargo_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_vehicle_with_owner(
    session: AsyncSession, vehicle_id: int
) -> tuple[Vehicle, User] | None:
    stmt = (
        select(Vehicle, User)
        .join(User, Vehicle.owner_id == User.id)
        .where(Vehicle.id == vehicle_id)
    )
    result = await session.execute(stmt)
    row = result.first()
    return (row[0], row[1]) if row else None


async def increment_total_deals(session: AsyncSession, user_id: int) -> None:
    user = await get_user_by_id(session, user_id)
    if user:
        user.total_deals += 1
        await session.commit()


async def create_review(
    session: AsyncSession,
    author_id: int,
    target_id: int,
    deal_id: int,
    rating: int,
    comment: str | None = None,
) -> Review:
    review = Review(
        author_id=author_id,
        target_id=target_id,
        deal_id=deal_id,
        rating=rating,
        comment=comment,
    )
    session.add(review)
    # Update target's rating
    target = await get_user_by_id(session, target_id)
    if target:
        reviews = await get_user_reviews(session, target_id)
        total = sum(r["rating"] for r in reviews) + rating
        count = len(reviews) + 1
        target.rating = round(total / count, 1)
    await session.commit()
    await session.refresh(review)
    return review
