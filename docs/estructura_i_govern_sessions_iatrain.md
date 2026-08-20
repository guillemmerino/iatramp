# Estructura i govern de les sessions d’IA Train

> **Estat:** base implementada i operativa
> **Actualitzat:** 20 d’agost de 2026
> **Domini:** `iatrain.training`
> **Abast actual:** creació, revisió, aprovació i execució de sessions, amb prescripció física
> **Fora d’abast actual:** motor de generació, planificació de temporada, motor tècnic i interfície específica d’edició

## 1. Objectiu

Aquesta capa defineix l’estructura sobre la qual IA Train podrà crear, revisar, aprovar i registrar entrenaments. No selecciona exercicis automàticament: proporciona un contracte de dades estable perquè l’entrenador, una interfície o el futur motor d’IA treballin sobre les mateixes regles.

La implementació viu dins de l’aplicació existent `iatrain`. Els models estan separats internament per domini, però es continuen exposant des de `iatrain.models` per mantenir la compatibilitat amb Django i amb el codi actual.

## 2. Principis de disseny

1. **La sessió és una identitat estable.** La data, l’organització i l’entrenador responsable pertanyen a la sessió.
2. **La planificació es versiona.** Els canvis rellevants creen una nova `TrainingSessionRevision`; no reescriuen una sessió aprovada.
3. **L’ordre forma part del domini.** Blocs i ítems tenen una posició explícita i única dins del seu pare.
4. **Rol i domini són conceptes diferents.** Un bloc de preparació pot ser físic, tècnic, mixt o general.
5. **Exercici i prescripció no són el mateix.** El catàleg defineix què és l’exercici; la sessió defineix com s’ha de fer avui.
6. **El planificat i l’executat no se sobreescriuen.** Els resultats reals es desen separadament.
7. **L’aprovació és una frontera de confiança.** Només es pot executar una versió aprovada i formada per exercicis validats editorialment.
8. **La personalització és explícita.** Una adaptació individual queda vinculada al gimnasta, a l’ítem i a la versió concreta.

## 3. Jerarquia de dades

```text
TrainingSession
└── TrainingSessionRevision
    ├── SessionParticipantPlan
    ├── SessionGoal
    └── TrainingBlock
        └── TrainingSessionItem
            ├── PhysicalExercisePrescription
            ├── SessionItemAlternative
            └── SessionItemAthleteAdjustment

TrainingSession
└── TrainingSessionExecution
    ├── SessionAttendance
    └── TrainingItemResult
```

La branca superior representa **què s’ha planificat**. La branca inferior representa **què ha passat realment**.

## 4. Sessió i versions

### 4.1. `TrainingSession`

És la identitat estable de la convocatòria. Conserva:

- organització;
- gimnàs opcional;
- grup d’entrenament opcional;
- data i hora programades;
- durada esperada;
- disciplina;
- abast individual o de grup;
- entrenador responsable;
- estat operatiu;
- origen manual, generat o importat;
- persona creadora i dates d’auditoria.

Regles principals:

- l’entrenador responsable ha d’estar actiu;
- un grup ha de pertànyer a la mateixa organització;
- una sessió de grup necessita un grup;
- una sessió individual no pot quedar lligada a un grup;
- el gimnàs ha d’estar vinculat activament a l’organització.

### 4.2. `TrainingSessionRevision`

Conté una versió concreta de la planificació:

- número de versió;
- títol i objectiu general;
- durada planificada;
- origen de la proposta;
- motiu del canvi;
- versió substituïda, si existeix;
- autoria i dades d’aprovació.

El número és únic dins de la sessió i només pot existir una versió aprovada alhora. Una versió nova sempre neix com a esborrany.

Quan una nova versió substitueix l’aprovada, l’anterior passa a `superseded` i conserva qui i quan la va aprovar. Si una sessió ja ha començat a executar-se, no es pot canviar la versió aprovada.

## 5. Participants i objectius

### 5.1. `SessionParticipantPlan`

Declara quins gimnastes formen part de la versió. Per a cada participant permet indicar:

- participació completa, parcial o opcional;
- objectiu individual;
- notes de planificació.

Un gimnasta només pot aparèixer una vegada en cada versió i el seu perfil ha d’estar actiu.

### 5.2. `SessionGoal`

Representa un objectiu explícit de la sessió. Se separa en:

- domini: físic, tècnic, recuperació, avaluació o general;
- codi estable;
- descripció;
- prioritat principal, secundària o opcional;
- origen: entrenador, planificació, avaluació o sistema;
- justificació.

Per proposar una versió cal almenys un objectiu principal.

## 6. Blocs i ítems

### 6.1. `TrainingBlock`

Agrupa contingut amb un objectiu i una forma d’execució comuns.

El **rol** indica la funció dins de la sessió:

- preparació;
- principal;
- complementari;
- recuperació;
- avaluació.

El **domini** indica la naturalesa del treball:

- físic;
- tècnic;
- mixt;
- general.

Això permet, per exemple, tenir un bloc `preparation + physical` i un altre `main + physical` sense tractar tots dos com el mateix tipus de bloc.

També conserva ordre, durada, transició, objectiu, instruccions, opcionalitat, rondes, descans entre rondes i mode d’execució: seqüencial, circuit, estacions, supersèrie o paral·lel.

### 6.2. `TrainingSessionItem`

És la unitat executable ordenada dins d’un bloc. Pot representar:

- exercici físic;
- instrucció;
- recuperació;
- pausa;
- tasca tècnica;
- element tècnic;
- seqüència;
- avaluació.

Actualment només l’exercici físic té un detall especialitzat implementat. Els tipus tècnics existeixen perquè l’estructura sigui compartida, però el seu motor i les seves prescripcions encara no formen part d’aquesta fase.

Cada ítem pot conservar títol, instruccions, consignes, durada, descans posterior, justificació de selecció i opcionalitat.

## 7. Prescripció física i personalització

### 7.1. `PhysicalExercisePrescription`

Converteix una revisió validada del catàleg d’exercicis en una prescripció concreta. Un ítem físic ha de tenir exactament una prescripció i una prescripció no es pot afegir a un ítem no físic.

Pot expressar:

- exercici i revisió exacta utilitzada;
- dosi per repeticions, durada, distància, manteniment o assistència;
- sèries;
- repeticions, segons o distància;
- càrrega i unitat;
- mètrica i valor d’intensitat;
- tempo excèntric, pausa i tempo concèntric;
- intenció concèntrica controlada, ràpida o explosiva;
- descans entre sèries;
- notes d’execució.

Les unitats es desen amb el seu valor: no es permet una càrrega o una distància ambigua.

### 7.2. `SessionItemAlternative`

Defineix exercicis substitutius preparats abans de començar. Cada alternativa té prioritat, justificació i un desencadenant:

- material no disponible;
- dificultat excessiva;
- dolor o restricció;
- logística de grup;
- decisió de l’entrenador.

### 7.3. `SessionItemAthleteAdjustment`

Personalitza un ítem per a un participant concret. Pot substituir l’exercici o sobreescriure sèries, repeticions, durada, càrrega, intensitat i descans.

L’ajust i el participant han de pertànyer a la mateixa versió. La justificació i les notes d’adaptació permeten que el futur motor expliqui per què dos gimnastes reben una dosi diferent dins del mateix grup.

## 8. Cicle de vida i govern

### 8.1. Estat de la versió

```text
draft ──→ proposed ──→ approved ──→ superseded
  ↑           │
  └───────────┤
              └──→ rejected ──→ draft
```

- `draft`: es poden editar la versió, participants, objectius, blocs, ítems i prescripcions.
- `proposed`: el contingut queda bloquejat i preparat per revisar.
- `approved`: és l’única versió executable.
- `superseded`: era una versió aprovada, però una versió posterior l’ha substituït.
- `rejected`: permet tornar una proposta a revisió. L’estat existeix al model, però encara no hi ha un servei públic específic per rebutjar-la.

No es permet editar ni eliminar el detall d’una versió que ja no sigui esborrany. Les transicions d’estat també estan restringides al model, no només a la interfície.

### 8.2. Validació abans de proposar

La versió ha de tenir:

- almenys un participant;
- almenys un objectiu principal;
- almenys un bloc;
- almenys un ítem dins de cada bloc;
- una prescripció per a cada ítem físic;
- una suma de durades de blocs que no superi la durada planificada.

En aquest pas es poden revisar plans que encara fan referència a exercicis en esborrany.

### 8.3. Validació abans d’aprovar

A més de les regles anteriors:

- l’entrenador ha de poder editar l’entrenament de tots els participants dins de l’organització;
- l’exercici principal de cada prescripció ha d’estar validat editorialment;
- totes les alternatives han d’estar validades;
- qualsevol exercici substitutiu d’una adaptació individual també ha d’estar validat.

Aquesta frontera evita que el futur LLM converteixi una proposta provisional en una sessió executable sense revisió professional.

### 8.4. Estat operatiu de la sessió

```text
scheduled → in_progress → completed
     └──────────────────→ cancelled
```

Els serveis actuals implementen l’inici i la finalització normal o interrompuda. L’estat `cancelled` està reservat al model, però encara no té un servei públic propi.

## 9. Execució real

### 9.1. `TrainingSessionExecution`

Fixa quina versió aprovada s’ha executat, qui l’ha supervisat i les dates reals d’inici i finalització. Una sessió només pot tenir una execució.

No es pot iniciar una sessió sense versió aprovada. Quan comença, la sessió passa a `in_progress`; quan finalitza, passa a `completed`.

### 9.2. `SessionAttendance`

Registra per participant:

- present, absent, parcial o justificat;
- hora d’entrada i sortida;
- notes.

Només es pot registrar assistència per als gimnastes inclosos en la versió aprovada.

### 9.3. `TrainingItemResult`

Conserva el resultat d’un ítem per a un gimnasta:

- completat, parcial, omès, substituït o aturat;
- exercici realment executat;
- sèries, repeticions, durada i càrrega reals;
- esforç percebut de 0 a 10;
- qualitat d’execució d’1 a 5;
- resposta al dolor;
- retorn del gimnasta i de l’entrenador;
- autoria i moment del registre.

L’ítem ha de pertànyer exactament a la versió aprovada de l’execució i el gimnasta ha de formar part de la planificació.

## 10. Planificació i execució no són equivalents

| Concepte | Planificat | Executat |
|---|---|---|
| Exercici | `PhysicalExercisePrescription.exercise_revision` | `TrainingItemResult.exercise_revision_performed` |
| Sèries | `sets` | `actual_sets` |
| Repeticions | `repetitions` | `actual_repetitions` |
| Durada | `duration_seconds` | `actual_duration_seconds` |
| Càrrega | `load_value` i `load_unit` | `actual_load_value` i `actual_load_unit` |
| Intensitat prevista | `intensity_metric` i `intensity_value` | `perceived_exertion` |
| Adaptació prevista | `SessionItemAthleteAdjustment` | exercici i resultat real registrats |

Exemple: una prescripció de `3 × 8` pot produir un resultat real de `3 × 7`. El resultat no modifica la prescripció; tots dos registres es conserven per poder explicar, comparar i aprendre.

## 11. Exemple resumit

```text
Sessió: Preparació física de trampolí, 60 minuts
Versió 1: Esborrany

Participants
└── Aina: participació completa

Objectiu principal
└── Físic: millorar força i control del tren inferior

Bloc 1
├── Rol: preparació
├── Domini: físic
├── Durada: 15 minuts
└── Ítem 1: esquat amb pes corporal
    ├── Prescripció: 3 × 8, RPE 6, descans 60 s
    ├── Alternativa: esquat assistit si la dificultat és excessiva
    └── Ajust Aina: 3 × 6 si apareix pèrdua d’alineació
```

Flux posterior:

```text
esborrany
→ proposta estructuralment vàlida
→ aprovació amb exercicis validats
→ inici de l’execució
→ assistència d’Aina: present
→ resultat: 3 × 7, RPE 7,5, qualitat 4/5
→ sessió completada
```

## 12. Serveis d’aplicació disponibles

La creació i les transicions no haurien de repetir-se en vistes, comandes o eines d’IA. La capa `iatrain.training.services` proporciona:

- `create_training_session`;
- `create_session_revision`;
- `validate_session_revision`;
- `propose_session_revision`;
- `reopen_session_revision`;
- `approve_session_revision`;
- `start_session_execution`;
- `complete_session_execution`.

Aquests serveis resolen autoria, permisos, bloqueig concurrent, validació integral i canvis d’estat.

## 13. Identitat i historial

Les referències a persones i perfils formen part del mecanisme general de fusió d’identitats d’IA Train. Quan es consoliden dos perfils:

- es traslladen sessions creades i aprovades;
- es retargeten entrenadors responsables i supervisors;
- es preserven participants i adaptacions;
- es consoliden assistències duplicades;
- es conserven els comentaris dels resultats coincidents.

Això evita eliminar o trencar l’historial d’una sessió quan dues identitats representaven la mateixa persona.

## 14. Frontera amb el futur motor

El motor de generació haurà de produir **propostes en esborrany** sobre aquesta estructura. No haurà de crear models paral·lels ni guardar una sessió completa en JSON.

El motor podrà:

1. interpretar la petició i el context dels participants;
2. definir objectius i blocs;
3. consultar exercicis candidats;
4. crear prescripcions, alternatives i ajustos;
5. justificar cada selecció;
6. validar la coherència del conjunt;
7. presentar una proposta editable a l’entrenador.

L’aprovació continuarà sent una acció governada. La connexió futura amb el motor tècnic reutilitzarà sessió, versió, participants, objectius, blocs i ítems, afegint els detalls especialitzats necessaris per als ítems tècnics.

## 15. Implementació de referència

- Models de sessió: `iatrain/training/models/sessions.py`
- Models de planificació: `iatrain/training/models/planning.py`
- Models d’execució: `iatrain/training/models/execution.py`
- Serveis i transicions: `iatrain/training/services.py`
- Integració administrativa: `iatrain/admin.py`
- Fusió d’identitats: `iatrain/identity.py`
- Migració inicial: `iatrain/migrations/0009_trainingblock_trainingsession_and_more.py`
- Proves funcionals: `iatrain/tests/test_training_sessions.py`

