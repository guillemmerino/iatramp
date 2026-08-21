import os

from celery import Celery


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iatramp.settings")

app = Celery("iatramp")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
