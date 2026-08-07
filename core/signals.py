from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Person


@receiver(post_save, sender=get_user_model(), dispatch_uid="core_create_person_for_user")
def create_person_for_new_user(sender, instance, created, raw=False, **kwargs):
    if not created or raw:
        return
    Person.objects.get_or_create(
        user=instance,
        defaults={
            "first_name": instance.first_name.strip() or instance.get_username(),
            "last_name": instance.last_name.strip(),
            "email": instance.email,
            "is_provisional": True,
        },
    )
