# -*- coding: utf-8 -*-
"""Точка входа: поднимает юзербот Константина и бота-одобрятор в одном asyncio-цикле."""

import asyncio

import approval_bot
import userbot


async def main():
    # связываем юзербот с ботом-одобрятором ДО старта опроса,
    # чтобы самое первое событие не ушло мимо в консоль
    userbot.approval_notifier = approval_bot.notify

    await userbot.start()
    await asyncio.gather(
        userbot.client.run_until_disconnected(),
        approval_bot.start_polling(),
    )


if __name__ == "__main__":
    asyncio.run(main())
