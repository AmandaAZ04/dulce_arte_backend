from datetime import time, timedelta

from django.db import connection
from django.db.models import F, Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import Pedido


APERTURA = time(8)
CIERRE = time(19)
MINIMO_PREPARACION = 180
EN_COCINA = ('PAGO_PENDIENTE', 'RECIBIDO', 'PREPARACION', 'HORNEADO', 'CALIDAD')


def bloquear_agenda():
    if connection.vendor == 'postgresql':
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(%s)', [3040819])


def primer_retiro(items, excluir=None, margen=0):
    pendientes = Pedido.objects.filter(estado__in=EN_COCINA)
    if excluir is not None:
        pendientes = pendientes.exclude(pk=excluir)
    minutos_pendientes = pendientes.aggregate(total=Sum(F('receta__minutos') * F('cantidad')))['total'] or 0
    minutos_nuevos = sum(item['receta'].minutos * item['cantidad'] for item in items)
    restante = timedelta(minutes=max(MINIMO_PREPARACION, minutos_nuevos) + minutos_pendientes + margen)
    actual = timezone.localtime()
    if actual.second or actual.microsecond:
        actual = actual.replace(second=0, microsecond=0) + timedelta(minutes=1)
    while True:
        apertura = actual.replace(hour=8, minute=0)
        cierre = actual.replace(hour=19, minute=0)
        if actual.weekday() != 6:
            inicio = max(apertura, actual)
            if inicio < cierre:
                if restante <= cierre - inicio:
                    return inicio + restante
                restante -= cierre - inicio
        actual = apertura + timedelta(days=1)


def validar_horario(retiro):
    local = timezone.localtime(retiro)
    if local.weekday() == 6 or not APERTURA <= local.time() <= CIERRE:
        raise ValidationError('Los retiros son de lunes a sábado, de 08:00 a 19:00. El domingo el local está cerrado.')
    if retiro > timezone.now() + timedelta(days=90):
        raise ValidationError('Elige una fecha dentro de los próximos 90 días.')
    return retiro


def validar_capacidad(retiro, items, excluir=None):
    validar_horario(retiro)
    minimo = primer_retiro(items, excluir)
    if retiro < minimo:
        raise ValidationError({'retiro': f'La primera hora disponible es {minimo:%d/%m/%Y a las %H:%M} (hora de Chile).'})
