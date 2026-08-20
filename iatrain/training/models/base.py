from django.core.exceptions import ValidationError
from django.db import models


class CleanOnSaveModel(models.Model):
    """Keep domain invariants active outside forms and the admin."""

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class RevisionOwnedModel(CleanOnSaveModel):
    """A planning detail that can only change while its revision is a draft."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def owning_revision(self):
        raise NotImplementedError

    def assert_revision_is_draft(self):
        revision = self.owning_revision()
        if revision and revision.pk:
            current_status = type(revision).objects.filter(pk=revision.pk).values_list(
                "status", flat=True
            ).first()
        else:
            current_status = getattr(revision, "status", None)
        if revision and current_status != "draft":
            raise ValidationError(
                "El detall d'una sessió només es pot modificar mentre la versió és un esborrany."
            )

    def clean(self):
        super().clean()
        self.assert_revision_is_draft()

    def delete(self, *args, **kwargs):
        self.assert_revision_is_draft()
        return super().delete(*args, **kwargs)
