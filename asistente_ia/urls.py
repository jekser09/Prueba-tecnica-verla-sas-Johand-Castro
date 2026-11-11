from .views import default
from django.urls import path

urlpatterns = [
    path("",default,name="asis_default"),
]