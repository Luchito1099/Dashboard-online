#!/bin/sh
# entrypoint.sh — se ejecuta al arrancar el contenedor en Coolify.
# 1) Aplica migraciones. 2) Crea/asegura el superusuario. 3) Levanta Gunicorn.
set -e

echo "Aplicando migraciones..."
python manage.py migrate --noinput

# Crea (o actualiza la contraseña de) el superusuario desde las variables
# DJANGO_SUPERUSER_USERNAME / DJANGO_SUPERUSER_PASSWORD / DJANGO_SUPERUSER_EMAIL.
# Es idempotente: si ya existe, solo le re-asegura la contraseña y los permisos.
if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
  echo "Asegurando superusuario $DJANGO_SUPERUSER_USERNAME..."
  python manage.py shell -c "
import os
from django.contrib.auth import get_user_model
U = get_user_model()
nombre = os.environ['DJANGO_SUPERUSER_USERNAME']
clave = os.environ['DJANGO_SUPERUSER_PASSWORD']
correo = os.environ.get('DJANGO_SUPERUSER_EMAIL', '')
usuario, creado = U.objects.get_or_create(username=nombre, defaults={'email': correo})
usuario.is_staff = True
usuario.is_superuser = True
usuario.is_active = True
usuario.set_password(clave)
usuario.save()
from core.models import Perfil
perfil, _ = Perfil.objects.get_or_create(usuario=usuario)
perfil.rol = 'admin'
perfil.activo = True
perfil.save()
print('Superusuario creado.' if creado else 'Superusuario actualizado.')
" || echo "Aviso: no se pudo asegurar el superusuario (continuo igual)."
fi

echo "Iniciando Gunicorn..."
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3
