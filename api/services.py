from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError, PermissionDenied
from .models import Insumo, Receta, Pedido, MaterialPedido, Movimiento, Historial, Aviso

def registrar(pedido, usuario, detalle):
    Historial.objects.create(pedido=pedido,usuario=usuario,estado=pedido.estado,detalle=detalle)

def avisar(pedido, evento):
    aviso, _ = Aviso.objects.get_or_create(pedido=pedido,evento=evento)
    # Un fallo SMTP nunca deshace una reserva; el aviso queda pendiente para reintento.
    from .mail import enviar_aviso
    transaction.on_commit(lambda: enviar_aviso(aviso.pk))

def bloquear_materiales(pedido):
    materiales = list(pedido.materiales.select_related('insumo').order_by('insumo_id'))
    insumos = {i.pk:i for i in Insumo.objects.select_for_update().filter(pk__in=[m.insumo_id for m in materiales]).order_by('pk')}
    return materiales, insumos

def reservar(pedido):
    materiales, insumos = bloquear_materiales(pedido)
    if not materiales: raise ValidationError('La receta no tiene ingredientes definidos.')
    faltantes = [f'{insumos[m.insumo_id].nombre}: faltan {m.cantidad-insumos[m.insumo_id].disponible} {insumos[m.insumo_id].unidad}' for m in materiales if insumos[m.insumo_id].disponible < m.cantidad]
    if faltantes: raise ValidationError({'inventario':faltantes})
    for m in materiales:
        i = insumos[m.insumo_id]
        i.reservado += m.cantidad
        i.save(update_fields=['reservado'])

@transaction.atomic
def crear_pedido(usuario, datos):
    # La clave de solicitud evita duplicados por doble clic o reintento de red.
    anterior = Pedido.objects.filter(solicitud=datos['solicitud']).first()
    if anterior:
        if anterior.cliente_id != usuario.pk: raise PermissionDenied()
        return anterior
    receta = Receta.objects.select_for_update().get(pk=datos.pop('receta').pk)
    if not receta.activa: raise ValidationError('Este producto no está disponible.')
    personalizado = bool(datos.get('diseno') or datos.get('preferencias'))
    p = Pedido.objects.create(cliente=usuario,receta=receta,producto=receta.nombre,total=receta.precio*datos['cantidad'],estado='COTIZACION' if personalizado else 'RECIBIDO',**datos)
    for item in receta.ingredientes.all():
        MaterialPedido.objects.create(pedido=p,insumo=item.insumo,cantidad=item.cantidad*p.cantidad)
    if not personalizado: reservar(p)
    registrar(p,usuario,'Solicitud personalizada recibida' if personalizado else 'Pedido confirmado; ingredientes reservados')
    avisar(p,'creado')
    return p

@transaction.atomic
def cotizar(pedido_id, usuario, total, nota, materiales):
    p=Pedido.objects.select_for_update().get(pk=pedido_id)
    if p.estado not in ['COTIZACION','COTIZADO']: raise ValidationError('Solo puedes cotizar solicitudes pendientes.')
    if not materiales: raise ValidationError('Define los ingredientes de este pedido.')
    p.materiales.all().delete()
    for m in materiales:
        MaterialPedido.objects.create(pedido=p,**m)
    p.total=total
    p.nota_equipo=nota
    p.estado='COTIZADO'
    p.save()
    registrar(p,usuario,'Cotización preparada para aprobación del cliente')
    avisar(p, f'cotizacion-{p.historial.count()}')
    return p

@transaction.atomic
def aceptar(pedido_id, usuario):
    p=Pedido.objects.select_for_update().get(pk=pedido_id)
    if p.cliente_id != usuario.pk: raise PermissionDenied()
    if p.estado=='RECIBIDO': return p
    if p.estado!='COTIZADO': raise ValidationError('La cotización aún no está lista para aceptar.')
    if p.retiro <= timezone.now(): raise ValidationError('La fecha de retiro ya pasó; solicita una nueva cotización.')
    reservar(p)
    p.estado='RECIBIDO'
    p.save()
    registrar(p,usuario,'Cotización aceptada; ingredientes reservados')
    avisar(p,'aceptado')
    return p

@transaction.atomic
def cambiar_estado(pedido_id, usuario, nuevo):
    p=Pedido.objects.select_for_update().get(pk=pedido_id)
    if nuevo==p.estado: return p
    flujo={'RECIBIDO':'PREPARACION','PREPARACION':'HORNEADO','HORNEADO':'CALIDAD','CALIDAD':'LISTO'}
    if nuevo=='CANCELADO':
        permitidos=['COTIZACION','COTIZADO','RECIBIDO']
        if usuario.is_staff: permitidos+=['PREPARACION','HORNEADO','CALIDAD','LISTO']
        if p.estado not in permitidos: raise ValidationError('Este pedido ya no se puede cancelar.')
        if not usuario.is_staff and p.cliente_id != usuario.pk: raise PermissionDenied()
        if p.pagado: raise ValidationError('Un pedido pagado necesita resolver el reembolso antes de cancelarse.')
        if p.estado=='RECIBIDO':
            mats, insumos=bloquear_materiales(p)
            for m in mats:
                i=insumos[m.insumo_id]; i.reservado-=m.cantidad; i.save(update_fields=['reservado'])
    else:
        if not usuario.is_staff: raise PermissionDenied()
        if flujo.get(p.estado)!=nuevo: raise ValidationError('El pedido debe seguir el orden de preparación.')
        if nuevo=='PREPARACION':
            mats, insumos=bloquear_materiales(p)
            for m in mats:
                i=insumos[m.insumo_id]
                if i.stock<m.cantidad or i.reservado<m.cantidad: raise ValidationError('Inventario inconsistente. Revisa las reservas.')
                i.stock-=m.cantidad; i.reservado-=m.cantidad; i.save(update_fields=['stock','reservado'])
                Movimiento.objects.create(insumo=i,pedido=p,cantidad=-m.cantidad,motivo='Consumo de receta',usuario=usuario)
            p.consumido=True
    p.estado=nuevo; p.save()
    registrar(p,usuario,'Cancelado; los ingredientes ya utilizados no vuelven a bodega' if nuevo=='CANCELADO' and p.consumido else p.get_estado_display())
    if nuevo in ['LISTO','CANCELADO']: avisar(p,nuevo.lower())
    return p

@transaction.atomic
def ajustar(insumo_id, usuario, cantidad, motivo):
    i=Insumo.objects.select_for_update().get(pk=insumo_id)
    if i.stock+cantidad < i.reservado: raise ValidationError('No puedes dejar menos stock que el ya reservado.')
    i.stock+=cantidad; i.save(update_fields=['stock'])
    Movimiento.objects.create(insumo=i,cantidad=cantidad,motivo=motivo,usuario=usuario)
    return i

@transaction.atomic
def retirar(token, usuario, pagado):
    if not usuario.is_staff: raise PermissionDenied()
    try: p=Pedido.objects.select_for_update().get(token=token)
    except Pedido.DoesNotExist: raise ValidationError('Código de retiro no encontrado.')
    if p.estado=='RETIRADO': return p
    if p.estado!='LISTO': raise ValidationError('El pedido todavía no está listo para retirar.')
    if not (pagado or p.pagado): raise ValidationError('Confirma que el pago fue recibido en el local.')
    p.pagado=True; p.estado='RETIRADO'; p.save()
    registrar(p,usuario,'Pago recibido y retiro confirmado en mesón')
    avisar(p,'retirado')
    return p
