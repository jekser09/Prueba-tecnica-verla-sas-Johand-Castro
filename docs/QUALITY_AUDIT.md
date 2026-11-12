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
| **Renderizado de Imágenes de Oferta** | **Aprobado** | Rutas `/media/ofertas/YYYY/MM/...` enlazadas con `{{ o.imagen.url }}` y verificadas con `Router.png`. |
| **Pico CSS y Purga de Estilos Inline** | **Aprobado** | Cero etiquetas `<style>` dentro de templates. Clases utilitarias y tokens unificados en `static/css/verla.css`. |
| **Formateo de Moneda (COP)** | **Aprobado** | Módulo `static/js/formatters.js` aplicando `Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP' })`. |
| **Notificaciones y Modales (SweetAlert2)** | **Aprobado** | Reemplazo total de alertas nativas del navegador por `window.VerlaAlert` con tema oscuro VERLA. Confirmaciones en eliminaciones y cancelaciones. |
| **Eliminación y Cancelación (Admin)** | **Aprobado** | Vistas de eliminación segura con captura de `ProtectedError` para Ciudades, Aliados, Coordinadores y cancelación/eliminación de Ofertas. |
| **Normalización Relacional (3FN) Vendedor-Aliado** | **Aprobado** | Remoción de la FK redundante `aliado` en `Vendedor`. El Aliado se deriva de forma unívoca a través de `coordinador.aliado`. Formulario simplificado (solo selecciona Coordinador) y migración `0003_remove_vendedor_aliado` aplicada. |
| **Suite de Pruebas Automatizadas** | **Aprobado** | **41 de 41 pruebas pasando** (`Ran 41 tests in 18.716s — OK`). |
| **Sincronización de Base de Datos** | **Aprobado** | `makemigrations --check --dry-run` retorna `No changes detected`. |

---

## 3. Estado de la Suite de Pruebas

```text
Ran 41 tests in 18.716s

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
