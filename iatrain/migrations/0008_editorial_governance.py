from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0007_release_organization_models"),
        ("iatrain", "0007_elementrotation_elementrotationsegment_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="knowledgeconcept",
            name="last_validated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="knowledgeconcept",
            name="last_validated_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="validated_knowledge_concepts",
                to="core.person",
            ),
        ),
        migrations.AddField(
            model_name="knowledgerelation",
            name="last_validated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="knowledgerelation",
            name="last_validated_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="validated_knowledge_relations",
                to="core.person",
            ),
        ),
        migrations.AddField(
            model_name="elementrotation",
            name="last_validated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="elementrotation",
            name="last_validated_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="validated_element_rotations",
                to="core.person",
            ),
        ),
        migrations.CreateModel(
            name="KnowledgeEditorialEvent",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("target_model", models.CharField(max_length=100)),
                ("target_id", models.PositiveBigIntegerField()),
                ("target_repr", models.CharField(max_length=255)),
                ("from_status", models.CharField(max_length=20)),
                ("to_status", models.CharField(max_length=20)),
                ("reason", models.TextField(blank=True, default="")),
                ("snapshot", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "decided_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="knowledge_editorial_decisions",
                        to="core.person",
                    ),
                ),
            ],
            options={"ordering": ("-created_at", "-id")},
        ),
        migrations.AddIndex(
            model_name="knowledgeeditorialevent",
            index=models.Index(
                fields=["target_model", "target_id", "created_at"],
                name="iatrain_editorial_target_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="knowledgeeditorialevent",
            index=models.Index(
                fields=["decided_by", "created_at"],
                name="iatrain_editorial_actor_idx",
            ),
        ),
        migrations.AlterField(
            model_name="athleteobservation",
            name="concept",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="athlete_observations",
                to="iatrain.knowledgeconcept",
            ),
        ),
        migrations.AlterField(
            model_name="elementrotation",
            name="element",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="rotation_profile",
                to="iatrain.knowledgeconcept",
            ),
        ),
        migrations.AlterField(
            model_name="elementnotation",
            name="element",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="rotation_notations",
                to="iatrain.knowledgeconcept",
            ),
        ),
        migrations.AlterField(
            model_name="elementnotation",
            name="rotation",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="notations",
                to="iatrain.elementrotation",
            ),
        ),
    ]
