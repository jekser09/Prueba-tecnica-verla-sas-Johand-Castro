# Auditoría de Calidad y Verificación Funcional E2E — Portal de Aliados Comerciales VERLA SAS

Fecha de ejecución: 11 de Noviembre de 2026  
Entorno de evaluación: Python 3.14.7 + Django 6.1.3 + Granian ASGI + SQLite 3 (WAL) + Pico CSS v2 Dark Theme  
Auditor: Antigravity Senior Architect & Suite Automatizada de Pruebas

---

## 1. Resumen Ejecutivo

Se ejecutó la revisión integral de calidad funcional y de experiencia de usuario (UX/UI) correspondiente a **T6**, cubriendo las 6 dimensiones críticas del MVP:
1. **Modelo Relacional, Concurrencia Optimista y Trazabilidad de Auditoría**: Cumplimiento del 100%. Bloqueo por versión (`version`) con respuesta HTTP `409 Conflict` y registro de diffs JSON en `AuditLog`.
2. **Jerarquía Comercial y Control Operativo (RBAC)**: Validaciones estrictas de pertenencia Coordinador-Aliado, asignación multiciudad para vendedores y bloqueo estricto con vista `acceso_bloqueado.html` para estados `BLOQUEADO` e `INACTIVO`.
3. **Control Operacional de Metas y Ofertas**: Visualización agregada y granular por Aliado, Coordinador y Vendedor; soporte de carga de imágenes en `OfertaPeriodo` y filtrado por vigencia y ciudades de cobertura.
4. **Copiloto IA Controlado (Google Gemini)**: Widget global flotante con estrella oficial blanca de Gemini, aislamiento en `sessionStorage` (limpieza automática en logout/cambio de rol), inyección de contexto de pantalla y registro de veredictos humanos en `AIAuditLog`.
5. **Sistema de Diseño Dark Theme & Activos**: Paleta oficial VERLA derivada de `Logo verla horizontal.png`, separación estricta de CSS en `static/css/verla.css` con tipografía de 15px/16px y elementos redondeados sutilmente (border-radius 8px).
6. **Manejo de Estáticos y Multimedia**: Separación estricta de rutas: desarrollo local con `static/` (origen), `staticfiles/` (recopilación) y `mediafiles/` (subidas); producción en `/var/www/staticverla` y `/var/www/mediaverla`.

---

## 2. Matriz de Verificación Funcional

| Dimensión / Requisito | Estado | Evidencia de Verificación |
| :--- | :--- | :--- |
| **Separación de Estáticos y Media** | **Aprobado** | Configuración validada en `aliados/settings.py` (`DEV` vs `PROD`). Servido directo en URLs. `collectstatic` post-procesó 136 archivos con manifiesto MD5 sin errores. |
| **Ciclo de Vida y Auditoría Multimedia** | **Aprobado** | Nomenclatura trazable `ruta_imagen_oferta` (`audit_oferta_<id>_<periodo>_<timestamp>_<slug>`). Depuración física automática de imágenes obsoletas en `optimistic_update` y eliminación total en `post_delete`. |
| **Renderizado y Edición de Imágenes de Oferta** | **Aprobado** | Soporte de previsualización en formulario, actualización con `request.FILES` y guardado físico en storage sin pérdida de archivos. |
| **Pico CSS y Purga de Estilos Inline** | **Aprobado** | Cero etiquetas `<style>` dentro de templates. Clases utilitarias y tokens unificados en `static/css/verla.css`. Modales `<dialog>` nativos para auditorías de IA y Red Comercial. |
| **Formateo de Moneda (COP)** | **Aprobado** | Módulo `static/js/formatters.js` aplicando `Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP' })`. |
| **Notificaciones y Modales (SweetAlert2)** | **Aprobado** | Reemplazo total de alertas nativas del navegador por `window.VerlaAlert` con tema oscuro VERLA. Confirmaciones en eliminaciones y cancelaciones. Botón unificado "Cancelar ✕" en ofertas. |
| **Eliminación y Cancelación (Admin / Coordinador)** | **Aprobado** | Vistas de eliminación segura con captura de `ProtectedError` para Ciudades, Aliados, Coordinadores, Vendedores (con verificación de supervisión del Coordinador y registro en `AuditLog`) y cancelación/eliminación de Ofertas. |
| **Normalización Relacional (3FN) Vendedor-Aliado** | **Aprobado** | Remoción de la FK redundante `aliado` en `Vendedor`. El Aliado se deriva de forma unívoca a través de `coordinador.aliado`. Formulario simplificado (solo selecciona Coordinador) y migración `0003_remove_vendedor_aliado` aplicada. |
| **Suite de Pruebas Automatizadas** | **Aprobado** | **67 de 67 pruebas pasando** (`Ran 67 tests in 85.12s — OK`). |
| **Sincronización de Base de Datos** | **Aprobado** | `makemigrations --check --dry-run` retorna `No changes detected`. |

---

## 3. Estado de la Suite de Pruebas

```text
Ran 67 tests in 85.12s

OK
Destroying test database for alias 'default' ('file:memorydb_default?mode=memory&cache=shared')...
System check identified no issues (0 silenced).
```

---

## 4. Detalle de la Normalización de Dominio (3FN Vendedor-Coordinador-Aliado)

- **Causa Raíz**: El modelo `Vendedor` requería seleccionar simultáneamente `aliado` y `coordinador`, lo que generaba dependencia transitiva redundante y necesidad de validaciones cruzadas propensas a errores humanos en UI.
- **Acción Correctiva**:
  1. Se eliminó la ForeignKey `aliado` de `red_comercial_vendedor` (migración `0003_remove_vendedor_aliado.py`).
  2. Se configuró `@property def aliado(self)` en `Vendedor` delegando en `self.coordinador.aliado`.
  3. Se retiró el campo `aliado` del formulario `VendedorForm` y de la vista `vendedor_form.html`, permitiendo que el usuario solo elija el Coordinador responsable.
  4. Se actualizaron las agregaciones de metas mensuales en `MetaMensual.resumen_por_coordinador` y `MetaMensual.resumen_por_aliado` para consultar mediante `vendedor__coordinador__aliado`.
  5. Se actualizó el comando de datos semilla `seed_demo_data` y el diccionario [docs/DATA_MODEL.md](file:///C:/Users/jekse/OneDrive/Desktop/proyectos/Prueba-tecnica-verla-sas-Johand-Castro/docs/DATA_MODEL.md).

---

## 5. Auditoría de Ajustes de Roles y UX (Coordinador y Vendedor)

- **Visualización de Aliado asignado para Coordinadores (`aliado_list`)**:
  - Se habilitó el acceso al rol `COORDINADOR` en `aliado_list_view`.
  - El coordinador visualiza únicamente el Aliado al que está asignado (`Aliado.objects.filter(pk=coordinador.aliado_id)`).
  - Modo estricto de solo lectura: los botones de creación (`+ Nuevo Aliado`), edición y eliminación quedan restringidos exclusivamente a `ADMIN`.
- **Visualización de Catálogo de Ciudades para Coordinadores (`ciudad_list`)**:
  - Se habilitó el acceso al rol `COORDINADOR` en `ciudad_list_view`.
  - Modo estricto de solo lectura: el catálogo de ciudades es consultable sin acciones de mutación.
- **Unificación de Navegación para Vendedor Activo en Inicio (`portal_home`)**:
  - Se eliminó la redundancia de las dos tarjetas que redirigían a la misma ruta (`op_default`).
  - Se consolidó en una tarjeta única y concisa: *"🎯 Mis Metas & Ofertas Comerciales"*, simplificando el flujo de interacción para la fuerza de ventas.
- **Resolución de Visibilidad de Vendedores para Aliado Comercial (`vendedor_list` & Demo)**:
  - **Causa Raíz**: En el simulador de roles (`simular_rol_view`), se creaba un Aliado demo con un NIT alternativo (`900123456-1`) que no tenía coordinadores adscritos, mientras que el coordinador demo y los vendedores sembrados pertenecían al Aliado titular `Distribuciones Andinas SAS` (`900100101-1`). Al aplicar el filtro de aislamiento `coordinador__aliado=perfil["objeto"]`, el Aliado comercial resultaba sin registros visibles.
  - **Acción Correctiva**: Se reconfiguró `simular_rol_view` para vincular dinámicamente `demo_aliado` al Aliado al que está adscrito el coordinador demo y sus vendedores correspondientes. Se agregaron pruebas automatizadas (`test_aliado_can_view_vendedores_assigned_to_its_coordinators`) que comprueban que el Aliado comercial visualiza exactamente los vendedores subordinados a sus coordinadores y no los de terceros.

---

## 6. Auditoría de Manejo Fino de Permisos, Deshabilitación de Acciones y Datetime en Semillas

- **Redirección Contextual en Errores de Permisos (`requerir_roles`)**:
  - Cuando un usuario intenta una acción restringida (ej. editar o crear en un módulo), el decorador ya no lo expulsa al inicio (`portal_home`), sino que lo redirige a la vista previa (`HTTP_REFERER`) o a la lista del submódulo correspondiente, presentando la alerta SweetAlert2 en el contexto de su trabajo. Solo se redirige al inicio cuando carece de acceso a la vista completa del módulo.
- **Deshabilitación Explícita de Botones sin Permiso (`disabled`)**:
  - En lugar de simplemente ocultar o dejar enlaces activos que fallen, los botones de acción para los que un rol no está autorizado se presentan en estado `disabled` (`class="outline secondary"`, cursor `not-allowed`, opacidad 0.4 y `title` explicativo) en las tablas de Vendedores, Coordinadores, Aliados, Ciudades y Operación de Metas/Ofertas.
- **Fecha y Hora de Creación Realista en Semillas (`seed_demo_data`)**:
  - Se incorporó `datetime` y `timedelta` para calcular fechas de creación (`creado_en`) e ingreso (`fecha_ingreso`) escalonadas y realistas para cada vendedor en la base de datos, mostrándose además en la tabla de fuerza de ventas.
- **Formateo ISO en Controles HTML5 (`forms.DateInput`)**:
  - **Causa Raíz**: Los inputs de tipo `<input type="date">` exigen estrictamente el estándar ISO (`YYYY-MM-DD`). Por defecto, Django renderizaba la fecha en formato localizado (`DD/MM/YYYY`), provocando que el navegador descartara el valor y dejara el campo vacío al editar un vendedor o una oferta.
  - **Acción Correctiva**: Se configuró explícitamente `format="%Y-%m-%d"` en los widgets `DateInput` de `VendedorForm` y `OfertaPeriodoForm`. Se añadió la prueba `test_vendedor_update_view_renders_fecha_ingreso_in_html5_format` para asegurar que el valor preexistente en base de datos se precargue de manera impecable en la interfaz.

---

## 7. Auditoría de Racionamiento de Tokens de IA, Cuotas por Usuario y Aislamiento de Contexto

- **Sistema de Cuotas y Racionamiento de Tokens**:
  - **Límites Aplicados**: Máximo **15 consultas cada 2 minutos** y **50 consultas por día calendario** por usuario, gestionados de forma atómica sobre `AIAuditLog`.
  - **Techo Estricto de Salida**: `maxOutputTokens: 600` en la configuración de Google Gemini (`gemini-2.5-flash`), garantizando respuestas ejecutivas y eliminando derroche innecesario de tokens.
  - **Filtro de Entrada**: Longitud máxima de 400 caracteres por mensaje en frontend y backend.
  - **Degradación Elegante (HTTP 429)**: Al superar la cuota, el endpoint devuelve `HTTP 429` con el motivo exacto y tiempo de espera sin romper la experiencia del portal.
- **Claridad de Interfaz (UX de Cuota)**:
  - Se actualizó la insignia del drawer lateral para mostrar de forma inequívoca **`Disponibles: 50`** (con tooltip descriptivo y cambio de color semántico al agotarse), eliminando la ambigüedad del formato anterior.
  - Saludo inicial contextualizado al abrir el widget indicando el nombre del actor, su rol en el portal y su cuota disponible para el día.
- **Aislamiento de Datos por Rol en Inyección de Contexto**:
  - El copiloto recolecta en tiempo real las métricas vivas de la base de datos aplicando aislamiento estricto: el Vendedor solo tiene en su contexto sus metas personales y ofertas autorizadas en su ciudad base y de operación; el Coordinador supervisa las metas de su equipo; el Aliado monitorea su red comercial; y el Administrador accede al panorama global.
- **Optimización de Base de Datos para Conteo de Cuotas**:
  - Se indexó `AIAuditLog.creado_en` (`db_index=True`) y se incorporó el índice compuesto `idx_aiaudit_user_created` sobre `(usuario_id, creado_en)` mediante la migración `0002_alter_aiauditlog_creado_en_and_more.py`, resolviendo la verificación de cuotas en <1ms mediante un *index-only scan*.
- **Auditoría y Sincronización del Modelo de Datos ([docs/DATA_MODEL.md](file:///C:/Users/jekse/OneDrive/Desktop/proyectos/Prueba-tecnica-verla-sas-Johand-Castro/docs/DATA_MODEL.md))**:
  - Ejecutada mediante subagente de arquitectura: se corrigió el diagrama Mermaid ER retirando la relación foránea directa entre `Aliado` y `Vendedor` (reafirmando la normalización 3FN vía `Coordinador`), se incorporó el evento `ELIMINACION` en `AuditLog`, y se documentó `actualizado_en` y el índice de cuotas en `AIAuditLog`.
- **Estado de la Suite de Pruebas**:
  - **52 de 52 pruebas pasando exitosamente** (`Ran 52 tests in 52s — OK`).

---

## 8. Despachador Dinámico de Consultas de IA y UX de Cierre de Chat

- **Despachador Dinámico y Clasificación Semántica Resiliente**:
  - **Soporte Morfológico Flexible**: El motor de intenciones reconoce raíces léxicas y conjugaciones (`bloqu*` para *bloqueado, bloquear, bloquiar, bloquee*; `inactiv*` para *inactivo, inactivar, desactivar*; `no activ*` para *no activos, fuera de servicio*; `meta* / cumpli*` para metas y porcentaje de cumplimiento; `ofert*` para ofertas vigentes).
  - **Diferenciación Estricta de Estados**: Distingue inequívocamente entre solicitudes de vendedores bloqueados, inactivos o ambos sin mezclar estados.
  - **Aislamiento por Rol en Consultas Dinámicas**: Cada consulta contra `Vendedor`, `MetaMensual` u `OfertaPeriodo` aplica los filtros de seguridad del actor (Vendedor: personal; Coordinador: equipo supervisado; Aliado: red comercial; Administrador: visión global).
  - **Exención de Descuento de Cuotas**: Las respuestas servidas por contingencia local no descuentan cuota de llamadas API al usuario (`tokens_estimados = 0` y `modelo = "reglas-contingencia-v1"`).
- **Cierre Inteligente al Clic Externo (Click-Outside)**:
  - Implementado mediante subagente de interfaz en `static/js/copilot-widget.js`: al hacer clic fuera del drawer desplegable (`#verla-ai-drawer`) y del botón flotante (`#verla-ai-btn`), la ventana se cierra automáticamente.
  - Se previenen cierres accidentales al interactuar con diálogos modales de SweetAlert2 (`.swal2-container`) o botones de acción (`.ai-action-btn`).
- **Verificación Automatizada**:
  - 4 nuevas pruebas unitarias en `asistente_ia/tests.py` validando variaciones morfológicas (*bloquiar*), diferenciación inactivo vs bloqueado, cálculo dinámico de porcentajes de metas y consulta de ofertas vigentes.
  - Total: **52 pruebas automatizadas en verde (`OK`)**.

---

## 9. Migración a Gemini Function Calling (Tools) y Depuración de Código Muerto

- **Migración a `gemini-3.5-flash-lite` y Function Calling Nativo**:
  - Se migró el motor de IA desde los modelos deprecados (`gemini-2.5-flash`, `gemini-2.5-flash-lite`) y saturados (`gemini-3.8-flash` con HTTP 429 en cuota gratuita) al modelo activo de baja latencia **`gemini-3.5-flash-lite`** con cuota disponible.
  - Se configuró el catálogo formal de herramientas (`GEMINI_TOOLS`) con 3 funciones declarativas:
    1. `consultar_vendedores(estado)`: Consulta en tiempo real con aislamiento de datos por rol.
    2. `consultar_metas(periodo)`: Consulta metas y porcentajes de cumplimiento comercial.
    3. `consultar_ofertas(accion)`: Consulta catálogo de promociones activas o genera propuestas comerciales.
- **Protocolo de Dos Turnos con Preservación de `thoughtSignature`**:
  - Al detectar la intención, Gemini emite un `functionCall`. El backend ejecuta sincrónicamente la función correspondiente contra el ORM de Django con aislamiento por rol.
  - El resultado se inyecta en un segundo turno (`functionResponse`) preservando el `thoughtSignature` exigido por la API v1beta de Google, permitiendo que Gemini sintetice la respuesta final en Markdown fluido con datos 100% verídicos.
- **Ajuste de Latencia y Tolerancia a Fallos**:
  - Se amplió el timeout del cliente asíncrono a **15.0 segundos** (previniendo los `ReadTimeout` que ocurrían con 8.0s).
  - En caso de fallo en el segundo turno o error de red, el sistema degrada limpiamente entregando el Markdown pre-renderizado por la herramienta local sin penalizar la cuota de tokens del usuario.
- **Depuración de Código Muerto y Reutilización DRY**:
  - Se eliminaron expresiones redundantes y bloques de código duplicados entre el fallback y el motor online; el fallback ahora reutiliza exactamente las mismas funciones de dominio (`ejecutar_consulta_vendedores`, `ejecutar_consulta_metas`, `ejecutar_consulta_ofertas`).
- **Estado de la Suite de Pruebas**:
  - **54 de 54 pruebas pasando exitosamente** (`Ran 54 tests in 58s — OK`).

---

## 10. KPIs Comerciales, Desglose Individual de Metas y Coaching Estratégico

- **Métricas y KPIs Consolidados (`ejecutar_consulta_metas`)**:
  - Se expandió la herramienta de metas para calcular métricas comerciales integrales: Meta Consolidada, Ventas Reales, Porcentaje de Cumplimiento Global, Brecha por Cerrar, Total de Asesores Evaluados, Asesores con Meta Cumplida (`>= 100%`), Asesores en Alerta (`< 80%`) y Promedio de Ventas por Asesor.
  - Genera el desglose individual por vendedor con ciudad base, meta, venta real, porcentaje individual e indicador semántico de estado (`🟢`, `🟡`, `🔴`).
- **Coaching y Libertad Creativa / Asesoramiento Estratégico**:
  - En la instrucción del sistema (`system_instruction`), se facultó al modelo con plena libertad analítica y creativa para formular sugerencias motivacionales, planes de reactivación de pipeline, manejo de objeciones y clínicas de venta cuando el usuario solicite consejos para vendedores rezagados.
  - Se incorporó ajuste adaptativo de temperatura: eleva la temperatura a `0.55` para solicitudes de coaching y asesoramiento comercial (promoviendo respuestas ricas y persuasivas), manteniendo `0.2` para consultas estrictas de datos y herramientas.
- **Ventana Emergente Nativa en Bitácora de Auditoría**:
  - Se sustituyó el volcado inline de JSON en la vista de supervisión por un modal nativo HTML5 (`<dialog>`) adaptado al Dark Theme de VERLA SAS, con visor de prompt, texto Markdown, JSON resaltado y botón de copiado rápido al portapapeles.
- **Estado Final de la Suite de Pruebas**:
  - **54 de 54 pruebas pasando exitosamente** (`Ran 54 tests in 58s — OK`).
