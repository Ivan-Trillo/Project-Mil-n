# Project Milán

Project Milán es un punto de venta web para tiendas pequeñas. Con él puedes cobrar en caja con lector de código de barras, llevar el inventario y los proveedores, ver las ventas del día en un panel y administrar a los empleados por rol. Es mi proyecto final de Ingeniería en Tecnologías de la Información en la Universidad Politécnica de Sinaloa, y lo hice para aprender Django y PostgreSQL.

## Qué hace

- **Caja:** se agregan productos escaneando o buscando por nombre, se pueden tener hasta 10 tickets abiertos, aplicar descuento y cobrar con F2. El ticket se imprime en papel de 58 u 80 mm.
- **Inventario:** alta y edición de productos con foto, categorías, entradas y ajustes de existencia, y aviso cuando un producto tiene poca existencia.
- **Proveedores:** registro de proveedores y a quién se le compra cada producto.
- **Registro de ventas:** consulta por fecha, folio o cajero, reimpresión y cancelación de ventas.
- **Dashboard:** resumen del día, ventas por día y productos más vendidos.
- **Empleados:** alta de usuarios con tres roles, Administrador, Encargado y Cajero.
- **Bitácora:** guarda quién hizo cada cambio importante, solo la ve el Administrador.
- **Configuración:** datos del negocio, IVA y mensaje del ticket.

## Tecnologías

- Python 3.12 o superior
- Django 5.2 LTS
- PostgreSQL 17
- Bootstrap 5.3 y Bootstrap Icons (ya vienen incluidos en `static/vendor`, no se descargan de internet)
- Pillow para las fotos de los productos

Las versiones exactas están en `requirements.txt`.

## Instalación

Necesitas tener instalados Python, PostgreSQL y Git. Los pasos sirven igual para macOS y para Ubuntu Server, solo cambia cómo se instala PostgreSQL.

### 1. Instalar PostgreSQL

En macOS con Homebrew:

```bash
brew install postgresql@17
brew services start postgresql@17
```

En Ubuntu Server:

```bash
sudo apt install postgresql
sudo systemctl enable --now postgresql
```

### 2. Crear la base de datos

Entra a PostgreSQL (en macOS `psql postgres`, en Ubuntu `sudo -u postgres psql`) y crea el usuario y la base de datos:

```sql
CREATE USER milan WITH PASSWORD 'contraseña' CREATEDB;
CREATE DATABASE milan OWNER milan;
\q
```

El permiso `CREATEDB` es para que Django pueda crear la base de datos temporal cuando corres las pruebas.

### 3. Descargar el proyecto e instalar las dependencias

```bash
git clone https://github.com/Ivan-Trillo/Project-Mil-n.git milan
cd milan
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4. Configurar el archivo .env

Copia el archivo de ejemplo y ábrelo para poner tus datos:

```bash
cp .env.example .env
```

| Variable                                                  | Para qué sirve                                                              |
| --------------------------------------------------------- | --------------------------------------------------------------------------- |
| `DJANGO_SECRET_KEY`                                       | Clave secreta de Django, tiene que ser larga y distinta en cada instalación |
| `DJANGO_DEBUG`                                            | `True` mientras desarrollas, `False` en producción                          |
| `DJANGO_ALLOWED_HOSTS`                                    | Direcciones desde donde se abre el sistema, separadas por comas             |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | Datos de la base de datos que creaste en el paso 2                          |
| `TIME_ZONE`                                               | Zona horaria del negocio, por defecto `America/Mazatlan`                    |

Para generar una clave secreta puedes usar:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### 5. Crear las tablas y el primer administrador

```bash
python manage.py migrate
python manage.py createsuperuser
```

Las migraciones crean solas los tres roles. El usuario que creas con `createsuperuser` todavía no tiene rol, así que hay que darle el de Administrador:

```bash
python manage.py shell -c "from cuentas.models import Usuario; from django.contrib.auth.models import Group; Usuario.objects.get(username='TU_USUARIO').groups.set([Group.objects.get(name='Administrador')])"
```

Cambia `TU_USUARIO` por el nombre que pusiste. Los demás empleados ya se dan de alta desde el propio sistema, en la sección Empleados.

## Cómo usarlo

```bash
source .venv/bin/activate
python manage.py runserver
```

Abre http://127.0.0.1:8000 en el navegador y entra con tu administrador. La primera vez el sistema te manda a Configuración para capturar los datos del negocio.

En macOS también puedes usar el script `iniciar.sh`, que enciende PostgreSQL si está apagado, aplica las migraciones y arranca el servidor:

```bash
./iniciar.sh
```

Para usarlo en otras computadoras de la misma red o desde internet, pon `DJANGO_DEBUG=False` y agrega la dirección o el dominio en `DJANGO_ALLOWED_HOSTS`. Las computadoras de caja solo necesitan un navegador. El lector de código de barras tiene que funcionar como teclado (USB o Bluetooth), y la impresora térmica se instala en la computadora como cualquier impresora.

## Pruebas

El proyecto tiene 125 pruebas automatizadas, repartidas en el archivo `tests.py` de cada aplicación. Para correrlas:

```bash
python manage.py test
```

Si quieres ver el nombre de cada prueba, agrega `--verbosity 2`. Muchas pruebas llevan en el nombre el caso de prueba del ESR que verifican, por ejemplo `test_cp_ven_13_cobro_atomico`.

## Respaldos

Se recomienda hacer un respaldo diario de la base de datos. Para hacerlo a mano:

```bash
mkdir -p respaldos
pg_dump -U milan -F c milan > respaldos/milan_$(date +%F).dump
```

Para que se haga solo todos los días a las 11 de la noche, abre `crontab -e` y agrega esta línea (cambia la ruta por donde está tu proyecto):

```
0 23 * * * cd /ruta/a/milan && pg_dump -U milan -F c milan > respaldos/milan_$(date +\%F).dump
```

Para que `pg_dump` no pida la contraseña, guárdala en el archivo `~/.pgpass` con permisos 600.

Para restaurar un respaldo, detén el servidor y corre:

```bash
pg_restore -U milan -d milan --clean --if-exists respaldos/milan_AAAA-MM-DD.dump
```

La carpeta `respaldos/` no se sube a GitHub, está en el `.gitignore`. Lo ideal es copiar los respaldos también a otro disco.

## Estructura del proyecto

| Carpeta                  | Qué contiene                                            |
| ------------------------ | ------------------------------------------------------- |
| `config/`                | Configuración general de Django y las rutas principales |
| `cuentas/`               | Inicio de sesión, roles y empleados                     |
| `productos/`             | Inventario, categorías, movimientos y proveedores       |
| `ventas/`                | Caja, cobro, tickets y registro de ventas               |
| `panel/`                 | Dashboard                                               |
| `auditoria/`             | Bitácora (Three Dots)                                   |
| `configuracion/`         | Datos del negocio                                       |
| `core/`                  | Página de inicio, menú y partes compartidas             |
| `templates/` y `static/` | Plantillas, estilos, JavaScript y Bootstrap             |
| `media/`                 | Fotos de los productos (no se sube a GitHub)            |
| `logs/`                  | Registro de errores del sistema                         |

## Documentación

Los requisitos del sistema están en la Especificación de Requisitos de Software (ESR) del proyecto, hecha con base en la norma ISO/IEC/IEEE 29148.

## Autor

Iván Oswaldo Trillo Zamora, Universidad Politécnica de Sinaloa, 2026.
