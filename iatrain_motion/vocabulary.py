"""Versioned, reviewable seed for the first functional-anatomy vocabulary."""

from .models import MotionConcept, MotionRelation


SEED_VERSION = "functional_anatomy_v2"


def _node(code, name, definition, kind, laterality="not_applicable"):
    return {
        "code": code,
        "name": name,
        "definition": definition,
        "kind": kind,
        "laterality": laterality,
        "provenance": {"seed": SEED_VERSION},
    }


K = MotionConcept.Kind
L = MotionConcept.Laterality

CONCEPTS = (
    _node("sagittal_plane", "Pla sagital", "Pla vertical que divideix el cos en porcions dreta i esquerra.", K.PLANE),
    _node("frontal_plane", "Pla frontal", "Pla vertical que divideix el cos en porcions anterior i posterior.", K.PLANE),
    _node("transverse_plane", "Pla transversal", "Pla que divideix el cos en porcions superior i inferior.", K.PLANE),
    _node("mediolateral_axis", "Eix mediolateral", "Eix orientat de costat a costat, perpendicular al pla sagital.", K.AXIS),
    _node("anteroposterior_axis", "Eix anteroposterior", "Eix orientat d'anterior a posterior, perpendicular al pla frontal.", K.AXIS),
    _node("longitudinal_axis", "Eix longitudinal", "Eix orientat en direcció superior-inferior, perpendicular al pla transversal.", K.AXIS),
    _node("whole_body", "Cos", "Conjunt funcional complet dels segments corporals.", K.SEGMENT, L.UNPAIRED),
    _node("head_neck", "Cap i coll", "Regió funcional formada pel cap i el coll.", K.SEGMENT, L.MIDLINE),
    _node("trunk", "Tronc", "Regió axial funcional entre el coll i la pelvis.", K.SEGMENT, L.MIDLINE),
    _node("pelvis", "Pelvis", "Segment axial que transmet moviment i càrrega entre el tronc i les extremitats inferiors.", K.SEGMENT, L.MIDLINE),
    _node("upper_limb", "Extremitat superior", "Cadena segmentària parella de la cintura escapular fins a la mà.", K.SEGMENT, L.PAIRED),
    _node("shoulder_girdle", "Cintura escapular", "Segment funcional parell que connecta l'extremitat superior amb el tronc.", K.SEGMENT, L.PAIRED),
    _node("upper_arm", "Braç", "Segment de l'extremitat superior entre l'espatlla i el colze.", K.SEGMENT, L.PAIRED),
    _node("forearm", "Avantbraç", "Segment de l'extremitat superior entre el colze i el canell.", K.SEGMENT, L.PAIRED),
    _node("hand", "Mà", "Segment distal de l'extremitat superior a partir del canell.", K.SEGMENT, L.PAIRED),
    _node("lower_limb", "Extremitat inferior", "Cadena segmentària parella de la pelvis fins al peu.", K.SEGMENT, L.PAIRED),
    _node("thigh", "Cuixa", "Segment de l'extremitat inferior entre el maluc i el genoll.", K.SEGMENT, L.PAIRED),
    _node("lower_leg", "Cama", "Segment de l'extremitat inferior entre el genoll i el turmell.", K.SEGMENT, L.PAIRED),
    _node("foot", "Peu", "Segment distal de l'extremitat inferior a partir del turmell.", K.SEGMENT, L.PAIRED),
    _node("thoracolumbar_spine_complex", "Complex vertebral toracolumbar", "Conjunt funcional d'articulacions vertebrals que permet el moviment del tronc respecte de la pelvis.", K.JOINT, L.MIDLINE),
    _node("cervical_spine_complex", "Complex vertebral cervical", "Conjunt funcional d'articulacions cervicals que permet el moviment del cap i el coll respecte del tronc.", K.JOINT, L.MIDLINE),
    _node("scapulothoracic_joint", "Articulació funcional escapulotoràcica", "Interfície funcional entre la cintura escapular i el tòrax que descriu els moviments de l'escàpula sobre el tronc.", K.JOINT, L.PAIRED),
    _node("shoulder_joint", "Articulació de l'espatlla", "Complex funcional centrat en l'articulació glenohumeral entre la cintura escapular i el braç.", K.JOINT, L.PAIRED),
    _node("elbow_joint", "Articulació del colze", "Complex articular entre el braç i l'avantbraç.", K.JOINT, L.PAIRED),
    _node("wrist_joint", "Articulació del canell", "Complex articular entre l'avantbraç i la mà.", K.JOINT, L.PAIRED),
    _node("hip_joint", "Articulació del maluc", "Articulació coxofemoral entre la pelvis i la cuixa.", K.JOINT, L.PAIRED),
    _node("knee_joint", "Articulació del genoll", "Complex articular entre la cuixa i la cama.", K.JOINT, L.PAIRED),
    _node("ankle_joint", "Complex articular del turmell", "Complex funcional entre la cama i el peu que inclou els moviments talocrurals i del retropeu.", K.JOINT, L.PAIRED),
)


def _action(code, name, definition):
    return _node(code, name, definition, K.JOINT_ACTION)


CONCEPTS += (
    _action("trunk_flexion", "Flexió del tronc", "Moviment que redueix l'angle anterior entre el tronc i la pelvis."),
    _action("trunk_extension", "Extensió del tronc", "Moviment que augmenta l'angle anterior entre el tronc i la pelvis."),
    _action("trunk_lateral_flexion", "Flexió lateral del tronc", "Inclinació del tronc cap a un costat en el pla frontal."),
    _action("trunk_axial_rotation", "Rotació axial del tronc", "Rotació del tronc respecte de la pelvis al voltant de l'eix longitudinal."),
    _action("neck_flexion", "Flexió cervical", "Moviment del cap i el coll en flexió respecte del tronc."),
    _action("neck_extension", "Extensió cervical", "Moviment del cap i el coll en extensió respecte del tronc."),
    _action("neck_lateral_flexion", "Flexió lateral cervical", "Inclinació lateral del cap i el coll respecte del tronc."),
    _action("neck_axial_rotation", "Rotació axial cervical", "Rotació del cap i el coll al voltant de l'eix longitudinal."),
    _action("scapular_elevation", "Elevació escapular", "Desplaçament superior de la cintura escapular respecte del tòrax."),
    _action("scapular_depression", "Depressió escapular", "Desplaçament inferior de la cintura escapular respecte del tòrax."),
    _action("scapular_protraction", "Protracció escapular", "Desplaçament anterolateral de l'escàpula sobre el tòrax."),
    _action("scapular_retraction", "Retracció escapular", "Desplaçament posteromedial de l'escàpula sobre el tòrax."),
    _action("scapular_upward_rotation", "Rotació superior escapular", "Rotació de l'escàpula que orienta superiorment la cavitat glenoide."),
    _action("scapular_downward_rotation", "Rotació inferior escapular", "Rotació de l'escàpula que orienta inferiorment la cavitat glenoide."),
    _action("shoulder_flexion", "Flexió d'espatlla", "Moviment anterior o superior del braç principalment en el pla sagital."),
    _action("shoulder_extension", "Extensió d'espatlla", "Moviment posterior del braç principalment en el pla sagital."),
    _action("shoulder_abduction", "Abducció d'espatlla", "Allunyament del braç respecte del pla medial principalment en el pla frontal."),
    _action("shoulder_adduction", "Adducció d'espatlla", "Aproximació del braç cap al pla medial principalment en el pla frontal."),
    _action("shoulder_internal_rotation", "Rotació interna d'espatlla", "Rotació de l'húmer que orienta anteriorment la seva cara lateral al voltant de l'eix longitudinal."),
    _action("shoulder_external_rotation", "Rotació externa d'espatlla", "Rotació de l'húmer en sentit oposat a la rotació interna al voltant de l'eix longitudinal."),
    _action("shoulder_horizontal_abduction", "Abducció horitzontal d'espatlla", "Moviment posterior del braç en el pla transversal des d'una posició elevada."),
    _action("shoulder_horizontal_adduction", "Adducció horitzontal d'espatlla", "Moviment anterior del braç en el pla transversal des d'una posició elevada."),
    _action("elbow_flexion", "Flexió de colze", "Moviment que redueix l'angle entre el braç i l'avantbraç."),
    _action("elbow_extension", "Extensió de colze", "Moviment que augmenta l'angle entre el braç i l'avantbraç."),
    _action("wrist_flexion", "Flexió de canell", "Moviment palmar de la mà respecte de l'avantbraç."),
    _action("wrist_extension", "Extensió de canell", "Moviment dorsal de la mà respecte de l'avantbraç."),
    _action("wrist_radial_deviation", "Desviació radial de canell", "Moviment de la mà cap al costat radial de l'avantbraç."),
    _action("wrist_ulnar_deviation", "Desviació cubital de canell", "Moviment de la mà cap al costat cubital de l'avantbraç."),
    _action("hip_flexion", "Flexió de maluc", "Moviment que aproxima anteriorment la cuixa al tronc o el tronc a la cuixa."),
    _action("hip_extension", "Extensió de maluc", "Moviment que augmenta l'angle anterior entre la cuixa i la pelvis."),
    _action("hip_abduction", "Abducció de maluc", "Allunyament de la cuixa respecte del pla medial principalment en el pla frontal."),
    _action("hip_adduction", "Adducció de maluc", "Aproximació de la cuixa cap al pla medial principalment en el pla frontal."),
    _action("hip_internal_rotation", "Rotació interna de maluc", "Rotació medial de la cuixa respecte de la pelvis al voltant del seu eix longitudinal."),
    _action("hip_external_rotation", "Rotació externa de maluc", "Rotació lateral de la cuixa respecte de la pelvis al voltant del seu eix longitudinal."),
    _action("knee_flexion", "Flexió de genoll", "Moviment que redueix l'angle entre la cuixa i la cama."),
    _action("knee_extension", "Extensió de genoll", "Moviment que augmenta l'angle entre la cuixa i la cama."),
    _action("ankle_dorsiflexion", "Flexió dorsal de turmell", "Moviment que aproxima el dors del peu a la cara anterior de la cama."),
    _action("ankle_plantarflexion", "Flexió plantar de turmell", "Moviment que allunya el dors del peu de la cara anterior de la cama."),
    _action("foot_inversion", "Inversió del peu", "Moviment compost que orienta la planta del peu medialment."),
    _action("foot_eversion", "Eversió del peu", "Moviment compost que orienta la planta del peu lateralment."),
)


R = MotionRelation.RelationType

RELATIONS = [
    ("head_neck", R.PART_OF, "whole_body"),
    ("trunk", R.PART_OF, "whole_body"),
    ("pelvis", R.PART_OF, "whole_body"),
    ("upper_limb", R.PART_OF, "whole_body"),
    ("shoulder_girdle", R.PART_OF, "upper_limb"),
    ("upper_arm", R.PART_OF, "upper_limb"),
    ("forearm", R.PART_OF, "upper_limb"),
    ("hand", R.PART_OF, "upper_limb"),
    ("lower_limb", R.PART_OF, "whole_body"),
    ("thigh", R.PART_OF, "lower_limb"),
    ("lower_leg", R.PART_OF, "lower_limb"),
    ("foot", R.PART_OF, "lower_limb"),
]

for joint, proximal, distal in (
    ("thoracolumbar_spine_complex", "pelvis", "trunk"),
    ("cervical_spine_complex", "trunk", "head_neck"),
    ("scapulothoracic_joint", "trunk", "shoulder_girdle"),
    ("shoulder_joint", "shoulder_girdle", "upper_arm"),
    ("elbow_joint", "upper_arm", "forearm"),
    ("wrist_joint", "forearm", "hand"),
    ("hip_joint", "pelvis", "thigh"),
    ("knee_joint", "thigh", "lower_leg"),
    ("ankle_joint", "lower_leg", "foot"),
):
    RELATIONS.extend(((joint, R.PROXIMAL_SEGMENT, proximal), (joint, R.DISTAL_SEGMENT, distal)))

ACTION_FAMILIES = (
    ("trunk_flexion", "trunk_extension", "thoracolumbar_spine_complex", "sagittal_plane", "mediolateral_axis"),
    ("shoulder_flexion", "shoulder_extension", "shoulder_joint", "sagittal_plane", "mediolateral_axis"),
    ("shoulder_abduction", "shoulder_adduction", "shoulder_joint", "frontal_plane", "anteroposterior_axis"),
    ("shoulder_internal_rotation", "shoulder_external_rotation", "shoulder_joint", "transverse_plane", "longitudinal_axis"),
    ("shoulder_horizontal_abduction", "shoulder_horizontal_adduction", "shoulder_joint", "transverse_plane", "longitudinal_axis"),
    ("scapular_elevation", "scapular_depression", "scapulothoracic_joint", "frontal_plane", "anteroposterior_axis"),
    ("scapular_protraction", "scapular_retraction", "scapulothoracic_joint", "transverse_plane", "longitudinal_axis"),
    ("scapular_upward_rotation", "scapular_downward_rotation", "scapulothoracic_joint", "frontal_plane", "anteroposterior_axis"),
    ("neck_flexion", "neck_extension", "cervical_spine_complex", "sagittal_plane", "mediolateral_axis"),
    ("elbow_flexion", "elbow_extension", "elbow_joint", "sagittal_plane", "mediolateral_axis"),
    ("wrist_flexion", "wrist_extension", "wrist_joint", "sagittal_plane", "mediolateral_axis"),
    ("wrist_radial_deviation", "wrist_ulnar_deviation", "wrist_joint", "frontal_plane", "anteroposterior_axis"),
    ("hip_flexion", "hip_extension", "hip_joint", "sagittal_plane", "mediolateral_axis"),
    ("hip_abduction", "hip_adduction", "hip_joint", "frontal_plane", "anteroposterior_axis"),
    ("hip_internal_rotation", "hip_external_rotation", "hip_joint", "transverse_plane", "longitudinal_axis"),
    ("knee_flexion", "knee_extension", "knee_joint", "sagittal_plane", "mediolateral_axis"),
    ("ankle_dorsiflexion", "ankle_plantarflexion", "ankle_joint", "sagittal_plane", "mediolateral_axis"),
    ("foot_inversion", "foot_eversion", "ankle_joint", "frontal_plane", "anteroposterior_axis"),
)

for first, second, joint, plane, axis in ACTION_FAMILIES:
    for action in (first, second):
        RELATIONS.extend(
            (
                (action, R.ACTION_AT_JOINT, joint),
                (action, R.PRIMARY_PLANE, plane),
                (action, R.PRIMARY_AXIS, axis),
            )
        )
    RELATIONS.append((first, R.OPPOSITE_OF, second))

for action, joint, plane, axis in (
    ("trunk_lateral_flexion", "thoracolumbar_spine_complex", "frontal_plane", "anteroposterior_axis"),
    ("trunk_axial_rotation", "thoracolumbar_spine_complex", "transverse_plane", "longitudinal_axis"),
    ("neck_lateral_flexion", "cervical_spine_complex", "frontal_plane", "anteroposterior_axis"),
    ("neck_axial_rotation", "cervical_spine_complex", "transverse_plane", "longitudinal_axis"),
):
    RELATIONS.extend(
        (
            (action, R.ACTION_AT_JOINT, joint),
            (action, R.PRIMARY_PLANE, plane),
            (action, R.PRIMARY_AXIS, axis),
        )
    )

RELATIONS = tuple(RELATIONS)
