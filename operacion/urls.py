from .views import default
from django.urls import path

urlpatterns = [
    path("",default,name="op_default"),
]