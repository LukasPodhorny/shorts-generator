"""The pdftoreel MCP server.

Curated tools over the same service functions the REST routers use, so agents
get identical auth, credit, ownership, and SSRF behavior. Mounted into the
FastAPI app at ``/mcp`` (see ``api/main.py``) over Streamable HTTP.
"""

import os
from pathlib import Path

from fastmcp import FastMCP
from mcp.server.auth.json_response import PydanticJSONResponse
from mcp.server.auth.routes import build_metadata
from mcp.shared.auth import ProtectedResourceMetadata
from mcp.types import Icon
from starlette.middleware import Middleware
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Route

from api.mcp.oauth_provider import PdftoreelOAuthProvider
from api.mcp.ratelimit import RateLimitMiddleware, build_store
from api.mcp.tools import account, billing, catalog, generate, series, uploads


def _resource_url() -> str:
    return os.getenv("MCP_BASE_URL", "http://localhost:8000/mcp").rstrip("/")


_ICON_PATH = Path(__file__).resolve().parent / "icons" / "logo-v2.png"

oauth_provider = PdftoreelOAuthProvider()
mcp = FastMCP(
    "pdftoreel",
    auth=oauth_provider,
    # Brand logo so clients (Claude) render our icon instead of a default
    # tile. The dark background is baked in because Claude composites
    # icons onto its own white tile. Baked at import; MCP_BASE_URL is set
    # before boot in every deployed environment.
    icons=[
        Icon(
            src=f"{_resource_url()}/icons/logo-v2.png",
            mimeType="image/png",
            sizes=["192x192"],
        )
    ],
)

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


async def _authorization_server_metadata(request) -> Response:
    # RFC 8414 metadata lives at the ORIGIN root
    # (/.well-known/oauth-authorization-server[/mcp]); Claude probes these
    # origin variants only, so the parent app serves the exact document the
    # mounted sub-app serves: same SDK builder, same live provider options.
    metadata = build_metadata(
        _resource_url(),  # type: ignore[arg-type]
        oauth_provider.service_documentation_url,
        oauth_provider.client_registration_options,
        oauth_provider.revocation_options,
    )
    return PydanticJSONResponse(
        content=metadata, headers={"Cache-Control": "public, max-age=3600"}
    )


# Registered on the parent app in api/main.py. mcp_exact_route and
# mcp_icon_route MUST precede app.mount("/mcp", ...) so they match first.
mcp_exact_route = Route("/mcp", endpoint=_MCPExactPath(), methods=["GET", "POST", "DELETE"])


async def _mcp_icon(request) -> Response:
    return FileResponse(
        _ICON_PATH,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


mcp_icon_route = Route("/mcp/icons/logo-v2.png", endpoint=_mcp_icon, methods=["GET"])
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
authorization_server_routes = [
    Route(
        "/.well-known/oauth-authorization-server",
        endpoint=_authorization_server_metadata,
        methods=["GET", "OPTIONS"],
    ),
    Route(
        "/.well-known/oauth-authorization-server/{rest:path}",
        endpoint=_authorization_server_metadata,
        methods=["GET", "OPTIONS"],
    ),
]
