from django.conf import settings
from django.contrib.sessions.middleware import SessionMiddleware
from django.utils.cache import patch_vary_headers


class SesionesPorRol(SessionMiddleware):
    """Selecciona la sesión antes de autenticar la solicitud."""

    def process_request(self, request):
        path = request.path_info
        request.sesion_equipo = (
            path.startswith(('/equipo/', '/admin/'))
            or path == '/cuenta/' and request.GET.get('equipo') == '1'
            or path.startswith('/api/') and (
                request.headers.get('X-Dulce-Rol') == 'equipo'
                or request.method == 'GET' and request.GET.get('equipo') == '1'
            )
        )
        if request.sesion_equipo:
            request.cookies_equipo_originales = request.COOKIES
            cookies = request.COOKIES.copy()
            key = settings.SESSION_COOKIE_NAME
            equipo = cookies.pop(key + '_equipo', None)
            cookies.pop(key, None)
            if equipo is not None:
                cookies[key] = equipo
            request.COOKIES = cookies
        super().process_request(request)

    def process_response(self, request, response):
        response = super().process_response(request, response)
        if request.path_info.startswith('/api/'):
            patch_vary_headers(response, ('X-Dulce-Rol',))
        if request.sesion_equipo:
            key = settings.SESSION_COOKIE_NAME
            cookie = response.cookies.pop(key, None)
            if cookie is not None:
                name = key + '_equipo'
                response.cookies[name] = cookie.value
                response.cookies[name].update(cookie)
            request.COOKIES = request.cookies_equipo_originales
        return response
