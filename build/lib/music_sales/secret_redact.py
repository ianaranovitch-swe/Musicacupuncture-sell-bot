"""Маскирование секретов в логах (Stripe, webhook, токен бота)."""

from __future__ import annotations

import logging
import re

# Не выводим в лог полные ключи Stripe и signing secret.
_STRIPE_SK = re.compile(r"sk_(?:live|test)_[A-Za-z0-9]{10,}")
_WHSEC = re.compile(r"whsec_[A-Za-z0-9]{10,}")
# Грубая маска для токена Telegram: цифры:алфавитно-цифровой_хвост
_BOT_TOKEN_LIKE = re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{25,}\b")


def redact_message(text: str) -> str:
    if not isinstance(text, str):
        return text
    s = _STRIPE_SK.sub("sk_***REDACTED***", text)
    s = _WHSEC.sub("whsec_***REDACTED***", s)
    s = _BOT_TOKEN_LIKE.sub("BOT_TOKEN_REDACTED", s)
    return s


class SecretRedactFilter(logging.Filter):
    """Фильтр для root-логгера: подменяет секреты в record.msg перед записью."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_message(record.msg)
        if record.args:
            new_args = []
            for a in record.args:
                new_args.append(redact_message(a) if isinstance(a, str) else a)
            record.args = tuple(new_args)
        return True
