import json

from django.test import TestCase
from django.urls import reverse

from ...base import _BaseTrampoliDataMixin
from ....models.judging import (
    JudgeDeviceToken,
    JudgePortalAssignment,
    JudgeScoreDraft,
    JudgeScoringLane,
    JudgeScoringWindow,
)
from ....models.scoring import ScoreEntry, ScoreRevision, ScoringSchema


class JudgeGuidedFlowTests(_BaseTrampoliDataMixin, TestCase):
    def setUp(self):
        self.competicio = self._create_competicio("Comp flux guiat")
        self.aparell = self._create_aparell("TRA_FLOW", "Trampoli flux")
        self.comp_aparell = self._create_comp_aparell(self.competicio, self.aparell)
        ScoringSchema.objects.create(
            aparell=self.aparell,
            schema={
                "fields": [
                    {
                        "label": "Execucio",
                        "code": "E",
                        "type": "matrix",
                        "shape": "judge_x_item",
                        "judges": {"count": 1},
                        "items": {"count": 3},
                        "decimals": 1,
                    },
                ],
                "computed": [{"code": "TOTAL", "label": "Total", "formula": "0"}],
            },
        )
        self.inscripcio = self._create_inscripcio(self.competicio, "Gimnasta guiat")
        self.controller_token = JudgeDeviceToken.objects.create(
            competicio=self.competicio,
            comp_aparell=self.comp_aparell,
            label="Control pista",
            permissions=[],
        )
        self.controller_assignment = JudgePortalAssignment.objects.create(
            judge_token=self.controller_token,
            competicio=self.competicio,
            comp_aparell=self.comp_aparell,
            label="Control pista",
            ordre=1,
            permissions=[],
        )
        self.standard_token = JudgeDeviceToken.objects.create(
            competicio=self.competicio,
            comp_aparell=self.comp_aparell,
            label="Jutge E1",
            permissions=[],
        )
        self.standard_assignment = JudgePortalAssignment.objects.create(
            judge_token=self.standard_token,
            competicio=self.competicio,
            comp_aparell=self.comp_aparell,
            label="Jutge E1",
            ordre=1,
            permissions=[
                {
                    "field_code": "E",
                    "judge_index": 1,
                    "item_start": 1,
                    "item_count": 3,
                    "role": "standard",
                }
            ],
        )
        self.lane = JudgeScoringLane.objects.create(
            competicio=self.competicio,
            comp_aparell=self.comp_aparell,
            is_enabled=True,
            controller_assignment=self.controller_assignment,
        )

    def _url(self, name, token):
        return reverse(name, kwargs={"token": token.id})

    def _open(self):
        return self.client.post(
            self._url("judge_flow_open", self.controller_token),
            data=json.dumps({
                "assignment_id": self.controller_assignment.id,
                "subject_kind": "inscripcio",
                "subject_id": self.inscripcio.id,
                "exercici": 1,
            }),
            content_type="application/json",
        )

    def test_controller_without_fields_sees_control_panel(self):
        response = self.client.get(reverse(
            "judge_portal_assignment",
            kwargs={"token": self.controller_token.id, "assignment_id": self.controller_assignment.id},
        ))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["judge_flow_enabled"])
        self.assertTrue(response.context["judge_flow_is_controller"])
        self.assertContains(response, "Control de pista")
        self.assertContains(response, "Aquest controlador no te camps de puntuacio assignats")
        self.assertNotContains(response, "Mode competicio")

    def test_only_controller_can_open_and_follower_receives_active_subject(self):
        forbidden = self.client.post(
            self._url("judge_flow_open", self.standard_token),
            data=json.dumps({
                "assignment_id": self.standard_assignment.id,
                "subject_kind": "inscripcio",
                "subject_id": self.inscripcio.id,
                "exercici": 1,
            }),
            content_type="application/json",
        )
        self.assertEqual(forbidden.status_code, 403)

        opened = self._open()
        self.assertEqual(opened.status_code, 200, opened.content)
        state = self.client.get(
            f"{self._url('judge_flow_state', self.standard_token)}?assignment_id={self.standard_assignment.id}"
        )
        self.assertEqual(state.status_code, 200)
        self.assertFalse(state.json()["is_controller"])
        self.assertEqual(state.json()["window"]["subject_id"], self.inscripcio.id)

    def test_guided_draft_is_scoped_to_window_and_finalized_once(self):
        opened = self._open()
        self.assertEqual(opened.status_code, 200, opened.content)
        window_id = opened.json()["window"]["id"]

        draft_response = self.client.post(
            self._url("judge_draft_update", self.standard_token),
            data=json.dumps({
                "assignment_id": self.standard_assignment.id,
                "window_id": window_id,
                "subject_kind": "inscripcio",
                "subject_id": self.inscripcio.id,
                "exercici": 1,
                "inputs_patch": {"E": [0.5, 0.6, 0.7]},
            }),
            content_type="application/json",
        )
        self.assertEqual(draft_response.status_code, 200, draft_response.content)
        self.assertTrue(JudgeScoreDraft.objects.filter(scoring_window_id=window_id).exists())

        close = self.client.post(
            self._url("judge_flow_close", self.controller_token),
            data=json.dumps({
                "assignment_id": self.controller_assignment.id,
                "window_id": window_id,
            }),
            content_type="application/json",
        )
        self.assertEqual(close.status_code, 200, close.content)
        finalize = self.client.post(
            self._url("judge_flow_finalize", self.controller_token),
            data=json.dumps({
                "assignment_id": self.controller_assignment.id,
                "window_id": window_id,
            }),
            content_type="application/json",
        )
        self.assertEqual(finalize.status_code, 200, finalize.content)

        window = JudgeScoringWindow.objects.get(pk=window_id)
        self.assertEqual(window.status, JudgeScoringWindow.Status.FINALIZED)
        self.assertFalse(JudgeScoreDraft.objects.filter(scoring_window=window).exists())
        entry = ScoreEntry.objects.get(
            competicio=self.competicio,
            comp_aparell=self.comp_aparell,
            inscripcio=self.inscripcio,
            exercici=1,
        )
        self.assertEqual(entry.inputs["E"][0], [0.5, 0.6, 0.7])
        self.assertEqual(ScoreRevision.objects.filter(score_entry=entry).count(), 1)

    def test_guided_draft_rejects_another_subject(self):
        other = self._create_inscripcio(self.competicio, "Altre gimnasta", ordre=2)
        opened = self._open()
        window_id = opened.json()["window"]["id"]

        response = self.client.post(
            self._url("judge_draft_update", self.standard_token),
            data=json.dumps({
                "assignment_id": self.standard_assignment.id,
                "window_id": window_id,
                "subject_kind": "inscripcio",
                "subject_id": other.id,
                "exercici": 1,
                "inputs_patch": {"E": [0.1, 0.2, 0.3]},
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["reason"], "window_subject_mismatch")

    def test_controller_can_close_and_finalize_without_new_scores(self):
        opened = self._open()
        self.assertEqual(opened.status_code, 200, opened.content)
        window_id = opened.json()["window"]["id"]

        close = self.client.post(
            self._url("judge_flow_close", self.controller_token),
            data=json.dumps({
                "assignment_id": self.controller_assignment.id,
                "window_id": window_id,
            }),
            content_type="application/json",
        )
        self.assertEqual(close.status_code, 200, close.content)

        finalize = self.client.post(
            self._url("judge_flow_finalize", self.controller_token),
            data=json.dumps({
                "assignment_id": self.controller_assignment.id,
                "window_id": window_id,
            }),
            content_type="application/json",
        )
        self.assertEqual(finalize.status_code, 200, finalize.content)
        self.assertEqual(
            JudgeScoringWindow.objects.get(pk=window_id).status,
            JudgeScoringWindow.Status.FINALIZED,
        )
        self.assertFalse(ScoreEntry.objects.filter(
            competicio=self.competicio,
            comp_aparell=self.comp_aparell,
            inscripcio=self.inscripcio,
            exercici=1,
        ).exists())
        self.assertEqual(ScoreRevision.objects.count(), 0)

    def test_controller_finalizes_standard_score_without_supervisor_validation(self):
        supervisor_token = JudgeDeviceToken.objects.create(
            competicio=self.competicio,
            comp_aparell=self.comp_aparell,
            label="Supervisor E",
            permissions=[],
        )
        JudgePortalAssignment.objects.create(
            judge_token=supervisor_token,
            competicio=self.competicio,
            comp_aparell=self.comp_aparell,
            label="Supervisor E",
            ordre=1,
            permissions=[{
                "field_code": "E",
                "judge_index": 1,
                "item_start": 1,
                "item_count": 3,
                "role": "supervisor",
            }],
        )
        opened = self._open()
        window_id = opened.json()["window"]["id"]
        draft = self.client.post(
            self._url("judge_draft_update", self.standard_token),
            data=json.dumps({
                "assignment_id": self.standard_assignment.id,
                "window_id": window_id,
                "subject_kind": "inscripcio",
                "subject_id": self.inscripcio.id,
                "exercici": 1,
                "inputs_patch": {"E": [0.4, 0.5, 0.6]},
            }),
            content_type="application/json",
        )
        self.assertEqual(draft.status_code, 200, draft.content)
        self.client.post(
            self._url("judge_flow_close", self.controller_token),
            data=json.dumps({
                "assignment_id": self.controller_assignment.id,
                "window_id": window_id,
            }),
            content_type="application/json",
        )

        finalize = self.client.post(
            self._url("judge_flow_finalize", self.controller_token),
            data=json.dumps({
                "assignment_id": self.controller_assignment.id,
                "window_id": window_id,
            }),
            content_type="application/json",
        )

        self.assertEqual(finalize.status_code, 200, finalize.content)
        entry = ScoreEntry.objects.get(
            competicio=self.competicio,
            comp_aparell=self.comp_aparell,
            inscripcio=self.inscripcio,
            exercici=1,
        )
        self.assertEqual(entry.inputs["E"][0], [0.4, 0.5, 0.6])

    def test_pending_score_does_not_block_next_subject_and_can_be_published_later(self):
        other = self._create_inscripcio(self.competicio, "Seguent gimnasta", ordre=2)
        first = self._open()
        first_window_id = first.json()["window"]["id"]
        close = self.client.post(
            self._url("judge_flow_close", self.controller_token),
            data=json.dumps({
                "assignment_id": self.controller_assignment.id,
                "window_id": first_window_id,
            }),
            content_type="application/json",
        )
        self.assertEqual(close.status_code, 200, close.content)
        self.assertIsNone(close.json()["window"])
        self.assertEqual(close.json()["pending_windows"][0]["id"], first_window_id)

        second = self.client.post(
            self._url("judge_flow_open", self.controller_token),
            data=json.dumps({
                "assignment_id": self.controller_assignment.id,
                "subject_kind": "inscripcio",
                "subject_id": other.id,
                "exercici": 1,
            }),
            content_type="application/json",
        )
        self.assertEqual(second.status_code, 200, second.content)
        second_window_id = second.json()["window"]["id"]
        self.assertEqual(second.json()["window"]["subject_id"], other.id)
        self.assertEqual(second.json()["pending_windows"][0]["id"], first_window_id)

        publish_first = self.client.post(
            self._url("judge_flow_finalize", self.controller_token),
            data=json.dumps({
                "assignment_id": self.controller_assignment.id,
                "window_id": first_window_id,
            }),
            content_type="application/json",
        )
        self.assertEqual(publish_first.status_code, 200, publish_first.content)
        self.assertEqual(publish_first.json()["window"]["id"], second_window_id)
        self.assertEqual(publish_first.json()["pending_windows"], [])
        self.assertEqual(
            JudgeScoringWindow.objects.get(pk=first_window_id).status,
            JudgeScoringWindow.Status.FINALIZED,
        )
        self.assertEqual(
            JudgeScoringWindow.objects.get(pk=second_window_id).status,
            JudgeScoringWindow.Status.OPEN,
        )

    def test_controller_can_reopen_a_pending_score(self):
        opened = self._open()
        window_id = opened.json()["window"]["id"]
        self.client.post(
            self._url("judge_flow_close", self.controller_token),
            data=json.dumps({
                "assignment_id": self.controller_assignment.id,
                "window_id": window_id,
            }),
            content_type="application/json",
        )

        reopened = self.client.post(
            self._url("judge_flow_reopen", self.controller_token),
            data=json.dumps({
                "assignment_id": self.controller_assignment.id,
                "window_id": window_id,
            }),
            content_type="application/json",
        )

        self.assertEqual(reopened.status_code, 200, reopened.content)
        self.assertEqual(reopened.json()["window"]["id"], window_id)
        self.assertEqual(reopened.json()["window"]["status"], JudgeScoringWindow.Status.OPEN)
        self.assertEqual(reopened.json()["pending_windows"], [])

    def test_organization_can_choose_guided_or_free_mode(self):
        self._login_competicio_user(self.competicio, role="owner", username_prefix="flow_owner")
        url = reverse("qr_admin_detail", kwargs={
            "competicio_id": self.competicio.id,
            "token_id": self.standard_token.id,
        })

        page = self.client.get(url)
        self.assertContains(page, "Flux de competicio")
        self.assertContains(page, "Mode guiat")

        guided = self.client.post(url, data={
            "action": "configure_guided_flow",
            "assignment_id": self.standard_assignment.id,
            "flow_mode": "guided",
            "is_controller": "1",
        })
        self.assertEqual(guided.status_code, 302)
        self.lane.refresh_from_db()
        self.assertTrue(self.lane.is_enabled)
        self.assertEqual(self.lane.controller_assignment_id, self.standard_assignment.id)

        free = self.client.post(url, data={
            "action": "configure_guided_flow",
            "assignment_id": self.standard_assignment.id,
            "flow_mode": "free",
        })
        self.assertEqual(free.status_code, 302)
        self.lane.refresh_from_db()
        self.assertFalse(self.lane.is_enabled)
        self.assertIsNone(self.lane.controller_assignment_id)
