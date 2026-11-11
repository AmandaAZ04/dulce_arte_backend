import uuid
from decimal import Decimal
from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator

# Las cantidades usan la unidad base de cada insumo: g, ml o unidad.
class Insumo(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    unidad = models.CharField(max_length=8, choices=[('g','gramos'),('ml','mililitros'),('u','unidades')])
    stock = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    reservado = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    minimo = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    class Meta:
        ordering = ['nombre']
        constraints = [models.CheckConstraint(condition=models.Q(stock__gte=0, reservado__gte=0) & models.Q(stock__gte=models.F('reservado')), name='insumo_saldo_valido')]
    @property
    def disponible(self): return self.stock - self.reservado
    def __str__(self): return f'{self.nombre} ({self.unidad})'

class Receta(models.Model):
    nombre = models.CharField(max_length=120)
    descripcion = models.TextField()
    categoria = models.CharField(max_length=30, choices=[('Tortas','Tortas'),('Tartas','Tartas'),('Dulces','Dulces'),('Galletas','Galletas')])
    precio = models.DecimalField(max_digits=10, decimal_places=0, validators=[MinValueValidator(1)])
    porciones = models.PositiveSmallIntegerField(default=8, validators=[MinValueValidator(1)])
    minutos = models.PositiveSmallIntegerField(default=60, validators=[MinValueValidator(1)])
    pasos = models.TextField(help_text='Un paso por línea.')
    alergenos = models.CharField(max_length=250, blank=True)
    imagen = models.CharField(max_length=120, default='torta-frutilla.svg')
    activa = models.BooleanField(default=True)
    class Meta: ordering = ['id']
    def __str__(self): return self.nombre

class IngredienteReceta(models.Model):
    receta = models.ForeignKey(Receta, on_delete=models.CASCADE, related_name='ingredientes')
    insumo = models.ForeignKey(Insumo, on_delete=models.PROTECT)
    cantidad = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    class Meta:
        constraints = [models.UniqueConstraint(fields=['receta','insumo'], name='ingrediente_unico'),models.CheckConstraint(condition=models.Q(cantidad__gt=0),name='bom_positiva')]
    def __str__(self): return f'{self.insumo.nombre}: {self.cantidad}'

class Pedido(models.Model):
    class Estado(models.TextChoices):
        COTIZACION='COTIZACION','Por cotizar'
        COTIZADO='COTIZADO','Cotización lista'
        RECIBIDO='RECIBIDO','Recibido'
        PREPARACION='PREPARACION','En preparación'
        HORNEADO='HORNEADO','Horneado / decorado'
        CALIDAD='CALIDAD','Control de calidad'
        LISTO='LISTO','Listo para retirar'
        RETIRADO='RETIRADO','Retirado'
        CANCELADO='CANCELADO','Cancelado'
    cliente = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name='pedidos')
    receta = models.ForeignKey(Receta,on_delete=models.PROTECT)
    producto = models.CharField(max_length=120)
    cantidad = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    total = models.DecimalField(max_digits=12,decimal_places=0)
    retiro = models.DateTimeField()
    telefono = models.CharField(max_length=30)
    diseno = models.TextField(blank=True)
    preferencias = models.TextField(blank=True, help_text='Solicitudes de ingredientes a revisar por el equipo.')
    nota_equipo = models.TextField(blank=True)
    estado = models.CharField(max_length=20,choices=Estado.choices,default=Estado.COTIZACION)
    pagado = models.BooleanField(default=False)
    consumido = models.BooleanField(default=False)
    token = models.UUIDField(default=uuid.uuid4,unique=True,editable=False)
    solicitud = models.UUIDField(default=uuid.uuid4,unique=True,editable=False)
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['retiro','id']
        constraints = [models.CheckConstraint(condition=models.Q(cantidad__gte=1,total__gte=0),name='pedido_valores_validos')]
    @property
    def codigo(self): return f'DA-{self.pk:04d}'
    def __str__(self): return f'{self.codigo} · {self.producto}'

# Copia histórica de la BOM por pedido. Cambiar la receta no altera lo reservado.
class MaterialPedido(models.Model):
    pedido = models.ForeignKey(Pedido,on_delete=models.CASCADE,related_name='materiales')
    insumo = models.ForeignKey(Insumo,on_delete=models.PROTECT)
    cantidad = models.DecimalField(max_digits=12,decimal_places=2,validators=[MinValueValidator(Decimal('0.01'))])
    class Meta:
        constraints = [models.UniqueConstraint(fields=['pedido','insumo'],name='material_pedido_unico'),models.CheckConstraint(condition=models.Q(cantidad__gt=0),name='material_positivo')]

class Movimiento(models.Model):
    insumo = models.ForeignKey(Insumo,on_delete=models.PROTECT)
    pedido = models.ForeignKey(Pedido,on_delete=models.PROTECT,null=True,blank=True)
    cantidad = models.DecimalField(max_digits=12,decimal_places=2)
    motivo = models.CharField(max_length=200)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,null=True)
    creado = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ['-creado']

class Historial(models.Model):
    pedido = models.ForeignKey(Pedido,on_delete=models.CASCADE,related_name='historial')
    estado = models.CharField(max_length=20,choices=Pedido.Estado.choices)
    detalle = models.CharField(max_length=250)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,null=True)
    creado = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ['creado']

class Aviso(models.Model):
    pedido = models.ForeignKey(Pedido,on_delete=models.CASCADE,related_name='avisos')
    evento = models.CharField(max_length=50)
    enviado = models.BooleanField(default=False)
    intentos = models.PositiveIntegerField(default=0)
    error = models.CharField(max_length=250,blank=True)
    creado = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['pedido','evento'],name='aviso_unico_evento')]
