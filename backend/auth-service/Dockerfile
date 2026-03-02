FROM python:3.11-slim

WORKDIR /app

COPY auth-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY auth-service/ .
COPY scripts /app/scripts
COPY core /app/core
RUN python3 /app/scripts/extract_api_permissions.py --output /app/api_permissions.json --exclude scripts,core,vendor /app/core /app

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
