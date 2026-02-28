FROM python:3.11-slim

WORKDIR /app

COPY core/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY core/ .
COPY common /app/common

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
