# Despliegue de Dulce Arte en AWS EC2

Esta guía instala Django, PostgreSQL, Gunicorn y Nginx en una instancia Ubuntu. Ejecuta los comandos en EC2 con un usuario que pueda usar `sudo`.

## Crear la instancia

En AWS Academy selecciona:

- AMI: Ubuntu Server 24.04 LTS.
- Tipo: `t3.micro` o el permitido por el laboratorio.
- Almacenamiento: 12 GB o más.
- Grupo de seguridad: SSH 22 solo desde tu IP y HTTP 80 desde Internet. Abre HTTPS 443 solo si configuras un dominio y certificado.
- Par de claves: descarga el archivo `.pem` y guárdalo en una carpeta privada. No lo subas a Git.

Anota la IP pública que aparezca en la vista de EC2.

## Conectar e instalar

Desde PowerShell:

```powershell
ssh -i "C:\ruta\tu-clave.pem" ubuntu@TU_IP_PUBLICA
```

En la instancia:

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y git python3-venv python3-pip postgresql postgresql-contrib nginx
```

## Base de datos y código

```bash
sudo -u postgres psql
```

Dentro de PostgreSQL, elige una contraseña privada:

```sql
CREATE USER dulce_arte_user WITH PASSWORD 'CAMBIA_ESTA_CLAVE';
CREATE DATABASE dulce_arte OWNER dulce_arte_user;
\q
```

Luego:

```bash
sudo adduser --system --group --home /srv/dulce_arte dulcearte
sudo -u dulcearte git clone https://github.com/AmandaAZ04/dulce_arte_backend.git /srv/dulce_arte/app
sudo -u dulcearte python3 -m venv /srv/dulce_arte/venv
sudo -u dulcearte /srv/dulce_arte/venv/bin/pip install --upgrade pip
sudo -u dulcearte /srv/dulce_arte/venv/bin/pip install -r /srv/dulce_arte/app/requirements-deploy.txt
```

## Archivo privado de configuración

```bash
sudo install -d -m 750 -o root -g dulcearte /etc/dulce_arte
sudo cp /srv/dulce_arte/app/deploy/ec2/dulce_arte.env.example /etc/dulce_arte/dulce_arte.env
sudo chown root:dulcearte /etc/dulce_arte/dulce_arte.env
sudo chmod 640 /etc/dulce_arte/dulce_arte.env
sudo nano /etc/dulce_arte/dulce_arte.env
```

Cambia `DJANGO_SECRET_KEY`, `DB_PASSWORD`, `DJANGO_ALLOWED_HOSTS` y `PUBLIC_BASE_URL` con la IP o DNS público. Genera una clave nueva con:

```bash
/srv/dulce_arte/venv/bin/python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

## Migrar y servir estáticos

```bash
cd /srv/dulce_arte/app
sudo -u dulcearte bash -c 'set -a; . /etc/dulce_arte/dulce_arte.env; set +a; /srv/dulce_arte/venv/bin/python manage.py migrate'
sudo -u dulcearte bash -c 'set -a; . /etc/dulce_arte/dulce_arte.env; set +a; /srv/dulce_arte/venv/bin/python manage.py cargar_demo'
sudo -u dulcearte bash -c 'set -a; . /etc/dulce_arte/dulce_arte.env; set +a; /srv/dulce_arte/venv/bin/python manage.py createsuperuser'
sudo install -d -m 755 -o www-data -g www-data /var/www/dulce_arte/static
sudo -u dulcearte bash -c 'set -a; . /etc/dulce_arte/dulce_arte.env; set +a; /srv/dulce_arte/venv/bin/python manage.py collectstatic --noinput'
sudo rsync -a --delete /srv/dulce_arte/app/staticfiles/ /var/www/dulce_arte/static/
```

## Activar Gunicorn y Nginx

```bash
sudo cp /srv/dulce_arte/app/deploy/ec2/dulce_arte.service /etc/systemd/system/dulce_arte.service
sudo cp /srv/dulce_arte/app/deploy/ec2/nginx.conf /etc/nginx/sites-available/dulce_arte
sudo ln -s /etc/nginx/sites-available/dulce_arte /etc/nginx/sites-enabled/dulce_arte
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl daemon-reload
sudo systemctl enable --now dulce_arte nginx
```

Visita `http://TU_IP_PUBLICA/`, luego comprueba `/admin/` y `/equipo/`.

## Diagnóstico y actualización

```bash
sudo systemctl status dulce_arte nginx postgresql --no-pager
sudo journalctl -u dulce_arte -n 80 --no-pager
sudo tail -n 50 /var/log/nginx/error.log
```

Para actualizar:

```bash
cd /srv/dulce_arte/app
sudo -u dulcearte git pull
sudo -u dulcearte /srv/dulce_arte/venv/bin/pip install -r requirements-deploy.txt
sudo -u dulcearte bash -c 'set -a; . /etc/dulce_arte/dulce_arte.env; set +a; /srv/dulce_arte/venv/bin/python manage.py migrate'
sudo -u dulcearte bash -c 'set -a; . /etc/dulce_arte/dulce_arte.env; set +a; /srv/dulce_arte/venv/bin/python manage.py collectstatic --noinput'
sudo rsync -a --delete staticfiles/ /var/www/dulce_arte/static/
sudo systemctl restart dulce_arte
```

No uses `DEBUG=True`, no abras PostgreSQL al exterior y no publiques `.pem`, `.env` ni contraseñas.
