# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY app /app/app
COPY data /app/data

EXPOSE 8000

# Use PORT environment variable if set, otherwise default to 8000
ENV PORT=8000
CMD uvicorn app.main:app --host 0.0.0.0 --port $PORT

