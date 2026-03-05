FROM python:3.11-slim

# Prevents .pyc files and enables stdout/stderr flushing
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cloud Run injects PORT; default to 8080
ENV PORT=8080

# Use gunicorn for production — 1 worker is fine since state is in-memory
# (multiple workers would have split state)
CMD exec gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 60 app:app
