import importlib.util
import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_csv(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in str(raw).split(",") if item.strip()]


def _env_str(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or "").strip()


APP_ENV = _env_str("APP_ENV", "dev")
SECRET_KEY = _env_str("DJANGO_SECRET_KEY", "dev-only-change-me")
if APP_ENV == "prod" and SECRET_KEY in {"", "dev-only-change-me", "change-me"}:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY is required when APP_ENV=prod")

DEBUG = _env_bool("DEBUG", APP_ENV != "prod")
ALLOWED_HOSTS = _env_csv("ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = _env_csv("CSRF_TRUSTED_ORIGINS", "")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "iatramp",
    "core.apps.CoreConfig",
    "organizations.apps.OrganizationsConfig",
    "iatrain.apps.IatrainConfig",
    "iatrain_motion.apps.IatrainMotionConfig",
    "competicions_trampoli",
]
if importlib.util.find_spec("django_celery_results") is not None:
    INSTALLED_APPS.append("django_celery_results")

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "iatramp.urls"
WSGI_APPLICATION = "iatramp.wsgi.application"
ASGI_APPLICATION = "iatramp.asgi.application"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.debug",
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "iatramp.context_processors.app_env",
        "core.context_processors.assistant",
        "core.context_processors.platform_notifications",
    ]},
}]

POSTGRES_DB = os.getenv("POSTGRES_DB")
if POSTGRES_DB:
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": POSTGRES_DB,
        "USER": os.getenv("POSTGRES_USER"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD"),
        "HOST": os.getenv("POSTGRES_HOST", "db"),
        "PORT": os.getenv("POSTGRES_PORT", "5432"),
    }}
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

LANGUAGE_CODE = "ca"
TIME_ZONE = "Europe/Madrid"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = os.getenv("STATIC_ROOT", str(BASE_DIR / "var" / "static"))
STATIC_VERSION = _env_str("STATIC_VERSION", "dev-1")

MEDIA_URL = os.getenv("MEDIA_URL", "/media/")
MEDIA_ROOT = os.getenv("MEDIA_ROOT", str(BASE_DIR / "media"))

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
X_FRAME_OPTIONS = "SAMEORIGIN"
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/competicions/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

DATA_UPLOAD_MAX_NUMBER_FILES = int(os.getenv("DATA_UPLOAD_MAX_NUMBER_FILES", "500"))
DATA_UPLOAD_MAX_MEMORY_SIZE = int(os.getenv("DATA_UPLOAD_MAX_MEMORY_SIZE", str(150 * 1024 * 1024)))
FILE_UPLOAD_MAX_MEMORY_SIZE = int(os.getenv("FILE_UPLOAD_MAX_MEMORY_SIZE", str(10 * 1024 * 1024)))
JUDGE_VIDEO_FFPROBE_BIN = os.getenv("JUDGE_VIDEO_FFPROBE_BIN", "ffprobe")
JUDGE_VIDEO_FFPROBE_TIMEOUT_SECONDS = int(os.getenv("JUDGE_VIDEO_FFPROBE_TIMEOUT_SECONDS", "15"))

COMPETICIONS_APP_FONT_FAMILY = _env_str("COMPETICIONS_APP_FONT_FAMILY", "")
COMPETICIONS_APP_FONT_FOLDER = _env_str("COMPETICIONS_APP_FONT_FOLDER", "")
COMPETICIONS_APP_FONT_FILES = None

REDIS_URL = os.getenv("REDIS_URL", os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0"))
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", REDIS_URL)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "django-db")

EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "no-reply@iatramp.local")

OPENAI_API_KEY = _env_str("OPENAI_API_KEY", "")
OPENAI_AVATAR_MODEL = _env_str("OPENAI_AVATAR_MODEL", "gpt-5.5")
OPENAI_AVATAR_TIMEOUT_SECONDS = int(os.getenv("OPENAI_AVATAR_TIMEOUT_SECONDS", "30"))

if _env_bool("USE_X_FORWARDED_PROTO", False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
if APP_ENV == "prod":
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = _env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", True)
    SECURE_HSTS_PRELOAD = _env_bool("SECURE_HSTS_PRELOAD", False)
