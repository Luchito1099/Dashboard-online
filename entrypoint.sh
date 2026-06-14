#!/bin/sh
# entrypoint.sh — se ejecuta al arrancar el contenedor en Coolify.
# Aplica migraciones automáticamente y luego levanta Gunicorn.
set -e

echo "Aplicando migraciones..."
python manage.py migrate --noinput

echo "Iniciando Gunicorn..."
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3
