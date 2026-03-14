FROM python:3.12-slim

WORKDIR /app

# System dependencies (tesseract for OCR)
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-spa \
    libpq-dev \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency manifest and install (without dev deps)
COPY pyproject.toml .
RUN uv sync --no-dev --no-install-project

COPY . .

RUN mkdir -p storage/docs/cantabria storage/docs/asturias

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
