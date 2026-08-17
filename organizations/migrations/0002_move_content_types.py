from django.db import migrations


MODEL_NAMES = (
    "organization",
    "membership",
    "membershiprole",
    "membershippermission",
    "organizationmembershiprequest",
    "organizationmembershiprequestrole",
)


def _move_content_types(apps, *, source_label, target_label):
    ContentType = apps.get_model("contenttypes", "ContentType")
    for model_name in MODEL_NAMES:
        source = ContentType.objects.filter(
            app_label=source_label,
            model=model_name,
        ).first()
        target = ContentType.objects.filter(
            app_label=target_label,
            model=model_name,
        ).first()
        if source is None:
            continue
        if target is not None and target.pk != source.pk:
            raise RuntimeError(
                f"ContentType collision for {target_label}.{model_name}; "
                "resolve it before applying the organization ownership migration."
            )
        source.app_label = target_label
        source.save(update_fields=("app_label",))


def forwards(apps, schema_editor):
    _move_content_types(
        apps,
        source_label="core",
        target_label="organizations",
    )


def backwards(apps, schema_editor):
    _move_content_types(
        apps,
        source_label="organizations",
        target_label="core",
    )


class Migration(migrations.Migration):
    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        ("core", "0007_release_organization_models"),
        ("organizations", "0001_adopt_core_organization_models"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]

