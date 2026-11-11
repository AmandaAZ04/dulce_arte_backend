import uuid
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from rest_framework.exceptions import PermissionDenied, ValidationError
from . import services
from .models import PagoWebpay, Pedido


def webpay_transaction():
    # Mantener explícitamente el ambiente de integración: nunca cobra dinero real.
    from transbank.common.integration_api_keys import IntegrationApiKeys
    from transbank.common.integration_commerce_codes import IntegrationCommerceCodes
    from transbank.common.integration_type import IntegrationType
    from transbank.common.options import WebpayOptions
    from transbank.webpay.webpay_plus.transaction import Transaction
    options=WebpayOptions(IntegrationCommerceCodes.WEBPAY_PLUS,IntegrationApiKeys.WEBPAY,IntegrationType.TEST,timeout=20)
    return Transaction(options)


@transaction.atomic
def iniciar_pago(usuario,datos,return_url):
    anterior=PagoWebpay.objects.select_for_update().filter(solicitud=datos['solicitud']).first()
    if anterior:
        if anterior.cliente_id!=usuario.pk: raise PermissionDenied()
        if anterior.estado==PagoWebpay.Estado.INICIADO and anterior.token_ws and anterior.url_webpay:
            return {'pago_id':anterior.pk,'token':anterior.token_ws,'url':anterior.url_webpay}
        raise ValidationError('Este intento de compra ya terminó. Actualiza el carrito para iniciar otro.')

    pedidos=[]
    total=Decimal('0')
    for item in datos['items']:
        pedido=services.crear_pedido(usuario,{
            'receta':item['receta'],
            'cantidad':item['cantidad'],
            'retiro':datos['retiro'],
            'telefono':datos['telefono'],
            'diseno':'',
            'preferencias':'',
            'solicitud':uuid.uuid4(),
        })
        pedido.estado=Pedido.Estado.PAGO_PENDIENTE
        pedido.save(update_fields=['estado','actualizado'])
        services.registrar(pedido,usuario,'Esperando confirmación del pago de prueba en Webpay')
        pedidos.append(pedido)
        total+=pedido.total
    if total>Decimal('999999999'):
        raise ValidationError('El total supera el máximo permitido por el ambiente de prueba de Webpay.')

    pago=PagoWebpay.objects.create(
        cliente=usuario,
        solicitud=datos['solicitud'],
        buy_order='DA'+uuid.uuid4().hex[:24],
        session_id='dulce-'+uuid.uuid4().hex[:16],
        monto=total,
    )
    pago.pedidos.set(pedidos)
    respuesta=webpay_transaction().create(pago.buy_order,pago.session_id,float(total),return_url)
    pago.token_ws=respuesta['token']
    pago.url_webpay=respuesta['url']
    pago.save(update_fields=['token_ws','url_webpay','actualizado'])
    return {'pago_id':pago.pk,'token':pago.token_ws,'url':pago.url_webpay}


@transaction.atomic
def iniciar_pago_pedido(usuario,pedido_id,return_url):
    pedido=Pedido.objects.select_for_update().filter(pk=pedido_id,cliente=usuario).first()
    if not pedido: raise PermissionDenied()
    previo=pedido.pagos_webpay.select_for_update().filter(estado=PagoWebpay.Estado.INICIADO).order_by('-creado').first()
    if previo and previo.token_ws and previo.url_webpay:
        return {'pago_id':previo.pk,'token':previo.token_ws,'url':previo.url_webpay}
    if pedido.estado!=Pedido.Estado.RECIBIDO or pedido.pagado or pedido.consumido:
        raise ValidationError('Este pedido todavía no se puede pagar en Webpay.')
    pago=PagoWebpay.objects.create(
        cliente=usuario,
        buy_order='DA'+uuid.uuid4().hex[:24],
        session_id='dulce-'+uuid.uuid4().hex[:16],
        monto=pedido.total,
    )
    pago.pedidos.add(pedido)
    pedido.estado=Pedido.Estado.PAGO_PENDIENTE
    pedido.save(update_fields=['estado','actualizado'])
    services.registrar(pedido,usuario,'Esperando confirmación del pago de prueba en Webpay')
    respuesta=webpay_transaction().create(pago.buy_order,pago.session_id,float(pago.monto),return_url)
    pago.token_ws=respuesta['token']
    pago.url_webpay=respuesta['url']
    pago.save(update_fields=['token_ws','url_webpay','actualizado'])
    return {'pago_id':pago.pk,'token':pago.token_ws,'url':pago.url_webpay}


@transaction.atomic
def cancelar_pago(pago,estado,detalle,codigo_respuesta=None):
    pago=PagoWebpay.objects.select_for_update().get(pk=pago.pk)
    if pago.estado!=PagoWebpay.Estado.INICIADO:
        return pago
    pedidos=list(pago.pedidos.select_for_update().order_by('pk'))
    for pedido in pedidos:
        if pedido.estado!=Pedido.Estado.PAGO_PENDIENTE:
            continue
        materiales,insumos=services.bloquear_materiales(pedido)
        for material in materiales:
            insumo=insumos[material.insumo_id]
            insumo.reservado=max(Decimal('0'),insumo.reservado-material.cantidad)
            insumo.save(update_fields=['reservado'])
        pedido.estado=Pedido.Estado.CANCELADO
        pedido.save(update_fields=['estado','actualizado'])
        services.registrar(pedido,None,detalle)
    pago.estado=estado
    pago.codigo_respuesta=codigo_respuesta
    pago.save(update_fields=['estado','codigo_respuesta','actualizado'])
    return pago


@transaction.atomic
def confirmar_pago(token):
    pago=PagoWebpay.objects.select_for_update().filter(token_ws=token).first()
    if not pago:
        return False
    if pago.estado==PagoWebpay.Estado.PAGADO:
        return True
    if pago.estado!=PagoWebpay.Estado.INICIADO:
        return False
    respuesta=webpay_transaction().commit(token)
    response_code=respuesta.get('response_code')
    try:
        monto=Decimal(str(respuesta.get('amount')))
    except Exception:
        monto=Decimal('-1')
    aprobado=(
        respuesta.get('status')=='AUTHORIZED'
        and response_code==0
        and respuesta.get('buy_order')==pago.buy_order
        and respuesta.get('session_id')==pago.session_id
        and monto==pago.monto
    )
    if not aprobado:
        cancelar_pago(pago,PagoWebpay.Estado.RECHAZADO,'Pago de prueba rechazado en Webpay',response_code)
        return False
    for pedido in pago.pedidos.select_for_update().order_by('pk'):
        if pedido.estado!=Pedido.Estado.PAGO_PENDIENTE:
            continue
        pedido.pagado=True
        pedido.estado=Pedido.Estado.RECIBIDO
        pedido.save(update_fields=['pagado','estado','actualizado'])
        services.registrar(pedido,None,'Pago de prueba aprobado en Webpay; pedido confirmado')
    pago.estado=PagoWebpay.Estado.PAGADO
    pago.codigo_respuesta=response_code
    pago.save(update_fields=['estado','codigo_respuesta','actualizado'])
    return True


def abortar_pago(buy_order):
    pago=PagoWebpay.objects.filter(buy_order=buy_order).first()
    if pago:
        cancelar_pago(pago,PagoWebpay.Estado.ANULADO,'El cliente canceló el pago en Webpay')
        return True
    return False


def verificar_pago(pago_id,usuario):
    pago=PagoWebpay.objects.filter(pk=pago_id).first()
    if not pago or pago.cliente_id!=usuario.pk:
        raise PermissionDenied()
    if pago.estado!=PagoWebpay.Estado.INICIADO:
        return pago.estado
    estado=webpay_transaction().status(pago.token_ws)
    if estado.get('buy_order')!=pago.buy_order or Decimal(str(estado.get('amount')))!=pago.monto:
        raise ValidationError('Los datos informados por Webpay no coinciden con este pedido.')
    if estado.get('status')=='AUTHORIZED':
        confirmar_pago(pago.token_ws)
    elif estado.get('status') in ['FAILED','REVERSED','NULLIFIED']:
        cancelar_pago(pago,PagoWebpay.Estado.RECHAZADO,'Webpay informó que el pago no fue aprobado',estado.get('response_code'))
    return PagoWebpay.objects.get(pk=pago_id).estado
