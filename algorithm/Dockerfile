FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    ca-certificates \
    curl \
    build-essential \
    gcc \
    python3-dev \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Use local lazyllm submodule and make algorithm root importable (common, etc.)
ENV PYTHONPATH=/app

# Default: run parsing (Document + server). Override CMD in compose per service.
CMD ["python", "parsing/parsing.py"]
