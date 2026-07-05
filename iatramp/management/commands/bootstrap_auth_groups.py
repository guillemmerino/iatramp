from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from iatramp.auth_groups import GLOBAL_AUTH_GROUPS


class Command(BaseCommand):
    help = "Create the global groups used by IA Tramp."

    def handle(self, *args, **options):
        for name, description in GLOBAL_AUTH_GROUPS.items():
            group, created = Group.objects.get_or_create(name=name)
            status = "created" if created else "exists"
            self.stdout.write(f"{name}: {status} - {description}")