"""Serialize a user's chat and Mini App actions that share conversational state."""

import asyncio
from functools import wraps
from weakref import WeakValueDictionary

_locks = WeakValueDictionary()


def user_lock(user_id):
    lock = _locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _locks[user_id] = lock
    return lock


def locked_private(callback):
    @wraps(callback)
    async def wrapped(update, context):
        if update.effective_user and update.effective_chat and update.effective_chat.type == "private":
            async with user_lock(update.effective_user.id):
                return await callback(update, context)
        return await callback(update, context)
    return wrapped
