from django.core.management.base import BaseCommand
from api.models import Aviso
from api.mail import enviar_aviso
class Command(BaseCommand):
    help='Reintenta los avisos que el servidor de correo no pudo aceptar.'
    def handle(self,*args,**options):
        ids=list(Aviso.objects.filter(enviado=False).values_list('id',flat=True))
        for pk in ids: enviar_aviso(pk)
        self.stdout.write(f'Avisos revisados: {len(ids)}')
