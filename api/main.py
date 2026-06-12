import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routers import generate, upload, users, admin, public
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)


app = FastAPI(title="PDF-TO-REEL API")

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


@app.get("/")
def root():
    return {"message": "AI Shorts API is running"}
