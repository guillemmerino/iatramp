from decimal import Decimal, InvalidOperation

from django.db import migrations


TOTAL_CODES = ("TOTAL", "total", "tot")
BATCH_SIZE = 500


def _output_total(outputs):
    if not isinstance(outputs, dict):
        return None
    for code in TOTAL_CODES:
        if code not in outputs:
            continue
        try:
            value = Decimal(str(outputs[code]))
        except (InvalidOperation, TypeError, ValueError):
            return None
        return value if value.is_finite() else None
    return None


def _backfill_model(model):
    pending = []
    queryset = model.objects.filter(total=0).only("id", "outputs", "total")
    for item in queryset.iterator(chunk_size=BATCH_SIZE):
        total = _output_total(item.outputs)
        if total is None or total == 0:
            continue
        item.total = total
        pending.append(item)
        if len(pending) >= BATCH_SIZE:
            model.objects.bulk_update(pending, ["total"], batch_size=BATCH_SIZE)
            pending = []
    if pending:
        model.objects.bulk_update(pending, ["total"], batch_size=BATCH_SIZE)


def backfill_tot_score_values(apps, schema_editor):
    for model_name in (
        "ScoreEntry",
        "TeamScoreEntry",
        "ScoreRevision",
        "PublishedScoreEntry",
        "PublishedTeamScoreEntry",
    ):
        _backfill_model(apps.get_model("competicions_trampoli", model_name))


class Migration(migrations.Migration):
    dependencies = [
        ("competicions_trampoli", "0076_score_publication_workflow"),
    ]

    operations = [
        migrations.RunPython(backfill_tot_score_values, migrations.RunPython.noop),
    ]
