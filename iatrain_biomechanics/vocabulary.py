"""Reviewable functional-biomechanics seed for professional exercise reasoning."""

from iatrain_motion.models import MotionConcept

from .models import BiomechanicalContext, MuscleActionFunction, MuscleStabilizationFunction


SEED_VERSION = "functional_biomechanics_v1"


SOURCES = (
    {
        "code": "openstax_ap2_lower_limb",
        "title": "Anatomy and Physiology 2e · Muscles of the pelvic girdle and lower limbs",
        "source_type": "textbook",
        "identifier_type": "url",
        "identifier": "https://openstax.org/books/anatomy-and-physiology-2e/pages/11-6-appendicular-muscles-of-the-pelvic-girdle-and-lower-limbs",
        "url": "https://openstax.org/books/anatomy-and-physiology-2e/pages/11-6-appendicular-muscles-of-the-pelvic-girdle-and-lower-limbs",
    },
    {
        "code": "openstax_ap2_upper_limb",
        "title": "Anatomy and Physiology 2e · Muscles of the pectoral girdle and upper limbs",
        "source_type": "textbook",
        "identifier_type": "url",
        "identifier": "https://openstax.org/books/anatomy-and-physiology-2e/pages/11-5-muscles-of-the-pectoral-girdle-and-upper-limbs",
        "url": "https://openstax.org/books/anatomy-and-physiology-2e/pages/11-5-muscles-of-the-pectoral-girdle-and-upper-limbs",
    },
    {
        "code": "openstax_ap2_axial",
        "title": "Anatomy and Physiology 2e · Axial muscles of the abdominal wall and thorax",
        "source_type": "textbook",
        "identifier_type": "url",
        "identifier": "https://openstax.org/books/anatomy-and-physiology-2e/pages/11-4-axial-muscles-of-the-abdominal-wall-and-thorax",
        "url": "https://openstax.org/books/anatomy-and-physiology-2e/pages/11-4-axial-muscles-of-the-abdominal-wall-and-thorax",
    },
    {
        "code": "uberon_anatomy_ontology",
        "title": "Uberon integrated anatomy ontology",
        "source_type": "anatomy_ontology",
        "identifier_type": "ontology",
        "identifier": "http://purl.obolibrary.org/obo/uberon.owl",
        "url": "https://www.ebi.ac.uk/ols4/ontologies/uberon",
    },
)


CONTEXTS = (
    {
        "code": "general_functional_context",
        "name": "Context funcional general",
        "description": (
            "Afirmació qualitativa general sense imposar una postura, una càrrega o una cadena "
            "cinètica concreta; qualsevol jerarquia s'ha de revisar en el cas d'ús."
        ),
        "kinetic_chain": BiomechanicalContext.KineticChain.UNSPECIFIED,
        "loading_conditions": {"scope": "qualitative", "activation_inferred": False},
    },
    {
        "code": "open_kinetic_chain",
        "name": "Cadena cinètica oberta",
        "description": "Context on l'extrem distal es pot moure sense un suport extern fix dominant.",
        "kinetic_chain": BiomechanicalContext.KineticChain.OPEN,
        "loading_conditions": {"distal_constraint": "not_fixed"},
    },
    {
        "code": "closed_kinetic_chain",
        "name": "Cadena cinètica tancada",
        "description": "Context on l'extrem distal està condicionat per un suport extern dominant.",
        "kinetic_chain": BiomechanicalContext.KineticChain.CLOSED,
        "loading_conditions": {"distal_constraint": "externally_fixed_or_supported"},
    },
)


L = MotionConcept.Laterality


def _group(code, name, definition, laterality):
    return {
        "code": code,
        "name": name,
        "definition": definition,
        "kind": MotionConcept.Kind.MUSCLE_GROUP,
        "laterality": laterality,
    }


GROUPS = (
    _group("gluteal_muscles", "Musculatura glútia", "Conjunt de músculs glútis que mouen i estabilitzen la pelvis i el maluc.", L.PAIRED),
    _group("deep_hip_external_rotators", "Rotadors externs profunds del maluc", "Grup profund que contribueix a la rotació externa i al control coxofemoral.", L.PAIRED),
    _group("hip_flexors", "Flexors del maluc", "Músculs amb capacitat funcional per contribuir a la flexió del maluc.", L.PAIRED),
    _group("hip_extensors", "Extensors del maluc", "Músculs amb capacitat funcional per contribuir a l'extensió del maluc.", L.PAIRED),
    _group("hip_abductors", "Abductors del maluc", "Músculs amb capacitat funcional per contribuir a l'abducció del maluc.", L.PAIRED),
    _group("hip_adductors", "Adductors del maluc", "Músculs amb capacitat funcional per contribuir a l'adducció del maluc.", L.PAIRED),
    _group("knee_extensors", "Extensors del genoll", "Músculs amb capacitat funcional per contribuir a l'extensió del genoll.", L.PAIRED),
    _group("knee_flexors", "Flexors del genoll", "Músculs amb capacitat funcional per contribuir a la flexió del genoll.", L.PAIRED),
    _group("ankle_plantarflexors", "Flexors plantars del turmell", "Músculs que contribueixen a la flexió plantar del turmell.", L.PAIRED),
    _group("ankle_dorsiflexors", "Flexors dorsals del turmell", "Músculs que contribueixen a la flexió dorsal del turmell.", L.PAIRED),
    _group("foot_invertors", "Inversors del peu", "Músculs que contribueixen funcionalment a la inversió del peu.", L.PAIRED),
    _group("foot_evertors", "Eversors del peu", "Músculs que contribueixen funcionalment a l'eversió del peu.", L.PAIRED),
    _group("abdominal_wall", "Paret abdominal", "Músculs anterolaterals que mouen i estabilitzen el tronc i gestionen la pressió abdominal.", L.MIDLINE),
    _group("trunk_flexors", "Flexors del tronc", "Músculs que contribueixen a la flexió toracolumbar.", L.MIDLINE),
    _group("trunk_extensors", "Extensors del tronc", "Músculs que contribueixen a l'extensió toracolumbar.", L.MIDLINE),
    _group("trunk_rotators", "Rotadors del tronc", "Músculs que contribueixen a la rotació axial del tronc.", L.MIDLINE),
    _group("trunk_lateral_flexors", "Flexors laterals del tronc", "Músculs que contribueixen a la flexió lateral del tronc.", L.MIDLINE),
    _group("trunk_stabilizers", "Estabilitzadors del tronc", "Músculs que contribueixen al control segmentari, postural o de transferència de força del tronc.", L.MIDLINE),
    _group("cervical_muscles", "Musculatura cervical funcional", "Músculs rellevants per al moviment i control del complex cervical.", L.MIDLINE),
    _group("scapular_stabilizers", "Estabilitzadors escapulars", "Músculs que posicionen i controlen la cintura escapular sobre el tòrax.", L.PAIRED),
    _group("rotator_cuff", "Manegot dels rotadors", "Conjunt supraespinós, infraespinós, rodó menor i subescapular que contribueix al moviment i centratge glenohumeral.", L.PAIRED),
    _group("shoulder_flexors", "Flexors de l'espatlla", "Músculs que contribueixen a la flexió de l'espatlla.", L.PAIRED),
    _group("shoulder_extensors", "Extensors de l'espatlla", "Músculs que contribueixen a l'extensió de l'espatlla.", L.PAIRED),
    _group("shoulder_abductors", "Abductors de l'espatlla", "Músculs que contribueixen a l'abducció de l'espatlla.", L.PAIRED),
    _group("shoulder_adductors", "Adductors de l'espatlla", "Músculs que contribueixen a l'adducció de l'espatlla.", L.PAIRED),
    _group("shoulder_internal_rotators", "Rotadors interns de l'espatlla", "Músculs que contribueixen a la rotació interna de l'espatlla.", L.PAIRED),
    _group("shoulder_external_rotators", "Rotadors externs de l'espatlla", "Músculs que contribueixen a la rotació externa de l'espatlla.", L.PAIRED),
    _group("elbow_flexors", "Flexors del colze", "Músculs que contribueixen a la flexió del colze.", L.PAIRED),
    _group("elbow_extensors", "Extensors del colze", "Músculs que contribueixen a l'extensió del colze.", L.PAIRED),
    _group("wrist_flexors", "Flexors del canell", "Músculs que contribueixen a la flexió del canell.", L.PAIRED),
    _group("wrist_extensors", "Extensors del canell", "Músculs que contribueixen a l'extensió del canell.", L.PAIRED),
)


def _muscle(code, name, definition, groups, joints, source):
    return {
        "code": code,
        "name": name,
        "definition": definition,
        "kind": MotionConcept.Kind.MUSCLE,
        "laterality": L.PAIRED,
        "groups": tuple(groups),
        "joints": tuple(joints),
        "source": source,
    }


MUSCLES = (
    _muscle("gluteus_maximus", "Gluti major", "Múscul gluti superficial potent, rellevant per a l'extensió i la rotació externa del maluc.", ("gluteal_muscles", "hip_extensors"), ("hip_joint",), "openstax_ap2_lower_limb"),
    _muscle("gluteus_medius", "Gluti mitjà", "Múscul gluti lateral que contribueix a l'abducció i al control frontal de la pelvis.", ("gluteal_muscles", "hip_abductors"), ("hip_joint",), "openstax_ap2_lower_limb"),
    _muscle("gluteus_minimus", "Gluti menor", "Múscul gluti profund que contribueix a l'abducció, rotació interna i estabilització del maluc.", ("gluteal_muscles", "hip_abductors"), ("hip_joint",), "openstax_ap2_lower_limb"),
    _muscle("iliopsoas", "Iliopsoes", "Unitat funcional formada principalment per psoes major i ilíac, amb una contribució important a la flexió del maluc.", ("hip_flexors",), ("hip_joint", "thoracolumbar_spine_complex"), "openstax_ap2_lower_limb"),
    _muscle("tensor_fasciae_latae", "Tensor de la fàscia lata", "Múscul anterolateral del maluc que contribueix a flexió, abducció, rotació interna i control lateral.", ("hip_flexors", "hip_abductors"), ("hip_joint",), "openstax_ap2_lower_limb"),
    _muscle("sartorius", "Sartori", "Múscul biarticular superficial que travessa maluc i genoll i combina flexió, abducció i rotació externa del maluc amb flexió del genoll.", ("hip_flexors", "knee_flexors"), ("hip_joint", "knee_joint"), "openstax_ap2_lower_limb"),
    _muscle("rectus_femoris", "Recte femoral", "Component biarticular del quàdriceps que travessa maluc i genoll.", ("hip_flexors", "knee_extensors"), ("hip_joint", "knee_joint"), "openstax_ap2_lower_limb"),
    _muscle("vastus_lateralis", "Vast lateral", "Component lateral monoarticular del quàdriceps, extensor del genoll.", ("knee_extensors",), ("knee_joint",), "openstax_ap2_lower_limb"),
    _muscle("vastus_medialis", "Vast medial", "Component medial monoarticular del quàdriceps, extensor del genoll i contribuïdor al control patel·lar.", ("knee_extensors",), ("knee_joint",), "openstax_ap2_lower_limb"),
    _muscle("vastus_intermedius", "Vast intermedi", "Component profund monoarticular del quàdriceps, extensor del genoll.", ("knee_extensors",), ("knee_joint",), "openstax_ap2_lower_limb"),
    _muscle("biceps_femoris_long_head", "Bíceps femoral · cap llarg", "Component biarticular posterior que travessa el maluc i el genoll.", ("hip_extensors", "knee_flexors"), ("hip_joint", "knee_joint"), "openstax_ap2_lower_limb"),
    _muscle("biceps_femoris_short_head", "Bíceps femoral · cap curt", "Component posterior monoarticular que travessa el genoll però no el maluc.", ("knee_flexors",), ("knee_joint",), "openstax_ap2_lower_limb"),
    _muscle("semitendinosus", "Semitendinós", "Múscul isquiotibial biarticular que contribueix a extensió de maluc i flexió de genoll.", ("hip_extensors", "knee_flexors"), ("hip_joint", "knee_joint"), "openstax_ap2_lower_limb"),
    _muscle("semimembranosus", "Semimembranós", "Múscul isquiotibial biarticular que contribueix a extensió de maluc i flexió de genoll.", ("hip_extensors", "knee_flexors"), ("hip_joint", "knee_joint"), "openstax_ap2_lower_limb"),
    _muscle("adductor_magnus", "Adductor major", "Múscul medial ampli amb funcions d'adducció i contribucions dependents de la regió a flexió o extensió del maluc.", ("hip_adductors", "hip_extensors"), ("hip_joint",), "openstax_ap2_lower_limb"),
    _muscle("adductor_longus", "Adductor llarg", "Múscul medial de la cuixa que contribueix principalment a l'adducció del maluc.", ("hip_adductors",), ("hip_joint",), "openstax_ap2_lower_limb"),
    _muscle("adductor_brevis", "Adductor curt", "Múscul medial profund que contribueix a l'adducció del maluc.", ("hip_adductors",), ("hip_joint",), "openstax_ap2_lower_limb"),
    _muscle("gracilis", "Gràcil", "Múscul medial biarticular que travessa maluc i genoll.", ("hip_adductors", "knee_flexors"), ("hip_joint", "knee_joint"), "openstax_ap2_lower_limb"),
    _muscle("pectineus", "Pectini", "Múscul proximal medial que contribueix a flexió i adducció del maluc.", ("hip_flexors", "hip_adductors"), ("hip_joint",), "openstax_ap2_lower_limb"),
    _muscle("piriformis", "Piriforme", "Múscul profund posterior del maluc amb funció rotadora dependent de la posició articular.", ("deep_hip_external_rotators",), ("hip_joint",), "openstax_ap2_lower_limb"),
    _muscle("obturator_internus", "Obturador intern", "Múscul profund del maluc que contribueix a rotació externa i estabilització coxofemoral.", ("deep_hip_external_rotators",), ("hip_joint",), "openstax_ap2_lower_limb"),
    _muscle("obturator_externus", "Obturador extern", "Múscul profund del maluc que contribueix a rotació externa i control coxofemoral.", ("deep_hip_external_rotators",), ("hip_joint",), "openstax_ap2_lower_limb"),
    _muscle("gemellus_superior", "Gemin superior", "Múscul profund curt que contribueix a rotació externa i estabilització del maluc.", ("deep_hip_external_rotators",), ("hip_joint",), "openstax_ap2_lower_limb"),
    _muscle("gemellus_inferior", "Gemin inferior", "Múscul profund curt que contribueix a rotació externa i estabilització del maluc.", ("deep_hip_external_rotators",), ("hip_joint",), "openstax_ap2_lower_limb"),
    _muscle("quadratus_femoris", "Quadrat femoral", "Múscul profund posterior que contribueix a la rotació externa del maluc.", ("deep_hip_external_rotators",), ("hip_joint",), "openstax_ap2_lower_limb"),
    _muscle("gastrocnemius", "Gastrocnemi", "Múscul superficial biarticular del panxell que travessa genoll i turmell.", ("ankle_plantarflexors", "knee_flexors"), ("knee_joint", "ankle_joint"), "openstax_ap2_lower_limb"),
    _muscle("soleus", "Soli", "Múscul profund del panxell, monoarticular i potent flexor plantar amb funció postural.", ("ankle_plantarflexors",), ("ankle_joint",), "openstax_ap2_lower_limb"),
    _muscle("tibialis_anterior", "Tibial anterior", "Múscul anterior de la cama que contribueix a flexió dorsal i inversió del peu.", ("ankle_dorsiflexors", "foot_invertors"), ("ankle_joint",), "openstax_ap2_lower_limb"),
    _muscle("tibialis_posterior", "Tibial posterior", "Múscul profund posterior que contribueix a inversió, flexió plantar i suport funcional del peu.", ("ankle_plantarflexors", "foot_invertors"), ("ankle_joint",), "openstax_ap2_lower_limb"),
    _muscle("fibularis_longus", "Fibular llarg", "Múscul lateral de la cama que contribueix a eversió i flexió plantar del peu.", ("foot_evertors", "ankle_plantarflexors"), ("ankle_joint",), "openstax_ap2_lower_limb"),
    _muscle("fibularis_brevis", "Fibular curt", "Múscul lateral de la cama que contribueix principalment a eversió del peu.", ("foot_evertors",), ("ankle_joint",), "openstax_ap2_lower_limb"),
    _muscle("rectus_abdominis", "Recte abdominal", "Múscul longitudinal anterior de la paret abdominal que contribueix a flexió i control del tronc.", ("abdominal_wall", "trunk_flexors"), ("thoracolumbar_spine_complex",), "openstax_ap2_axial"),
    _muscle("external_oblique", "Oblic extern", "Múscul anterolateral superficial que contribueix a flexió, flexió lateral, rotació i estabilització del tronc.", ("abdominal_wall", "trunk_flexors", "trunk_rotators", "trunk_lateral_flexors"), ("thoracolumbar_spine_complex",), "openstax_ap2_axial"),
    _muscle("internal_oblique", "Oblic intern", "Múscul anterolateral intermedi que contribueix a flexió, flexió lateral, rotació i estabilització del tronc.", ("abdominal_wall", "trunk_flexors", "trunk_rotators", "trunk_lateral_flexors"), ("thoracolumbar_spine_complex",), "openstax_ap2_axial"),
    _muscle("transversus_abdominis", "Transvers abdominal", "Múscul profund de la paret abdominal orientat transversalment, rellevant per al control de pressió i estabilització.", ("abdominal_wall", "trunk_stabilizers"), ("thoracolumbar_spine_complex",), "openstax_ap2_axial"),
    _muscle("erector_spinae", "Erector de la columna", "Grup muscular longitudinal posterior que contribueix a extensió, flexió lateral i control postural del tronc.", ("trunk_extensors", "trunk_lateral_flexors", "trunk_stabilizers"), ("thoracolumbar_spine_complex",), "openstax_ap2_axial"),
    _muscle("multifidus", "Multífid", "Musculatura profunda segmentària vertebral que contribueix a extensió, rotació i estabilitat intersegmentària.", ("trunk_extensors", "trunk_rotators", "trunk_stabilizers"), ("thoracolumbar_spine_complex",), "openstax_ap2_axial"),
    _muscle("quadratus_lumborum", "Quadrat lumbar", "Múscul posterior de la paret abdominal que contribueix a flexió lateral, extensió i control lumbopèlvic.", ("trunk_lateral_flexors", "trunk_extensors", "trunk_stabilizers"), ("thoracolumbar_spine_complex",), "openstax_ap2_axial"),
    _muscle("sternocleidomastoid", "Esternoclidomastoïdal", "Múscul cervical superficial amb funcions de flexió, flexió lateral i rotació dependents de l'activació unilateral o bilateral.", ("cervical_muscles",), ("cervical_spine_complex",), "openstax_ap2_axial"),
    _muscle("splenius_capitis", "Espleni del cap", "Múscul cervical posterior que contribueix a extensió, flexió lateral i rotació del cap.", ("cervical_muscles",), ("cervical_spine_complex",), "openstax_ap2_axial"),
    _muscle("splenius_cervicis", "Espleni del coll", "Múscul cervical posterior que contribueix a extensió, flexió lateral i rotació cervical.", ("cervical_muscles",), ("cervical_spine_complex",), "openstax_ap2_axial"),
    _muscle("deltoid_anterior", "Deltoide anterior", "Porció anterior del deltoide amb contribució prominent a flexió i rotació interna de l'espatlla.", ("shoulder_flexors", "shoulder_internal_rotators"), ("shoulder_joint",), "openstax_ap2_upper_limb"),
    _muscle("deltoid_middle", "Deltoide mitjà", "Porció mitjana del deltoide amb contribució prominent a l'abducció de l'espatlla.", ("shoulder_abductors",), ("shoulder_joint",), "openstax_ap2_upper_limb"),
    _muscle("deltoid_posterior", "Deltoide posterior", "Porció posterior del deltoide que contribueix a extensió, rotació externa i abducció horitzontal.", ("shoulder_extensors", "shoulder_external_rotators"), ("shoulder_joint",), "openstax_ap2_upper_limb"),
    _muscle("pectoralis_major", "Pectoral major", "Múscul anterior del tòrax que mou l'húmer en adducció, rotació interna i adducció horitzontal.", ("shoulder_adductors", "shoulder_internal_rotators", "shoulder_flexors"), ("shoulder_joint",), "openstax_ap2_upper_limb"),
    _muscle("latissimus_dorsi", "Dorsal ample", "Múscul posterior ampli que contribueix a extensió, adducció i rotació interna de l'espatlla.", ("shoulder_extensors", "shoulder_adductors", "shoulder_internal_rotators"), ("shoulder_joint",), "openstax_ap2_upper_limb"),
    _muscle("teres_major", "Rodó major", "Múscul escapulohumeral que contribueix a extensió, adducció i rotació interna de l'espatlla.", ("shoulder_extensors", "shoulder_adductors", "shoulder_internal_rotators"), ("shoulder_joint",), "openstax_ap2_upper_limb"),
    _muscle("supraspinatus", "Supraespinós", "Múscul del manegot dels rotadors que contribueix a abducció i centratge glenohumeral.", ("rotator_cuff", "shoulder_abductors"), ("shoulder_joint",), "openstax_ap2_upper_limb"),
    _muscle("infraspinatus", "Infraespinós", "Múscul del manegot dels rotadors amb contribució principal a rotació externa i estabilitat glenohumeral.", ("rotator_cuff", "shoulder_external_rotators"), ("shoulder_joint",), "openstax_ap2_upper_limb"),
    _muscle("teres_minor", "Rodó menor", "Múscul del manegot dels rotadors que contribueix a rotació externa i centratge glenohumeral.", ("rotator_cuff", "shoulder_external_rotators"), ("shoulder_joint",), "openstax_ap2_upper_limb"),
    _muscle("subscapularis", "Subescapular", "Múscul anterior del manegot dels rotadors que contribueix a rotació interna i centratge glenohumeral.", ("rotator_cuff", "shoulder_internal_rotators"), ("shoulder_joint",), "openstax_ap2_upper_limb"),
    _muscle("trapezius_upper", "Trapezi superior", "Porció superior del trapezi que contribueix a elevació i rotació superior de l'escàpula.", ("scapular_stabilizers",), ("scapulothoracic_joint",), "openstax_ap2_upper_limb"),
    _muscle("trapezius_middle", "Trapezi mitjà", "Porció mitjana del trapezi que contribueix principalment a retracció escapular.", ("scapular_stabilizers",), ("scapulothoracic_joint",), "openstax_ap2_upper_limb"),
    _muscle("trapezius_lower", "Trapezi inferior", "Porció inferior del trapezi que contribueix a depressió i rotació superior escapular.", ("scapular_stabilizers",), ("scapulothoracic_joint",), "openstax_ap2_upper_limb"),
    _muscle("serratus_anterior", "Serrat anterior", "Múscul toracoescapular que contribueix a protracció, rotació superior i control de l'escàpula.", ("scapular_stabilizers",), ("scapulothoracic_joint",), "openstax_ap2_upper_limb"),
    _muscle("rhomboid_major", "Romboide major", "Múscul toracoescapular que contribueix a retracció i rotació inferior de l'escàpula.", ("scapular_stabilizers",), ("scapulothoracic_joint",), "openstax_ap2_upper_limb"),
    _muscle("rhomboid_minor", "Romboide menor", "Múscul toracoescapular que contribueix a retracció i control medial de l'escàpula.", ("scapular_stabilizers",), ("scapulothoracic_joint",), "openstax_ap2_upper_limb"),
    _muscle("levator_scapulae", "Elevador de l'escàpula", "Múscul cervical-escapular que contribueix a elevació i rotació inferior de l'escàpula.", ("scapular_stabilizers",), ("scapulothoracic_joint",), "openstax_ap2_upper_limb"),
    _muscle("pectoralis_minor", "Pectoral menor", "Múscul toracoescapular anterior que contribueix a protracció, depressió i control escapular.", ("scapular_stabilizers",), ("scapulothoracic_joint",), "openstax_ap2_upper_limb"),
    _muscle("biceps_brachii", "Bíceps braquial", "Múscul anterior biarticular del braç que contribueix a flexió del colze i, secundàriament, de l'espatlla.", ("elbow_flexors", "shoulder_flexors"), ("elbow_joint", "shoulder_joint"), "openstax_ap2_upper_limb"),
    _muscle("brachialis", "Braquial", "Múscul anterior monoarticular del braç amb contribució principal a flexió del colze.", ("elbow_flexors",), ("elbow_joint",), "openstax_ap2_upper_limb"),
    _muscle("brachioradialis", "Braquioradial", "Múscul superficial de l'avantbraç que contribueix a flexió del colze, especialment en posició neutra de l'avantbraç.", ("elbow_flexors",), ("elbow_joint",), "openstax_ap2_upper_limb"),
    _muscle("triceps_brachii", "Tríceps braquial", "Grup muscular posterior del braç amb contribució principal a extensió del colze.", ("elbow_extensors",), ("elbow_joint",), "openstax_ap2_upper_limb"),
    _muscle("anconeus", "Ancòneu", "Múscul posterior curt que assisteix l'extensió i estabilització del colze.", ("elbow_extensors",), ("elbow_joint",), "openstax_ap2_upper_limb"),
    _muscle("flexor_carpi_radialis", "Flexor radial del carp", "Múscul anterior de l'avantbraç que contribueix a flexió i desviació radial del canell.", ("wrist_flexors",), ("wrist_joint",), "openstax_ap2_upper_limb"),
    _muscle("flexor_carpi_ulnaris", "Flexor cubital del carp", "Múscul anterior de l'avantbraç que contribueix a flexió i desviació cubital del canell.", ("wrist_flexors",), ("wrist_joint",), "openstax_ap2_upper_limb"),
    _muscle("palmaris_longus", "Palmar llarg", "Múscul anterior superficial que pot assistir la flexió del canell i tensar l'aponeurosi palmar.", ("wrist_flexors",), ("wrist_joint",), "openstax_ap2_upper_limb"),
    _muscle("extensor_carpi_radialis_longus", "Extensor radial llarg del carp", "Múscul posterior que contribueix a extensió i desviació radial del canell.", ("wrist_extensors",), ("wrist_joint",), "openstax_ap2_upper_limb"),
    _muscle("extensor_carpi_radialis_brevis", "Extensor radial curt del carp", "Múscul posterior que contribueix a extensió i desviació radial del canell.", ("wrist_extensors",), ("wrist_joint",), "openstax_ap2_upper_limb"),
    _muscle("extensor_carpi_ulnaris", "Extensor cubital del carp", "Múscul posterior que contribueix a extensió i desviació cubital del canell.", ("wrist_extensors",), ("wrist_joint",), "openstax_ap2_upper_limb"),
)


C = MuscleActionFunction.ContributionClass


FUNCTIONS_BY_MUSCLE = {
    "gluteus_maximus": (("hip_extension", C.MAJOR), ("hip_external_rotation", C.SUPPORTING)),
    "gluteus_medius": (("hip_abduction", C.MAJOR), ("hip_internal_rotation", C.VARIABLE)),
    "gluteus_minimus": (("hip_abduction", C.SUPPORTING), ("hip_internal_rotation", C.VARIABLE)),
    "iliopsoas": (("hip_flexion", C.MAJOR), ("trunk_flexion", C.VARIABLE)),
    "tensor_fasciae_latae": (("hip_flexion", C.SUPPORTING), ("hip_abduction", C.SUPPORTING), ("hip_internal_rotation", C.SUPPORTING)),
    "sartorius": (("hip_flexion", C.SUPPORTING), ("hip_abduction", C.SUPPORTING), ("hip_external_rotation", C.SUPPORTING), ("knee_flexion", C.SUPPORTING)),
    "rectus_femoris": (("hip_flexion", C.SUPPORTING), ("knee_extension", C.MAJOR)),
    "vastus_lateralis": (("knee_extension", C.MAJOR),),
    "vastus_medialis": (("knee_extension", C.MAJOR),),
    "vastus_intermedius": (("knee_extension", C.MAJOR),),
    "biceps_femoris_long_head": (("hip_extension", C.SUPPORTING), ("knee_flexion", C.MAJOR)),
    "biceps_femoris_short_head": (("knee_flexion", C.MAJOR),),
    "semitendinosus": (("hip_extension", C.SUPPORTING), ("knee_flexion", C.MAJOR)),
    "semimembranosus": (("hip_extension", C.SUPPORTING), ("knee_flexion", C.MAJOR)),
    "adductor_magnus": (("hip_adduction", C.MAJOR), ("hip_extension", C.VARIABLE)),
    "adductor_longus": (("hip_adduction", C.MAJOR), ("hip_flexion", C.VARIABLE)),
    "adductor_brevis": (("hip_adduction", C.MAJOR), ("hip_flexion", C.VARIABLE)),
    "gracilis": (("hip_adduction", C.SUPPORTING), ("knee_flexion", C.SUPPORTING)),
    "pectineus": (("hip_adduction", C.SUPPORTING), ("hip_flexion", C.SUPPORTING)),
    "piriformis": (("hip_external_rotation", C.VARIABLE), ("hip_abduction", C.VARIABLE)),
    "obturator_internus": (("hip_external_rotation", C.MAJOR),),
    "obturator_externus": (("hip_external_rotation", C.MAJOR),),
    "gemellus_superior": (("hip_external_rotation", C.SUPPORTING),),
    "gemellus_inferior": (("hip_external_rotation", C.SUPPORTING),),
    "quadratus_femoris": (("hip_external_rotation", C.MAJOR),),
    "gastrocnemius": (("ankle_plantarflexion", C.MAJOR), ("knee_flexion", C.SUPPORTING)),
    "soleus": (("ankle_plantarflexion", C.MAJOR),),
    "tibialis_anterior": (("ankle_dorsiflexion", C.MAJOR), ("foot_inversion", C.SUPPORTING)),
    "tibialis_posterior": (("foot_inversion", C.MAJOR), ("ankle_plantarflexion", C.SUPPORTING)),
    "fibularis_longus": (("foot_eversion", C.MAJOR), ("ankle_plantarflexion", C.SUPPORTING)),
    "fibularis_brevis": (("foot_eversion", C.MAJOR),),
    "rectus_abdominis": (("trunk_flexion", C.MAJOR),),
    "external_oblique": (("trunk_flexion", C.SUPPORTING), ("trunk_lateral_flexion", C.SUPPORTING), ("trunk_axial_rotation", C.MAJOR)),
    "internal_oblique": (("trunk_flexion", C.SUPPORTING), ("trunk_lateral_flexion", C.SUPPORTING), ("trunk_axial_rotation", C.MAJOR)),
    "erector_spinae": (("trunk_extension", C.MAJOR), ("trunk_lateral_flexion", C.SUPPORTING)),
    "multifidus": (("trunk_extension", C.SUPPORTING), ("trunk_axial_rotation", C.VARIABLE)),
    "quadratus_lumborum": (("trunk_lateral_flexion", C.MAJOR), ("trunk_extension", C.SUPPORTING)),
    "sternocleidomastoid": (("neck_flexion", C.MAJOR), ("neck_lateral_flexion", C.VARIABLE), ("neck_axial_rotation", C.VARIABLE)),
    "splenius_capitis": (("neck_extension", C.MAJOR), ("neck_lateral_flexion", C.SUPPORTING), ("neck_axial_rotation", C.SUPPORTING)),
    "splenius_cervicis": (("neck_extension", C.MAJOR), ("neck_lateral_flexion", C.SUPPORTING), ("neck_axial_rotation", C.SUPPORTING)),
    "deltoid_anterior": (("shoulder_flexion", C.MAJOR), ("shoulder_internal_rotation", C.SUPPORTING), ("shoulder_horizontal_adduction", C.SUPPORTING)),
    "deltoid_middle": (("shoulder_abduction", C.MAJOR),),
    "deltoid_posterior": (("shoulder_extension", C.MAJOR), ("shoulder_external_rotation", C.SUPPORTING), ("shoulder_horizontal_abduction", C.MAJOR)),
    "pectoralis_major": (("shoulder_adduction", C.MAJOR), ("shoulder_internal_rotation", C.MAJOR), ("shoulder_horizontal_adduction", C.MAJOR), ("shoulder_flexion", C.VARIABLE)),
    "latissimus_dorsi": (("shoulder_extension", C.MAJOR), ("shoulder_adduction", C.MAJOR), ("shoulder_internal_rotation", C.SUPPORTING)),
    "teres_major": (("shoulder_extension", C.SUPPORTING), ("shoulder_adduction", C.SUPPORTING), ("shoulder_internal_rotation", C.SUPPORTING)),
    "supraspinatus": (("shoulder_abduction", C.MAJOR),),
    "infraspinatus": (("shoulder_external_rotation", C.MAJOR),),
    "teres_minor": (("shoulder_external_rotation", C.MAJOR),),
    "subscapularis": (("shoulder_internal_rotation", C.MAJOR),),
    "trapezius_upper": (("scapular_elevation", C.MAJOR), ("scapular_upward_rotation", C.MAJOR)),
    "trapezius_middle": (("scapular_retraction", C.MAJOR),),
    "trapezius_lower": (("scapular_depression", C.MAJOR), ("scapular_upward_rotation", C.MAJOR)),
    "serratus_anterior": (("scapular_protraction", C.MAJOR), ("scapular_upward_rotation", C.MAJOR)),
    "rhomboid_major": (("scapular_retraction", C.MAJOR), ("scapular_downward_rotation", C.MAJOR)),
    "rhomboid_minor": (("scapular_retraction", C.MAJOR), ("scapular_downward_rotation", C.SUPPORTING)),
    "levator_scapulae": (("scapular_elevation", C.MAJOR), ("scapular_downward_rotation", C.SUPPORTING)),
    "pectoralis_minor": (("scapular_protraction", C.SUPPORTING), ("scapular_depression", C.SUPPORTING)),
    "biceps_brachii": (("elbow_flexion", C.MAJOR), ("shoulder_flexion", C.SUPPORTING)),
    "brachialis": (("elbow_flexion", C.MAJOR),),
    "brachioradialis": (("elbow_flexion", C.SUPPORTING),),
    "triceps_brachii": (("elbow_extension", C.MAJOR),),
    "anconeus": (("elbow_extension", C.SUPPORTING),),
    "flexor_carpi_radialis": (("wrist_flexion", C.MAJOR), ("wrist_radial_deviation", C.SUPPORTING)),
    "flexor_carpi_ulnaris": (("wrist_flexion", C.MAJOR), ("wrist_ulnar_deviation", C.SUPPORTING)),
    "palmaris_longus": (("wrist_flexion", C.SUPPORTING),),
    "extensor_carpi_radialis_longus": (("wrist_extension", C.MAJOR), ("wrist_radial_deviation", C.SUPPORTING)),
    "extensor_carpi_radialis_brevis": (("wrist_extension", C.MAJOR), ("wrist_radial_deviation", C.SUPPORTING)),
    "extensor_carpi_ulnaris": (("wrist_extension", C.MAJOR), ("wrist_ulnar_deviation", C.SUPPORTING)),
}


S = MuscleStabilizationFunction.StabilizationType

STABILIZATIONS = (
    ("transversus_abdominis_trunk_postural", "transversus_abdominis", "segment", "trunk", S.POSTURAL, "Contribueix al control de la paret abdominal, la pressió interna i l'estabilitat funcional del tronc."),
    ("multifidus_spine_centering", "multifidus", "joint", "thoracolumbar_spine_complex", S.JOINT_CENTERING, "Contribueix al control intersegmentari del complex vertebral toracolumbar."),
    ("erector_spinae_trunk_postural", "erector_spinae", "segment", "trunk", S.POSTURAL, "Contribueix al manteniment i control de la postura del tronc sota càrrega."),
    ("gluteus_medius_pelvis_control", "gluteus_medius", "segment", "pelvis", S.SEGMENT_CONTROL, "Contribueix al control frontal de la pelvis, especialment en suport unilateral."),
    ("gluteus_minimus_hip_centering", "gluteus_minimus", "joint", "hip_joint", S.JOINT_CENTERING, "Contribueix al control i centratge funcional del cap femoral."),
    ("deep_rotators_hip_centering_piriformis", "piriformis", "joint", "hip_joint", S.JOINT_CENTERING, "Pot contribuir al control rotacional i al centratge funcional del maluc."),
    ("soleus_ankle_postural", "soleus", "joint", "ankle_joint", S.POSTURAL, "Contribueix al control postural de l'avanç de la tíbia sobre el peu en càrrega."),
    ("tibialis_posterior_foot_control", "tibialis_posterior", "segment", "foot", S.SEGMENT_CONTROL, "Contribueix al control funcional medial del peu sota càrrega."),
    ("supraspinatus_shoulder_centering", "supraspinatus", "joint", "shoulder_joint", S.JOINT_CENTERING, "Contribueix al centratge glenohumeral durant el moviment del braç."),
    ("infraspinatus_shoulder_centering", "infraspinatus", "joint", "shoulder_joint", S.JOINT_CENTERING, "Contribueix al control posterior i al centratge glenohumeral."),
    ("teres_minor_shoulder_centering", "teres_minor", "joint", "shoulder_joint", S.JOINT_CENTERING, "Contribueix al control posterior i al centratge glenohumeral."),
    ("subscapularis_shoulder_centering", "subscapularis", "joint", "shoulder_joint", S.JOINT_CENTERING, "Contribueix al control anterior i al centratge glenohumeral."),
    ("serratus_anterior_scapular_control", "serratus_anterior", "segment", "shoulder_girdle", S.SEGMENT_CONTROL, "Contribueix a mantenir i orientar l'escàpula sobre el tòrax durant el moviment del braç."),
    ("trapezius_lower_scapular_control", "trapezius_lower", "segment", "shoulder_girdle", S.SEGMENT_CONTROL, "Contribueix al control de la cintura escapular durant l'elevació del braç."),
    ("trapezius_middle_scapular_control", "trapezius_middle", "segment", "shoulder_girdle", S.SEGMENT_CONTROL, "Contribueix al control medial i posterior de la cintura escapular."),
    ("anconeus_elbow_centering", "anconeus", "joint", "elbow_joint", S.JOINT_CENTERING, "Assisteix l'estabilització funcional del colze durant l'extensió i la càrrega."),
)


def source_for_muscle(muscle_code):
    return next(item["source"] for item in MUSCLES if item["code"] == muscle_code)
