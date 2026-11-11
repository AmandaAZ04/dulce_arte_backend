from django.contrib import admin
from .models import *
admin.site.site_header='Dulce Arte · Administración'
admin.site.site_title='Dulce Arte'
admin.site.index_title='El taller, en orden'

class IngredienteInline(admin.TabularInline):
    model=IngredienteReceta
    extra=1
@admin.register(Receta)
class RecetaAdmin(admin.ModelAdmin):
    list_display=['nombre','categoria','precio','porciones','activa']
    list_filter=['categoria','activa']
    search_fields=['nombre','descripcion']
    inlines=[IngredienteInline]
@admin.register(Insumo)
class InsumoAdmin(admin.ModelAdmin):
    list_display=['nombre','unidad','stock','reservado','disponible','minimo']
    search_fields=['nombre']
    list_filter=['unidad']
    readonly_fields=['stock','reservado','disponible']
    def get_readonly_fields(self,request,obj=None): return self.readonly_fields+(['unidad'] if obj else [])

# Las operaciones de cocina/retiro se realizan por los servicios transaccionales.
class Auditoria(admin.ModelAdmin):
    def has_add_permission(self,request): return False
    def has_change_permission(self,request,obj=None): return False
    def has_delete_permission(self,request,obj=None): return False
@admin.register(Pedido)
class PedidoAdmin(Auditoria):
    list_display=['codigo','cliente','producto','retiro','estado','total','pagado']
    list_filter=['estado','pagado','retiro']
    search_fields=['producto','cliente__email','cliente__first_name']
@admin.register(Movimiento)
class MovimientoAdmin(Auditoria):
    list_display=['insumo','cantidad','motivo','usuario','creado']
    search_fields=['insumo__nombre','motivo']
    list_filter=['creado']
@admin.register(Historial)
class HistorialAdmin(Auditoria):
    list_display=['pedido','estado','detalle','usuario','creado']
    list_filter=['estado']
@admin.register(MaterialPedido)
class MaterialAdmin(Auditoria): list_display=['pedido','insumo','cantidad']
@admin.register(IngredienteReceta)
class BOMAdmin(Auditoria): list_display=['receta','insumo','cantidad']
@admin.register(Aviso)
class AvisoAdmin(Auditoria):
    list_display=['pedido','evento','enviado','intentos','error']
    list_filter=['enviado']
