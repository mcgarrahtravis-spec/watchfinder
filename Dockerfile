FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8000

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ship with demo lots so first paint has opportunities.
ENV WATCHFINDER_CONFIG=/app/config.demo.yaml

EXPOSE 8000

CMD ["sh", "-c", "uvicorn watchfinder.web.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
