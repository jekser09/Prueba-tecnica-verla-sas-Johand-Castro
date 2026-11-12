from django.urls import path

from asistente_ia.views import (
    api_consultar_asistente_view,
    api_estado_asistente_view,
    api_veredicto_humano_view,
    asistente_auditoria_list_view,
)

urlpatterns = [
    path("", asistente_auditoria_list_view, name="asis_default"),
    path("api/estado/", api_estado_asistente_view, name="asistente_api_estado"),
    path("api/consultar/", api_consultar_asistente_view, name="asistente_api_consultar"),
    path("api/veredicto/", api_veredicto_humano_view, name="asistente_api_veredicto"),
]
