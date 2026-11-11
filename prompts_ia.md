# Registro de apoyo de IA

**Proyecto:** Dulce Arte
**Asignatura:** Desarrollo Backend
**Estudiante:** Amanda Angélica Álvarez Álvarez

Este archivo registra el uso de IA como apoyo. El diseño, la adaptación al caso y las pruebas fueron revisados antes de incorporarse al proyecto.

## Análisis de la evaluación

**Consulta:** Lee la pauta de Evaluación 3 y el proyecto 3. Identifica funcionalidades, requisitos técnicos, entregables y rúbrica.

**Apoyo aplicado:** Se organizó el alcance en pedidos personalizados, Kanban, listas de materiales, inventario, retiro presencial, Django Admin, PostgreSQL y despliegue EC2.

## Modelo de datos

**Consulta:** Propón un modelo normalizado para una pastelería que maneje recetas, ingredientes, pedidos, cotizaciones, inventario y estados de cocina.

**Apoyo aplicado:** Se separaron `Receta`, `Insumo`, `IngredienteReceta`, `Pedido`, `MaterialPedido`, `Movimiento` e `Historial`. Cada pedido conserva una copia de sus materiales aunque una receta cambie.

## Inventario

**Consulta:** Define una regla segura para reservar ingredientes al confirmar un pedido y descontarlos al iniciar la preparación, evitando sobreventa y doble descuento.

**Apoyo aplicado:** Se usaron transacciones Django, bloqueos de fila (`select_for_update`), reservas y pruebas de pedidos simultáneos.

## Interfaz

**Consulta:** Diseña una vista cálida para clientes y otra para el equipo, con recetario, Kanban e inventario que muestre los ingredientes faltantes en rojo.

**Apoyo aplicado:** Se construyeron templates Django, CSS responsivo y JavaScript que consume la API del mismo dominio. Las recetas no disponibles se ven grises y muestran `disponible/necesario`.

## QR y retiro

**Consulta:** Diseña retiro presencial con QR sin exponer datos privados ni permitir que el enlace por sí solo entregue el pedido.

**Apoyo aplicado:** Se usa un UUID no predecible para seguimiento mínimo. Solo una cuenta `is_staff` puede confirmar pago y retiro en el mesón.

## Despliegue

**Consulta:** Crea una guía de despliegue de Django con PostgreSQL en Ubuntu EC2 usando Gunicorn, systemd y Nginx, con claves fuera de Git.

**Apoyo aplicado:** Se agregaron archivos de ejemplo y una guía que mantiene variables privadas en `/etc/dulce_arte/dulce_arte.env`.
