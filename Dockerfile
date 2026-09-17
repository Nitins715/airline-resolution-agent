FROM python:3.13-slim

WORKDIR /app

# Install system dependencies for psycopg2 and pgvector
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Collect static files
RUN python manage.py collectstatic --noinput

# Run gunicorn on port 8000 (or PORT from env)
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-8000} airline_core.wsgi:application"]
