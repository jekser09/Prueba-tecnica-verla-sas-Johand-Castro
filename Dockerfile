# Multi-stage Dockerfile para el Portal de Aliados Comerciales — VERLA SAS
# Optimizado con Astral uv y Python 3.14 slim para despliegues ligeros y reproducibles
FROM ghcr.io/astral-sh/uv:latest AS uv

FROM python:3.14-slim AS runtime

# Dependencias mínimas del sistema operativo
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copiar binarios oficiales de uv
COPY --from=uv /uv /uvx /bin/

# Configuración de variables de entorno de Python y servidor
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    PORT=8080

WORKDIR /app

# Copiar manifiestos de dependencias para aprovechar la caché de capas de Docker
COPY pyproject.toml uv.lock ./

# Instalar dependencias del proyecto sin entorno virtual (en el sistema del contenedor)
RUN uv sync --frozen --no-dev --no-install-project

# Copiar el código fuente completo del proyecto (incluye fixtures iniciales y db.sqlite3)
COPY . .

# Crear directorios para estáticos, multimedia y volumen
RUN mkdir -p /data/mediafiles /app/staticfiles /app/mediafiles

# Compilar y minificar archivos estáticos con hash MD5 durante la fase de construcción
RUN SECRET_KEY="build-time-secret-key-for-collectstatic" \
    DEPLOY="DEV" \
    python manage.py collectstatic --no-input

# Permisos de ejecución para el script de entrada
RUN chmod +x /app/entrypoint.sh

# Puerto HTTP estándar para la aplicación
EXPOSE 8080

# Punto de entrada para inicialización de almacenamiento y arranque de Granian ASGI
ENTRYPOINT ["/app/entrypoint.sh"]
