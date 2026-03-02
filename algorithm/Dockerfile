FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default: run parsing (Document + server). Override CMD in compose per service.
CMD ["python", "parsing/parsing.py"]
