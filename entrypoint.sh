#!/usr/bin/env bash
set -e

echo "=========================================================="
echo "  VERLA SAS — Portal de Aliados Comerciales (Granian ASGI)"
echo "=========================================================="

DATA_DIR="${DATA_DIR:-/data}"
PORT="${PORT:-8080}"

# 1. Configuración de persistencia si existe volumen montado (/data)
if [ -d "$DATA_DIR" ]; then
    echo "[Storage] Volumen persistente detectado en $DATA_DIR"
    
    # Base de datos SQLite 3 (WAL mode)
    if [ ! -f "$DATA_DIR/db.sqlite3" ]; then
        if [ -f /app/db.sqlite3 ]; then
            echo "[Storage] Inicializando db.sqlite3 persistente con datos de prueba pre-cargados..."
            cp /app/db.sqlite3 "$DATA_DIR/db.sqlite3"
        fi
    else
        echo "[Storage] Base de datos persistente existente encontrada en $DATA_DIR/db.sqlite3"
    fi
    ln -sf "$DATA_DIR/db.sqlite3" /app/db.sqlite3
    export DATABASE_PATH="$DATA_DIR/db.sqlite3"

    # Archivos multimedia (imágenes de ofertas variables)
    mkdir -p "$DATA_DIR/mediafiles"
    if [ -d /app/mediafiles ] && [ ! -L /app/mediafiles ]; then
        echo "[Storage] Sincronizando recursos multimedia iniciales al volumen persistente..."
        cp -rn /app/mediafiles/* "$DATA_DIR/mediafiles"/ 2>/dev/null || true
        rm -rf /app/mediafiles
    fi
    ln -sf "$DATA_DIR/mediafiles" /app/mediafiles
    export MEDIA_ROOT="$DATA_DIR/mediafiles"
else
    echo "[Storage] Modo efímero (sin volumen externo montado)."
fi

# 2. Aplicar migraciones pendientes
echo "[Django] Ejecutando migraciones de base de datos..."
python manage.py migrate --no-input

# 3. Lanzar Granian ASGI Server en Rust con montaje nativo de estáticos y media
echo "[Granian] Iniciando servidor ASGI en 0.0.0.0:$PORT..."
exec granian \
    --interface asgi \
    --host 0.0.0.0 \
    --port "$PORT" \
    --workers 2 \
    --static-path-route /static \
    --static-path-mount /app/staticfiles \
    --static-path-route /media \
    --static-path-mount /app/mediafiles \
    aliados.asgi:application
