"""
Configuracion del sistema web de punto de venta

Todos los datos sensibles (clave secreta, contraseña de la base de datos, etc)
se leen de variables de entorno o del archivo .env, nunca se escriben aquí (RNF-DIS-07)
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

#toma las variables del archivo .env
load_dotenv(BASE_DIR / ".env")


def env_bool(nombre, por_defecto=False):
    """Lee una variable de entorno como verdadero/falso."""
    valor = os.environ.get(nombre)
    if valor is None:
        return por_defecto
    return valor.strip().lower() in ("1", "true", "si", "sí", "yes")


def env_lista(nombre, por_defecto=""):
    """Lee una variable de entorno separada por comas como lista."""
    valor = os.environ.get(nombre, por_defecto)
    return [x.strip() for x in valor.split(",") if x.strip()]


#--- Seguridad basica ---------------------------------------------------------

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = env_lista("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")


#--- Aplicaciones ---------------------------------------------------------------
# Cada modulo de la ERS es una aplicación de Django independiente (RNF-DIS-03)

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
]

PROJECT_APPS = [
    "core",            # plantillas base, paginas de error y utilidades
    "cuentas",         # autenticacion, sesiones y usuarios (3.1.1 y 3.1.5)
    "configuracion",   # configuracion del negocio (3.1.7)
    "productos",       # productos e inventario (3.1.2)
    "ventas",          # caja y ventas (3.1.3)
    "panel",           # panel de control (3.1.4)
    "auditoria",       # bitacora Three Dots (3.1.6)
]

INSTALLED_APPS = DJANGO_APPS + PROJECT_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "cuentas.middleware.CambioPasswordObligatorioMiddleware",
    "configuracion.middleware.ConfiguracionInicialMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.sistema",
            ],
            #filtros de formato disponibles en todas las plantillas sin {% load %}
            "builtins": [
                "django.templatetags.static",
                "core.templatetags.formato",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


#--- Base de datos postgre 17 ------------------------------------

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "milan"),
        "USER": os.environ.get("DB_USER", "milan"),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
        #las transacciones se controlan a mano con transaction.atomic()
        #en las operaciones que tocan varias tablas (RNF-CON-01)
        "ATOMIC_REQUESTS": False,
        "CONN_MAX_AGE": 60,
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


#--- Usuarios y contraseñas ----------------------------------------------------------

#modelo de usuario
AUTH_USER_MODEL = "cuentas.Usuario"

#RNF-SEG-01: Django guarda las contraseñas con PBKDF2 y sal por defecto
#RNF-SEG-02: minimo 8 caracteres y que no sea una contraseña común
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

#RF-AUT-05: la sesion se cierra tras 30 minutos sin actividad.
#cada peticion renueva el plazo, así que solo expira si el usuario deja de usar el sistema esto es supr util
SESSION_COOKIE_AGE = 30 * 60
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "inicio"
LOGOUT_REDIRECT_URL = "login"


#---idioma, zona horaria y formatos (RNF-USA-04, RNF-INT-05) -------------------------

LANGUAGE_CODE = "es-mx"
# Solo español. Sin esta lista, LocaleMiddleware usa el idioma del navegador
# y un navegador en inglés muestra las fechas como "Thursday 19 November"
LANGUAGES = [("es-mx", "Español (México)")]
TIME_ZONE = os.environ.get("TIME_ZONE", "America/Mazatlan")
USE_I18N = True
USE_TZ = True


#---Archivos estaticos ---------------------------------------------------------------

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

#fotos de productos que suben los usuarios
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"


#--- Registro de errores (RNF-CON-04) ---------------------------------------------------
#el detalle tecnico se guarda en logs/sistema.log, el usuario solo ve un mensaje en español

LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "detallado": {
            "format": "{asctime} [{levelname}] {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "consola": {"class": "logging.StreamHandler", "formatter": "detallado"},
        "archivo": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOGS_DIR / "sistema.log",
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "detallado",
            "encoding": "utf-8",
        },
    },
    "root": {"handlers": ["consola", "archivo"], "level": "INFO"},
    "loggers": {
        "django.request": {
            "handlers": ["archivo"],
            "level": "ERROR",
            "propagate": True,
        },
    },
}


#---Ajustes de produccion (RNF-SEG-06, RNF-INT-12, RNF-INT-14) -------------------------
# Solo se activan cuando DEBUG está apagado realmenre no se usan pero es bueno tenerlos

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SSL_REDIRECT", True)
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    CSRF_TRUSTED_ORIGINS = env_lista("DJANGO_CSRF_TRUSTED_ORIGINS")

SESSION_COOKIE_HTTPONLY = True
