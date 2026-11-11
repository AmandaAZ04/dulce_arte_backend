from decimal import Decimal
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from api.models import *

class Command(BaseCommand):
    help='Carga recetas ilustrativas e insumos sin sobrescribir existencias ni cuentas.'
    @transaction.atomic
    def handle(self,*args,**kwargs):
        insumos={}
        for nombre,unidad,stock,minimo in [('Harina','g',8000,1000),('Azúcar','g',6000,800),('Huevos','u',48,12),('Mantequilla','g',2500,500),('Leche','ml',4000,1000),('Crema','ml',3000,500),('Frutillas','g',1800,400),('Chocolate','g',2000,300),('Queso crema','g',0,500),('Limón','u',24,6),('Galletas de vainilla','g',800,300),('Canela','g',0,50),('Levadura','g',100,30)]:
            i,creado=Insumo.objects.get_or_create(nombre=nombre,defaults={'unidad':unidad,'stock':stock,'minimo':minimo})
            insumos[nombre]=i
            if creado: Movimiento.objects.create(insumo=i,cantidad=stock,motivo='Inventario inicial de demostración')
        recetas=[
            ('Frutillas & crema','Tortas',24900,10,90,'Capas suaves de bizcocho, crema fresca y frutillas. Un clásico para celebrar.','torta-frutilla.svg','Gluten, huevos y lácteos',{'Harina':350,'Azúcar':250,'Huevos':6,'Crema':500,'Frutillas':400},'Precalienta el horno a 180 °C y prepara dos moldes.\nBate huevos y azúcar hasta obtener una mezcla aireada.\nIncorpora la harina tamizada con movimientos envolventes.\nHornea 30 minutos y deja enfriar completamente.\nMonta la crema y corta las frutillas lavadas.\nRellena y decora. Conserva refrigerada hasta el retiro.'),
            ('Chocolate de la casa','Tortas',28900,12,100,'Intensa, húmeda y con una cobertura de chocolate que abraza cada bocado.','torta-chocolate.svg','Gluten, huevos y lácteos',{'Harina':300,'Azúcar':300,'Huevos':5,'Chocolate':400,'Mantequilla':200,'Leche':200},'Precalienta el horno a 175 °C.\nDerrite el chocolate con la mantequilla a baño maría.\nBate huevos y azúcar e incorpora la mezcla de chocolate.\nAgrega harina y leche alternadamente.\nHornea 40 minutos y verifica la cocción.\nEnfría, cubre con chocolate y revisa la terminación.'),
            ('Cheesecake de frutillas','Tartas',22900,8,80,'Cremoso, delicado y con un corazón de frutillas sobre una base crujiente.','cheesecake.svg','Gluten, huevos y lácteos',{'Queso crema':600,'Galletas de vainilla':200,'Mantequilla':100,'Azúcar':150,'Huevos':3,'Frutillas':200},'Tritura las galletas y mezcla con mantequilla.\nPresiona la base en un molde desmontable.\nBate queso crema, azúcar y huevos suavemente.\nVierte sobre la base y hornea a 160 °C hasta cuajar.\nEnfría y refrigera antes de desmoldar.\nTermina con frutillas y revisa la presentación.'),
            ('Pie de limón','Tartas',18900,8,75,'El equilibrio perfecto entre limón, masa dorada y una nube de merengue.','limon.svg','Gluten, huevos y lácteos',{'Harina':250,'Mantequilla':150,'Azúcar':250,'Huevos':4,'Limón':4,'Leche':200},'Prepara una masa con harina, mantequilla y parte del azúcar.\nRefrigera, estira y hornea la base a 180 °C.\nCocina el relleno de limón con leche, yemas y azúcar.\nRellena la base y enfría.\nPrepara el merengue con claras y azúcar.\nDecora, dora la superficie y conserva refrigerado.'),
            ('Cookies con chocolate','Galletas',8900,6,35,'Seis galletas doraditas por fuera, suaves por dentro y llenas de chocolate.','cookies.svg','Gluten, huevos y lácteos',{'Harina':250,'Mantequilla':120,'Azúcar':150,'Huevos':1,'Chocolate':150},'Bate la mantequilla con el azúcar.\nAgrega el huevo y mezcla hasta integrar.\nIncorpora la harina y el chocolate picado.\nForma seis porciones y enfría 20 minutos.\nHornea a 180 °C durante 12 minutos.\nDeja enfriar y empaca seis unidades por caja.'),
            ('Rollitos de canela','Dulces',11900,6,120,'Seis rollitos esponjosos, con aroma a canela y un suave glaseado.','rolls.svg','Gluten, huevos y lácteos',{'Harina':500,'Leche':250,'Mantequilla':100,'Azúcar':150,'Huevos':1,'Canela':20,'Levadura':10},'Mezcla harina, leche, huevo, levadura y parte del azúcar.\nAmasa, agrega mantequilla y deja fermentar.\nEstira y cubre con mantequilla, canela y azúcar.\nEnrolla, corta seis porciones y deja levar nuevamente.\nHornea a 180 °C durante 25 minutos.\nGlasea y empaca cuando se hayan entibiado.')]
        for nombre,cat,precio,porciones,minutos,desc,img,alerg,bom,pasos in recetas:
            r,creado=Receta.objects.get_or_create(nombre=nombre,defaults={'categoria':cat,'precio':precio,'porciones':porciones,'minutos':minutos,'descripcion':desc,'imagen':img,'alergenos':alerg,'pasos':pasos})
            if creado:
                for n,c in bom.items(): IngredienteReceta.objects.create(receta=r,insumo=insumos[n],cantidad=c)
        self.stdout.write(self.style.SUCCESS('Vitrina y recetario preparados. No se han creado contraseñas públicas.'))
