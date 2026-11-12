"""
URL configuration for aliados project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from red_comercial.views_core import home_view, simular_rol_view

urlpatterns = [
    path('', home_view, name='portal_home'),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('simular-rol/', simular_rol_view, name='simular_rol'),
    path('admin/', admin.site.urls),
    path("comercial/", include('red_comercial.urls')),
    path("operacion/", include('operacion.urls')),
    path("asistente/", include('asistente_ia.urls')),
]
