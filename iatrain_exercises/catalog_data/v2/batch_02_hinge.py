from .common import batch, variant as V
from .templates import HINGE, HIP_BRIDGE


ROWS = [
    V("barbell_conventional_deadlift", "Pes mort convencional amb barra", "deadlift", "Pes mort", HINGE, equipment=("barbell",), difficulty="advanced", objective="max_strength"),
    V("barbell_sumo_deadlift", "Pes mort sumo amb barra", "deadlift", "Pes mort", HINGE, equipment=("barbell",), difficulty="advanced", objective="max_strength"),
    V("trap_bar_deadlift", "Pes mort amb barra hexagonal", "deadlift", "Pes mort", HINGE, equipment=("trap_bar",), difficulty="intermediate", objective="max_strength"),
    V("kettlebell_deadlift", "Pes mort amb kettlebell", "deadlift", "Pes mort", HINGE, equipment=("kettlebell",), difficulty="beginner"),
    V("double_dumbbell_deadlift", "Pes mort amb dues manuelles", "deadlift", "Pes mort", HINGE, equipment=("dumbbell",), difficulty="beginner"),
    V("landmine_deadlift", "Pes mort amb landmine", "deadlift", "Pes mort", HINGE, equipment=("barbell", "landmine"), difficulty="beginner"),
    V("barbell_rack_pull", "Rack pull amb barra", "rack_pull", "Rack pull", HINGE, equipment=("barbell", "box"), difficulty="advanced", objective="max_strength"),
    V("barbell_block_pull", "Pes mort des de blocs", "rack_pull", "Rack pull", HINGE, equipment=("barbell", "box"), difficulty="advanced", objective="max_strength"),
    V("barbell_romanian_deadlift", "Pes mort romanès amb barra", "romanian_deadlift", "Pes mort romanès", HINGE, equipment=("barbell",), difficulty="intermediate"),
    V("dumbbell_romanian_deadlift", "Pes mort romanès amb manuelles", "romanian_deadlift", "Pes mort romanès", HINGE, equipment=("dumbbell",), difficulty="beginner"),
    V("kettlebell_romanian_deadlift", "Pes mort romanès amb kettlebell", "romanian_deadlift", "Pes mort romanès", HINGE, equipment=("kettlebell",), difficulty="beginner"),
    V("smith_romanian_deadlift", "Pes mort romanès a màquina Smith", "romanian_deadlift", "Pes mort romanès", HINGE, equipment=("smith_machine",), difficulty="intermediate"),
    V("band_romanian_deadlift", "Pes mort romanès amb banda", "romanian_deadlift", "Pes mort romanès", HINGE, equipment=("elastic_band",), difficulty="beginner"),
    V("bodyweight_good_morning", "Good morning amb pes corporal", "good_morning", "Good morning", HINGE, difficulty="beginner", modality="motor_control"),
    V("barbell_good_morning", "Good morning amb barra", "good_morning", "Good morning", HINGE, equipment=("barbell",), difficulty="advanced"),
    V("band_good_morning", "Good morning amb banda", "good_morning", "Good morning", HINGE, equipment=("elastic_band",), difficulty="beginner"),
    V("wall_hip_hinge_drill", "Frontissa de maluc amb referència de paret", "hip_hinge_drill", "Aprenentatge de frontissa", HINGE, equipment=("wall",), difficulty="beginner", modality="motor_control", objective="motor_control"),
    V("dowel_hip_hinge_drill", "Frontissa de maluc amb barra de referència", "hip_hinge_drill", "Aprenentatge de frontissa", HINGE, equipment=("barbell",), difficulty="beginner", modality="warm_up", objective="preparation"),
    V("floor_glute_bridge", "Pont de glutis a terra", "glute_bridge", "Pont de glutis", HIP_BRIDGE, optional_equipment=("mat",), difficulty="beginner", modality="motor_control"),
    V("band_glute_bridge", "Pont de glutis amb banda", "glute_bridge", "Pont de glutis", HIP_BRIDGE, equipment=("elastic_band",), difficulty="beginner"),
    V("weighted_glute_bridge", "Pont de glutis amb disc", "glute_bridge", "Pont de glutis", HIP_BRIDGE, equipment=("weight_plate",), difficulty="intermediate"),
    V("feet_elevated_glute_bridge", "Pont de glutis amb peus elevats", "glute_bridge", "Pont de glutis", HIP_BRIDGE, equipment=("bench",), difficulty="intermediate"),
    V("stability_ball_glute_bridge", "Pont de glutis sobre pilota", "glute_bridge", "Pont de glutis", HIP_BRIDGE, equipment=("stability_ball",), difficulty="intermediate", modality="motor_control"),
    V("dumbbell_hip_thrust", "Hip thrust amb mancuerna", "hip_thrust", "Hip thrust", HIP_BRIDGE, equipment=("dumbbell", "bench"), difficulty="beginner"),
    V("band_hip_thrust", "Hip thrust amb banda", "hip_thrust", "Hip thrust", HIP_BRIDGE, equipment=("elastic_band", "bench"), difficulty="beginner"),
    V("smith_machine_hip_thrust", "Hip thrust a màquina Smith", "hip_thrust", "Hip thrust", HIP_BRIDGE, equipment=("smith_machine", "bench"), difficulty="intermediate", objective="max_strength"),
    V("machine_hip_thrust", "Hip thrust en màquina guiada", "hip_thrust", "Hip thrust", HIP_BRIDGE, equipment=("resistance_machine",), difficulty="beginner"),
    V("shoulders_elevated_bodyweight_hip_thrust", "Hip thrust amb pes corporal", "hip_thrust", "Hip thrust", HIP_BRIDGE, equipment=("bench",), difficulty="beginner", modality="muscular_endurance"),
]

BATCH = batch("02_hinge", "Frontisses, pesos morts i ponts de maluc", ROWS)

