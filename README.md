# Portal de Aliados Comerciales — VERLA SAS (MVP)

Plataforma integral para la gestión operativa de la red comercial de **VERLA SAS**: administración de aliados, coordinadores, vendedores y cobertura por ciudades, seguimiento de metas mensuales frente a resultados reales, publicación de ofertas vigentes por período y asistencia con Inteligencia Artificial gobernada (*human-in-the-loop*).

---

## 1. Resumen Ejecutivo y Criterios de Evaluación

El reto técnico evalúa **criterio de diseño arquitectónico y operación real** (no maquetado estático) sobre seis frentes con igual ponderación:

| Frente Evaluado | Alcance y Solución Adoptada |
| :--- | :--- |
| **1. Modelo de Datos** | Esquema relacional normalizado con integridad referencial, versionamiento por fila para concurrencia y tabla de auditoría histórica (`AuditLog`) para trazabilidad completa. |
| **2. MVP Funcional** | CRUD real de aliados, coordinadores, vendedores (ficha de empleado) y ciudades; operación multi-ciudad; comparativa mensual de metas vs. resultados reales; ofertas vigentes con texto e imágenes por período. |
| **3. Uso de IA** | Integración asíncrona con **Google Gemini API (`gemini-3.5-flash-lite`)** para redacción asistida de ofertas y análisis de brechas de metas, con control humano obligatorio y registro de métricas (`AIAuditLog`). |
| **4. Pruebas y Bloqueo** | RBAC por rol (Administrador, Aliado, Coordinador, Vendedor), control de edición concurrente mediante *Optimistic Locking* (`version` + HTTP `409 Conflict`) y suite automatizada de pruebas. |
| **5. Despliegue y Plan** | Aplicación contenedorizada y desplegada en vivo sobre servidor Rust ASGI (**Granian**), acompañada de cronograma de ejecución con entregables verificables. |
| **6. Sustentación (Video)** | Defensa técnica de 5 a 8 minutos cubriendo arquitectura, decisiones de diseño y demostración del sistema operando en vivo. |

---

## 2. Requerimientos del Negocio y Alcance del MVP

### 2.1 Reglas de Negocio
- **Aliado Comercial**: Titular del contrato comercial y responsable directo de su red de coordinadores y vendedores.
- **Coordinadores y Vendedores**: Cada aliado cuenta con coordinadores y vendedores asignados. Todo vendedor posee una **ficha de empleado** con datos propios: documento de identidad, datos de contacto, cargo, ciudad base, fecha de ingreso y estado operativo.
- **Cobertura Geográfica y Estados**: Un vendedor puede operar en **una o varias ciudades** y encontrarse en estado `ACTIVO`, `INACTIVO` o `BLOQUEADO` (un vendedor bloqueado o inactivo tiene restringida su operación comercial según las reglas del dominio).
- **Metas vs. Resultados Reales**: Se miden mensualmente (`YYYY-MM`) permitiendo agregación y trazabilidad por **vendedor**, **coordinador** y **aliado**.
- **Ofertas Vigentes por Período**: Publicación de promociones y condiciones comerciales con contenido textual e imágenes variables según el período de vigencia, visibles para la fuerza de ventas activa.

### 2.2 Entregables Exigidos
- [ ] **Arquitectura y Modelo de Datos**: Diagrama Entidad-Relación (DER) y diccionario de datos detallado.
- [ ] **MVP Funcional en Vivo**: Operaciones CRUD completas con historial de cambios auditable.
- [ ] **Seguridad, Roles y Concurrencia**: Matriz de permisos por rol y prevención de pérdida de actualizaciones (*lost updates*) en edición simultánea.
- [ ] **Módulo de IA con Control**: Documentación e implementación de dónde aporta valor, con qué guardrails opera y cómo se mide su efectividad.
- [ ] **Estrategia de Pruebas**: Pruebas automatizadas de reglas críticas de negocio, permisos y colisiones de concurrencia.
- [ ] **Despliegue y Cronograma**: URL pública funcional, plan de trabajo con hitos/fechas y video de sustentación (5–8 min).

---

## 3. Stack Tecnológico Definido

El stack fue seleccionado priorizando **robustez transaccional, velocidad de entrega (sprint de 17 horas) y rendimiento en producción**:

| Capa | Tecnología | Justificación Arquitectónica |
| :--- | :--- | :--- |
| **Lenguaje y Runtime** | **Python 3.14** | Tipado moderno, mejoras de rendimiento del intérprete y soporte de ruedas binarias (`cp314`) en todo el stack seleccionado. |
| **Gestor de Paquetes y Entorno** | **`uv` (Astral)** | Gestor de paquetes ultrarrápido escrito en Rust. Resuelve e instala dependencias en milisegundos con aislamiento determinista (`pyproject.toml`). |
| **Framework Backend** | **Django 5.x / 6.x (ORM + Auth + Templates)** | Baterías incluidas para autenticación, RBAC nativo, protección CSRF, migraciones deterministas y soporte transaccional (`select_for_update` / `F()` expressions). |
| **Servidor HTTP / ASGI** | **Granian (`--interface asgi`)** | Servidor HTTP en Rust (Hyper/Tokio) que ejecuta la aplicación ASGI y sirve `/static` y `/media` directamente desde Rust sin sobrecargar los workers de Python ni requerir WhiteNoise. |
| **Frontend y Estética** | **Pico CSS (CDN) + Vanilla JS (ES6+)** | Interfaz semántica, minimalista y responsiva sin advertencias de compiladores JIT en navegador ni complejidad de bundlers Node.js. |
| **Serialización y Minificación** | **`ManifestStaticFilesStorage` + `rjsmin` / `rcssmin` + `django-minify-html`** | Pipeline 100% nativo en `collectstatic`: minifica archivos `.js` y `.css`, agrega hash MD5 al nombre del archivo para *cache-busting* inmutable y minifica el HTML en tiempo de respuesta. |
| **Base de Datos** | **SQLite 3 en modo WAL (`transaction_mode=IMMEDIATE`)** | Motor ACID embebido con cero latencia de red, lecturas no bloqueantes (`WAL`), cola de escritura segura (`busy_timeout=5000`), soporte atómico para *Optimistic Locking* y portabilidad inmediata a PostgreSQL mediante el ORM de Django. |
| **Inteligencia Artificial** | **Google Gemini API (`gemini-3.5-flash-lite`) vía `httpx.AsyncClient`** | Endpoint asíncrono no bloqueante con salida JSON estructurada, tier gratuito sin fricción y capa de auditoría (`AIAuditLog`). |

---

## 4. Estrategia de Ejecución y Plan de Abordaje (Sprint 17 Horas)

El desarrollo se estructura en **6 fases incrementales**. La integración de IA se ubica estratégicamente después de construir el núcleo transaccional (CRUD, metas y ofertas) para que el modelo opere sobre **datos reales del dominio**.

```mermaid
flowchart LR
    F1["Fase 1: Arquitectura y Modelo de Datos"] --> F2["Fase 2: Core CRUD + Auditoría + Concurrencia"]
    F2 --> F3["Fase 3: Metas Mensuales y Ofertas Vigentes"]
    F3 --> F4["Fase 4: Integración IA (Gemini) con Control"]
    F4 --> F5["Fase 5: Suite de Pruebas Críticas"]
    F5 --> F6["Fase 6: Despliegue en Vivo y Video"]
```

### Detalle del Cronograma Operativo (11 Nov 16:00 – 12 Nov 09:00)

| Fase | Ventana Estimada | Entregable Verificable |
| :--- | :--- | :--- |
| **Fase 1: Modelo de Datos y Base del Proyecto** | 11 Nov · 16:30 – 18:00 | Inicialización de Django sobre Python 3.14 + Granian, configuración de minificación/serialización de estáticos, diseño del DER, diccionario de datos y migraciones iniciales. |
| **Fase 2: Red Comercial, Roles y Concurrencia** | 11 Nov · 18:00 – 21:00 | CRUD de Ciudades, Aliados, Coordinadores y Vendedores (ficha completa y asignación multi-ciudad), RBAC por rol, historial de cambios (`AuditLog`) y bloqueo optimista (`version`). |
| **Fase 3: Metas Mensuales y Ofertas por Período** | 11 Nov · 21:00 – 23:30 | Tablero de Metas vs. Resultados reales (por vendedor, coordinador y aliado) y módulo de Ofertas vigentes con carga de imágenes y vista dedicada para el vendedor. |
| **Fase 4: Uso de IA (Google Gemini)** | 11 Nov · 23:30 – 01:30 | Servicio asíncrono (`async def`) conectado a Gemini para generación asistida de ofertas y diagnóstico de cumplimiento de metas, con aprobación humana y telemetría en `AIAuditLog`. |
| **Fase 5: Pruebas Automatizadas y Casos Críticos** | 12 Nov · 01:30 – 03:30 | Pruebas unitarias y de integración cubriendo colisión de edición concurrente (`409 Conflict`), restricciones de vendedores bloqueados/inactivos, cálculo de metas y fallback de IA. |
| **Fase 6: Despliegue, Documentación Final y Video** | 12 Nov · 03:30 – 08:30 | Despliegue en la nube verificable, revisión final de documentación técnica y grabación/envío del video de defensa (5 a 8 minutos) antes de las 09:00 a.m. |

---

## 5. Diseño de Gobernanza para Concurrencia e IA

### 5.1 Control de Bloqueo y Edición Concurrente
- **Bloqueo Optimista (*Optimistic Concurrency Control*)**: Cada entidad editable (`Aliado`, `Coordinador`, `Vendedor`, `MetaMensual`, `OfertaPeriodo`) incluye un campo entero `version`. Toda actualización valida `WHERE id = :id AND version = :current_version` incrementando `version = version + 1` de forma atómica. Si otro usuario modificó el registro previamente, el sistema rechaza la escritura con estado `409 Conflict`, preserva los cambios en pantalla y exige recargar o confirmar antes de sobrescribir.
- **Trazabilidad (`AuditLog`)**: Cada creación, actualización o cambio de estado (`ACTIVO`, `INACTIVO`, `BLOQUEADO`) registra actor, fecha/hora UTC, entidad, identificador, snapshot `before/after` en JSON y versión resultante.

### 5.2 Inteligencia Artificial: Real, Medible y con Control
1. **¿Dónde aporta y para qué?**:
   - **Asistente de Redacción de Ofertas**: Genera propuestas de texto comercial estructurado para un período y segmento específico, listas para copiar al portapapeles.
   - **Analista de Cumplimiento Comercial**: Evalúa las desviaciones entre metas del mes y resultados reales con aislamiento estricto por rol (vendedor, coordinador, aliado o administrador) y sugiere planes de acción ejecutivos.
2. **¿Con qué control y racionamiento de tokens?**:
   - *Human-in-the-loop*: La IA jamás modifica registros directamente; entrega recomendaciones estructuradas que el usuario debe revisar y aprobar explícitamente (`ACEPTADO`, `EDITADO`, `DESCARTADO`).
   - **Racionamiento de Tokens y Cuotas de Usuario**: Techo estricto de `maxOutputTokens: 600` en Gemini, longitud máxima de prompt de 400 caracteres, y cuota por usuario de **15 consultas cada 2 minutos** y **50 consultas por día calendario** evaluadas en tiempo real sobre `AIAuditLog` con índice optimizado `(usuario_id, creado_en)`.
   - **Degradación Elegante**: Modo de contingencia local determinístico ante agotamiento de cuota de Google (HTTP 429) o fallos de conexión externa.
3. **¿Cómo se mide?**:
   - Registro en `AIAuditLog` de latencia en milisegundos, tokens utilizados, usuario solicitante y decisión final del operador (`ACEPTADO`, `EDITADO`, `DESCARTADO`).
   - Indicador dinámico de cuota en la cabecera del chat (`Disponibles: 50`) con notificación preventiva si se aproxima al límite.

---

## 6. Guía de Instalación y Puesta en Marcha

El proyecto utiliza **`uv`** (desarrollado por Astral en Rust) como gestor unificado de paquetes, entornos virtuales y dependencias para garantizar una instalación ultrarrápida, aislada y determinista.

### 6.1. Requisitos Previos

1. **Python >= 3.14** (o Python 3.12+ soportado en `pyproject.toml`).
2. **`uv` instalado en el sistema**:
   - **En Windows (PowerShell)**:
     ```powershell
     powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
     ```
   - **En Linux / macOS (curl)**:
     ```bash
     curl -LsSf https://astral.sh/uv/install.sh | sh
     ```

### 6.2. Clonación y Configuración del Entorno

1. **Clonar el repositorio y entrar a la carpeta**:
   ```bash
   git clone <url-del-repositorio>
   cd Prueba-tecnica-verla-sas-Johand-Castro
   ```

2. **Sincronizar el entorno virtual y dependencias con `uv`**:
   ```bash
   uv sync
   ```
   *`uv` creará automáticamente el entorno virtual (`.venv`) e instalará con pinning estricto todas las dependencias definidas en `pyproject.toml`.*

3. **Configurar las Variables de Entorno (`.env`)**:
   Copie la plantilla de variables de entorno:
   ```bash
   cp .env.template .env
   ```
   *En Windows (PowerShell)*:
   ```powershell
   Copy-Item .env.template .env
   ```
   Ajuste los valores en su archivo `.env`:
   ```dotenv
   SECRET_KEY="clave-secreta-para-entorno-local-verla"
   DEPLOY="DEV"
   URL_BASE="/APP"
   GEMINI_API_KEY="tu-api-key-de-google-gemini"
   ```
   > [!NOTE]
   > La variable `GEMINI_API_KEY` es opcional para desarrollo local. En caso de ausencia, expiración o límite de tasa (HTTP 429), el asistente de IA conmuta automáticamente a un modo de contingencia (*fallback*) determinístico y estructurado sin interrumpir la experiencia de usuario.

### 6.3. Base de Datos y Activos Estáticos

1. **Aplicar las migraciones de base de datos (SQLite en modo WAL)**:
   ```bash
   uv run python manage.py migrate
   ```

2. **Compilar y minificar los activos estáticos (CSS/JS con hash MD5)**:
   ```bash
   uv run python manage.py collectstatic --no-input
   ```

3. **(Opcional) Crear superusuario administrador**:
   ```bash
   uv run python manage.py createsuperuser
   ```

### 6.4. Ejecución del Servidor

El proyecto soporta dos modos de ejecución:

#### Opción A: Servidor ASGI de Producción con Granian (Recomendado)
Ejecuta la capa de transporte sobre el motor HTTP en Rust (**Granian**), sirviendo estáticos y multimedia directamente a nivel de socket con soporte de recarga en caliente (*auto-reload*):
```bash
uv run granian --interface asgi aliados.asgi:application --host 127.0.0.1 --port 8000 --reload
```

#### Opción B: Servidor de Desarrollo Nativo de Django
```bash
uv run python manage.py runserver
```

Una vez iniciado, acceda desde su navegador a:
👉 **`http://127.0.0.1:8000/`** (o a la ruta con prefijo `http://127.0.0.1:8000/APP/`).

---

## 7. Ejecución de la Suite de Pruebas Automatizadas

El proyecto cuenta con una cobertura integral de pruebas unitarias y de integración que validan la jerarquía comercial, el control de concurrencia optimista (HTTP 409), el ciclo de vida multimedia con eliminación física de archivos y la telemetría del copiloto IA:

```bash
uv run python manage.py test
```

**Resultado esperado:**
```text
Ran 67 tests in ~65s — OK (0 fallos, 0 errores)
```

