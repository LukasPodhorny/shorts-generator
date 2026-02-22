# AI Shorts Headless API Documentation

This directory contains the FastAPI backend for the `aishorts` library. It serves as a headless interface to manage users, credits, file uploads, and video generation jobs.

## 1. Architecture Overview

The backend is built using **FastAPI** and follows a modular architecture:

*   **`main.py`**: The entry point. It initializes the app, database, and routers.
*   **`auth.py`**: Handles Firebase Authentication.
*   **`database.py`**: Manages the SQLModel database connection (SQLite/PostgreSQL).
*   **`models.py`**: Defines the database schema.
*   **`tasks.py`**: Contains background workers for long-running video generation tasks.
*   **`routers/`**: Separate modules for API endpoints (`generate`, `upload`).

---

## 2. Authentication

Authentication is handled via **Firebase Admin SDK**.

*   **Mechanism**: Bearer Token (JWT).
*   **Dependency**: `get_current_user` in `api/auth.py`.
*   **Flow**:
    1.  Frontend sends `Authorization: Bearer <firebase_id_token>`.
    2.  Backend verifies the token using Firebase Admin.
    3.  If valid, the user's Firebase UID and email are extracted.
    4.  If the user does not exist in the local SQL database, they are **Just-In-Time (JIT) provisioned** with default credits.

---

## 3. Database Schema (`api/models.py`)

We use **SQLModel** (a wrapper around SQLAlchemy + Pydantic).

### Tables
1.  **`User`**
    *   `id`: String (Firebase UID).
    *   `credits`: Integer (Balance for generating videos).
    *   `email`: String.

2.  **`Avatar`** & **`VideoTemplate`**
    *   Stores configuration for avatars (voice, face) and video templates (fonts, backgrounds).
    *   **Note**: These store complex Pydantic configurations as a JSON column (`data`).

3.  **`ReelSeries`**
    *   Represents a single "Job" or request from the user.
    *   `status`: `Queued`, `Processing`, `Done`, `Failed`.

4.  **`Reel`**
    *   Represents the actual video files generated within a series.
    *   `cloudflare_r2_url`: The public URL of the final video.
    *   `local_path`: Path on the server disk.

---

## 4. API Endpoints

### 📂 Uploads (`api/routers/upload.py`)

*   **`POST /api/upload`**
    *   **Auth**: Required.
    *   **Body**: `multipart/form-data` (File).
    *   **Action**: Saves the file to a local `uploads/` directory.
    *   **Returns**: Local file path (to be passed to the generate endpoint).

### 🎬 Generation (`api/routers/generate.py`)

*   **`POST /api/generate`**
    *   **Auth**: Required.
    *   **Body**: `GenerateRequest` (template name, avatar names, input text, file paths).
    *   **Logic**:
        1.  Checks if user has enough credits.
        2.  Deducts credits.
        3.  Creates `ReelSeries` and `Reel` records in DB with status `Queued`.
        4.  Dispatches `process_reel_task` to **BackgroundTasks**.
    *   **Returns**: `series_id` immediately (non-blocking).

*   **`GET /api/status/{series_id}`**
    *   **Action**: Poll this endpoint to check if the video is `Done`.
    *   **Returns**: The series object, including the list of Reels and their URLs.

*   **`POST /api/add-credits`**
    *   **Action**: Adds mock credits to a user (Dev/Testing only).

---

## 5. Background Processing (`api/tasks.py`)

Video generation is heavy and cannot run in the main request loop. It runs in a background task:

1.  **Initialization**:
    *   Fetches the full `Avatar` and `VideoTemplate` configurations from the DB based on the names provided in the request.
    *   Initializes the `ShortsGenerator` from the core library.

2.  **Generation**:
    *   Calls `shorts_generator.generate_shorts_async()`.
    *   This runs the LLM script generation, TTS, Image generation, and FFmpeg editing.

3.  **Storage**:
    *   The final `.mp4` is uploaded to **Cloudflare R2** using `boto3`.
    *   The public URL is saved to the `Reel` record.

4.  **Completion**:
    *   Updates `ReelSeries` status to `Done`.
    *   If an error occurs, the transaction is rolled back, and status is set to `Failed`.

---

## 6. Setup & Configuration

### Environment Variables
Ensure these are set in your `.env` file:

```bash
DATABASE_URL=sqlite:///database.db
FIREBASE_CREDENTIALS_PATH=firebase_credentials.json

# Cloudflare R2 (S3 Compatible)
R2_ENDPOINT_URL=...
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_BUCKET_NAME=...
R2_PUBLIC_URL=...

# AI Services
GEMINI_API_KEY=...
OPENAI_API_KEY=...
TTS_API_KEY=...
```

### Database Population
Before running the API, you must sync your JSON config files to the database:

```bash
python scripts/populate_db.py
```
