"""Convert service-layer exceptions into MCP tool errors, with call logging."""

import logging
import time
from contextlib import contextmanager
from typing import Iterator

from fastapi import HTTPException
from fastmcp.exceptions import ToolError
from pydantic import ValidationError

logger = logging.getLogger("pdftoreel.mcp")


@contextmanager
def mcp_errors(tool_name: str) -> Iterator[None]:
    """Map HTTPException/ValidationError to ToolError so agents get clean errors.

    Also logs one line per call (tool, duration, outcome) for production
    observability. User identity is never logged here; the caller uid stays
    in the request context only.
    """
    start = time.monotonic()
    try:
        yield
    except ToolError:
        logger.info(
            "mcp tool=%s outcome=error duration_ms=%d",
            tool_name,
            _elapsed_ms(start),
        )
        raise
    except HTTPException as e:
        logger.info(
            "mcp tool=%s outcome=http_%s duration_ms=%d",
            tool_name,
            e.status_code,
            _elapsed_ms(start),
        )
        raise ToolError(f"{e.status_code}: {e.detail}") from e
    except ValidationError as e:
        details = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}"
            for err in e.errors()
        )
        logger.info(
            "mcp tool=%s outcome=invalid_input duration_ms=%d",
            tool_name,
            _elapsed_ms(start),
        )
        raise ToolError(f"Invalid input: {details}") from e
    else:
        logger.info(
            "mcp tool=%s outcome=ok duration_ms=%d",
            tool_name,
            _elapsed_ms(start),
        )


def _elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)
