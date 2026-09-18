#!/usr/bin/env bash
set -o errexit

echo "Applying database migrations..."
python manage.py migrate --no-input

echo "Seeding assignment data..."
python manage.py seed_assignment_data

echo "Starting Gunicorn server..."
exec gunicorn airline_core.wsgi:application --log-file -
