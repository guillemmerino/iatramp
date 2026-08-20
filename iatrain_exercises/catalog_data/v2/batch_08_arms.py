from .common import batch, variant as V
from .templates import ELBOW_EXTENSION, ELBOW_FLEXION


ROWS = [
    V("standing_barbell_curl", "Curl de bíceps amb barra", "elbow_curl", "Flexió de colze amb càrrega", ELBOW_FLEXION, equipment=("barbell",), difficulty="intermediate", kinetic_chain="open"),
    V("standing_dumbbell_curl", "Curl de bíceps amb manuelles", "elbow_curl", "Flexió de colze amb càrrega", ELBOW_FLEXION, equipment=("dumbbell",), difficulty="beginner", kinetic_chain="open"),
    V("alternating_dumbbell_curl", "Curl alternant amb manuelles", "elbow_curl", "Flexió de colze amb càrrega", ELBOW_FLEXION, equipment=("dumbbell",), difficulty="beginner", laterality="alternating", kinetic_chain="open"),
    V("single_arm_cable_curl", "Curl unilateral amb politja", "elbow_curl", "Flexió de colze amb càrrega", ELBOW_FLEXION, equipment=("cable_machine",), difficulty="beginner", laterality="unilateral", kinetic_chain="open"),
    V("bilateral_cable_curl", "Curl bilateral amb politja", "elbow_curl", "Flexió de colze amb càrrega", ELBOW_FLEXION, equipment=("cable_machine",), difficulty="beginner", kinetic_chain="open"),
    V("band_biceps_curl", "Curl de bíceps amb banda", "elbow_curl", "Flexió de colze amb càrrega", ELBOW_FLEXION, equipment=("elastic_band",), difficulty="beginner", kinetic_chain="open"),
    V("seated_dumbbell_curl", "Curl assegut amb manuelles", "elbow_curl", "Flexió de colze amb càrrega", ELBOW_FLEXION, equipment=("dumbbell", "bench"), difficulty="beginner", kinetic_chain="open"),
    V("incline_dumbbell_curl", "Curl inclinat amb manuelles", "elbow_curl", "Flexió de colze amb càrrega", ELBOW_FLEXION, equipment=("dumbbell", "bench"), difficulty="intermediate", kinetic_chain="open"),
    V("preacher_curl_machine", "Curl predicador en màquina", "preacher_curl", "Curl predicador", ELBOW_FLEXION, equipment=("resistance_machine",), difficulty="beginner", kinetic_chain="open"),
    V("dumbbell_concentration_curl", "Curl concentrat amb mancuerna", "elbow_curl", "Flexió de colze amb càrrega", ELBOW_FLEXION, equipment=("dumbbell", "bench"), difficulty="intermediate", laterality="unilateral", kinetic_chain="open"),
    V("dumbbell_hammer_curl", "Curl martell amb manuelles", "elbow_curl", "Flexió de colze amb càrrega", ELBOW_FLEXION, equipment=("dumbbell",), difficulty="beginner", kinetic_chain="open"),
    V("cable_rope_hammer_curl", "Curl martell amb corda de politja", "elbow_curl", "Flexió de colze amb càrrega", ELBOW_FLEXION, equipment=("cable_machine",), difficulty="beginner", kinetic_chain="open"),
    V("cable_triceps_pushdown", "Extensió de colze a politja", "triceps_extension", "Extensió de colze", ELBOW_EXTENSION, equipment=("cable_machine",), difficulty="beginner", kinetic_chain="open"),
    V("rope_triceps_pushdown", "Extensió de colze amb corda de politja", "triceps_extension", "Extensió de colze", ELBOW_EXTENSION, equipment=("cable_machine",), difficulty="beginner", kinetic_chain="open"),
    V("single_arm_cable_triceps_extension", "Extensió unilateral de colze amb politja", "triceps_extension", "Extensió de colze", ELBOW_EXTENSION, equipment=("cable_machine",), difficulty="intermediate", laterality="unilateral", kinetic_chain="open"),
    V("band_triceps_pushdown", "Extensió de colze amb banda", "triceps_extension", "Extensió de colze", ELBOW_EXTENSION, equipment=("elastic_band",), difficulty="beginner", kinetic_chain="open"),
    V("dumbbell_overhead_triceps_extension", "Extensió de colze sobre el cap amb mancuerna", "overhead_triceps_extension", "Extensió de colze sobre el cap", ELBOW_EXTENSION, equipment=("dumbbell",), difficulty="intermediate", kinetic_chain="open"),
    V("single_arm_overhead_triceps_extension", "Extensió unilateral de colze sobre el cap", "overhead_triceps_extension", "Extensió de colze sobre el cap", ELBOW_EXTENSION, equipment=("dumbbell",), difficulty="intermediate", laterality="unilateral", kinetic_chain="open"),
    V("cable_overhead_triceps_extension", "Extensió de colze sobre el cap amb politja", "overhead_triceps_extension", "Extensió de colze sobre el cap", ELBOW_EXTENSION, equipment=("cable_machine",), difficulty="intermediate", kinetic_chain="open"),
    V("barbell_lying_triceps_extension", "Extensió de colze estirat amb barra", "lying_triceps_extension", "Extensió de colze estirat", ELBOW_EXTENSION, equipment=("barbell", "bench"), difficulty="advanced", kinetic_chain="open"),
    V("dumbbell_lying_triceps_extension", "Extensió de colze estirat amb manuelles", "lying_triceps_extension", "Extensió de colze estirat", ELBOW_EXTENSION, equipment=("dumbbell", "bench"), difficulty="intermediate", kinetic_chain="open"),
    V("bench_dip_bent_knees", "Fons de tríceps al banc amb genolls flexionats", "bench_dip", "Fons al banc", ELBOW_EXTENSION, equipment=("bench",), difficulty="beginner", kinetic_chain="closed"),
    V("bench_dip_straight_legs", "Fons de tríceps al banc amb cames esteses", "bench_dip", "Fons al banc", ELBOW_EXTENSION, equipment=("bench",), difficulty="intermediate", kinetic_chain="closed"),
    V("assisted_dip_machine", "Fons assistit en màquina", "dip", "Fons", ELBOW_EXTENSION, equipment=("resistance_machine",), difficulty="beginner", kinetic_chain="closed"),
    V("parallel_bar_dip", "Fons en paral·leles", "dip", "Fons", ELBOW_EXTENSION, equipment=("resistance_machine",), difficulty="advanced", kinetic_chain="closed", objective="max_strength"),
]

BATCH = batch("08_arms", "Flexió i extensió de colze", ROWS)

