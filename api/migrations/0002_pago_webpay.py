import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('api', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='pedido',
            name='estado',
            field=models.CharField(
                choices=[
                    ('COTIZACION', 'Por cotizar'),
                    ('COTIZADO', 'Cotización lista'),
                    ('PAGO_PENDIENTE', 'Pago pendiente en Webpay'),
                    ('RECIBIDO', 'Recibido'),
                    ('PREPARACION', 'En preparación'),
                    ('HORNEADO', 'Horneado / decorado'),
                    ('CALIDAD', 'Control de calidad'),
                    ('LISTO', 'Listo para retirar'),
                    ('RETIRADO', 'Retirado'),
                    ('CANCELADO', 'Cancelado'),
                ], default='COTIZACION', max_length=20,
            ),
        ),
        migrations.CreateModel(
            name='PagoWebpay',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('solicitud', models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ('buy_order', models.CharField(max_length=26, unique=True)),
                ('session_id', models.CharField(max_length=61)),
                ('token_ws', models.CharField(blank=True, max_length=64)),
                ('url_webpay', models.URLField(blank=True, max_length=255)),
                ('monto', models.DecimalField(decimal_places=0, max_digits=12)),
                ('estado', models.CharField(choices=[('INICIADO', 'Pago iniciado'), ('PAGADO', 'Pago aprobado'), ('RECHAZADO', 'Pago rechazado'), ('ANULADO', 'Pago cancelado')], default='INICIADO', max_length=12)),
                ('codigo_respuesta', models.IntegerField(blank=True, null=True)),
                ('creado', models.DateTimeField(auto_now_add=True)),
                ('actualizado', models.DateTimeField(auto_now=True)),
                ('cliente', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='pagos_webpay', to=settings.AUTH_USER_MODEL)),
                ('pedidos', models.ManyToManyField(related_name='pagos_webpay', to='api.pedido')),
            ],
            options={'ordering': ['-creado']},
        ),
    ]
