from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


class OrderCb(CallbackData, prefix="ord"):
    action: str
    order_id: int


class ResponseCb(CallbackData, prefix="rsp"):
    action: str
    order_id: int
    response_id: int


def order_card_keyboard(order_id: int, url: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="👁 Переглянути відгук",
            callback_data=OrderCb(action="view", order_id=order_id).pack(),
        ),
        InlineKeyboardButton(
            text="❌ Пропустити",
            callback_data=OrderCb(action="skip", order_id=order_id).pack(),
        ),
    )
    builder.row(InlineKeyboardButton(text="🔗 Відкрити", url=url))
    return builder.as_markup()


def response_keyboard(order_id: int, response_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Відправити вручну",
            callback_data=ResponseCb(action="send", order_id=order_id, response_id=response_id).pack(),
        ),
        InlineKeyboardButton(
            text="✏️ Переписати",
            callback_data=ResponseCb(action="rewrite", order_id=order_id, response_id=response_id).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="❌ Скасувати",
            callback_data=ResponseCb(action="cancel", order_id=order_id, response_id=response_id).pack(),
        )
    )
    return builder.as_markup()


def score_picker_keyboard(current: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for s in range(4, 10):
        mark = "✅ " if s == current else ""
        builder.button(text=f"{mark}{s}", callback_data=f"score:{s}")
    builder.adjust(3)
    return builder.as_markup()
