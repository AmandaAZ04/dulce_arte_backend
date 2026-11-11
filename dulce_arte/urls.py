from django.contrib import admin
from django.urls import path,include,re_path
from django.views.generic import RedirectView
from api import web_views as web
urlpatterns=[path('admin/',admin.site.urls),path('api/',include('api.urls')),path('',web.inicio,name='inicio'),path('equipo/',web.equipo),path('cuenta/',web.cuenta),path('mis-pedidos/',web.mis_pedidos),path('seguimiento/<uuid:token>/',web.seguimiento),re_path(r'^(?!api/|admin/|static/).+$',RedirectView.as_view(url='/',permanent=False),name='frontend-fallback')]
