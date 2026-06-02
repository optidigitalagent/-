from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    budget: Mapped[float | None] = mapped_column(Float, nullable=True)
    url: Mapped[str] = mapped_column(String(1000), unique=True, nullable=False)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="new")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    employer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    employer_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    category: Mapped[str | None] = mapped_column(String(300), nullable=True)
    deadline: Mapped[str | None] = mapped_column(String(200), nullable=True)
    bid_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    employer_phone: Mapped[str | None] = mapped_column(String(100), nullable=True)
    employer_telegram: Mapped[str | None] = mapped_column(String(200), nullable=True)
    employer_email: Mapped[str | None] = mapped_column(String(200), nullable=True)

    responses: Mapped[list["Response"]] = relationship("Response", back_populates="order")


class Response(Base):
    __tablename__ = "responses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(Integer, ForeignKey("orders.id"), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    result: Mapped[str | None] = mapped_column(String(100), nullable=True)

    order: Mapped["Order"] = relationship("Order", back_populates="responses")


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=True)


_MIGRATIONS = [
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS employer_name TEXT",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS employer_url TEXT",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS category TEXT",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS deadline TEXT",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS bid_count INTEGER",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS employer_phone TEXT",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS employer_telegram TEXT",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS employer_email TEXT",
]


async def init_db() -> None:
    from db import engine  # local import avoids circular reference at module level
    from sqlalchemy import text

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for stmt in _MIGRATIONS:
            await conn.execute(text(stmt))
