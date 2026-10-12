"""Background dispatch for MCP-triggered generations.

HTTP routes dispatch ``process_reel_task`` through request-scoped
``BackgroundTasks``; MCP tools have no request scope, so they schedule the
same coroutine as an ``asyncio`` task instead. The coroutine handles its own
errors (marks the series failed, refunds credits), and the module-level set
keeps task references alive until completion.
"""

import asyncio

from api.tasks import process_reel_task

_running_tasks: set[asyncio.Task] = set()


def dispatch_task(series_id: int, request_data: dict, total_cost: int) -> None:
    """Schedule ``process_reel_task``; matches the ``create_generation`` hook."""
    task = asyncio.get_running_loop().create_task(
        process_reel_task(series_id, request_data, total_cost)
    )
    _running_tasks.add(task)
    task.add_done_callback(_running_tasks.discard)
