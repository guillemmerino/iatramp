from .common import batch, variant as V
from .templates import SHOULDER_ABDUCTION, SHOULDER_EXTERNAL_ROTATION, VERTICAL_PRESS


ROWS = [
    V("standing_barbell_overhead_press", "Press militar dempeus amb barra", "overhead_press", "Press vertical", VERTICAL_PRESS, equipment=("barbell",), difficulty="advanced", kinetic_chain="open", objective="max_strength"),
    V("seated_barbell_overhead_press", "Press militar assegut amb barra", "overhead_press", "Press vertical", VERTICAL_PRESS, equipment=("barbell", "bench"), difficulty="advanced", kinetic_chain="open", objective="max_strength"),
    V("standing_dumbbell_overhead_press", "Press vertical dempeus amb manuelles", "overhead_press", "Press vertical", VERTICAL_PRESS, equipment=("dumbbell",), difficulty="intermediate", kinetic_chain="open"),
    V("seated_dumbbell_overhead_press", "Press vertical assegut amb manuelles", "overhead_press", "Press vertical", VERTICAL_PRESS, equipment=("dumbbell", "bench"), difficulty="beginner", kinetic_chain="open"),
    V("neutral_grip_dumbbell_press", "Press vertical amb presa neutra", "overhead_press", "Press vertical", VERTICAL_PRESS, equipment=("dumbbell",), difficulty="intermediate", kinetic_chain="open"),
    V("alternating_dumbbell_overhead_press", "Press vertical alternant amb manuelles", "overhead_press", "Press vertical", VERTICAL_PRESS, equipment=("dumbbell",), difficulty="advanced", laterality="alternating", kinetic_chain="open", modality="motor_control"),
    V("single_arm_dumbbell_overhead_press", "Press vertical unilateral amb mancuerna", "overhead_press", "Press vertical", VERTICAL_PRESS, equipment=("dumbbell",), difficulty="advanced", laterality="unilateral", kinetic_chain="mixed", modality="motor_control"),
    V("single_arm_kettlebell_press", "Press vertical unilateral amb kettlebell", "overhead_press", "Press vertical", VERTICAL_PRESS, equipment=("kettlebell",), difficulty="advanced", laterality="unilateral", kinetic_chain="mixed"),
    V("half_kneeling_single_arm_press", "Press unilateral des de mig agenollat", "overhead_press", "Press vertical", VERTICAL_PRESS, equipment=("dumbbell", "mat"), difficulty="intermediate", laterality="unilateral", kinetic_chain="mixed", modality="motor_control"),
    V("landmine_press_bilateral", "Press bilateral amb landmine", "landmine_press", "Press amb landmine", VERTICAL_PRESS, equipment=("barbell", "landmine"), difficulty="beginner", kinetic_chain="mixed"),
    V("half_kneeling_landmine_press", "Press unilateral amb landmine des de mig agenollat", "landmine_press", "Press amb landmine", VERTICAL_PRESS, equipment=("barbell", "landmine", "mat"), difficulty="intermediate", laterality="unilateral", kinetic_chain="mixed", modality="motor_control"),
    V("machine_shoulder_press", "Press bilateral d'espatlles en màquina", "machine_shoulder_press_family", "Press d'espatlles en màquina", VERTICAL_PRESS, equipment=("resistance_machine",), difficulty="beginner", kinetic_chain="open"),
    V("cable_overhead_press", "Press vertical bilateral amb politja", "cable_overhead_press_family", "Press vertical amb politja", VERTICAL_PRESS, equipment=("cable_machine",), difficulty="intermediate", kinetic_chain="open"),
    V("band_overhead_press", "Press vertical bilateral amb banda", "band_overhead_press_family", "Press vertical amb banda", VERTICAL_PRESS, equipment=("elastic_band",), difficulty="beginner", kinetic_chain="open"),
    V("pike_push_up", "Flexió de braços en posició de V invertida", "pike_push_up_family", "Flexió vertical", VERTICAL_PRESS, optional_equipment=("mat",), difficulty="intermediate", kinetic_chain="closed"),
    V("feet_elevated_pike_push_up", "Flexió vertical amb peus elevats", "pike_push_up_family", "Flexió vertical", VERTICAL_PRESS, equipment=("bench",), difficulty="advanced", kinetic_chain="closed"),
    V("wall_assisted_handstand_push_up", "Flexió vertical invertida assistida a la paret", "handstand_push_up", "Flexió vertical invertida", VERTICAL_PRESS, equipment=("wall",), difficulty="advanced", kinetic_chain="closed", objective="max_strength"),
    V("dumbbell_lateral_raise", "Elevació lateral amb manuelles", "lateral_raise", "Elevació lateral", SHOULDER_ABDUCTION, equipment=("dumbbell",), difficulty="beginner", kinetic_chain="open"),
    V("single_arm_cable_lateral_raise", "Elevació lateral unilateral amb politja", "lateral_raise", "Elevació lateral", SHOULDER_ABDUCTION, equipment=("cable_machine",), difficulty="intermediate", laterality="unilateral", kinetic_chain="open"),
    V("band_lateral_raise", "Elevació lateral amb banda", "lateral_raise", "Elevació lateral", SHOULDER_ABDUCTION, equipment=("elastic_band",), difficulty="beginner", kinetic_chain="open"),
    V("machine_lateral_raise", "Elevació lateral en màquina", "lateral_raise", "Elevació lateral", SHOULDER_ABDUCTION, equipment=("resistance_machine",), difficulty="beginner", kinetic_chain="open"),
    V("lean_away_cable_lateral_raise", "Elevació lateral inclinada amb politja", "lateral_raise", "Elevació lateral", SHOULDER_ABDUCTION, equipment=("cable_machine",), difficulty="advanced", laterality="unilateral", kinetic_chain="open"),
    V("side_lying_dumbbell_lateral_raise", "Elevació lateral estirat de costat", "lateral_raise", "Elevació lateral", SHOULDER_ABDUCTION, equipment=("dumbbell", "bench"), difficulty="intermediate", laterality="unilateral", kinetic_chain="open"),
    V("cable_external_rotation_elbow_near_body", "Rotació externa amb politja i colze al costat", "shoulder_external_rotation", "Rotació externa d'espatlla", SHOULDER_EXTERNAL_ROTATION, equipment=("cable_machine",), difficulty="beginner", laterality="unilateral", kinetic_chain="open"),
    V("side_lying_dumbbell_external_rotation", "Rotació externa amb mancuerna en decúbit lateral", "shoulder_external_rotation", "Rotació externa d'espatlla", SHOULDER_EXTERNAL_ROTATION, equipment=("dumbbell", "mat"), difficulty="beginner", laterality="unilateral", kinetic_chain="open"),
    V("band_external_rotation_abducted", "Rotació externa amb banda i braç elevat", "shoulder_external_rotation", "Rotació externa d'espatlla", SHOULDER_EXTERNAL_ROTATION, equipment=("elastic_band",), difficulty="intermediate", laterality="unilateral", kinetic_chain="open", modality="motor_control"),
    V("cable_external_rotation_abducted", "Rotació externa amb politja i braç elevat", "shoulder_external_rotation", "Rotació externa d'espatlla", SHOULDER_EXTERNAL_ROTATION, equipment=("cable_machine",), difficulty="advanced", laterality="unilateral", kinetic_chain="open", modality="motor_control"),
    V("bilateral_band_external_rotation", "Rotació externa bilateral amb banda", "shoulder_external_rotation", "Rotació externa d'espatlla", SHOULDER_EXTERNAL_ROTATION, equipment=("elastic_band",), difficulty="beginner", kinetic_chain="open", modality="warm_up", objective="preparation"),
]

BATCH = batch("06_vertical_shoulder", "Empenta vertical i espatlla", ROWS)
