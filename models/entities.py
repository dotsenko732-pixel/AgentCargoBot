"""Core database entities for AgentCargoBot."""

import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.database import Base


# ── Enums ──────────────────────────────────────────────────────────────────


class UserRole(str, enum.Enum):
    SHIPPER = "shipper"  # грузовладелец
    CARRIER = "carrier"  # перевозчик
    BOTH = "both"


class CargoStatus(str, enum.Enum):
    ACTIVE = "active"
    MATCHED = "matched"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class VehicleType(str, enum.Enum):
    TENT = "tent"  # тент
    REF = "ref"  # рефрижератор
    BOARD = "board"  # бортовой
    CONTAINER = "container"
    FLATBED = "flatbed"  # площадка
    ISOTERM = "isoterm"
    TANKER = "tanker"  # цистерна
    OTHER = "other"


class DealStatus(str, enum.Enum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    CONFIRMED = "confirmed"
    DISPUTED = "disputed"
    CANCELLED = "cancelled"


class SubscriptionPlan(str, enum.Enum):
    FREE = "free"
    STANDARD = "standard"  # 990 сом/мес
    BUSINESS = "business"  # 2990 сом/мес


class PaymentType(str, enum.Enum):
    SUBSCRIPTION = "subscription"
    PROMO_BOOST = "promo_boost"
    VERIFICATION = "verification"
    COMMISSION = "commission"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    REFUNDED = "refunded"
    FAILED = "failed"


# ── Models ─────────────────────────────────────────────────────────────────


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.SHIPPER)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rating: Mapped[float] = mapped_column(Float, default=0.0)
    total_deals: Mapped[int] = mapped_column(Integer, default=0)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    subscription_plan: Mapped[SubscriptionPlan] = mapped_column(
        Enum(SubscriptionPlan), default=SubscriptionPlan.FREE
    )
    subscription_until: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    cargos_this_month: Mapped[int] = mapped_column(Integer, default=0)
    month_reset: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    # Relationships
    cargos: Mapped[list["Cargo"]] = relationship(back_populates="owner")
    vehicles: Mapped[list["Vehicle"]] = relationship(back_populates="owner")
    reviews_received: Mapped[list["Review"]] = relationship(
        back_populates="target", foreign_keys="Review.target_id"
    )


class Vehicle(Base):
    __tablename__ = "vehicles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    vehicle_type: Mapped[VehicleType] = mapped_column(Enum(VehicleType))
    max_weight_tons: Mapped[float] = mapped_column(Float)
    max_volume_m3: Mapped[float | None] = mapped_column(Float, nullable=True)
    plate_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)

    # Current location for proactive matching
    current_city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    destination_city: Mapped[str | None] = mapped_column(String(255), nullable=True)

    owner: Mapped["User"] = relationship(back_populates="vehicles")


class Cargo(Base):
    __tablename__ = "cargos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    weight_tons: Mapped[float] = mapped_column(Float)
    volume_m3: Mapped[float | None] = mapped_column(Float, nullable=True)
    vehicle_type_required: Mapped[VehicleType | None] = mapped_column(
        Enum(VehicleType), nullable=True
    )

    # Route
    origin_city: Mapped[str] = mapped_column(String(255), index=True)
    destination_city: Mapped[str] = mapped_column(String(255), index=True)

    # Pricing
    budget_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    budget_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="KGS")

    # Dates
    pickup_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delivery_deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    status: Mapped[CargoStatus] = mapped_column(
        Enum(CargoStatus), default=CargoStatus.ACTIVE
    )
    is_promoted: Mapped[bool] = mapped_column(Boolean, default=False)
    promoted_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    owner: Mapped["User"] = relationship(back_populates="cargos")
    deals: Mapped[list["Deal"]] = relationship(back_populates="cargo")


class Deal(Base):
    __tablename__ = "deals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cargo_id: Mapped[int] = mapped_column(ForeignKey("cargos.id"))
    shipper_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    carrier_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    agreed_price: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(10), default="KGS")
    status: Mapped[DealStatus] = mapped_column(
        Enum(DealStatus), default=DealStatus.PROPOSED
    )
    commission_amount: Mapped[float] = mapped_column(Float, default=0.0)
    commission_paid: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    cargo: Mapped["Cargo"] = relationship(back_populates="deals")
    shipper: Mapped["User"] = relationship(foreign_keys=[shipper_id])
    carrier: Mapped["User"] = relationship(foreign_keys=[carrier_id])


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    target_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    deal_id: Mapped[int] = mapped_column(ForeignKey("deals.id"))
    rating: Mapped[int] = mapped_column(Integer)  # 1-5
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    target: Mapped["User"] = relationship(
        back_populates="reviews_received", foreign_keys=[target_id]
    )


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    payment_type: Mapped[PaymentType] = mapped_column(Enum(PaymentType))
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(10), default="KGS")
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus), default=PaymentStatus.PENDING
    )
    telegram_payment_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Reference to related entity (deal_id, cargo_id, etc.)
    reference_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    user: Mapped["User"] = relationship(foreign_keys=[user_id])
