FROM python:3.11-slim

# Install system dependencies (FFmpeg, LaTeX)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    texlive-latex-base \
    texlive-fonts-recommended \
    texlive-latex-extra \
    imagemagick \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Install the aishorts package from the local src/ directory
RUN pip install .

# Expose port (Railway dynamically injects $PORT, but 8000 is our default)
EXPOSE 8000

# Start Uvicorn
CMD alembic upgrade head && uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}


