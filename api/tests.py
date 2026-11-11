import uuid
from decimal import Decimal
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
from django.test import TestCase,TransactionTestCase,override_settings,Client
from django.contrib.auth import get_user_model
from django.db import close_old_connections,connection
from django.utils import timezone
from django.core import mail
from rest_framework.test import APIClient
from rest_framework.exceptions import ValidationError,PermissionDenied
from .models import *
from . import services
from .mail import enviar_aviso,comprobante,qr_png

PASSWORD='PruebaDulce!2026'
def setup_data(obj):
    User=get_user_model()
    obj.client_user=User.objects.create_user('cliente@example.com','cliente@example.com',PASSWORD,first_name='Cliente')
    obj.other=User.objects.create_user('otra@example.com','otra@example.com',PASSWORD)
    obj.staff=User.objects.create_user('equipo@example.com','equipo@example.com',PASSWORD,is_staff=True)
    obj.flour=Insumo.objects.create(nombre='Harina',unidad='g',stock=1000,minimo=100)
    obj.recipe=Receta.objects.create(nombre='Torta',descripcion='Torta de prueba',categoria='Tortas',precio=10000,porciones=8,minutos=60,pasos='Mezclar\nHornear')
    IngredienteReceta.objects.create(receta=obj.recipe,insumo=obj.flour,cantidad=300)
    obj.api=APIClient();obj.api.force_authenticate(obj.client_user)
def payload(obj,**kwargs):
    data={'receta':obj.recipe,'cantidad':1,'retiro':(timezone.now()+timedelta(days=3)).replace(hour=15,minute=0),'telefono':'+56912345678','diseno':'','preferencias':'','solicitud':uuid.uuid4()}
    data.update(kwargs);return data

@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class NegocioTests(TestCase):
    def setUp(self): setup_data(self)
    def order(self,**kw): return services.crear_pedido(self.client_user,payload(self,**kw))
    def test_reserva_no_consumo_y_disponibilidad(self):
        p=self.order();self.flour.refresh_from_db()
        self.assertEqual((self.flour.stock,self.flour.reservado),(1000,300))
        self.assertEqual(p.estado,'RECIBIDO')
        self.assertEqual(self.api.get('/api/recetas/').data[0]['unidades_disponibles'],2)
    def test_no_sobreventa_rollback_completo(self):
        with self.assertRaises(ValidationError): self.order(cantidad=4)
        self.assertEqual(Pedido.objects.count(),0);self.flour.refresh_from_db();self.assertEqual(self.flour.reservado,0)
    def test_reintento_no_duplica_pedido_ni_reserva(self):
        key=uuid.uuid4();a=self.order(solicitud=key);b=self.order(solicitud=key)
        self.assertEqual(a.pk,b.pk);self.flour.refresh_from_db();self.assertEqual(self.flour.reservado,300)
    def test_consumo_una_sola_vez(self):
        p=self.order();services.cambiar_estado(p.pk,self.staff,'PREPARACION');services.cambiar_estado(p.pk,self.staff,'PREPARACION')
        self.flour.refresh_from_db();self.assertEqual((self.flour.stock,self.flour.reservado),(700,0));self.assertEqual(Movimiento.objects.count(),1)
    def test_cancelar_libera_reserva_una_vez(self):
        p=self.order();services.cambiar_estado(p.pk,self.client_user,'CANCELADO');services.cambiar_estado(p.pk,self.client_user,'CANCELADO')
        self.flour.refresh_from_db();self.assertEqual((self.flour.stock,self.flour.reservado),(1000,0))
    def test_cancelacion_consumida_no_inventa_ingredientes(self):
        p=self.order();services.cambiar_estado(p.pk,self.staff,'PREPARACION');services.cambiar_estado(p.pk,self.staff,'CANCELADO')
        self.flour.refresh_from_db();self.assertEqual(self.flour.stock,700)
    def test_cliente_no_cancela_produccion(self):
        p=self.order();services.cambiar_estado(p.pk,self.staff,'PREPARACION')
        with self.assertRaises(ValidationError): services.cambiar_estado(p.pk,self.client_user,'CANCELADO')
    def test_no_saltar_etapas(self):
        p=self.order()
        with self.assertRaises(ValidationError): services.cambiar_estado(p.pk,self.staff,'LISTO')
    def test_no_cocina_cliente(self):
        p=self.order()
        with self.assertRaises(PermissionDenied): services.cambiar_estado(p.pk,self.client_user,'PREPARACION')
    def test_ajuste_respeta_reservas(self):
        self.order()
        with self.assertRaises(ValidationError): services.ajustar(self.flour.pk,self.staff,-800,'Merma')
        self.flour.refresh_from_db();self.assertEqual(self.flour.stock,1000)
    def test_receta_snapshot_inmutable(self):
        p=self.order();IngredienteReceta.objects.filter(receta=self.recipe).update(cantidad=800)
        services.cambiar_estado(p.pk,self.staff,'PREPARACION');self.flour.refresh_from_db();self.assertEqual(self.flour.stock,700)
    def test_cotizacion_personalizada_aceptacion(self):
        p=self.order(diseno='Rosa');self.flour.refresh_from_db();self.assertEqual(self.flour.reservado,0)
        services.cotizar(p.pk,self.staff,15000,'Diseño rosa',[{'insumo':self.flour,'cantidad':Decimal(450)}])
        services.aceptar(p.pk,self.client_user);self.flour.refresh_from_db();p.refresh_from_db()
        self.assertEqual((p.total,self.flour.reservado),(15000,450))
    def test_aceptar_cotizacion_sin_stock(self):
        p=self.order(diseno='Grande');services.cotizar(p.pk,self.staff,20000,'Grande',[{'insumo':self.flour,'cantidad':Decimal(1500)}])
        with self.assertRaises(ValidationError): services.aceptar(p.pk,self.client_user)
        p.refresh_from_db();self.assertEqual(p.estado,'COTIZADO')
    def test_retiro_requiere_listo_y_pago(self):
        p=self.order()
        with self.assertRaises(ValidationError): services.retirar(p.token,self.staff,True)
        for s in ['PREPARACION','HORNEADO','CALIDAD','LISTO']: services.cambiar_estado(p.pk,self.staff,s)
        with self.assertRaises(ValidationError): services.retirar(p.token,self.staff,False)
        services.retirar(p.token,self.staff,True);services.retirar(p.token,self.staff,True)
        p.refresh_from_db();self.assertEqual(p.estado,'RETIRADO');self.assertTrue(p.pagado)
        self.assertEqual(p.historial.filter(estado='RETIRADO').count(),1)
    def test_retiro_cliente_denegado(self):
        p=self.order()
        with self.assertRaises(PermissionDenied): services.retirar(p.token,self.client_user,True)
    def test_privacidad_api_pdf_qr(self):
        p=self.order();self.api.force_authenticate(self.other)
        self.assertEqual(self.api.get('/api/pedidos/').data,[])
        for suffix in ['', 'comprobante/','qr/']:
            self.assertEqual(self.api.get(f'/api/pedidos/{p.pk}/'+suffix).status_code,404)
    def test_cliente_no_accede_inventario_y_recetas_internas(self):
        self.assertEqual(self.api.get('/api/insumos/').status_code,403)
        self.assertEqual(self.api.post('/api/recetas/',{}).status_code,403)
        data=self.api.get('/api/recetas/').data[0]
        self.assertNotIn('pasos',data);self.assertNotIn('ingredientes',data)
    def test_qr_publico_minimo_no_retiro(self):
        p=self.order();self.api.force_authenticate(None)
        r=self.api.get(f'/api/seguimiento/{p.token}/')
        self.assertEqual(r.status_code,200);self.assertNotIn('telefono',r.data);self.assertNotIn('cliente_email',r.data)
        self.assertEqual(self.api.post('/api/pedidos/retirar/',{'token':str(p.token),'pagado':True},format='json').status_code,403)
    def test_fecha_y_cantidad_invalidas(self):
        data=payload(self);data['receta']=self.recipe.pk;data['solicitud']=str(data['solicitud']);data['retiro']=timezone.now().isoformat();data['cantidad']=0
        self.assertEqual(self.api.post('/api/pedidos/',data,format='json').status_code,400)
    def test_precio_cliente_no_controla_total(self):
        data=payload(self);data['receta']=self.recipe.pk;data['solicitud']=str(data['solicitud']);data['total']=1
        r=self.api.post('/api/pedidos/',data,format='json');self.assertEqual(r.status_code,201);self.assertEqual(Decimal(r.data['total']),10000)
    def test_correo_pdf_qr_y_reintento(self):
        p=self.order();av=p.avisos.get();enviar_aviso(av.pk);enviar_aviso(av.pk)
        self.assertEqual(len(mail.outbox),1);self.assertEqual(len(mail.outbox[0].attachments),2)
        self.assertTrue(comprobante(p).startswith(b'%PDF'));self.assertTrue(qr_png(p).startswith(b'\x89PNG'))
    def test_fallo_correo_no_pierde_pedido(self):
        p=self.order();av=p.avisos.get()
        with patch('django.core.mail.EmailMessage.send',side_effect=OSError('offline')): enviar_aviso(av.pk)
        av.refresh_from_db();self.assertFalse(av.enviado);self.assertEqual(Pedido.objects.count(),1)
        enviar_aviso(av.pk);av.refresh_from_db();self.assertTrue(av.enviado)
    def test_csrf_login_y_registro(self):
        c=Client(enforce_csrf_checks=True)
        self.assertEqual(c.post('/api/cuenta/',data='{}',content_type='application/json').status_code,403)
    def test_registro_nunca_asigna_staff(self):
        r=self.client.post('/api/cuenta/',data={'modo':'registro','email':'NUEVA@example.com','nombre':'Nueva','password':PASSWORD,'is_staff':True},content_type='application/json')
        self.assertEqual(r.status_code,200)
        self.assertFalse(get_user_model().objects.get(username='nueva@example.com').is_staff)
    def test_equipo_protegido_y_logout(self):
        self.client.force_login(self.client_user)
        self.assertEqual(self.client.get('/equipo/').status_code,403)
        self.client.post('/api/cuenta/',data={'modo':'logout'},content_type='application/json')
        self.assertEqual(self.client.get('/mis-pedidos/').status_code,302)

@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class ConcurrenciaTests(TransactionTestCase):
    def setUp(self): setup_data(self)
    def test_dos_pedidos_disputan_ultimo_stock(self):
        self.flour.stock=300;self.flour.save();barrier=Barrier(2)
        def buy():
            close_old_connections();barrier.wait()
            try:
                with patch('api.services.avisar'):
                    services.crear_pedido(self.client_user,payload(self))
                return True
            except ValidationError: return False
            finally: close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(lambda _:buy(),range(2)))
        self.assertEqual(sorted(results),[False,True]);self.flour.refresh_from_db();self.assertEqual(self.flour.reservado,300)
    def test_dos_cocineros_no_descuentan_doble(self):
        with patch('api.services.avisar'): p=services.crear_pedido(self.client_user,payload(self))
        barrier=Barrier(2)
        def cook():
            close_old_connections();barrier.wait()
            try: return services.cambiar_estado(p.pk,self.staff,'PREPARACION').estado
            finally: close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(lambda _:cook(),range(2)))
        self.assertEqual(results,['PREPARACION','PREPARACION']);self.flour.refresh_from_db()
        self.assertEqual(self.flour.stock,700);self.assertEqual(Movimiento.objects.filter(pedido=p).count(),1)
