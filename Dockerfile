# Dockerfile — imagen lista para Coolify (Hetzner VPS)
FROM python:3.12-slim

# Salida sin buffer y sin .pyc para logs limpios
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Dependencias del sistema necesarias para psycopg2 / pillow
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Instalamos dependencias de Python (capa cacheable)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright + Chromium (para el scraper de Shalom). Instala el navegador y sus
# librerías del sistema. Aumenta el tamaño de la imagen ~400MB.
RUN playwright install --with-deps chromium

# Copiamos el proyecto
COPY . .

EXPOSE 8000

# Nada de collectstatic ni migrate en el build: eso se hace en runtime
# (ver entrypoint.sh) para no depender de la DB ni de los estáticos al construir.
CMD ["sh", "entrypoint.sh"]
