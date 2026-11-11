from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from api.mail_backend import iniciar_autorizacion, guardar_autorizacion


class Command(BaseCommand):
    help = "Autoriza el buzón Hotmail para enviar correo mediante Microsoft Graph."

    def handle(self, *args, **options):
        if not settings.MS_GRAPH_CLIENT_ID:
            raise CommandError("Configura MS_GRAPH_CLIENT_ID antes de autorizar el buzón.")
        try:
            app, cache, flow = iniciar_autorizacion()
        except Exception as exc:
            raise CommandError(str(exc)) from None

        self.stdout.write(self.style.WARNING(
            "Abre en tu navegador la dirección que aparece abajo, inicia sesión con el Hotmail de Dulce Arte y aprueba Mail.Send."
        ))
        self.stdout.write(flow["message"])
        self.stdout.write(self.style.WARNING("No compartas el código de un solo uso ni una captura de esta pantalla."))
        try:
            guardar_autorizacion(app, cache, flow)
        except Exception as exc:
            raise CommandError(str(exc)) from None
        self.stdout.write(self.style.SUCCESS("Buzón autorizado. La sesión OAuth quedó guardada con permisos privados."))
