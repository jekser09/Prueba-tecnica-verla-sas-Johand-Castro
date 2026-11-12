from django.urls import path

from red_comercial.views import (
    aliado_create_view,
    aliado_delete_view,
    aliado_list_view,
    aliado_update_view,
    audit_log_list_view,
    ciudad_create_view,
    ciudad_delete_view,
    ciudad_list_view,
    ciudad_update_view,
    coordinador_create_view,
    coordinador_delete_view,
    coordinador_list_view,
    coordinador_update_view,
    red_comercial_dashboard_view,
    vendedor_create_view,
    vendedor_delete_view,
    vendedor_list_view,
    vendedor_update_view,
)

urlpatterns = [
    path("", red_comercial_dashboard_view, name="com_default"),
    # Ciudades
    path("ciudades/", ciudad_list_view, name="ciudad_list"),
    path("ciudades/nueva/", ciudad_create_view, name="ciudad_create"),
    path("ciudades/<int:pk>/editar/", ciudad_update_view, name="ciudad_update"),
    path("ciudades/<int:pk>/eliminar/", ciudad_delete_view, name="ciudad_delete"),
    # Aliados
    path("aliados/", aliado_list_view, name="aliado_list"),
    path("aliados/nuevo/", aliado_create_view, name="aliado_create"),
    path("aliados/<int:pk>/editar/", aliado_update_view, name="aliado_update"),
    path("aliados/<int:pk>/eliminar/", aliado_delete_view, name="aliado_delete"),
    # Coordinadores
    path("coordinadores/", coordinador_list_view, name="coordinador_list"),
    path("coordinadores/nuevo/", coordinador_create_view, name="coordinador_create"),
    path("coordinadores/<int:pk>/editar/", coordinador_update_view, name="coordinador_update"),
    path("coordinadores/<int:pk>/eliminar/", coordinador_delete_view, name="coordinador_delete"),
    # Vendedores
    path("vendedores/", vendedor_list_view, name="vendedor_list"),
    path("vendedores/nuevo/", vendedor_create_view, name="vendedor_create"),
    path("vendedores/<int:pk>/editar/", vendedor_update_view, name="vendedor_update"),
    path("vendedores/<int:pk>/eliminar/", vendedor_delete_view, name="vendedor_delete"),
    # Auditoría
    path("auditoria/", audit_log_list_view, name="audit_log_list"),
]
