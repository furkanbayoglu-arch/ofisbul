from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Office(Base):
    __tablename__ = "offices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    ownership: Mapped[str | None] = mapped_column(Text)
    year_built: Mapped[str | None] = mapped_column(Text)
    certificate: Mapped[str | None] = mapped_column(Text)
    gross_leasable_area: Mapped[str | None] = mapped_column(Text)
    floor_size: Mapped[str | None] = mapped_column(Text)
    efficiency: Mapped[str | None] = mapped_column(Text)
    delivery_type: Mapped[str | None] = mapped_column(Text)
    asking_rent: Mapped[str | None] = mapped_column(Text)
    service_charge: Mapped[str | None] = mapped_column(Text)
    car_park_ratio: Mapped[str | None] = mapped_column(Text)
    tenants: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    picture1_url: Mapped[str | None] = mapped_column(Text)
    picture2_url: Mapped[str | None] = mapped_column(Text)
    alias_names: Mapped[str | None] = mapped_column(Text)
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    extra_values: Mapped[list["OfficeExtraValue"]] = relationship(
        back_populates="office", cascade="all, delete-orphan"
    )


class ExtraField(Base):
    __tablename__ = "extra_fields"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    section: Mapped[str] = mapped_column(String(255), nullable=False, default="Custom")
    field_type: Mapped[str] = mapped_column(String(64), nullable=False, default="text")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    office_values: Mapped[list["OfficeExtraValue"]] = relationship(
        back_populates="field", cascade="all, delete-orphan"
    )


class OfficeExtraValue(Base):
    __tablename__ = "office_extra_values"

    office_id: Mapped[int] = mapped_column(
        ForeignKey("offices.id", ondelete="CASCADE"), primary_key=True
    )
    field_id: Mapped[int] = mapped_column(
        ForeignKey("extra_fields.id", ondelete="CASCADE"), primary_key=True
    )
    value: Mapped[str | None] = mapped_column(Text)

    office: Mapped["Office"] = relationship(back_populates="extra_values")
    field: Mapped["ExtraField"] = relationship(back_populates="office_values")
