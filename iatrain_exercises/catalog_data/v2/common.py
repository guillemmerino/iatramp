"""Small constructors used by the pattern-specific data files.

The resulting dictionaries are deliberately plain data. Django models are not
imported here, so coverage and reference validation can run without a database.
"""

from copy import deepcopy


OBJECTIVE_BY_MODALITY = {
    "strength": "strength",
    "power": "power",
    "muscular_endurance": "muscular_endurance",
    "motor_control": "motor_control",
    "mobility": "mobility",
    "warm_up": "preparation",
}


def action_phase(code, name, intent, description, actions, muscles, phase_type="active"):
    return {
        "code": code,
        "name": name,
        "type": phase_type,
        "intent": intent,
        "key": True,
        "description": description,
        "actions": [
            {"code": action, "role": "primary" if index == 0 else "supporting"}
            for index, action in enumerate(actions)
        ],
        "muscles": [
            {
                "code": muscle,
                "role": role,
                "basis": basis,
                "basis_type": basis_type,
                "contraction": contraction,
            }
            for muscle, role, basis, basis_type, contraction in muscles
        ],
    }


def pair_template(
    *,
    summary,
    setup,
    execution,
    cues,
    outbound_actions,
    return_actions,
    muscles,
    source_refs,
    pattern,
):
    concentric = [(*row, "isometric" if row[3] == "stabilization" else "concentric") for row in muscles]
    eccentric = [(*row, "isometric" if row[3] == "stabilization" else "eccentric") for row in muscles]
    return {
        "summary": summary,
        "setup": setup,
        "execution": execution,
        "cues": cues,
        "movement_pattern": pattern,
        "source_refs": list(source_refs),
        "phases": [
            action_phase(
                "effort",
                "Fase de producció",
                "produce",
                "Es produeix el desplaçament principal de manera observable i controlada.",
                outbound_actions,
                concentric,
            ),
            action_phase(
                "return",
                "Fase de retorn",
                "control",
                "Es retorna a la posició inicial frenant el moviment sense perdre l'organització corporal.",
                return_actions,
                eccentric,
                "recovery",
            ),
        ],
    }


def hold_template(*, summary, setup, execution, cues, muscles, source_refs, pattern="trunk_control"):
    return {
        "summary": summary,
        "setup": setup,
        "execution": execution,
        "cues": cues,
        "movement_pattern": pattern,
        "source_refs": list(source_refs),
        "phases": [
            action_phase(
                "hold",
                "Manteniment",
                "hold",
                "Es manté la posició definida sense un desplaçament angular principal deliberat.",
                (),
                [(*row, "isometric") for row in muscles],
                "hold",
            )
        ],
    }


def variant(
    code,
    name,
    family_code,
    family_name,
    template,
    *,
    equipment=(),
    optional_equipment=(),
    modality="strength",
    execution_type="dynamic",
    difficulty="intermediate",
    laterality="bilateral",
    kinetic_chain="closed",
    objective=None,
    secondary_objective="motor_control",
    note="",
    source_refs=(),
):
    data = deepcopy(template)
    equipment = tuple(equipment)
    optional_equipment = tuple(optional_equipment)
    material = ", ".join(equipment) if equipment else "el pes corporal"
    specific_note = f" {note.strip()}" if note.strip() else ""
    primary_objective = objective or OBJECTIVE_BY_MODALITY[modality]
    objectives = [{"code": primary_objective, "priority": "primary"}]
    if secondary_objective and secondary_objective != primary_objective:
        objectives.append({"code": secondary_objective, "priority": "secondary"})
    if modality == "strength" and not equipment and "muscular_endurance" not in {row["code"] for row in objectives}:
        objectives.append({"code": "muscular_endurance", "priority": "secondary"})
    data.update(
        {
            "family": {"code": family_code, "name": family_name},
            "variant": {"code": code, "name": name},
            "revision": {
                "modality": modality,
                "execution_type": execution_type,
                "difficulty": difficulty,
                "laterality": laterality,
                "kinetic_chain": kinetic_chain,
                "movement_pattern": data.pop("movement_pattern"),
                "description": f"{name}: {data.pop('summary')} La resistència principal prové de {material}.{specific_note}",
                "setup": f"{data.pop('setup')} Prepara i comprova el material abans de començar.",
                "execution": data.pop("execution"),
                "coaching_cues": data.pop("cues"),
                "safety_notes": (
                    "Mantén només el rang i la velocitat que es puguin controlar; atura l'execució "
                    "si es perd la posició definida. Aquesta nota és pràctica i no és una indicació clínica."
                ),
                "requires_equipment": bool(equipment),
            },
            "equipment": [
                {"code": item, "requirement": "required"} for item in equipment
            ]
            + [{"code": item, "requirement": "optional"} for item in optional_equipment],
            "objectives": objectives,
            "constraints": [
                {
                    "code": "controlled_execution",
                    "kind": "requirement",
                    "severity": "important",
                    "statement": "La variant s'executa només amb una posició, trajectòria i rang observables i controlats.",
                }
            ],
            "source_refs": sorted(set(data.pop("source_refs", ())) | set(source_refs)),
        }
    )
    return data


def batch(code, title, variants):
    return {"code": code, "title": title, "variants": list(variants)}
