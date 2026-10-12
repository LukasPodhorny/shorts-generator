"""The pdftoreel MCP server.

Curated tools over the same service functions the REST routers use, so agents
get identical auth, credit, ownership, and SSRF behavior. Mounted into the
FastAPI app at ``/mcp`` (see ``api/main.py``) over Streamable HTTP.
"""

from fastmcp import FastMCP
from starlette.middleware import Middleware

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
