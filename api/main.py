import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routers import generate, upload, users, admin, public
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)


app = FastAPI(title="PDF-TO-REEL API")

# Add CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update this with specific domains in production
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
