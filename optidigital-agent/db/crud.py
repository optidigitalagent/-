from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Order, Response, Setting


async def save_order(session: AsyncSession, data: dict) -> Order | None:
    existing = await session.scalar(select(Order).where(Order.url == data["url"]))
    if existing:
        return None
    order = Order(**data)
    session.add(order)
    await session.commit()
    await session.refresh(order)
    return order


async def get_unseen_orders(session: AsyncSession) -> list[Order]:
    result = await session.scalars(select(Order).where(Order.status == "new").order_by(Order.created_at.desc()))
    return list(result.all())


async def update_order_status(session: AsyncSession, order_id: int, status: str) -> None:
    await session.execute(update(Order).where(Order.id == order_id).values(status=status))
    await session.commit()


async def save_response(session: AsyncSession, order_id: int, text: str, result: str | None = None) -> Response:
    response = Response(order_id=order_id, text=text, sent_at=datetime.utcnow(), result=result)
    session.add(response)
    await session.commit()
    await session.refresh(response)
    return response


async def get_setting(session: AsyncSession, key: str) -> str | None:
    row = await session.scalar(select(Setting).where(Setting.key == key))
    return row.value if row else None


async def set_setting(session: AsyncSession, key: str, value: str) -> None:
    row = await session.scalar(select(Setting).where(Setting.key == key))
    if row:
        row.value = value
    else:
        session.add(Setting(key=key, value=value))
    await session.commit()
