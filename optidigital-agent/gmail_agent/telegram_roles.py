"""Fail-closed Telegram actor resolution for Release 5A state writes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Iterable


class TelegramRole(StrEnum):
    ADULT_OWNER = "ADULT_OWNER"
    ARTEM = "ARTEM"
    VADIM = "VADIM"
    READ_ONLY_MEMBER = "READ_ONLY_MEMBER"


ROLE_SETTING = {
    TelegramRole.ADULT_OWNER: "TELEGRAM_ADULT_OWNER_USER_ID",
    TelegramRole.ARTEM: "TELEGRAM_ARTEM_USER_ID",
    TelegramRole.VADIM: "TELEGRAM_VADIM_USER_ID",
}


class TelegramAuthorizationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class TelegramActor:
    role: TelegramRole
    user_id: int
    username: str = ""

    @property
    def transition_actor(self) -> str:
        return {
            TelegramRole.ADULT_OWNER: "adult_owner",
            TelegramRole.ARTEM: "Artem",
            TelegramRole.VADIM: "Vadim",
            TelegramRole.READ_ONLY_MEMBER: "read_only_member",
        }[self.role]


def configured_role_ids(settings: Any) -> dict[TelegramRole, int]:
    result: dict[TelegramRole, int] = {}
    for role, setting_name in ROLE_SETTING.items():
        value = getattr(settings, setting_name, None)
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            result[role] = value
    return result


def resolve_telegram_actor(
    user_id: int,
    username: str,
    settings: Any,
) -> TelegramActor:
    for role, configured_id in configured_role_ids(settings).items():
        if configured_id == user_id:
            return TelegramActor(role, user_id, username or "")
    return TelegramActor(TelegramRole.READ_ONLY_MEMBER, user_id, username or "")


def authorize_telegram_actor(
    user_id: int,
    username: str,
    settings: Any,
    *,
    allowed_roles: Iterable[TelegramRole],
    required_settings: Iterable[str],
) -> TelegramActor:
    missing = [
        name
        for name in required_settings
        if not isinstance(getattr(settings, name, None), int)
        or isinstance(getattr(settings, name, None), bool)
        or getattr(settings, name, 0) <= 0
    ]
    if missing:
        raise TelegramAuthorizationError(
            "Missing required setting: " + ", ".join(missing)
        )
    configured = configured_role_ids(settings)
    matching_roles = [
        role for role, configured_id in configured.items() if configured_id == user_id
    ]
    if len(matching_roles) > 1:
        conflicting = ", ".join(ROLE_SETTING[role] for role in matching_roles)
        raise TelegramAuthorizationError(
            "Conflicting Telegram role settings: " + conflicting
        )
    actor = resolve_telegram_actor(user_id, username, settings)
    if actor.role not in set(allowed_roles):
        raise TelegramAuthorizationError(
            f"Telegram role {actor.role.value} is not allowed for this command"
        )
    return actor


def masked_user_id(user_id: int | None) -> str:
    value = str(user_id or "")
    if len(value) <= 4:
        return "****"
    return value[:2] + "*" * (len(value) - 4) + value[-2:]
