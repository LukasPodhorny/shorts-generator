import asyncio
import inspect
from typing import Callable, Any


async def await_or_thread(func: Callable, *args, **kwargs) -> Any:
    if inspect.iscoroutinefunction(func):
        return await func(*args, **kwargs)
    print(f"Running {func.__name__} in thread...")
    return await asyncio.to_thread(func, *args, **kwargs)
