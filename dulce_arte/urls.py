from django.contrib import admin
from django.urls import path,include
from api import web_views as web
urlpatterns=[path('admin/',admin.site.urls),path('api/',include('api.urls')),path('',web.inicio,name='inicio'),path('equipo/',web.equipo),path('cuenta/',web.cuenta),path('mis-pedidos/',web.mis_pedidos),path('seguimiento/<uuid:token>/',web.seguimiento)]
