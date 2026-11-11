from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from .models import Insumo, Receta, IngredienteReceta, Pedido, MaterialPedido, Historial, Movimiento

class InsumoSerializer(serializers.ModelSerializer):
    disponible=serializers.DecimalField(max_digits=12,decimal_places=2,read_only=True)
    class Meta:
        model=Insumo
        fields=['id','nombre','unidad','stock','reservado','disponible','minimo']
        read_only_fields=['stock','reservado']
    def validate_unidad(self,v):
        if self.instance and self.instance.unidad!=v and (self.instance.stock or self.instance.ingredientereceta_set.exists() or self.instance.materialpedido_set.exists()):
            raise serializers.ValidationError('No cambies la unidad de un insumo utilizado; crea otro insumo.')
        return v

class BOMSerializer(serializers.Serializer):
    insumo=serializers.PrimaryKeyRelatedField(queryset=Insumo.objects.all())
    cantidad=serializers.DecimalField(max_digits=10,decimal_places=2,min_value=Decimal('0.01'))

class RecetaSerializer(serializers.ModelSerializer):
    ingredientes=serializers.SerializerMethodField()
    ingredientes_publicos=serializers.SerializerMethodField()
    disponible=serializers.SerializerMethodField()
    unidades_disponibles=serializers.SerializerMethodField()
    bom=BOMSerializer(many=True,write_only=True,required=False)
    class Meta:
        model=Receta
        fields=['id','nombre','descripcion','categoria','precio','porciones','minutos','pasos','alergenos','imagen','activa','ingredientes','ingredientes_publicos','disponible','unidades_disponibles','bom']
    def to_representation(self,instance):
        data=super().to_representation(instance)
        request=self.context.get('request')
        if not request or not request.user.is_staff:
            data.pop('ingredientes',None); data.pop('pasos',None)
        return data
    def get_ingredientes(self,r):
        return [{'insumo':m.insumo_id,'nombre':m.insumo.nombre,'unidad':m.insumo.unidad,'cantidad':str(m.cantidad),'disponible':str(m.insumo.disponible),'falta':str(max(0,m.cantidad-m.insumo.disponible))} for m in r.ingredientes.all()]
    def get_ingredientes_publicos(self,r):
        return list(r.ingredientes.select_related('insumo').order_by('pk').values_list('insumo__nombre',flat=True))
    def get_unidades_disponibles(self,r):
        return min([int(m.insumo.disponible//m.cantidad) for m in r.ingredientes.all()] or [0])
    def get_disponible(self,r): return r.activa and self.get_unidades_disponibles(r)>0
    def validate_bom(self,v):
        if not v: raise serializers.ValidationError('Agrega al menos un ingrediente.')
        ids=[x['insumo'].pk for x in v]
        if len(ids)!=len(set(ids)): raise serializers.ValidationError('No repitas ingredientes.')
        return v
    def validate_imagen(self,v):
        if v not in ['torta-frutilla.svg','torta-chocolate.svg','cheesecake.svg','limon.svg','cookies.svg','rolls.svg']:
            raise serializers.ValidationError('Selecciona una ilustración del catálogo.')
        return v
    def validate(self,attrs):
        if not self.instance and not attrs.get('bom'): raise serializers.ValidationError({'bom':'Agrega los ingredientes de la receta.'})
        return attrs
    @transaction.atomic
    def create(self,data):
        bom=data.pop('bom'); r=Receta.objects.create(**data)
        for m in bom: IngredienteReceta.objects.create(receta=r,**m)
        return r
    @transaction.atomic
    def update(self,instance,data):
        instance=Receta.objects.select_for_update().get(pk=instance.pk)
        bom=data.pop('bom',None)
        instance=super().update(instance,data)
        if bom is not None:
            instance.ingredientes.all().delete()
            for m in bom: IngredienteReceta.objects.create(receta=instance,**m)
        return instance

class NuevoPedidoSerializer(serializers.Serializer):
    receta=serializers.PrimaryKeyRelatedField(queryset=Receta.objects.filter(activa=True))
    cantidad=serializers.IntegerField(min_value=1,max_value=20)
    retiro=serializers.DateTimeField()
    telefono=serializers.RegexField(r'^\+?[0-9 ()-]{8,25}$')
    diseno=serializers.CharField(required=False,allow_blank=True,max_length=1500,default='')
    preferencias=serializers.CharField(required=False,allow_blank=True,max_length=1500,default='')
    solicitud=serializers.UUIDField()
    def validate_retiro(self,v):
        from datetime import timedelta
        if v < timezone.now()+timedelta(hours=24): raise serializers.ValidationError('Pide con al menos 24 horas de anticipación.')
        if v > timezone.now()+timedelta(days=90): raise serializers.ValidationError('Elige una fecha dentro de los próximos 90 días.')
        hora=timezone.localtime(v)
        if not 10<=hora.hour<19: raise serializers.ValidationError('Los retiros son entre 10:00 y 18:59.')
        return v

class HistorialSerializer(serializers.ModelSerializer):
    etiqueta=serializers.CharField(source='get_estado_display',read_only=True)
    class Meta: model=Historial; fields=['estado','etiqueta','detalle','creado']

class PedidoSerializer(serializers.ModelSerializer):
    codigo=serializers.CharField(read_only=True)
    etiqueta=serializers.CharField(source='get_estado_display',read_only=True)
    cliente_nombre=serializers.SerializerMethodField()
    cliente_email=serializers.EmailField(source='cliente.email',read_only=True)
    historial=HistorialSerializer(many=True,read_only=True)
    materiales=serializers.SerializerMethodField()
    class Meta:
        model=Pedido
        fields=['id','codigo','receta','producto','cantidad','total','retiro','telefono','diseno','preferencias','nota_equipo','estado','etiqueta','pagado','token','cliente_nombre','cliente_email','historial','materiales','creado']
        read_only_fields=fields
    def get_cliente_nombre(self,p): return p.cliente.get_full_name() or p.cliente.username
    def get_materiales(self,p):
        if not self.context['request'].user.is_staff: return []
        return [{'insumo':m.insumo_id,'nombre':m.insumo.nombre,'cantidad':str(m.cantidad),'unidad':m.insumo.unidad} for m in p.materiales.select_related('insumo')]
class CotizacionSerializer(serializers.Serializer):
    total=serializers.DecimalField(max_digits=12,decimal_places=0,min_value=1)
    nota=serializers.CharField(max_length=1500,allow_blank=True)
    materiales=BOMSerializer(many=True,allow_empty=False)
    def validate_materiales(self,v):
        ids=[m['insumo'].pk for m in v]
        if len(ids)!=len(set(ids)): raise serializers.ValidationError('No repitas ingredientes.')
        return v

class AjusteSerializer(serializers.Serializer):
    cantidad=serializers.DecimalField(max_digits=12,decimal_places=2)
    motivo=serializers.CharField(min_length=3,max_length=200)
    def validate_cantidad(self,v):
        if not v: raise serializers.ValidationError('La cantidad no puede ser cero.')
        return v

class RetiroSerializer(serializers.Serializer):
    token=serializers.UUIDField()
    pagado=serializers.BooleanField()

class MovimientoSerializer(serializers.ModelSerializer):
    nombre=serializers.CharField(source='insumo.nombre')
    unidad=serializers.CharField(source='insumo.unidad')
    class Meta: model=Movimiento; fields=['id','nombre','unidad','cantidad','motivo','creado','pedido']
