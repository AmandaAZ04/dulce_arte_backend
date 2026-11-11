from django.urls import path,include
from rest_framework.routers import DefaultRouter
from . import views,payment_views
router=DefaultRouter()
router.register('recetas',views.RecetaViewSet,basename='receta')
router.register('insumos',views.InsumoViewSet)
router.register('pedidos',views.PedidoViewSet,basename='pedido')
router.register('movimientos',views.MovimientoViewSet)
urlpatterns=[path('cuenta/',views.cuenta),path('seguimiento/<uuid:token>/',views.seguimiento),path('pagos/disponibilidad/',payment_views.disponibilidad),path('pagos/iniciar/',payment_views.iniciar),path('pagos/pedido/<int:pedido_id>/iniciar/',payment_views.iniciar_pedido),path('pagos/<int:pago_id>/verificar/',payment_views.verificar),path('pagos/retorno/',payment_views.retorno,name='webpay-return'),path('',include(router.urls))]
