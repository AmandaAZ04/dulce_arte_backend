import json
from django.contrib.auth import authenticate,login,logout,get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_protect,ensure_csrf_cookie
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.core.validators import validate_email
from rest_framework import viewsets,status
from rest_framework.decorators import action,api_view,permission_classes
from rest_framework.permissions import AllowAny,IsAdminUser,IsAuthenticated,BasePermission,SAFE_METHODS
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError, NotFound
from rest_framework.throttling import ScopedRateThrottle
from .models import Insumo,Receta,Pedido,Movimiento
from .serializer import *
from . import services
from .mail import comprobante,qr_png

def usuario_data(u):
    return {'id':u.pk,'nombre':u.first_name or u.username,'email':u.email,'equipo':u.is_staff} if u.is_authenticated else None

# CSRF también se exige en login y registro anónimos.
@ensure_csrf_cookie
@csrf_protect
@require_http_methods(['GET','POST'])
def cuenta(request):
    if request.method=='GET': return JsonResponse({'usuario':usuario_data(request.user)})
    from django.core.cache import cache
    key='login:'+request.META.get('REMOTE_ADDR','local')
    intentos=cache.get(key,0)
    if intentos>=20: return JsonResponse({'detail':'Demasiados intentos. Espera una hora.'},status=429)
    cache.set(key,intentos+1,3600)
    try:
        data=json.loads(request.body)
        modo=data.get('modo','login')
        if modo=='logout':
            logout(request); return JsonResponse({'usuario':None})
        email=str(data.get('email','')).strip().lower()
        password=data.get('password','')
        User=get_user_model()
        if modo=='registro':
            nombre=str(data.get('nombre','')).strip()
            if not 2<=len(nombre)<=100: raise DjangoValidationError('Escribe tu nombre (2 a 100 caracteres).')
            validate_email(email)
            if len(email)>150: raise DjangoValidationError('Correo demasiado largo.')
            if User.objects.filter(email__iexact=email).exists() or User.objects.filter(username__iexact=email).exists():
                raise DjangoValidationError('Ese correo ya tiene una cuenta. Inicia sesión o prueba con otro correo.')
            user=User(username=email,email=email,first_name=nombre)
            validate_password(password,user)
            with transaction.atomic():
                user.set_password(password); user.save()
        else:
            # Los clientes nuevos usan el correo como nombre de usuario. Busca
            # también por correo para que las cuentas antiguas y el equipo
            # puedan iniciar sesión escribiendo siempre su email.
            user_model=get_user_model()
            account=user_model.objects.filter(email__iexact=email).order_by('pk').first()
            if account is None:
                account=user_model.objects.filter(username__iexact=email).first()
            username=account.get_username() if account else email
            user=authenticate(request,username=username,password=password)
            if user is None: return JsonResponse({'detail':'Correo o contraseña incorrectos.'},status=400)
        login(request,user); cache.delete(key)
        return JsonResponse({'usuario':usuario_data(user)})
    except (DjangoValidationError,IntegrityError,ValueError,TypeError) as exc:
        msg='Ese correo ya está registrado.' if isinstance(exc,IntegrityError) else ' '.join(exc.messages) if isinstance(exc,DjangoValidationError) else 'Datos inválidos.'
        return JsonResponse({'detail':msg},status=400)

class CatalogoPermiso(BasePermission):
    def has_permission(self,request,view): return request.method in SAFE_METHODS or bool(request.user.is_authenticated and request.user.is_staff)

class RecetaViewSet(viewsets.ModelViewSet):
    serializer_class=RecetaSerializer
    permission_classes=[CatalogoPermiso]
    def get_queryset(self):
        qs=Receta.objects.prefetch_related('ingredientes__insumo')
        return qs if self.request.user.is_staff else qs.filter(activa=True)
    def perform_destroy(self,instance):
        instance.activa=False; instance.save(update_fields=['activa'])

class InsumoViewSet(viewsets.ModelViewSet):
    queryset=Insumo.objects.all()
    serializer_class=InsumoSerializer
    permission_classes=[IsAdminUser]
    def destroy(self,request,*args,**kwargs):
        i=self.get_object()
        if i.stock or i.reservado: raise ValidationError('Solo puedes eliminar un insumo sin stock ni reservas.')
        try: return super().destroy(request,*args,**kwargs)
        except ProtectedError: raise ValidationError('Este insumo está vinculado a recetas o movimientos.')
    @action(detail=True,methods=['post'])
    def ajustar(self,request,pk=None):
        self.get_object()
        s=AjusteSerializer(data=request.data);s.is_valid(raise_exception=True)
        i=services.ajustar(int(pk),request.user,**s.validated_data)
        return Response(self.get_serializer(i).data)

class PedidoViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class=PedidoSerializer
    def get_queryset(self):
        qs=Pedido.objects.select_related('cliente','receta').prefetch_related('historial','pagos_webpay')
        if self.request.user.is_staff:
            return qs.prefetch_related('materiales__insumo')
        return qs.filter(cliente=self.request.user)
    def create(self, request):
        serializer = NuevoPedidoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        if not (datos['diseno'].strip() or datos['preferencias'].strip()):
            raise ValidationError('Describe el diseño o los ingredientes que quieres personalizar. Para una compra estándar, usa el carrito.')
        pedido = services.crear_pedido(request.user, datos)
        return Response(self.get_serializer(pedido).data, status=status.HTTP_201_CREATED)
    @action(detail=True,methods=['post'])
    def aceptar(self,request,pk=None):
        self.get_object(); p=services.aceptar(int(pk),request.user)
        return Response(self.get_serializer(p).data)
    @action(detail=True,methods=['post'],permission_classes=[IsAdminUser])
    def cotizar(self,request,pk=None):
        self.get_object();s=CotizacionSerializer(data=request.data);s.is_valid(raise_exception=True)
        p=services.cotizar(int(pk),request.user,**s.validated_data)
        return Response(self.get_serializer(p).data)
    @action(detail=True,methods=['post'])
    def estado(self,request,pk=None):
        self.get_object(); p=services.cambiar_estado(int(pk),request.user,request.data.get('estado'))
        return Response(self.get_serializer(p).data)
    @action(detail=False,methods=['post'],permission_classes=[IsAdminUser])
    def retirar(self,request):
        s=RetiroSerializer(data=request.data);s.is_valid(raise_exception=True)
        p=services.retirar(usuario=request.user,**s.validated_data)
        return Response(self.get_serializer(p).data)
    @action(detail=True,methods=['get'])
    def comprobante(self,request,pk=None):
        p=self.get_object()
        if not request.user.is_staff and p.estado in ['COTIZACION','COTIZADO','PAGO_PENDIENTE','CANCELADO']:
            raise NotFound()
        r=HttpResponse(comprobante(p),content_type='application/pdf')
        r['Content-Disposition']=f'attachment; filename="{p.codigo}.pdf"';r['Cache-Control']='no-store';return r
    @action(detail=True,methods=['get'])
    def qr(self,request,pk=None):
        p=self.get_object()
        if not request.user.is_staff and p.estado in ['COTIZACION','COTIZADO','PAGO_PENDIENTE','CANCELADO']:
            raise NotFound()
        r=HttpResponse(qr_png(p),content_type='image/png');r['Cache-Control']='no-store';return r

class MovimientoViewSet(viewsets.ReadOnlyModelViewSet):
    queryset=Movimiento.objects.select_related('insumo').all()[:100]
    serializer_class=MovimientoSerializer
    permission_classes=[IsAdminUser]

@api_view(['GET'])
@permission_classes([AllowAny])
def seguimiento(request,token):
    p=get_object_or_404(Pedido,token=token)
    # El enlace QR no publica datos personales, receta interna ni autoriza el retiro.
    data={'codigo':p.codigo,'producto':p.producto,'cantidad':p.cantidad,'estado':p.estado,'etiqueta':p.get_estado_display(),'retiro':p.retiro,'historial':[{'estado':h.estado,'etiqueta':h.get_estado_display(),'creado':h.creado} for h in p.historial.all()]}
    response=Response(data);response['Cache-Control']='no-store';response['Referrer-Policy']='no-referrer';return response
