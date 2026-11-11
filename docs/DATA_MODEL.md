# Modelo de Datos y Diccionario de Datos — Portal de Aliados Comerciales VERLA SAS

Este documento especifica el esquema relacional, las restricciones de integridad, el control de concurrencia optimista (`version`) y el diccionario de datos de la base de datos SQLite 3 (`db.sqlite3` en modo WAL) para las 3 aplicaciones de dominio (`red_comercial`, `operacion`, `asistente_ia`).

---

## 1. Flujo de Dependencias y Principios del Esquema

- **Flujo unidireccional de dependencias**: `asistente_ia` -> `operacion` -> `red_comercial`.
- **Concurrencia Optimista (`VersionedModel`)**: Todas las entidades editables incluyen la columna entera `version` (inicia en `1`). Las actualizaciones validan atómicamente `WHERE id = :id AND version = :expected_version` e incrementan `version = version + 1`. Si otro usuario modificó el registro previamente, se lanza `ConcurrentModificationError` (traducido en la capa HTTP como `409 Conflict`).
- **Trazabilidad e Historial (`AuditLog`)**: Cada creación, edición o transición de estado/bloqueo registra el diferencial antes/después en formato JSON (`cambios_json`), el usuario actor y la versión resultante.
- **Extracción de Diagrama ER en DBeaver**: El archivo `db.sqlite3` en la raíz del proyecto se inicializa con `PRAGMA foreign_keys=ON;`. Al abrir `db.sqlite3` en DBeaver y seleccionar el esquema principal -> pestaña **ER Diagram**, todas las llaves foráneas y tablas puente M2M se visualizan automáticamente.

---

## 2. Diagrama Entidad-Relación (Mermaid ER)

```mermaid
erDiagram
    CIUDAD ||--o{ VENDEDOR : "ciudad_base"
    CIUDAD }o--o{ VENDEDOR : "ciudades_operacion (M2M)"
    CIUDAD }o--o{ OFERTA_PERIODO : "ciudades (M2M)"
    ALIADO ||--o{ COORDINADOR : "tiene"
    ALIADO ||--o{ VENDEDOR : "vincula"
    ALIADO ||--o{ OFERTA_PERIODO : "segmenta (opcional)"
    COORDINADOR ||--o{ VENDEDOR : "supervisa"
    VENDEDOR ||--o{ META_MENSUAL : "registra_metas"
    AUTH_USER ||--o| ALIADO : "perfil_aliado"
    AUTH_USER ||--o| COORDINADOR : "perfil_coordinador"
    AUTH_USER ||--o| VENDEDOR : "perfil_vendedor"
    AUTH_USER ||--o{ AUDIT_LOG : "ejecuta"
    AUTH_USER ||--o{ AI_AUDIT_LOG : "consulta"

    CIUDAD {
        bigint id PK
        varchar(10) codigo UK
        varchar(120) nombre UK
        varchar(120) departamento
        boolean activa
        int version
    }

    ALIADO {
        bigint id PK
        varchar(30) nit UK
        varchar(180) razon_social
        varchar(50) codigo_contrato UK
        varchar(254) correo_contacto
        varchar(30) telefono
        boolean activo
        int usuario_id FK
        int version
    }

    COORDINADOR {
        bigint id PK
        bigint aliado_id FK
        varchar(30) documento UK
        varchar(160) nombre_completo
        varchar(254) correo
        varchar(30) telefono
        boolean activo
        int usuario_id FK
        int version
    }

    VENDEDOR {
        bigint id PK
        bigint aliado_id FK
        bigint coordinador_id FK
        varchar(30) documento UK
        varchar(160) nombre_completo
        varchar(254) correo
        varchar(30) telefono
        varchar(100) cargo
        bigint ciudad_base_id FK
        varchar(15) estado "ACTIVO | INACTIVO | BLOQUEADO"
        varchar(255) motivo_estado
        date fecha_ingreso
        int usuario_id FK
        int version
    }

    AUDIT_LOG {
        bigint id PK
        varchar(80) entidad
        bigint registro_id
        varchar(30) accion "CREACION | ACTUALIZACION | CAMBIO_ESTADO | BLOQUEO"
        int usuario_id FK
        json cambios_json
        int version_resultante
        datetime fecha_evento
    }

    META_MENSUAL {
        bigint id PK
        bigint vendedor_id FK
        varchar(7) periodo "YYYY-MM"
        decimal meta_valor
        decimal resultado_real
        varchar(255) observaciones
        int version
    }

    OFERTA_PERIODO {
        bigint id PK
        varchar(160) titulo
        text descripcion
        varchar(100) imagen
        varchar(7) periodo "YYYY-MM"
        date fecha_inicio
        date fecha_fin
        boolean activa
        bigint aliado_id FK
        int version
    }

    AI_AUDIT_LOG {
        bigint id PK
        int usuario_id FK
        varchar(40) caso_uso "GENERACION_OFERTA | ANALISIS_METAS"
        varchar(60) modelo
        text prompt_resumen
        json respuesta_json
        int latencia_ms
        int tokens_estimados
        varchar(20) decision_humana "PENDIENTE | ACEPTADO | EDITADO | DESCARTADO"
        datetime creado_en
    }
```

---

## 3. Diccionario de Datos por Tabla

### 3.1. `red_comercial_ciudad` (`Ciudad`)
Catálogo oficial de ciudades donde opera la fuerza de ventas de VERLA SAS.

| Columna | Tipo SQL | Nulo | Restricciones / Índices | Descripción |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | No | `PK`, `AUTOINCREMENT` | Identificador único de la ciudad. |
| `codigo` | `VARCHAR(10)` | No | `UNIQUE` | Código corto estandarizado (ej. `BOG`, `MED`, `CLO`). |
| `nombre` | `VARCHAR(120)` | No | `UNIQUE` | Nombre oficial del municipio o distrito. |
| `departamento` | `VARCHAR(120)` | No | — | Departamento al que pertenece la ciudad. |
| `activa` | `BOOL` | No | `DEFAULT 1` | Indica si la ciudad está habilitada para operación comercial. |
| `version` | `INTEGER UNSIGNED` | No | `DEFAULT 1` | Versión para control de concurrencia optimista. |
| `creado_en` | `DATETIME` | No | — | Marca temporal de creación del registro. |
| `actualizado_en` | `DATETIME` | No | — | Marca temporal de última actualización. |

---

### 3.2. `red_comercial_aliado` (`Aliado`)
Entidad jurídica titular de un contrato de distribución comercial con VERLA SAS.

| Columna | Tipo SQL | Nulo | Restricciones / Índices | Descripción |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | No | `PK`, `AUTOINCREMENT` | Identificador único del aliado comercial. |
| `nit` | `VARCHAR(30)` | No | `UNIQUE` | Número de Identificación Tributaria con dígito de verificación. |
| `razon_social` | `VARCHAR(180)` | No | — | Nombre legal o razón social de la empresa aliada. |
| `codigo_contrato` | `VARCHAR(50)` | No | `UNIQUE` | Código de contrato marco suscrito con VERLA SAS. |
| `correo_contacto` | `VARCHAR(254)` | No | — | Correo electrónico principal de notificaciones. |
| `telefono` | `VARCHAR(30)` | No | — | Teléfono de contacto corporativo. |
| `activo` | `BOOL` | No | `DEFAULT 1` | Si es `0`, inhabilita operativamente a toda su red asociada. |
| `usuario_id` | `INTEGER` | Sí | `UNIQUE`, `FK -> auth_user(id)` (`SET NULL`) | Cuenta de usuario opcional asociada al perfil de Aliado. |
| `version` | `INTEGER UNSIGNED` | No | `DEFAULT 1` | Versión para control de concurrencia optimista. |
| `creado_en` | `DATETIME` | No | — | Fecha y hora de creación. |
| `actualizado_en` | `DATETIME` | No | — | Fecha y hora de última modificación. |

---

### 3.3. `red_comercial_coordinador` (`Coordinador`)
Supervisor comercial perteneciente a un `Aliado` y responsable de un equipo de vendedores.

| Columna | Tipo SQL | Nulo | Restricciones / Índices | Descripción |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | No | `PK`, `AUTOINCREMENT` | Identificador único del coordinador. |
| `aliado_id` | `BIGINT` | No | `FK -> red_comercial_aliado(id)` (`PROTECT`) | Aliado comercial al que pertenece el coordinador. |
| `documento` | `VARCHAR(30)` | No | `UNIQUE` | Documento de identidad del coordinador. |
| `nombre_completo` | `VARCHAR(160)` | No | — | Nombres y apellidos completos. |
| `correo` | `VARCHAR(254)` | No | — | Correo electrónico corporativo. |
| `telefono` | `VARCHAR(30)` | No | — | Número de contacto móvil. |
| `activo` | `BOOL` | No | `DEFAULT 1` | Indica si el coordinador se encuentra activo. |
| `usuario_id` | `INTEGER` | Sí | `UNIQUE`, `FK -> auth_user(id)` (`SET NULL`) | Cuenta de usuario opcional asociada al rol Coordinador. |
| `version` | `INTEGER UNSIGNED` | No | `DEFAULT 1` | Versión para control de concurrencia optimista. |
| `creado_en` | `DATETIME` | No | — | Fecha y hora de creación. |
| `actualizado_en` | `DATETIME` | No | — | Fecha y hora de última actualización. |

---

### 3.4. `red_comercial_vendedor` (`Vendedor`) y `red_comercial_vendedor_ciudades_operacion`
Ficha de funcionario comercial asignado a un `Coordinador`, con ciudad base, operación multiciudad y control de bloqueo operativo.

| Columna | Tipo SQL | Nulo | Restricciones / Índices | Descripción |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | No | `PK`, `AUTOINCREMENT` | Identificador único del vendedor. |
| `aliado_id` | `BIGINT` | No | `FK -> red_comercial_aliado(id)` (`PROTECT`) | Aliado empleador del vendedor (debe coincidir con el del coordinador). |
| `coordinador_id` | `BIGINT` | No | `FK -> red_comercial_coordinador(id)` (`PROTECT`) | Coordinador responsable directo del vendedor. |
| `documento` | `VARCHAR(30)` | No | `UNIQUE` | Cédula o documento de identidad del funcionario. |
| `nombre_completo` | `VARCHAR(160)` | No | — | Nombre completo del funcionario. |
| `correo` | `VARCHAR(254)` | No | — | Correo electrónico del vendedor. |
| `telefono` | `VARCHAR(30)` | No | — | Teléfono móvil del vendedor. |
| `cargo` | `VARCHAR(100)` | No | `DEFAULT 'Asesor Comercial'` | Cargo dentro de la estructura comercial. |
| `ciudad_base_id` | `BIGINT` | No | `FK -> red_comercial_ciudad(id)` (`PROTECT`) | Sede principal o ciudad base del funcionario. |
| `estado` | `VARCHAR(15)` | No | `INDEX`, `DEFAULT 'ACTIVO'` | Estado operativo: `ACTIVO`, `INACTIVO` o `BLOQUEADO`. |
| `motivo_estado` | `VARCHAR(255)` | No | `DEFAULT ''` | Justificación de inactivación o bloqueo operativo. |
| `fecha_ingreso` | `DATE` | No | — | Fecha de vinculación a la red comercial. |
| `usuario_id` | `INTEGER` | Sí | `UNIQUE`, `FK -> auth_user(id)` (`SET NULL`) | Usuario del portal para vista de vendedor. |
| `version` | `INTEGER UNSIGNED` | No | `DEFAULT 1` | Versión para control de concurrencia optimista. |
| `creado_en` | `DATETIME` | No | — | Fecha y hora de creación. |
| `actualizado_en` | `DATETIME` | No | — | Fecha y hora de última modificación. |

- **Tabla puente M2M `red_comercial_vendedor_ciudades_operacion`**:
  - `vendedor_id` (`FK -> red_comercial_vendedor.id`)
  - `ciudad_id` (`FK -> red_comercial_ciudad.id`)
  - Restricción única compuesta `(vendedor_id, ciudad_id)` que permite a un mismo vendedor operar en una o múltiples ciudades.

---

### 3.5. `red_comercial_auditlog` (`AuditLog`)
Bitácora inmutable de auditoría de cambios sobre las entidades del portal.

| Columna | Tipo SQL | Nulo | Restricciones / Índices | Descripción |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | No | `PK`, `AUTOINCREMENT` | Identificador único del evento de auditoría. |
| `entidad` | `VARCHAR(80)` | No | `INDEX` | Nombre de la clase de modelo auditada (ej. `Vendedor`, `Aliado`). |
| `registro_id` | `BIGINT UNSIGNED` | No | `INDEX` | Llave primaria del registro afectado. |
| `accion` | `VARCHAR(30)` | No | — | Tipo de evento: `CREACION`, `ACTUALIZACION`, `CAMBIO_ESTADO`, `BLOQUEO`. |
| `usuario_id` | `INTEGER` | Sí | `FK -> auth_user(id)` (`SET NULL`) | Actor autenticado que ejecutó la operación. |
| `cambios_json` | `JSON` | No | — | Diccionario `{campo: {"antes": valor_anterior, "despues": valor_nuevo}}`. |
| `version_resultante` | `INTEGER UNSIGNED` | No | `DEFAULT 1` | Número de versión del registro tras aplicar el cambio. |
| `fecha_evento` | `DATETIME` | No | `INDEX` | Marca de tiempo exacta del evento. |

---

### 3.6. `operacion_metamensual` (`MetaMensual`)
Registro de metas comerciales mensuales vs. resultados reales por vendedor y periodo (`YYYY-MM`).

| Columna | Tipo SQL | Nulo | Restricciones / Índices | Descripción |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | No | `PK`, `AUTOINCREMENT` | Identificador único de la meta mensual. |
| `vendedor_id` | `BIGINT` | No | `FK -> red_comercial_vendedor(id)` (`CASCADE`) | Vendedor al cual se asigna la meta. |
| `periodo` | `VARCHAR(7)` | No | `INDEX`, `uniq_meta_vendedor_periodo` | Periodo mensual en formato `YYYY-MM`. |
| `meta_valor` | `DECIMAL(14, 2)` | No | — | Valor monetario de la meta asignada en el mes. |
| `resultado_real` | `DECIMAL(14, 2)` | No | `DEFAULT 0.00` | Valor monetario real ejecutado acumulada en el mes. |
| `observaciones` | `VARCHAR(255)` | No | `DEFAULT ''` | Notas operativas o seguimiento de cumplimiento. |
| `version` | `INTEGER UNSIGNED` | No | `DEFAULT 1` | Versión para control de concurrencia optimista. |
| `creado_en` | `DATETIME` | No | — | Fecha y hora de creación. |
| `actualizado_en` | `DATETIME` | No | — | Fecha y hora de última modificación. |

---

### 3.7. `operacion_ofertaperiodo` (`OfertaPeriodo`) y `operacion_ofertaperiodo_ciudades`
Ofertas promocionales vigentes por periodo con soporte de textos comerciales, imagen (`ImageField`) y segmentación por aliado/ciudades.

| Columna | Tipo SQL | Nulo | Restricciones / Índices | Descripción |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | No | `PK`, `AUTOINCREMENT` | Identificador único de la oferta. |
| `titulo` | `VARCHAR(160)` | No | — | Título comercial de la promoción. |
| `descripcion` | `TEXT` | No | — | Condiciones comerciales, tarifas y beneficios de la oferta. |
| `imagen` | `VARCHAR(100)` | Sí | — | Ruta relativa en `MEDIA_ROOT` (`ofertas/%Y/%m/`) de la pieza gráfica. |
| `periodo` | `VARCHAR(7)` | No | `INDEX` | Periodo comercial de referencia (`YYYY-MM`). |
| `fecha_inicio` | `DATE` | No | — | Fecha de inicio de vigencia de la oferta. |
| `fecha_fin` | `DATE` | No | — | Fecha final de vigencia (`fecha_fin >= fecha_inicio`). |
| `activa` | `BOOL` | No | `INDEX`, `DEFAULT 1` | Permite activar o retirar inmediatamente la oferta del portal. |
| `aliado_id` | `BIGINT` | Sí | `FK -> red_comercial_aliado(id)` (`CASCADE`) | Si es `NULL`, aplica a todos los aliados; si se define, es exclusiva. |
| `version` | `INTEGER UNSIGNED` | No | `DEFAULT 1` | Versión para control de concurrencia optimista. |
| `creado_en` | `DATETIME` | No | — | Fecha y hora de creación. |
| `actualizado_en` | `DATETIME` | No | — | Fecha y hora de última modificación. |

- **Tabla puente M2M `operacion_ofertaperiodo_ciudades`**:
  - `ofertaperiodo_id` (`FK -> operacion_ofertaperiodo.id`)
  - `ciudad_id` (`FK -> red_comercial_ciudad.id`)
  - Si una oferta no tiene filas asociadas en esta tabla puente, se considera de cobertura nacional para todas las ciudades activas.

---

### 3.8. `asistente_ia_aiauditlog` (`AIAuditLog`)
Bitácora de auditoría y telemetría de interacciones con Google Gemini (`gemini-2.5-flash`) bajo esquema *human-in-the-loop*.

| Columna | Tipo SQL | Nulo | Restricciones / Índices | Descripción |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | No | `PK`, `AUTOINCREMENT` | Identificador único de la consulta al modelo IA. |
| `usuario_id` | `INTEGER` | Sí | `FK -> auth_user(id)` (`SET NULL`) | Usuario que solicitó la asistencia de IA. |
| `caso_uso` | `VARCHAR(40)` | No | `INDEX` | Caso de uso: `GENERACION_OFERTA` o `ANALISIS_METAS`. |
| `modelo` | `VARCHAR(60)` | No | `DEFAULT 'gemini-2.5-flash'` | Identificador del modelo invocado. |
| `prompt_resumen` | `TEXT` | No | — | Contexto o parámetros enviados al generador. |
| `respuesta_json` | `JSON` | No | — | Respuesta estructurada devuelta por el asistente. |
| `latencia_ms` | `INTEGER UNSIGNED` | No | `DEFAULT 0` | Tiempo de respuesta medido en milisegundos. |
| `tokens_estimados` | `INTEGER UNSIGNED` | No | `DEFAULT 0` | Conteo total de tokens reportados o estimados. |
| `decision_humana` | `VARCHAR(20)` | No | `INDEX`, `DEFAULT 'PENDIENTE'` | Veredicto humano: `PENDIENTE`, `ACEPTADO`, `EDITADO`, `DESCARTADO`. |
| `creado_en` | `DATETIME` | No | — | Fecha y hora de la consulta. |
| `actualizado_en` | `DATETIME` | No | — | Fecha y hora en que se registró la decisión humana. |
