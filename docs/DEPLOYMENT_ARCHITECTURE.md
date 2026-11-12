# Arquitectura de Despliegue en la Nube — VERLA SAS (Portal de Aliados Comerciales)

Este documento presenta la evaluación arquitectónica de plataformas de alojamiento en la nube (PaaS / CaaS) para el despliegue en producción del MVP del **Portal de Aliados Comerciales — VERLA SAS**, garantizando una URL pública con HTTPS/SSL automatizado, persistencia transaccional de SQLite 3 en modo WAL, persistencia de archivos multimedia (`mediafiles/`) y ejecución de alto desempeño mediante el servidor ASGI en Rust (**Granian**).

---

## 1. Matriz Comparativa de Plataformas Evaluadas (2026)

| Criterio | **Fly.io** *(Recomendado)* | **Railway** *(Alternativa GUI)* | **Render** *(Condicional)* | **Koyeb** | **Zeabur** |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Soporte de Volúmenes Persistentes (SQLite WAL)** | **Excelente**: Volúmenes NVMe en bloque ext4 dedicados (`[mounts]`), soporte nativo de locks POSIX sin red. | **Excelente**: Soporta *Railway Volumes* vinculados al servicio montados en `/data`. | **Restringido**: El Tier Gratuito es **100% efímero**. Requiere plan *Starter* ($7/mes) + disco ($0.25/GB). | **No en Free**: Almacenamiento estrictamente efímero en instancias gratuitas *Eco*. | **Bueno**: Soporta volúmenes persistentes en contenedor. |
| **Certificado SSL / HTTPS Automatizado** | **Instantáneo**: Wildcard Let's Encrypt administrado en `<app>.fly.dev` con renovación automática. | **Instantáneo**: Certificado TLS automático en `<app>.up.railway.app`. | **Instantáneo**: Certificado TLS en `<app>.onrender.com`. | **Instantáneo**: Certificado TLS en `<app>.koyeb.app`. | **Instantáneo**: Certificado TLS en `<app>.zeabur.app`. |
| **Tiempo de Arranque / Latencia en Frío** | **Sub-segundo** (Firecracker microVM). No sufre bloqueos de 50s en la sustentación. | **Inmediato**: Servicio activo continuo durante el período de prueba. | **Lento (50-70s)** en Free Tier por suspensión automática tras 15 min de inactividad. | **Rápido**: Micro instancias serverless. | **Rápido**: Contenedor activo. |
| **Compatibilidad con Granian ASGI (Rust)** | **Nativa 100%**: Ejecución directa en microVM Linux x86_64 sin proxies intermediarios invasivos. | **Nativa 100%**: Docker engine estándar. | **Nativa 100%**: Docker runtime. | **Nativa 100%**: Contenedor OCI. | **Nativa 100%**: Contenedor OCI. |
| **Modelo Gratuito / Crédito Inicial** | Nivel gratuito generoso / micro-facturación (< $0.05 por horas de prueba). | $5 USD de crédito inicial de prueba (requiere cuenta verificada). | Tier gratuito perpetuo para computo, pero **sin almacenamiento persistente**. | 1 micro-servicio Eco gratuito (efímero). | $5 USD de prueba gratuita. |
| **Fricción de Despliegue** | **Mínima**: CLI (`fly launch` / `fly deploy`) o GitHub Actions en 3 minutos. | **Mínima**: Conexión con repositorio de GitHub y clic en UI. | **Baja**: Conexión a GitHub con `render.yaml`. | **Baja**: Conexión a GitHub con `Dockerfile`. | **Baja**: Importación de repositorio Git. |
| **Veredicto Arquitectónico** | 🏆 **GANADOR ABSOLUTO**: La mejor plataforma para SQLite WAL + Granian ASGI. | 🥈 **SEGUNDO LUGAR**: Excelente para quien prefiera interfaz gráfica sin tocar CLI. | ⚠️ **NO APTO EN FREE TIER**: Cada reinicio borra la base de datos SQLite y las imágenes subidas. | ❌ **DESCARTADO**: Pérdida de estado en SQLite al reiniciar. | 🥉 **TERCERO**: Alternativa viable pero con menor ecosistema. |

---

## 2. Análisis Crítico de Restricciones Técnicas del Stack

### 2.1. Persistencia de SQLite 3 en Modo WAL (`PRAGMA journal_mode=WAL`)
- **El desafío de red vs. bloque**: SQLite en modo WAL utiliza archivos de memoria compartida (`.sqlite3-shm`) y bitácora de escritura adelantada (`.sqlite3-wal`). Requiere soporte estricto de bloqueos de archivos POSIX (`flock` / `fcntl`).
- **Por qué fallan los discos compartidos de red (NFS/EFS/SMB)**: Los sistemas de archivos distribuidos presentan latencias en locks que provocan errores fatales `database is locked (5)` o corrupción de punteros.
- **La solución de Fly.io y Railway**: Ambas plataformas proporcionan **volúmenes de bloques locales montados directamente en el kernel Linux** (formato ext4). SQLite WAL opera a velocidad de bus NVMe con cero riesgo de inconsistencia.

### 2.2. Persistencia de Archivos Multimedia (`mediafiles/`)
- Las imágenes promocionales de las ofertas comerciales (`OfertaPeriodo.imagen_promocional`) se almacenan en disco físico particionadas por fecha (`mediafiles/ofertas/%Y/%m/`).
- Al desplegar en contenedores sin volumen, cualquier reinicio o re-despliegue elimina las imágenes cargadas por los usuarios.
- **Estrategia implementada en `entrypoint.sh`**:
  Tanto `db.sqlite3` como `mediafiles/` se enlazan simbólicamente o se direccionan a la ruta persistente `/data/`. Si el volumen se inicia por primera vez vacío, el script inicializa automáticamente los datos de prueba pre-construidos en el contenedor, asegurando que la demostración cuente de inmediato con aliados, coordinadores, vendedores y ofertas sin intervención manual.

### 2.3. Ejecución de Granian ASGI (Rust)
- Granian ejecuta el socket HTTP en Rust puro (Hyper + Tokio) y pasa las corrutinas ASGI a Python.
- Gracias a las banderas `--static-path-route /static --static-path-mount /app/staticfiles --static-path-route /media --static-path-mount /app/mediafiles`, los archivos CSS, JS minificados y las imágenes subidas son despachadas directamente por el motor en Rust a velocidades C/Rust sin pasar por el intérprete de Python ni requerir servidores adicionales como Nginx o WhiteNoise.

### 2.4. Terminación SSL Automatizada (HTTPS)
- Las plataformas recomendadas gestionan la terminación SSL a nivel de su proxy de borde (Anycast Edge).
- En `aliados/settings.py` se incluyó `SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')`, garantizando que Django reconozca las conexiones seguras, genere URLs absolutas `https://` y no sufra redirecciones cíclicas (*redirect loops*).

---

## 3. Recomendación Definitiva: **Fly.io**

Fly.io es la opción arquitectónicamente superior para este proyecto por las siguientes razones:
1. **Soporte de Volúmenes de Bloque de Primera Clase**: Diseñado explícitamente para aplicaciones con SQLite embebido (impulsado por la comunidad de Litestream y creadores de SQLite).
2. **Latencia Mínima en Colombia**: Cuenta con región oficial en **Bogotá (`bog`)** y **Miami (`mia`)**, ofreciendo tiempos de respuesta inferiores a 25 ms.
3. **Cero Fricción en el Video de Sustentación**: No suspende la máquina con latencias de 50 segundos como Render Free. La máquina responde al instante.
4. **URL Pública Oficial con HTTPS**: `https://<nombre-elegido>.fly.dev` activa en menos de 2 minutos.

---

## 4. Guía de Despliegue Paso a Paso

### Opción A: Despliegue en Fly.io (Recomendado — 3 Minutos)

#### Paso 1. Instalar el CLI de Fly (`flyctl`)
- **Windows (PowerShell)**:
  ```powershell
  powershell -ExecutionPolicy ByPass -c "irm https://fly.io/install.ps1 | iex"
  ```
- **Linux / macOS**:
  ```bash
  curl -L https://fly.io/install.sh | sh
  ```

#### Paso 2. Iniciar Sesión en Fly.io
```bash
fly auth login
```

#### Paso 3. Crear la Aplicación y Reservar el Nombre
```bash
fly apps create verla-aliados-portal --machines
```
*(Si el nombre `verla-aliados-portal` ya fue tomado por otro usuario global, elija una variación como `verla-aliados-johand`).*

#### Paso 4. Crear el Volumen Persistente para SQLite y Multimedia
Cree un volumen de 1 GB en la región de Bogotá (`bog`) o Miami (`mia`):
```bash
fly volumes create verla_data --region bog --size 1
```

#### Paso 5. Configurar Secretos Sensibles
Configure la clave de seguridad de Django y la API Key de Gemini:
```bash
fly secrets set SECRET_KEY="clave-secreta-produccion-verla-2026" GEMINI_API_KEY="tu-api-key-de-gemini"
```

#### Paso 6. Desplegar la Aplicación
```bash
fly deploy
```
*Fly.io construirá la imagen utilizando el `Dockerfile` de múltiples etapas con `uv`, ejecutará `collectstatic`, montará el volumen `/data` y arrancará Granian ASGI.*

#### Paso 7. Abrir la Aplicación en el Navegador
```bash
fly open
```
La aplicación estará disponible de inmediato bajo HTTPS seguro:
👉 **`https://verla-aliados-portal.fly.dev/`**

---

### Opción B: Despliegue en Railway (Alternativa con Interfaz Web)

Para desplegar utilizando la interfaz visual de Railway:
1. Cree una cuenta en [Railway.app](https://railway.app/).
2. Haga clic en **"New Project"** -> **"Deploy from GitHub repo"** y seleccione este repositorio.
3. En la configuración del servicio:
   - Diríjase a **"Settings"** -> **"Volumes"** -> **"Add Volume"**.
   - Nombre del volumen: `verla_data`.
   - Mount Path: `/data`.
4. En **"Variables"**, defina:
   - `SECRET_KEY`: `clave-produccion-verla-railway`
   - `DEPLOY`: `PROD`
   - `ALLOWED_HOSTS`: `*`
   - `CSRF_TRUSTED_ORIGINS`: `https://*.up.railway.app`
   - `GEMINI_API_KEY`: *(opcional, tu API key de Gemini)*
5. En **"Networking"**, haga clic en **"Generate Domain"**.
6. Railway construirá el contenedor con el `Dockerfile`, montará el volumen `/data` y le otorgará su URL pública HTTPS:
👉 **`https://<servicio>.up.railway.app/`**

---

### Opción C: Despliegue en Render (Advertencia de Disco Efímero)

Si opta por Render con el archivo `render.yaml`:
1. Cree una cuenta en [Render.com](https://render.com/).
2. Seleccione **"New"** -> **"Blueprint"** y conecte este repositorio.
3. Render detectará automáticamente `render.yaml`.
> [!WARNING]
> Para mantener la persistencia de SQLite y de las fotos de ofertas en Render, es obligatorio seleccionar el plan **Starter ($7/mes)** debido a que los discos persistentes no están disponibles en el tier gratuito de Render. Si se despliega en el tier gratuito, los datos y las ofertas se resetearán cada vez que el servicio se suspenda por inactividad.

---

## 5. Lista de Verificación Post-Despliegue para el Video de Sustentación

Antes de grabar el video de sustentación de 5 a 8 minutos, verifique:

- [ ] **Acceso HTTPS**: El candado de seguridad SSL está activo en el navegador.
- [ ] **Simulador de Roles**: Ingrese a la plataforma y pruebe los cuatro roles pre-cargados (Administrador, Aliado, Coordinador, Vendedor) desde el menú superior.
- [ ] **Carga de Oferta con Imagen**: En el rol de Coordinador/Administrador, cree una oferta vigente adjuntando una imagen (`.jpg`/`.png`) y compruebe que se visualice correctamente en la vista de vendedor.
- [ ] **Asistente IA Gobernado**: Abra el widget flotante del copiloto, solicite un plan de acción para metas comerciales o una redacción de oferta, y apruebe/edite/descarte la recomendación.
- [ ] **Bloqueo Concurrente (409 Conflict)**: Abra dos pestañas privadas con el mismo vendedor, edite el teléfono en la primera pestaña y guarde; luego intente guardar en la segunda pestaña para demostrar la alerta SweetAlert2 de colisión optimista.
- [ ] **Persistencia Tras Reinicio**: Ejecute `fly apps restart verla-aliados-portal` y verifique que los registros creados sigan presentes.
