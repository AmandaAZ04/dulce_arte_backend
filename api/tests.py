import uuid
from decimal import Decimal
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
from django.test import TestCase,TransactionTestCase,Client
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import close_old_connections,connection
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.exceptions import ValidationError,PermissionDenied
from .models import *
from . import agenda, services
from .mail import comprobante,qr_png

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
    def test_cotizacion_desde_vitrina_no_reserva_ni_confia_en_precio(self):
        data=payload(self, diseno='Rosa')
        data.update(receta=self.recipe.pk, solicitud=str(data['solicitud']), total=1,
                    retiro=(timezone.localtime()+timedelta(days=3)).replace(hour=15,minute=0))
        r=self.api.post('/api/pedidos/',data,format='json')
        self.assertEqual(r.status_code,201)
        self.assertEqual(r.data['estado'],'COTIZACION')
        self.assertEqual(Decimal(r.data['total']),10000)
        self.flour.refresh_from_db()
        self.assertEqual(self.flour.reservado,0)
        data.update(diseno='',solicitud=str(uuid.uuid4()))
        self.assertEqual(self.api.post('/api/pedidos/',data,format='json').status_code,400)

    def test_taller_carga_sus_herramientas(self):
        self.client.post('/api/cuenta/', {'email':self.staff.email,'password':PASSWORD},
                         content_type='application/json', headers={'X-Dulce-Rol':'equipo'})
        response=self.client.get('/equipo/')
        self.assertContains(response,'/static/dulce/equipo.js')
        self.assertNotContains(response,'href="/admin/"')

    def test_agenda_salta_domingo_y_suma_pedidos_pendientes(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        chile = ZoneInfo('America/Santiago')
        sabado = datetime(2026, 11, 14, 18, 0, tzinfo=chile)
        items = [{'receta': self.recipe, 'cantidad': 1}]
        with patch('api.agenda.timezone.now', return_value=sabado):
            self.assertEqual(agenda.primer_retiro(items), datetime(2026, 11, 16, 10, 0, tzinfo=chile))
            self.order(cantidad=2)
            self.assertEqual(agenda.primer_retiro(items), datetime(2026, 11, 16, 12, 0, tzinfo=chile))
            with self.assertRaises(ValidationError):
                agenda.validar_horario(sabado + timedelta(days=1))

    def test_equipo_rechaza_cotizacion_y_cliente_ve_sugerencias(self):
        pedido = self.order(diseno='Flores')
        url = f'/api/pedidos/{pedido.pk}/rechazar-cotizacion/'
        datos = {'motivo':'Faltan insumos','alternativas':'La misma torta de 8 porciones'}
        self.assertEqual(self.api.post(url, datos, format='json').status_code,403)
        equipo = APIClient()
        equipo.force_authenticate(self.staff)
        self.assertEqual(equipo.post(url, datos, format='json').status_code,200)
        respuesta = self.api.get(f'/api/pedidos/{pedido.pk}/').data
        self.assertEqual(respuesta['estado'],'COTIZACION_RECHAZADA')
        self.assertEqual(respuesta['nota_equipo'],datos['motivo'])
        self.assertEqual(respuesta['alternativas'],datos['alternativas'])

    def test_demo_conserva_existencias_y_carga_recetas(self):
        call_command('cargar_demo',verbosity=0)
        call_command('cargar_demo',verbosity=0)
        self.flour.refresh_from_db()
        self.assertEqual(self.flour.stock,1000)
        self.assertEqual(Receta.objects.filter(nombre='Brownies de chocolate').count(),1)
        self.assertEqual(Receta.objects.get(nombre='Galletas de limón').ingredientes.count(),5)
        self.assertEqual(Insumo.objects.get(nombre='Queso crema').disponible,0)

    @patch('api.payments.webpay_transaction')
    def test_webpay_confirma_antes_de_enviar_a_cocina(self, gateway):
        gateway.return_value.create.return_value={
            'token':'token-demo','url':'https://webpay3gint.transbank.cl/webpayserver/initTransaction',
        }
        retiro=(timezone.localtime()+timedelta(days=3)).replace(hour=15,minute=0)
        response=self.api.post('/api/pagos/iniciar/',{
            'items':[{'receta':self.recipe.pk,'cantidad':1}],
            'telefono':'+56912345678','retiro':retiro.isoformat(),'solicitud':str(uuid.uuid4()),
        },format='json')
        self.assertEqual(response.status_code,201)
        pago=PagoWebpay.objects.get(pk=response.data['pago_id'])
        pedido=pago.pedidos.get()
        self.assertEqual(pedido.estado,Pedido.Estado.PAGO_PENDIENTE)
        self.assertEqual(self.api.get(f'/api/pedidos/{pedido.pk}/comprobante/').status_code,404)
        gateway.return_value.commit.return_value={
            'status':'AUTHORIZED','response_code':0,'amount':10000,
            'buy_order':pago.buy_order,'session_id':pago.session_id,
        }
        response=self.client.post('/api/pagos/retorno/',{'token_ws':'token-demo'})
        self.assertRedirects(response,'/mis-pedidos/?pago=ok',fetch_redirect_response=False)
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado,Pedido.Estado.RECIBIDO)
        self.assertTrue(pedido.pagado)
        self.assertEqual(self.api.get(f'/api/pedidos/{pedido.pk}/comprobante/').status_code,200)
    def test_cliente_descarga_comprobante_pdf_con_qr(self):
        p=self.order()
        response=self.api.get(f'/api/pedidos/{p.pk}/comprobante/')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response['Content-Type'],'application/pdf')
        self.assertIn('attachment',response['Content-Disposition'])
        self.assertTrue(response.content.startswith(b'%PDF'))
        self.assertTrue(qr_png(p).startswith(b'\x89PNG'))
        qr=self.api.get(f'/api/pedidos/{p.pk}/qr/')
        self.assertEqual(qr.status_code,200)
        self.assertEqual(qr['Content-Type'],'image/png')
    def test_no_descarga_boleta_antes_de_confirmar_o_cancelado(self):
        p=self.order(diseno='Flores')
        for suffix in ['comprobante/','qr/']:
            self.assertEqual(self.api.get(f'/api/pedidos/{p.pk}/{suffix}').status_code,404)
        p.estado='CANCELADO';p.save(update_fields=['estado'])
        for suffix in ['comprobante/','qr/']:
            self.assertEqual(self.api.get(f'/api/pedidos/{p.pk}/{suffix}').status_code,404)
    def test_csrf_login_y_registro(self):
        c=Client(enforce_csrf_checks=True)
        self.assertEqual(c.post('/api/cuenta/',data='{}',content_type='application/json').status_code,403)
    def test_registro_nunca_asigna_staff(self):
        r=self.client.post('/api/cuenta/',data={'modo':'registro','email':'NUEVA@example.com','nombre':'Nueva','password':PASSWORD,'is_staff':True},content_type='application/json')
        self.assertEqual(r.status_code,200)
        self.assertFalse(get_user_model().objects.get(username='nueva@example.com').is_staff)
    def test_equipo_protegido_y_logout(self):
        self.client.force_login(self.client_user)
        self.assertRedirects(self.client.get('/equipo/'),'/cuenta/?equipo=1')
        self.client.post('/api/cuenta/',data={'modo':'logout'},content_type='application/json')
        self.assertEqual(self.client.get('/mis-pedidos/').status_code,302)

    def test_cliente_y_equipo_tienen_sesiones_independientes(self):
        def login_as(user, **headers):
            return self.client.post('/api/cuenta/', {'email':user.email,'password':PASSWORD},
                                    content_type='application/json', headers=headers)
        equipo = {'X-Dulce-Rol':'equipo'}
        self.assertEqual(login_as(self.client_user).status_code,200)
        self.assertEqual(login_as(self.client_user, **equipo).status_code,403)
        self.assertEqual(login_as(self.staff, **equipo).status_code,200)
        self.assertEqual(self.client.get('/api/cuenta/').json()['usuario']['id'],self.client_user.id)
        self.assertEqual(self.client.get('/api/cuenta/',headers=equipo).json()['usuario']['id'],self.staff.id)
        pedido = self.order()
        self.assertEqual(self.client.post(f'/api/pedidos/{pedido.id}/estado/', {'estado':'PREPARACION'},
                                          content_type='application/json', headers=equipo).status_code,200)
        self.assertEqual(self.client.get(f'/api/pedidos/{pedido.id}/').json()['estado'],'PREPARACION')
        self.client.post('/api/cuenta/', {'modo':'logout'}, content_type='application/json', headers=equipo)
        self.assertIsNone(self.client.get('/api/cuenta/',headers=equipo).json()['usuario'])
        self.assertEqual(self.client.get('/api/cuenta/').json()['usuario']['id'],self.client_user.id)

class ConcurrenciaTests(TransactionTestCase):
    def setUp(self): setup_data(self)
    def test_dos_pedidos_disputan_ultimo_stock(self):
        self.flour.stock=300;self.flour.save();barrier=Barrier(2)
        def buy():
            close_old_connections();barrier.wait()
            try:
                services.crear_pedido(self.client_user,payload(self))
                return True
            except ValidationError: return False
            finally: close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(lambda _:buy(),range(2)))
        self.assertEqual(sorted(results),[False,True]);self.flour.refresh_from_db();self.assertEqual(self.flour.reservado,300)
    def test_dos_cocineros_no_descuentan_doble(self):
        p=services.crear_pedido(self.client_user,payload(self))
        barrier=Barrier(2)
        def cook():
            close_old_connections();barrier.wait()
            try: return services.cambiar_estado(p.pk,self.staff,'PREPARACION').estado
            finally: close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(lambda _:cook(),range(2)))
        self.assertEqual(results,['PREPARACION','PREPARACION']);self.flour.refresh_from_db()
        self.assertEqual(self.flour.stock,700);self.assertEqual(Movimiento.objects.filter(pedido=p).count(),1)
