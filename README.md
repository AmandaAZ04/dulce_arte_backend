# Dulce Arte

Aplicación para gestionar pedidos personalizados en una pastelería artesanal.

**Estudiante:** Amanda Angélica Álvarez Álvarez

**Sección:** IEC-N4-C1
**Año:** 2026

Todos los pedidos se retiran en el local. No hay despacho a domicilio.

## Funcionalidades

- Vitrina pública de recetas y pedidos con retiro entre las 10:00 y las 19:00.
- Cuentas de clientes y del equipo con permisos separados.
- Cotizaciones aprobadas por el cliente para encargos personalizados.
- Kanban de cocina y lista de materiales con reserva de inventario.
- Recetario interno que se muestra gris al faltar ingredientes y marca el faltante en rojo.
- QR y comprobante PDF para confirmar el retiro presencial.

## Ejecutar localmente

1. Clona el repositorio y crea un entorno virtual con Python.
2. Instala `requirements.txt`.
3. Copia `.env.example` como `.env` y define una base PostgreSQL llamada `dulce_arte`.
4. Ejecuta `python manage.py migrate`, `python manage.py cargar_demo`, `python manage.py createsuperuser` y `python manage.py runserver`.

Abre `http://127.0.0.1:8000/`.

## Reglas principales

1. Un pedido estándar reserva ingredientes. Un encargo personalizado espera cotización.
2. Al pasar a preparación se consumen los ingredientes mediante una transacción PostgreSQL.
3. La cancelación libera reservas no consumidas. Los ingredientes ya usados no regresan a bodega.
4. Solo el equipo confirma pago presencial y entrega con QR.
5. El QR muestra solo información necesaria para seguimiento.

## Boleta de pedido con QR

En **Mis compras**, el cliente puede descargar un PDF con los datos de su pedido y el QR para el retiro en el local. El QR también aparece en el seguimiento. La descarga sólo está disponible para pedidos confirmados; las cotizaciones pendientes y los pedidos cancelados no muestran el comprobante. El documento es informativo y no reemplaza una boleta tributaria.

## Pruebas

Ejecuta `python manage.py test api --verbosity 2`. Las pruebas cubren inventario, pedidos simultáneos, doble descuento, permisos, cotizaciones, QR y comprobantes.

## Despliegue

La guía de PostgreSQL, Gunicorn, systemd y Nginx está en `deploy/ec2/README.md`. Al publicar, agrega la IP pública de EC2 aquí.

## Archivos relevantes

- `api/`: dominio, reglas de negocio, API y administración.
- `dulce_arte/`: configuración y rutas Django.
- `templates/`: vistas de cliente, seguimiento y equipo.
- `static/dulce/`: diseño e interacciones de la interfaz.
- `deploy/ec2/`: servicio Gunicorn, Nginx y guía AWS.
- `prompts_ia.md`: evidencia de uso de IA.
