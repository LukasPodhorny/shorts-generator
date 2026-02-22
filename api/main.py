import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from api.database import create_db_and_tables
from api.routers import generate, upload
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(title="PDF-TO-REEL API", lifespan=lifespan)


app.include_router(generate.router)
app.include_router(upload.router)


@app.get("/")
def root():
    return {"message": "AI Shorts API is running"}
