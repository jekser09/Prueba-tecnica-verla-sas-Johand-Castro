from django.urls import path

from operacion.views import (
    meta_mensual_create_view,
    meta_mensual_update_view,
    oferta_periodo_create_view,
    oferta_periodo_update_view,
    operacion_dashboard_view,
)

urlpatterns = [
    path("", operacion_dashboard_view, name="op_default"),
    # Metas Mensuales
    path("metas/nueva/", meta_mensual_create_view, name="meta_create"),
    path("metas/<int:pk>/editar/", meta_mensual_update_view, name="meta_update"),
    # Ofertas del Periodo
    path("ofertas/nueva/", oferta_periodo_create_view, name="oferta_create"),
    path("ofertas/<int:pk>/editar/", oferta_periodo_update_view, name="oferta_update"),
]
