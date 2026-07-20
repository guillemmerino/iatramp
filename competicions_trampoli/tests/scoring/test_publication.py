import json

from django.test import TestCase
from django.urls import reverse

from ...models import CompeticioMembership
from ...models.scoring import (
    PublishedScoreEntry,
    ScoreEntry,
    ScorePublicationPolicy,
    ScorePublicationState,
    ScoreRevision,
)
from ...services.classificacions.engine.loaders import (
    classification_score_audience,
    load_score_entries,
)
from ...services.scoring.publication import score_write_context
from ..base import _BaseTrampoliDataMixin


class ScorePublicationWorkflowTests(_BaseTrampoliDataMixin, TestCase):
    def setUp(self):
        self.comp = self._create_competicio("Comp publicacio")
        self.user = self._login_competicio_user(
            self.comp,
            role=CompeticioMembership.Role.OWNER,
            username_prefix="publication_owner",
        )
        self.app = self._create_aparell("PUB_DMT", "DMT")
        self.comp_app = self._create_comp_aparell(self.comp, self.app)
        self.ins = self._create_inscripcio(self.comp, "Anna Publicacio")

    def _create_score(self, total):
        return ScoreEntry.objects.create(
            competicio=self.comp,
            inscripcio=self.ins,
            comp_aparell=self.comp_app,
            exercici=1,
            inputs={"E": total},
            outputs={"total": total},
            total=total,
        )

    def test_auto_mode_creates_revision_and_public_snapshot(self):
        entry = self._create_score(10)

        revision = ScoreRevision.objects.get(score_entry=entry)
        self.assertEqual(revision.publication_status, ScoreRevision.PublicationStatus.PUBLISHED)
        self.assertEqual(float(PublishedScoreEntry.objects.get(source_entry=entry).total), 10.0)
        self.assertEqual(entry.publication_state.current_revision_id, revision.id)
        self.assertEqual(entry.publication_state.published_revision_id, revision.id)

    def test_review_mode_keeps_previous_public_score_until_publish(self):
        entry = self._create_score(10)
        ScorePublicationPolicy.objects.create(
            competicio=self.comp,
            mode=ScorePublicationPolicy.Mode.ORGANIZATION_REVIEW,
            changed_by=self.user,
        )

        entry.inputs = {"E": 12}
        entry.outputs = {"total": 12}
        entry.total = 12
        with score_write_context(source=ScoreRevision.Source.ORGANIZATION, user=self.user):
            entry.save(update_fields=["inputs", "outputs", "total", "updated_at"])

        state = ScorePublicationState.objects.select_related("current_revision").get(score_entry=entry)
        pending = state.current_revision
        self.assertEqual(pending.publication_status, ScoreRevision.PublicationStatus.PENDING)
        self.assertEqual(float(PublishedScoreEntry.objects.get(source_entry=entry).total), 10.0)

        response = self.client.post(
            reverse("scoring_publication_publish", kwargs={"pk": self.comp.id}),
            data=json.dumps({"revision_ids": [pending.id]}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(float(PublishedScoreEntry.objects.get(source_entry=entry).total), 12.0)

    def test_public_classification_loader_uses_published_snapshot(self):
        entry = self._create_score(8)
        ScorePublicationPolicy.objects.create(
            competicio=self.comp,
            mode=ScorePublicationPolicy.Mode.ORGANIZATION_REVIEW,
        )
        entry.total = 9
        entry.outputs = {"total": 9}
        entry.save(update_fields=["outputs", "total", "updated_at"])

        internal = load_score_entries(
            self.comp,
            inscripcions=[self.ins],
            aparells=[self.comp_app],
        )
        with classification_score_audience("public"):
            public = load_score_entries(
                self.comp,
                inscripcions=[self.ins],
                aparells=[self.comp_app],
            )

        self.assertEqual(float(internal[0].total), 9.0)
        self.assertEqual(float(public[0].total), 8.0)

    def test_cannot_disable_review_mode_with_pending_revisions(self):
        ScorePublicationPolicy.objects.create(
            competicio=self.comp,
            mode=ScorePublicationPolicy.Mode.ORGANIZATION_REVIEW,
        )
        self._create_score(7)

        response = self.client.post(
            reverse("scoring_publication_policy", kwargs={"pk": self.comp.id}),
            data=json.dumps({"mode": "auto"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn("resoldre", response.json()["error"])

    def test_activity_exposes_recent_pending_correction(self):
        entry = self._create_score(7)
        ScorePublicationPolicy.objects.create(
            competicio=self.comp,
            mode=ScorePublicationPolicy.Mode.ORGANIZATION_REVIEW,
        )
        entry.total = 8
        entry.outputs = {"total": 8}
        with score_write_context(source=ScoreRevision.Source.ORGANIZATION, user=self.user):
            entry.save(update_fields=["outputs", "total", "updated_at"])

        response = self.client.get(
            reverse("scoring_publication_activity", kwargs={"pk": self.comp.id}),
            {"status": ScoreRevision.PublicationStatus.PENDING, "q": "Anna"},
        )

        self.assertEqual(response.status_code, 200)
        activity = response.json()["activity"]
        self.assertEqual(len(activity), 1)
        self.assertEqual(activity[0]["subject_name"], "Anna Publicacio")
        self.assertEqual(activity[0]["source"], ScoreRevision.Source.ORGANIZATION)
        self.assertTrue(activity[0]["is_correction"])
        self.assertEqual(activity[0]["published_total"], 7.0)

    def test_superseded_revision_cannot_be_published(self):
        entry = self._create_score(5)
        ScorePublicationPolicy.objects.create(
            competicio=self.comp,
            mode=ScorePublicationPolicy.Mode.ORGANIZATION_REVIEW,
        )
        entry.total = 6
        entry.save(update_fields=["total", "updated_at"])
        stale_revision_id = ScorePublicationState.objects.get(score_entry=entry).current_revision_id
        entry.refresh_from_db()
        entry.total = 7
        entry.save(update_fields=["total", "updated_at"])

        response = self.client.post(
            reverse("scoring_publication_publish", kwargs={"pk": self.comp.id}),
            data=json.dumps({"revision_ids": [stale_revision_id]}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            ScoreRevision.objects.get(pk=stale_revision_id).publication_status,
            ScoreRevision.PublicationStatus.SUPERSEDED,
        )
        self.assertEqual(float(PublishedScoreEntry.objects.get(source_entry=entry).total), 5.0)

    def test_rejecting_correction_keeps_last_public_score(self):
        entry = self._create_score(9)
        ScorePublicationPolicy.objects.create(
            competicio=self.comp,
            mode=ScorePublicationPolicy.Mode.ORGANIZATION_REVIEW,
        )
        entry.total = 11
        entry.save(update_fields=["total", "updated_at"])
        revision_id = ScorePublicationState.objects.get(score_entry=entry).current_revision_id

        response = self.client.post(
            reverse("scoring_publication_reject", kwargs={"pk": self.comp.id}),
            data=json.dumps({"revision_id": revision_id, "note": "Cal revisar la dificultat"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        revision = ScoreRevision.objects.get(pk=revision_id)
        self.assertEqual(revision.publication_status, ScoreRevision.PublicationStatus.REJECTED)
        self.assertEqual(revision.review_note, "Cal revisar la dificultat")
        self.assertEqual(float(PublishedScoreEntry.objects.get(source_entry=entry).total), 9.0)

    def test_readonly_user_cannot_publish(self):
        ScorePublicationPolicy.objects.create(
            competicio=self.comp,
            mode=ScorePublicationPolicy.Mode.ORGANIZATION_REVIEW,
        )
        entry = self._create_score(7)
        self.client.logout()
        self._login_competicio_user(
            self.comp,
            role=CompeticioMembership.Role.READONLY,
            username_prefix="publication_readonly",
        )

        response = self.client.post(
            reverse("scoring_publication_publish", kwargs={"pk": self.comp.id}),
            data=json.dumps({"revision_ids": [entry.publication_state.current_revision_id]}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)

    def test_deleting_score_cascades_publication_records(self):
        entry = self._create_score(6)
        entry_id = entry.id
        revision_id = entry.publication_state.current_revision_id

        entry.delete()

        self.assertFalse(ScoreRevision.objects.filter(pk=revision_id).exists())
        self.assertFalse(PublishedScoreEntry.objects.filter(source_entry_id=entry_id).exists())
