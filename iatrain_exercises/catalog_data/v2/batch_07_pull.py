from .common import batch, variant as V
from .templates import HORIZONTAL_ROW, REAR_PULL, VERTICAL_PULL


ROWS = [
    V("barbell_bent_over_row", "Rem inclinat amb barra", "row", "Rem", HORIZONTAL_ROW, equipment=("barbell",), difficulty="advanced", kinetic_chain="open", objective="max_strength"),
    V("underhand_barbell_row", "Rem inclinat amb barra i presa supina", "row", "Rem", HORIZONTAL_ROW, equipment=("barbell",), difficulty="advanced", kinetic_chain="open"),
    V("double_dumbbell_bent_over_row", "Rem inclinat amb dues manuelles", "row", "Rem", HORIZONTAL_ROW, equipment=("dumbbell",), difficulty="intermediate", kinetic_chain="open"),
    V("single_arm_dumbbell_row_bench", "Rem unilateral amb mancuerna i banc", "row", "Rem", HORIZONTAL_ROW, equipment=("dumbbell", "bench"), difficulty="beginner", laterality="unilateral", kinetic_chain="open"),
    V("single_arm_kettlebell_row", "Rem unilateral amb kettlebell", "row", "Rem", HORIZONTAL_ROW, equipment=("kettlebell",), difficulty="intermediate", laterality="unilateral", kinetic_chain="open"),
    V("chest_supported_dumbbell_row", "Rem amb manuelles i pit recolzat", "supported_row", "Rem amb suport", HORIZONTAL_ROW, equipment=("dumbbell", "bench"), difficulty="beginner", kinetic_chain="open"),
    V("chest_supported_barbell_row", "Rem amb barra i pit recolzat", "supported_row", "Rem amb suport", HORIZONTAL_ROW, equipment=("barbell", "bench"), difficulty="intermediate", kinetic_chain="open"),
    V("seated_cable_row_neutral", "Rem assegut amb politja i presa neutra", "cable_row", "Rem amb politja", HORIZONTAL_ROW, equipment=("cable_machine",), difficulty="beginner", kinetic_chain="open"),
    V("seated_cable_row_wide", "Rem assegut amb politja i presa ampla", "cable_row", "Rem amb politja", HORIZONTAL_ROW, equipment=("cable_machine",), difficulty="intermediate", kinetic_chain="open"),
    V("single_arm_cable_row", "Rem unilateral amb politja", "cable_row", "Rem amb politja", HORIZONTAL_ROW, equipment=("cable_machine",), difficulty="intermediate", laterality="unilateral", kinetic_chain="open"),
    V("standing_band_row", "Rem dempeus amb banda", "band_row", "Rem amb banda", HORIZONTAL_ROW, equipment=("elastic_band",), difficulty="beginner", kinetic_chain="open"),
    V("single_arm_band_row", "Rem unilateral amb banda", "band_row", "Rem amb banda", HORIZONTAL_ROW, equipment=("elastic_band",), difficulty="beginner", laterality="unilateral", kinetic_chain="open"),
    V("suspension_row_upright", "Rem en suspensió amb cos vertical", "suspension_row", "Rem en suspensió", HORIZONTAL_ROW, equipment=("suspension_trainer",), difficulty="beginner", kinetic_chain="closed"),
    V("suspension_row_inclined", "Rem en suspensió inclinat", "suspension_row", "Rem en suspensió", HORIZONTAL_ROW, equipment=("suspension_trainer",), difficulty="intermediate", kinetic_chain="closed"),
    V("inverted_row_bent_knees", "Rem invertit amb genolls flexionats", "inverted_row", "Rem invertit", HORIZONTAL_ROW, equipment=("smith_machine",), difficulty="beginner", kinetic_chain="closed"),
    V("inverted_row_straight_legs", "Rem invertit amb cames esteses", "inverted_row", "Rem invertit", HORIZONTAL_ROW, equipment=("smith_machine",), difficulty="intermediate", kinetic_chain="closed"),
    V("inverted_row_feet_elevated", "Rem invertit amb peus elevats", "inverted_row", "Rem invertit", HORIZONTAL_ROW, equipment=("smith_machine", "bench"), difficulty="advanced", kinetic_chain="closed"),
    V("cable_face_pull", "Tracció facial amb politja", "face_pull", "Tracció facial", REAR_PULL, equipment=("cable_machine",), difficulty="beginner", kinetic_chain="open", modality="motor_control"),
    V("band_face_pull", "Tracció facial amb banda", "face_pull", "Tracció facial", REAR_PULL, equipment=("elastic_band",), difficulty="beginner", kinetic_chain="open", modality="warm_up", objective="preparation"),
    V("reverse_cable_fly", "Obertura posterior amb politja", "rear_fly", "Obertura posterior", REAR_PULL, equipment=("cable_machine",), difficulty="intermediate", kinetic_chain="open"),
    V("reverse_dumbbell_fly", "Obertura posterior amb manuelles", "rear_fly", "Obertura posterior", REAR_PULL, equipment=("dumbbell",), difficulty="intermediate", kinetic_chain="open"),
    V("machine_reverse_fly", "Obertura posterior en màquina", "rear_fly", "Obertura posterior", REAR_PULL, equipment=("resistance_machine",), difficulty="beginner", kinetic_chain="open"),
    V("assisted_pull_up_machine", "Dominada assistida en màquina", "pull_up", "Dominada", VERTICAL_PULL, equipment=("resistance_machine",), difficulty="beginner", kinetic_chain="closed"),
    V("band_assisted_pull_up", "Dominada assistida amb banda", "pull_up", "Dominada", VERTICAL_PULL, equipment=("pull_up_bar", "elastic_band"), difficulty="beginner", kinetic_chain="closed"),
    V("bodyweight_pull_up", "Dominada pronada", "pull_up", "Dominada", VERTICAL_PULL, equipment=("pull_up_bar",), difficulty="advanced", kinetic_chain="closed"),
    V("neutral_grip_pull_up", "Dominada amb presa neutra", "pull_up", "Dominada", VERTICAL_PULL, equipment=("pull_up_bar",), difficulty="advanced", kinetic_chain="closed"),
    V("chin_up", "Dominada supina", "pull_up", "Dominada", VERTICAL_PULL, equipment=("pull_up_bar",), difficulty="advanced", kinetic_chain="closed"),
    V("lat_pulldown_wide_grip", "Jaló al pit amb presa ampla", "lat_pulldown", "Jaló vertical", VERTICAL_PULL, equipment=("cable_machine",), difficulty="beginner", kinetic_chain="open"),
    V("lat_pulldown_neutral_grip", "Jaló al pit amb presa neutra", "lat_pulldown", "Jaló vertical", VERTICAL_PULL, equipment=("cable_machine",), difficulty="beginner", kinetic_chain="open"),
    V("single_arm_lat_pulldown", "Jaló vertical unilateral", "lat_pulldown", "Jaló vertical", VERTICAL_PULL, equipment=("cable_machine",), difficulty="intermediate", laterality="unilateral", kinetic_chain="open"),
]

BATCH = batch("07_pull", "Traccions horitzontals i verticals", ROWS)

