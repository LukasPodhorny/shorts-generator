import pytest
import asyncio
from aishorts.utils.async_utils import await_or_thread


async def async_func(x):
    return x * 2


def sync_func(x):
    return x * 2


@pytest.mark.asyncio
async def test_await_or_thread_async():
    res = await await_or_thread(async_func, 10)
    assert res == 20


@pytest.mark.asyncio
async def test_await_or_thread_sync():
    res = await await_or_thread(sync_func, 10)
    assert res == 20
