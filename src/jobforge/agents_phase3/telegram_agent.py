"""Telegram interactive-agent contract.

Today's `jobforge.telegram.bot.TelegramBot` is a passive command dispatcher.
Phase 3 wants an outbound + action-button-driven agent: send a job → user taps
"apply" → agent enqueues the job for the application_agent. That richer
surface lives behind this ABC.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class InteractiveMessage:
    text: str
    inline_keyboard: list[list[dict[str, str]]] | None = None
    parse_mode: str = "MarkdownV2"


class TelegramAgent(ABC):
    @abstractmethod
    async def send(self, chat_id: str | int, message: InteractiveMessage) -> bool: ...

    @abstractmethod
    async def edit(
        self, chat_id: str | int, message_id: int, message: InteractiveMessage
    ) -> bool: ...

    @abstractmethod
    async def answer_callback(self, callback_id: str, text: str | None = None) -> None: ...

    @abstractmethod
    async def handle_update(self, update: dict[str, Any]) -> None: ...
