from django.urls import path,include
from rest_framework.routers import DefaultRouter
from . import views
router=DefaultRouter()
router.register('recetas',views.RecetaViewSet,basename='receta')
router.register('insumos',views.InsumoViewSet)
router.register('pedidos',views.PedidoViewSet,basename='pedido')
router.register('movimientos',views.MovimientoViewSet)
urlpatterns=[path('cuenta/',views.cuenta),path('seguimiento/<uuid:token>/',views.seguimiento),path('correos/',views.correos),path('',include(router.urls))]
