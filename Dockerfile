FROM python:3.12-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]"

# Copy app
COPY . .

EXPOSE 8000

CMD ["uvicorn", "jobos.api:app", "--host", "0.0.0.0", "--port", "8000"]
