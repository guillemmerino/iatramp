from celery import shared_task
from django.contrib.auth import get_user_model

from iatrain.engine.services import execute_block_generation_run
from iatrain.models import BlockGenerationRun


@shared_task(ignore_result=True, name="iatrain.execute_block_generation")
def execute_block_generation_task(run_id, user_id):
    run = BlockGenerationRun.objects.get(pk=run_id)
    user = get_user_model().objects.get(pk=user_id)
    execute_block_generation_run(user=user, run=run)
