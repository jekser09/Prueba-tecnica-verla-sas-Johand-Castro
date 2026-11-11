from django.shortcuts import render
from django.http import HttpRequest,HttpResponse,JsonResponse

# Create your views here.
def default(request: HttpRequest)->JsonResponse:
    return JsonResponse({'response':"modulo 'operacion' conectado"})