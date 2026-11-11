import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import msal
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail.backends.base import BaseEmailBackend


GRAPH_SEND_URL = "https://graph.microsoft.com/v1.0/me/sendMail"
GRAPH_SCOPES = ["Mail.Send"]


def _token_cache():
    cache = msal.SerializableTokenCache()
    path = Path(settings.MS_GRAPH_TOKEN_CACHE)
    if path.is_file():
        try:
            cache.deserialize(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise ImproperlyConfigured("No se pudo leer el inicio de sesión de Microsoft. Ejecuta autenticar_correo nuevamente.")
    return cache


def _save_token_cache(cache):
    if not cache.has_state_changed:
        return
    path = Path(settings.MS_GRAPH_TOKEN_CACHE)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as token_file:
        token_file.write(cache.serialize())
    os.chmod(path, 0o600)


def _msal_app(cache):
    client_id = settings.MS_GRAPH_CLIENT_ID
    if not client_id:
        raise ImproperlyConfigured("Falta MS_GRAPH_CLIENT_ID en la configuración de correo.")
    authority = f"https://login.microsoftonline.com/{settings.MS_GRAPH_TENANT}"
    return msal.PublicClientApplication(client_id, authority=authority, token_cache=cache)


def iniciar_autorizacion():
    """Inicia un inicio de sesión OAuth de dispositivo para la cuenta de correo."""
    cache = _token_cache()
    app = _msal_app(cache)
    flow = app.initiate_device_flow(scopes=GRAPH_SCOPES)
    if "user_code" not in flow:
        raise ImproperlyConfigured("Microsoft no pudo iniciar la autorización. Revisa el registro de la aplicación y sus permisos.")
    return app, cache, flow


def guardar_autorizacion(app, cache, flow):
    result = app.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        detail = result.get("error_description", "Microsoft no completó la autorización.")
        raise ImproperlyConfigured(detail)
    _save_token_cache(cache)
    return result


class MicrosoftGraphEmailBackend(BaseEmailBackend):
    """Envía correos con adjuntos por Microsoft Graph y OAuth2 delegado."""

    def _access_token(self):
        cache = _token_cache()
        app = _msal_app(cache)
        accounts = app.get_accounts()
        result = app.acquire_token_silent(GRAPH_SCOPES, account=accounts[0]) if accounts else None
        if not result or "access_token" not in result:
            raise ImproperlyConfigured("La cuenta de correo aún no está autorizada. Ejecuta el comando autenticar_correo.")
        _save_token_cache(cache)
        return result["access_token"]

    @staticmethod
    def _recipient_list(addresses):
        return [{"emailAddress": {"address": address}} for address in addresses if address]

    @staticmethod
    def _attachments(message):
        attachments = []
        for attachment in message.attachments:
            if hasattr(attachment, "filename"):
                filename, content, mimetype = attachment.filename, attachment.content, attachment.mimetype
            else:
                filename, content, mimetype = attachment
            if hasattr(content, "get_payload"):
                content = content.get_payload(decode=True)
            if isinstance(content, str):
                content = content.encode(message.encoding or "utf-8")
            if content is None:
                continue
            import base64

            attachments.append({
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": filename or "adjunto",
                "contentType": mimetype or "application/octet-stream",
                "contentBytes": base64.b64encode(content).decode("ascii"),
            })
        return attachments

    def _payload(self, message):
        body_content = message.body or ""
        body_type = "HTML" if message.content_subtype == "html" else "Text"
        graph_message = {
            "subject": message.subject or "",
            "body": {"contentType": body_type, "content": body_content},
            "toRecipients": self._recipient_list(message.to),
        }
        if message.cc:
            graph_message["ccRecipients"] = self._recipient_list(message.cc)
        if message.bcc:
            graph_message["bccRecipients"] = self._recipient_list(message.bcc)
        if message.reply_to:
            graph_message["replyTo"] = self._recipient_list(message.reply_to)
        attachments = self._attachments(message)
        if attachments:
            graph_message["attachments"] = attachments
        return {"message": graph_message, "saveToSentItems": True}

    def _send(self, message, access_token):
        request = Request(
            GRAPH_SEND_URL,
            data=json.dumps(self._payload(message)).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=25) as response:
                if response.status != 202:
                    raise RuntimeError(f"Microsoft Graph respondió HTTP {response.status}.")
        except HTTPError as exc:
            raise RuntimeError(f"Microsoft Graph rechazó el correo (HTTP {exc.code}).") from None
        except URLError:
            raise RuntimeError("No se pudo conectar con Microsoft Graph.") from None

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        try:
            access_token = self._access_token()
        except Exception:
            if self.fail_silently:
                return 0
            raise

        sent = 0
        for message in email_messages:
            try:
                self._send(message, access_token)
                sent += 1
            except Exception:
                if not self.fail_silently:
                    raise
        return sent
