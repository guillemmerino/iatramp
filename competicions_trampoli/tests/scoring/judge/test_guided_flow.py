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
from ....models.rotacions import (
    RotacioAssignacio,
    RotacioAssignacioGrup,
    RotacioEstacio,
    RotacioFranja,
)


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

    def _configure_two_judge_preview(self):
        schema_obj = ScoringSchema.objects.get(aparell=self.aparell)
        schema_obj.schema = {
            "fields": [
                {
                    "label": "Execucio",
                    "code": "E",
                    "type": "matrix",
                    "shape": "judge_x_item",
                    "judges": {"count": 2},
                    "items": {"count": 3},
                    "decimals": 1,
                },
            ],
            "computed": [
                {"code": "ROW", "label": "Per jutge", "formula": "row_custom_compute('E', 'x', return_mode='by_judge')"},
                {"code": "TOTAL", "label": "Total", "formula": "select_sum(ROW, select='all', agg='sum')"},
            ],
        }
        schema_obj.save(update_fields=["schema"])
        self.controller_assignment.permissions = [
            {
                "field_code": "E",
                "judge_index": 1,
                "item_start": 1,
                "item_count": 3,
                "role": "supervisor",
                "display_computed_codes": ["TOTAL"],
            }
        ]
        self.controller_assignment.save(update_fields=["permissions"])

    def test_controller_without_fields_sees_control_panel(self):
        response = self.client.get(reverse(
            "judge_portal_assignment",
            kwargs={"token": self.controller_token.id, "assignment_id": self.controller_assignment.id},
        ))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["judge_flow_enabled"])
        self.assertTrue(response.context["judge_flow_is_controller"])
        self.assertFalse(response.context["schema"]["fields"][0]["supports_individual_presence"])
        self.assertContains(response, "Control de pista")
        self.assertContains(response, "judge-portal-page--guided")
        self.assertContains(response, 'id="guidedPlanSidebar"')
        self.assertContains(response, 'id="guidedPendingSidebar"')
        self.assertContains(response, 'id="guidedPlanToggle"')
        self.assertContains(response, 'id="guidedPendingToggle"')
        self.assertContains(response, 'id="guidedDrawerBackdrop"')
        self.assertContains(response, 'id="guidedStartGroups"')
        self.assertContains(response, 'id="guidedExactPointButton"')
        self.assertContains(response, 'id="guidedPointModal"')
        self.assertContains(response, 'id="guidedExitButton"')
        self.assertContains(response, 'id="guidedExitModal"')
        self.assertContains(response, 'id="guidedSubjectExercisesModal"')
        self.assertContains(response, 'id="guidedExitPublishButton"')
        self.assertContains(response, "Pendent · Reobrir")
        self.assertContains(response, "requestGuidedNavigation")
        self.assertContains(response, 'id="guidedPresenceConfirmModal"')
        self.assertContains(response, 'id="guidedPresenceConfirmAccept"')
        self.assertContains(response, 'id="guidedCurrentExercise"')
        self.assertNotContains(response, 'id="guidedCancelButton"')
        self.assertNotContains(response, 'const accepted = window.confirm(`J${judgeIndex}')
        self.assertContains(response, "parsedVersion < guidedLastAppliedStateVersion")
        self.assertContains(response, "Aquest controlador no te camps de puntuacio assignats")
        self.assertNotContains(response, "Mode competicio")

    def test_runtime_schema_marks_multi_judge_presence_capability(self):
        self._configure_two_judge_preview()

        response = self.client.get(reverse(
            "judge_portal_assignment",
            kwargs={"token": self.controller_token.id, "assignment_id": self.controller_assignment.id},
        ))

        self.assertEqual(response.status_code, 200)
        field = next(item for item in response.context["schema"]["fields"] if item["code"] == "E")
        self.assertTrue(field["supports_individual_presence"])

    def test_single_judge_field_rejects_presence_override_as_defense_in_depth(self):
        opened = self._open()

        response = self.client.post(
            self._url("judge_flow_presence", self.controller_token),
            data=json.dumps({
                "assignment_id": self.controller_assignment.id,
                "window_id": opened.json()["window"]["id"],
                "field_code": "E",
                "judge_index": 1,
                "state": True,
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409, response.content)
        self.assertIn("no admet presencia individual", response.json()["error"])

    def test_guided_plan_uses_rotation_franja_and_configured_order(self):
        second = self._create_inscripcio(self.competicio, "Segona gimnasta", ordre=2, grup=1)
        franja = RotacioFranja.objects.create(
            competicio=self.competicio,
            hora_inici="09:00",
            hora_fi="09:30",
            ordre=1,
            titol="Primera franja",
        )
        estacio = RotacioEstacio.objects.create(
            competicio=self.competicio,
            tipus="aparell",
            comp_aparell=self.comp_aparell,
            ordre=1,
            actiu=True,
        )
        assignacio = RotacioAssignacio.objects.create(
            competicio=self.competicio,
            franja=franja,
            estacio=estacio,
        )
        RotacioAssignacioGrup.objects.create(
            assignacio=assignacio,
            grup=self.inscripcio.grup_competicio,
            ordre=1,
        )
        self.competicio.inscripcions_view = {
            "rotacions_order_modes": {str(franja.id): "rotate"},
        }
        self.competicio.save(update_fields=["inscripcions_view"])

        response = self.client.get(reverse(
            "judge_portal_assignment",
            kwargs={"token": self.controller_token.id, "assignment_id": self.controller_assignment.id},
        ))

        self.assertEqual(response.status_code, 200)
        plan = response.context["guided_plan_json"]
        self.assertEqual(plan[0]["franja_id"], franja.id)
        self.assertIn("Primera franja", plan[0]["label"])
        self.assertEqual(
            [item["subject_id"] for item in plan[0]["groups"][0]["subjects"]],
            [second.id, self.inscripcio.id],
        )

    def test_queue_context_is_snapshotted_and_returned_in_history(self):
        context = {
            "section_key": "franja:7",
            "section_label": "Franja matí",
            "group_key": "1",
            "group_label": "Grup 1",
            "franja_id": 7,
            "group_index": 0,
            "subject_index": 0,
            "queue_index": 3,
        }
        opened = self.client.post(
            self._url("judge_flow_open", self.controller_token),
            data=json.dumps({
                "assignment_id": self.controller_assignment.id,
                "subject_kind": "inscripcio",
                "subject_id": self.inscripcio.id,
                "exercici": 1,
                "queue_context": context,
            }),
            content_type="application/json",
        )

        self.assertEqual(opened.status_code, 200, opened.content)
        self.assertEqual(opened.json()["window"]["competition_context"], context)
        self.assertEqual(opened.json()["history_windows"][0]["competition_context"], context)

    def test_guided_supervisor_crash_reaches_standard_judge_live(self):
        schema_obj = ScoringSchema.objects.get(aparell=self.aparell)
        schema = dict(schema_obj.schema)
        fields = [dict(item) for item in schema.get("fields", [])]
        fields[0]["crash"] = {"enabled": True}
        schema["fields"] = fields
        schema_obj.schema = schema
        schema_obj.save(update_fields=["schema"])
        supervisor_permission = {
            "field_code": "E",
            "judge_index": 1,
            "item_start": 1,
            "item_count": 3,
            "role": "supervisor",
        }
        self.controller_assignment.permissions = [supervisor_permission]
        self.controller_assignment.save(update_fields=["permissions"])
        opened = self._open()
        self.assertEqual(opened.status_code, 200, opened.content)
        window_id = opened.json()["window"]["id"]

        crash = self.client.post(
            self._url("judge_draft_update", self.controller_token),
            data=json.dumps({
                "assignment_id": self.controller_assignment.id,
                "window_id": window_id,
                "subject_kind": "inscripcio",
                "subject_id": self.inscripcio.id,
                "exercici": 1,
                "inputs_patch": {"__crash__E": [2]},
            }),
            content_type="application/json",
        )
        self.assertEqual(crash.status_code, 200, crash.content)
        self.assertEqual(len(crash.json()["drafts"]), 1, crash.json())

        updates = self.client.get(
            f"{self._url('judge_draft_updates', self.standard_token)}?assignment_id={self.standard_assignment.id}"
        )
        self.assertEqual(updates.status_code, 200, updates.content)
        drafts = updates.json()["drafts"]
        self.assertEqual(len(drafts), 1)
        self.assertEqual(
            drafts[0]["normalized_inputs_patch"]["__crash__E"]["__set_list__"],
            [[0, 2]],
        )

    def test_draft_returns_live_computed_preview_and_automatic_presence(self):
        self._configure_two_judge_preview()
        opened = self._open()
        self.assertEqual(opened.status_code, 200, opened.content)

        draft = self.client.post(
            self._url("judge_draft_update", self.standard_token),
            data=json.dumps({
                "assignment_id": self.standard_assignment.id,
                "window_id": opened.json()["window"]["id"],
                "subject_kind": "inscripcio",
                "subject_id": self.inscripcio.id,
                "exercici": 1,
                "inputs_patch": {"E": [[1, 2, 3], [None, None, None]]},
            }),
            content_type="application/json",
        )

        self.assertEqual(draft.status_code, 200, draft.content)
        self.assertNotIn("preview", draft.json())
        state = self.client.get(
            f"{self._url('judge_flow_state', self.controller_token)}?assignment_id={self.controller_assignment.id}"
        )
        self.assertEqual(state.status_code, 200, state.content)
        preview = state.json()["preview"]
        self.assertEqual(preview["automatic_presence"]["E"], [True, False])
        self.assertEqual(preview["presence"]["E"], [True, False])
        self.assertEqual(preview["outputs"]["TOTAL"], 6.0)

    def test_controller_can_override_presence_and_finalization_uses_it(self):
        self._configure_two_judge_preview()
        opened = self._open()
        window_id = opened.json()["window"]["id"]
        initial_draft = self.client.post(
            self._url("judge_draft_update", self.standard_token),
            data=json.dumps({
                "assignment_id": self.standard_assignment.id,
                "window_id": window_id,
                "subject_kind": "inscripcio",
                "subject_id": self.inscripcio.id,
                "exercici": 1,
                "inputs_patch": {"E": [[1, 2, 3], [None, None, None]]},
            }),
            content_type="application/json",
        )
        self.assertEqual(initial_draft.status_code, 200, initial_draft.content)

        forced_valid = self.client.post(
            self._url("judge_flow_presence", self.controller_token),
            data=json.dumps({
                "assignment_id": self.controller_assignment.id,
                "window_id": window_id,
                "field_code": "E",
                "judge_index": 2,
                "state": True,
            }),
            content_type="application/json",
        )
        self.assertEqual(forced_valid.status_code, 200, forced_valid.content)
        self.assertEqual(forced_valid.json()["preview"]["presence"]["E"], [True, True], forced_valid.json())
        self.assertEqual(forced_valid.json()["preview"]["presence_overrides"]["E"], [None, True])

        restored_auto = self.client.post(
            self._url("judge_flow_presence", self.controller_token),
            data=json.dumps({
                "assignment_id": self.controller_assignment.id,
                "window_id": window_id,
                "field_code": "E",
                "judge_index": 2,
                "state": None,
            }),
            content_type="application/json",
        )
        self.assertEqual(restored_auto.status_code, 200, restored_auto.content)
        self.assertEqual(restored_auto.json()["preview"]["presence"]["E"], [True, False])

        forced_invalid = self.client.post(
            self._url("judge_flow_presence", self.controller_token),
            data=json.dumps({
                "assignment_id": self.controller_assignment.id,
                "window_id": window_id,
                "field_code": "E",
                "judge_index": 1,
                "state": False,
            }),
            content_type="application/json",
        )
        self.assertEqual(forced_invalid.status_code, 200, forced_invalid.content)
        self.assertEqual(forced_invalid.json()["preview"]["presence"]["E"], [False, False])
        self.assertEqual(forced_invalid.json()["preview"]["outputs"]["TOTAL"], 0.0)

        forbidden = self.client.post(
            self._url("judge_flow_presence", self.standard_token),
            data=json.dumps({
                "assignment_id": self.standard_assignment.id,
                "window_id": window_id,
                "field_code": "E",
                "judge_index": 1,
                "state": True,
            }),
            content_type="application/json",
        )
        self.assertEqual(forbidden.status_code, 403, forbidden.content)

        self.client.post(
            self._url("judge_flow_close", self.controller_token),
            data=json.dumps({"assignment_id": self.controller_assignment.id, "window_id": window_id}),
            content_type="application/json",
        )
        finalized = self.client.post(
            self._url("judge_flow_finalize", self.controller_token),
            data=json.dumps({"assignment_id": self.controller_assignment.id, "window_id": window_id}),
            content_type="application/json",
        )
        self.assertEqual(finalized.status_code, 200, finalized.content)
        entry = ScoreEntry.objects.get(
            competicio=self.competicio,
            comp_aparell=self.comp_aparell,
            inscripcio=self.inscripcio,
            exercici=1,
        )
        self.assertEqual(entry.inputs["__presence__E"], [False, False])
        self.assertEqual(float(entry.total), 0.0)

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
        self.assertGreater(draft_response.json()["lane_version"], opened.json()["lane_version"])
        self.assertTrue(JudgeScoreDraft.objects.filter(scoring_window_id=window_id).exists())
        state = self.client.get(
            f"{self._url('judge_flow_state', self.controller_token)}?assignment_id={self.controller_assignment.id}"
        )
        self.assertEqual(state.status_code, 200, state.content)
        self.assertEqual(state.json()["window"]["draft_count"], 1)

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

    def test_controller_cannot_duplicate_a_pending_subject_exercise(self):
        opened = self._open()
        window_id = opened.json()["window"]["id"]
        closed = self.client.post(
            self._url("judge_flow_close", self.controller_token),
            data=json.dumps({
                "assignment_id": self.controller_assignment.id,
                "window_id": window_id,
            }),
            content_type="application/json",
        )
        self.assertEqual(closed.status_code, 200, closed.content)

        duplicate = self._open()

        self.assertEqual(duplicate.status_code, 409, duplicate.content)
        self.assertIn("nota pendent", duplicate.json()["error"])
        self.assertEqual(
            JudgeScoringWindow.objects.filter(
                lane=self.lane,
                subject_id=self.inscripcio.id,
                exercici=1,
            ).count(),
            1,
        )

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

        free_portal = self.client.get(reverse(
            "judge_portal_assignment",
            kwargs={"token": self.standard_token.id, "assignment_id": self.standard_assignment.id},
        ))
        self.assertEqual(free_portal.status_code, 200)
        self.assertFalse(free_portal.context["judge_flow_enabled"])
        self.assertNotContains(free_portal, 'id="guidedFlowRoot"')
        self.assertContains(free_portal, "Mode competició")
