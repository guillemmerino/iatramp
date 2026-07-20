from __future__ import annotations

import copy
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from ...live_cache import mark_live_dirty
from ...models.scoring import (
    PublishedScoreEntry,
    PublishedTeamScoreEntry,
    ScoreEntry,
    ScorePublicationPolicy,
    ScorePublicationState,
    ScoreRevision,
    TeamScoreEntry,
)


@dataclass(frozen=True)
class ScoreWriteActor:
    source: str = ScoreRevision.Source.SYSTEM
    user_id: int | None = None
    judge_token_id: object | None = None


_score_write_actor = ContextVar("score_write_actor", default=ScoreWriteActor())
_recording_suspended = ContextVar("score_revision_recording_suspended", default=False)


@contextmanager
def score_write_context(*, source, user=None, judge_token=None):
    actor = ScoreWriteActor(
        source=str(source or ScoreRevision.Source.SYSTEM),
        user_id=getattr(user, "id", None),
        judge_token_id=getattr(judge_token, "id", None),
    )
    token = _score_write_actor.set(actor)
    try:
        yield
    finally:
        _score_write_actor.reset(token)


@contextmanager
def suspend_score_revision_recording():
    token = _recording_suspended.set(True)
    try:
        yield
    finally:
        _recording_suspended.reset(token)


def publication_mode_for(competicio_id: int) -> str:
    return (
        ScorePublicationPolicy.objects
        .filter(competicio_id=competicio_id)
        .values_list("mode", flat=True)
        .first()
        or ScorePublicationPolicy.Mode.AUTO
    )


def _entry_subject(entry):
    if isinstance(entry, TeamScoreEntry):
        return "team_unit", int(entry.team_subject_id)
    return "inscripcio", int(entry.inscripcio_id)


def _snapshot_entry(entry):
    values = {
        "competicio_id": entry.competicio_id,
        "exercici": entry.exercici,
        "comp_aparell_id": entry.comp_aparell_id,
        "fase_id": entry.fase_id,
        "inputs": copy.deepcopy(entry.inputs or {}),
        "outputs": copy.deepcopy(entry.outputs or {}),
        "total": entry.total,
    }
    if isinstance(entry, TeamScoreEntry):
        values["team_subject_id"] = entry.team_subject_id
        snapshot, _ = PublishedTeamScoreEntry.objects.update_or_create(
            source_entry=entry,
            defaults=values,
        )
    else:
        values["inscripcio_id"] = entry.inscripcio_id
        snapshot, _ = PublishedScoreEntry.objects.update_or_create(
            source_entry=entry,
            defaults=values,
        )
    return snapshot


def _is_empty_initial_entry(entry, created: bool) -> bool:
    if not created:
        return False
    return not (entry.inputs or entry.outputs) and float(entry.total or 0) == 0


@transaction.atomic
def record_score_revision(entry, *, created=False):
    if _recording_suspended.get() or _is_empty_initial_entry(entry, created):
        return None

    actor = _score_write_actor.get()
    subject_kind, subject_id = _entry_subject(entry)
    entry_filter = (
        {"team_score_entry": entry, "score_entry": None}
        if isinstance(entry, TeamScoreEntry)
        else {"score_entry": entry, "team_score_entry": None}
    )
    state = (
        ScorePublicationState.objects
        .select_for_update()
        .filter(**entry_filter)
        .first()
    )
    if state and state.current_revision.publication_status in {
        ScoreRevision.PublicationStatus.PENDING,
        ScoreRevision.PublicationStatus.REJECTED,
    }:
        ScoreRevision.objects.filter(pk=state.current_revision_id).update(
            publication_status=ScoreRevision.PublicationStatus.SUPERSEDED,
        )

    mode = publication_mode_for(entry.competicio_id)
    status = (
        ScoreRevision.PublicationStatus.PUBLISHED
        if mode == ScorePublicationPolicy.Mode.AUTO
        else ScoreRevision.PublicationStatus.PENDING
    )
    revision = ScoreRevision.objects.create(
        competicio_id=entry.competicio_id,
        comp_aparell_id=entry.comp_aparell_id,
        fase_id=entry.fase_id,
        subject_kind=subject_kind,
        subject_id=subject_id,
        exercici=entry.exercici,
        inputs=copy.deepcopy(entry.inputs or {}),
        outputs=copy.deepcopy(entry.outputs or {}),
        total=entry.total,
        source=actor.source,
        actor_user_id=actor.user_id,
        actor_judge_token_id=actor.judge_token_id,
        publication_status=status,
        reviewed_by_id=actor.user_id if status == ScoreRevision.PublicationStatus.PUBLISHED else None,
        reviewed_at=timezone.now() if status == ScoreRevision.PublicationStatus.PUBLISHED else None,
        **entry_filter,
    )
    if state is None:
        state = ScorePublicationState.objects.create(
            current_revision=revision,
            published_revision=revision if status == ScoreRevision.PublicationStatus.PUBLISHED else None,
            **entry_filter,
        )
    else:
        state.current_revision = revision
        if status == ScoreRevision.PublicationStatus.PUBLISHED:
            previous_id = state.published_revision_id
            state.published_revision = revision
            if previous_id and previous_id != revision.id:
                ScoreRevision.objects.filter(pk=previous_id).update(
                    publication_status=ScoreRevision.PublicationStatus.SUPERSEDED,
                )
        state.save(update_fields=["current_revision", "published_revision", "updated_at"])

    if status == ScoreRevision.PublicationStatus.PUBLISHED:
        _snapshot_entry(entry)
        transaction.on_commit(lambda cid=entry.competicio_id: mark_live_dirty(cid, audience="public"))
    transaction.on_commit(lambda cid=entry.competicio_id: mark_live_dirty(cid, audience="internal"))
    return revision


@transaction.atomic
def publish_revision(revision_id: int, *, user):
    revision = ScoreRevision.objects.select_for_update().get(pk=revision_id)
    state_filter = (
        {"team_score_entry_id": revision.team_score_entry_id}
        if revision.team_score_entry_id
        else {"score_entry_id": revision.score_entry_id}
    )
    state = ScorePublicationState.objects.select_for_update().get(**state_filter)
    if state.current_revision_id != revision.id:
        raise ValueError("Aquesta revisio ja ha estat substituida per una versio mes nova.")
    if revision.publication_status == ScoreRevision.PublicationStatus.REJECTED:
        raise ValueError("Una revisio rebutjada no es pot publicar.")
    previous_id = state.published_revision_id
    if previous_id and previous_id != revision.id:
        ScoreRevision.objects.filter(pk=previous_id).update(
            publication_status=ScoreRevision.PublicationStatus.SUPERSEDED,
        )
    revision.publication_status = ScoreRevision.PublicationStatus.PUBLISHED
    revision.reviewed_by = user
    revision.reviewed_at = timezone.now()
    revision.save(update_fields=["publication_status", "reviewed_by", "reviewed_at"])
    state.published_revision = revision
    state.save(update_fields=["published_revision", "updated_at"])
    entry = revision.team_score_entry or revision.score_entry
    _snapshot_entry(entry)
    transaction.on_commit(lambda cid=revision.competicio_id: mark_live_dirty(cid, audience="public"))
    return revision


@transaction.atomic
def reject_revision(revision_id: int, *, user, note: str):
    revision = ScoreRevision.objects.select_for_update().get(pk=revision_id)
    state_filter = (
        {"team_score_entry_id": revision.team_score_entry_id}
        if revision.team_score_entry_id
        else {"score_entry_id": revision.score_entry_id}
    )
    state = ScorePublicationState.objects.select_for_update().get(**state_filter)
    if state.current_revision_id != revision.id:
        raise ValueError("Aquesta revisio ja ha estat substituida per una versio mes nova.")
    if revision.publication_status != ScoreRevision.PublicationStatus.PENDING:
        raise ValueError("La revisio ja no esta pendent.")
    revision.publication_status = ScoreRevision.PublicationStatus.REJECTED
    revision.reviewed_by = user
    revision.reviewed_at = timezone.now()
    revision.review_note = str(note or "").strip()[:500]
    revision.save(update_fields=["publication_status", "reviewed_by", "reviewed_at", "review_note"])
    return revision


def backfill_entry_publication(entry):
    with score_write_context(source=ScoreRevision.Source.SYSTEM):
        revision = record_score_revision(entry, created=False)
    return revision
