FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libreoffice libreoffice-l10n-zh-cn curl ca-certificates fontconfig fonts-dejavu-core fonts-noto-cjk fonts-wqy-zenhei fonts-wqy-microhei \
    && fc-cache -f -v \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY office-convert-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY office-convert-service/ .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
