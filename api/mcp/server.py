"""The pdftoreel MCP server.

Curated tools over the same service functions the REST routers use, so agents
get identical auth, credit, ownership, and SSRF behavior. Mounted into the
FastAPI app at ``/mcp`` (see ``api/main.py``) over Streamable HTTP.
"""

import os

from fastmcp import FastMCP
from mcp.shared.auth import ProtectedResourceMetadata
from starlette.middleware import Middleware
from starlette.responses import JSONResponse
from starlette.routing import Route

from api.mcp.oauth_provider import PdftoreelOAuthProvider
from api.mcp.ratelimit import RateLimitMiddleware, build_store
from api.mcp.tools import account, billing, catalog, generate, series, uploads

mcp = FastMCP("pdftoreel", auth=PdftoreelOAuthProvider())

mcp.tool(catalog.list_avatars)
mcp.tool(catalog.list_video_templates)
mcp.tool(catalog.list_generation_configs)
mcp.tool(account.get_me)
mcp.tool(uploads.list_my_uploads)
mcp.tool(uploads.upload_file)
mcp.tool(uploads.delete_my_upload)
mcp.tool(generate.generate_reels)
mcp.tool(generate.plan_reels)
mcp.tool(series.get_series_status)
mcp.tool(series.list_my_series)
mcp.tool(series.delete_my_series)
mcp.tool(billing.list_subscription_plans)
mcp.tool(billing.get_subscription_checkout_url)

# ASGI app mounted at /mcp in api/main.py. path="/" because the mount point
# already provides the /mcp prefix (the default path would land at /mcp/mcp).
# stateless_http=True: required for multi-dyno Heroku (no session affinity).
# All our tools are plain request/response with no server-initiated flows,
# so nothing is lost by not keeping transport sessions.
_middleware = []
_store = build_store()
if _store is not None:
    _middleware.append(Middleware(RateLimitMiddleware, store=_store))
mcp_http_app = mcp.http_app(path="/", stateless_http=True, middleware=_middleware)


def _resource_url() -> str:
    return os.getenv("MCP_BASE_URL", "http://localhost:8000/mcp").rstrip("/")


class _MCPExactPath:
    # Serve the exact /mcp mount point without Starlette's trailing-slash
    # redirect (307), which strict MCP clients refuse to follow. Replicates
    # what Mount does (strip prefix, set root path) with remainder "/".
    # A callable instance (not a function) so Starlette invokes it with raw
    # (scope, receive, send) instead of wrapping it as f(request).
    async def __call__(self, scope, receive, send) -> None:
        await mcp_http_app(
            {
                **scope,
                "path": "/",
                "path_params": {},
                "root_path": scope.get("root_path", "") + "/mcp",
            },
            receive,
            send,
        )


async def _protected_resource_metadata(request) -> JSONResponse:
    # RFC 9728 metadata lives at the ORIGIN root
    # (/.well-known/oauth-protected-resource/mcp[/]); the mounted sub-app
    # cannot serve origin-root paths, so the parent app serves it here.
    # This origin hosts exactly one MCP server, so the bare path serves the
    # same document for clients that look there first.
    metadata = ProtectedResourceMetadata(
        resource=_resource_url(),  # type: ignore[arg-type]
        authorization_servers=[_resource_url()],  # type: ignore[list-item]
        scopes_supported=["read", "write"],
        resource_name="pdftoreel",
    )
    return JSONResponse(metadata.model_dump(mode="json", exclude_none=True))


# Registered on the parent app in api/main.py. mcp_exact_route MUST precede
# app.mount("/mcp", ...) so the exact path matches first.
mcp_exact_route = Route("/mcp", endpoint=_MCPExactPath(), methods=["GET", "POST", "DELETE"])
protected_resource_routes = [
    Route(
        "/.well-known/oauth-protected-resource",
        endpoint=_protected_resource_metadata,
        methods=["GET", "OPTIONS"],
    ),
    Route(
        "/.well-known/oauth-protected-resource/{rest:path}",
        endpoint=_protected_resource_metadata,
        methods=["GET", "OPTIONS"],
    ),
]
