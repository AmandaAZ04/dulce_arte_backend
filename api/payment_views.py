import logging

from django.conf import settings
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import APIException

from .payments import abortar_pago, confirmar_pago, iniciar_pago, iniciar_pago_pedido, verificar_pago
from .serializer import CheckoutSerializer

logger=logging.getLogger(__name__)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def iniciar(request):
    serializer=CheckoutSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    return_url=settings.PUBLIC_BASE_URL+reverse('webpay-return')
    try:
        resultado=iniciar_pago(request.user,serializer.validated_data,return_url)
    except APIException:
        raise
    except Exception as exc:
        logger.exception('No se pudo iniciar el pago Webpay')
        return Response({'detail':'No pudimos abrir Webpay. El carrito sigue guardado; inténtalo otra vez.'},status=status.HTTP_502_BAD_GATEWAY)
    return Response(resultado,status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def iniciar_pedido(request,pedido_id):
    try:
        resultado=iniciar_pago_pedido(request.user,pedido_id,settings.PUBLIC_BASE_URL+reverse('webpay-return'))
    except APIException:
        raise
    except Exception:
        logger.exception('No se pudo iniciar el pago del pedido')
        return Response({'detail':'No pudimos abrir Webpay. Inténtalo otra vez desde Mis compras.'},status=status.HTTP_502_BAD_GATEWAY)
    return Response(resultado,status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def verificar(request,pago_id):
    try:
        estado=verificar_pago(pago_id,request.user)
    except APIException:
        raise
    except Exception:
        logger.exception('No se pudo consultar el estado del pago Webpay')
        return Response({'detail':'No pudimos consultar Webpay. Inténtalo nuevamente.'},status=status.HTTP_502_BAD_GATEWAY)
    return Response({'estado':estado,'pagado':estado=='PAGADO'})


@csrf_exempt
@require_http_methods(['GET','POST'])
def retorno(request):
    token=request.POST.get('token_ws') or request.GET.get('token_ws')
    if token:
        try:
            ok=confirmar_pago(token)
        except Exception:
            logger.exception('Webpay no pudo confirmar la transacción')
            return HttpResponseRedirect('/mis-pedidos/?pago=pendiente')
        return HttpResponseRedirect('/mis-pedidos/?pago=ok' if ok else '/mis-pedidos/?pago=rechazado')
    buy_order=request.POST.get('TBK_ORDEN_COMPRA') or request.GET.get('TBK_ORDEN_COMPRA')
    canceled=request.POST.get('TBK_TOKEN') or request.GET.get('TBK_TOKEN')
    if canceled and buy_order:
        try:
            abortar_pago(buy_order)
        except Exception:
            logger.exception('No se pudo liberar la reserva de una compra cancelada')
        return HttpResponseRedirect('/mis-pedidos/?pago=cancelado')
    return HttpResponseRedirect('/mis-pedidos/?pago=sin-respuesta')
