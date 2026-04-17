FROM python:3.12-slim AS backend

WORKDIR /app
ENV PYTHONPATH=/app/backend

COPY backend ./backend
COPY .env.example ./.env.example

RUN pip install --no-cache-dir fastapi uvicorn pydantic-settings websockets

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "backend"]
