from django.db.models import Q
from django.utils import timezone
from django.views.generic import TemplateView

from .models import Person


class PlatformContextMixin:
    def get_platform_identity(self):
        user = self.request.user
        person = None
        memberships = []
        if user.is_authenticated:
            person = Person.objects.filter(user=user, is_active=True).first()
            if person is not None:
                today = timezone.localdate()
                memberships = list(
                    person.memberships.filter(
                        is_active=True,
                        organization__is_active=True,
                        start_date__lte=today,
                    )
                    .filter(Q(end_date__isnull=True) | Q(end_date__gte=today))
                    .select_related("organization")
                    .order_by("organization__name", "role")
                )
        return person, memberships

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        person, memberships = self.get_platform_identity()
        user = self.request.user
        if person is not None:
            display_name = person.display_name
        elif user.is_authenticated:
            display_name = user.get_full_name().strip() or user.get_username()
        else:
            display_name = "Visitant"
        initials = "".join(part[:1] for part in display_name.split()[:2]).upper() or "IA"
        context.update(
            {
                "platform_person": person,
                "platform_memberships": memberships,
                "platform_display_name": display_name,
                "platform_initials": initials,
            }
        )
        return context


class PlatformHomeView(PlatformContextMixin, TemplateView):
    template_name = "core/platform_home.html"


class PlatformSettingsView(PlatformContextMixin, TemplateView):
    template_name = "core/platform_settings.html"

