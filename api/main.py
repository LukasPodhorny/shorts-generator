import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routers import generate, upload, users, admin, public, plan, oauth
from api.mcp.server import (
    mcp_exact_route,
    mcp_http_app,
    protected_resource_routes,
)
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)


app = FastAPI(title="PDF-TO-REEL API", lifespan=mcp_http_app.lifespan)

# Allowed browser origins. Set CORS_ORIGINS as a comma-separated list in
# production; falls back to FRONTEND_URL, then localhost for development.
_cors_origins_env = os.getenv("CORS_ORIGINS")
if _cors_origins_env:
    allowed_origins = [o.strip() for o in _cors_origins_env.split(",") if o.strip()]
else:
    allowed_origins = [os.getenv("FRONTEND_URL", "http://localhost:3000")]

# Add CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(generate.router)
app.include_router(upload.router)
app.include_router(users.router)
app.include_router(admin.router)
app.include_router(public.router)
app.include_router(plan.router)
app.include_router(oauth.router)

# MCP server for agents (Streamable HTTP, same Firebase auth as REST).
# The parent app runs the MCP app's lifespan: without it the streamable-HTTP
# session manager is never initialized and every /mcp request fails.
# If this app ever needs its own lifespan tasks, combine both context
# managers into one @asynccontextmanager instead of replacing this.
#
# The exact /mcp route is registered before the mount so strict MCP clients
# get a direct answer instead of a 307 they refuse to follow. The origin-root
# OAuth metadata routes come from RFC 9728: the 401 advertises them at the
# origin root, which the mounted sub-app cannot serve by itself.
app.routes.append(mcp_exact_route)
app.mount("/mcp", mcp_http_app)
for _route in protected_resource_routes:
    app.routes.append(_route)


@app.get("/")
def root():
    return {"message": "AI Shorts API is running"}
