FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Use local lazyllm submodule and make algorithm root importable (common, etc.)
ENV PYTHONPATH=/app

# Default: run parsing (Document + server). Override CMD in compose per service.
CMD ["python", "parsing/parsing.py"]
