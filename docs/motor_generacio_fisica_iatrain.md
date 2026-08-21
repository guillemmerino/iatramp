# Motor de generació física d’IA Train

> **Estat:** primera versió funcional implementada
> **Actualitzat:** 21 d’agost de 2026
> **Domini:** `iatrain.engine`, integrat dins de l’aplicació `iatrain`
> **Abast:** generar, revisar, reformular i aplicar blocs de preparació física
> **Fora d’abast:** motor tècnic, diagnòstic clínic, aprenentatge automàtic a partir dels resultats i generació completa d’una sessió en una sola acció

Aquest document és el punt d’entrada per a qualsevol agent o desenvolupador que continuï el motor. Descriu les decisions de domini, els models, el contracte, el paper d’OpenAI, la selecció d’exercicis, la dosificació, la interfície i els buits pendents.

## 1. Resultat actual

Des de la pàgina d’una versió de sessió en esborrany, l’entrenador pot:

1. descriure en llenguatge natural què vol treballar;
2. indicar durada i funció del bloc;
3. obtenir una proposta d’exercicis del seu catàleg;
4. revisar objectiu interpretat, dosi, càrrega estimada, justificacions, advertiments, alternatives, adaptacions individuals i fonts;
5. demanar una reformulació en llenguatge natural;
6. descartar la proposta o afegir-la a la sessió.

La proposta no modifica la sessió fins que l’entrenador prem **Afegir a la sessió**. L’aplicació es fa dins d’una transacció i crea els models relacionals normals de sessió; el JSON de la proposta només és una traça auditable.

## 2. Principi arquitectònic

El LLM no és el motor de selecció ni té accés lliure a la base de dades. És una capa d’interpretació professional situada davant d’un motor determinista.

```text
llenguatge natural de l’entrenador
                ↓
OpenAI interpreta el context i crea BlockGenerationRequest
                ↓
validador canònic del servidor
                ↓
consulta privada del catàleg + filtres obligatoris
                ↓
puntuació explicable + dosificador
                ↓
BlockGenerationProposal validada
                ↓
revisió humana a la UI
                ↓
adaptador transaccional
                ↓
TrainingBlock + items + prescripcions + ajustaments
```

Aquesta separació permet canviar el model d’OpenAI o afegir un altre intèrpret sense reescriure el domini de sessions. També impedeix que una resposta generativa inventi identificadors, salti permisos o escrigui directament una sessió.

## 3. Models persistents implicats

### 3.1. Estructura de sessió

Els models viuen a `iatrain.training` i s’exposen també des de `iatrain.models`:

```text
TrainingSession
└── TrainingSessionRevision
    ├── SessionParticipantPlan
    ├── SessionGoal
    ├── BlockGenerationRun
    └── TrainingBlock
        └── TrainingSessionItem
            ├── PhysicalExercisePrescription
            ├── SessionItemAlternative
            └── SessionItemAthleteAdjustment
```

- `TrainingSessionRevision` és la frontera versionada i ha d’estar en `draft` per generar.
- `TrainingBlock` conserva funció, domini, durada, ordre i mode d’execució.
- `PhysicalExercisePrescription` fixa l’exercici i la dosi concreta d’aquell dia.
- `SessionItemAlternative` conserva substitucions preparades.
- `SessionItemAthleteAdjustment` sobreescriu la dosi o l’exercici per a un participant.

La documentació completa d’aquesta branca continua a [estructura_i_govern_sessions_iatrain.md](estructura_i_govern_sessions_iatrain.md).

### 3.2. `BlockGenerationRun`

És la traça d’una generació automàtica. Desa:

- versió de sessió i persona creadora;
- petició original i instrucció de reformulació;
- relació amb la proposta anterior, si n’és una reformulació;
- interpretació, request i proposal serialitzades;
- fonts declarades per la interpretació;
- model, versió del prompt, del motor i del contracte;
- estat `processing`, `proposed`, `applied`, `discarded` o `failed`;
- error operatiu concís;
- bloc aplicat, si l’entrenador l’ha acceptat.

No és la font autoritativa del bloc. Quan una proposta s’aplica, la font de veritat passa a ser el graf relacional normal de la sessió. No s’hi desen claus API.

### 3.3. `ExercisePrescriptionGuideline`

Viu a `iatrain_exercises` i depèn d’una `ExerciseRevision`. Defineix una envolupant de dosificació governada, no una recepta fixa:

- etapa: infància, adolescència, adult, adult gran o totes;
- experiència: inicial, intermèdia, avançada o totes;
- objectiu físic i funció del bloc;
- mode de dosi;
- mínim, valor habitual i màxim de sèries, repeticions o durada;
- descans, RPE, temps de preparació i temps estimat per repetició;
- demanda mecànica, neuromuscular, metabòlica i coordinativa de 0 a 5;
- regla d’aturada per pèrdua de qualitat;
- tipus d’evidència, font, any i justificació;
- estat actiu.

Forma part de la revisió de l’exercici i, per tant, queda sotmesa al mateix govern editorial. Una guia específica elegible preval sobre la baseline general.

### 3.4. Pont de material

`GymEquipment.catalog_equipment_codes` connecta una fila de l’inventari real amb els codis de material del catàleg d’exercicis. També hi ha equivalències automàtiques per noms habituals, per exemple `mancuerna → dumbbell` i `banda elàstica → elastic_band`.

La compatibilitat de material es resol al servidor. Un exercici amb material obligatori que no estigui disponible no és candidat.

## 4. Contracte no persistent

Els value objects de `iatrain/engine/contracts.py` formen la capa intermèdia entre llenguatge natural i models Django.

### Entrada: `BlockGenerationRequest`

Inclou:

- identificador, ordre i participants de la versió;
- nom, funció, domini i durada del bloc;
- `BlockObjective`: descripció, qualitat principal, qualitats secundàries, patrons i regions;
- mode d’execució, rondes i descans;
- intensitat objectiu;
- material disponible;
- restriccions obligatòries;
- preferències i instruccions lliures.

Els identificadors de sessió, participants i material, la funció indicada a la UI i el límit de temps són autoritat del servidor. El LLM no els pot substituir.

Restriccions obligatòries canòniques actuals:

- `validated_only`;
- `bodyweight_only`;
- `no_equipment`;
- `no_jumps`;
- `no_impact`;
- `avoid_high_impact`;
- `avoid_failure`.

Una instrucció que no encaixa en aquesta llista continua com a preferència o instrucció narrativa. No es converteix silenciosament en una regla que el motor no pugui garantir.

### Sortida: `BlockGenerationProposal`

Inclou:

- request original validada;
- ítems ordenats amb dosi;
- alternatives i adaptacions individuals;
- durada estimada;
- `BlockLoadEstimate` en quatre dimensions relatives;
- `BlockCoverage` de qualitats, patrons i regions;
- restriccions satisfetes o incomplertes;
- advertiments;
- confiança de la selecció;
- `generator_reference` amb versions de motor i guies.

El validador rebutja una proposta amb participants incorrectes, temps excedit, posicions duplicades, exercicis inexistents o aliens, dosi incoherent, adaptacions fora de la sessió o qualsevol restricció obligatòria no satisfeta.

## 5. Context viu de l’esportista

`build_block_engine_context` reutilitza `build_athlete_profile_context`. Per cada participant aporta una fotografia temporal de:

- edat i etapa vital;
- perfils esportius i experiència acumulada;
- condicions actives i impacte sobre l’entrenament;
- insights confirmats;
- observacions vigents;
- respostes recents a entrenaments;
- disponibilitat o absència de permís sobre dades de salut.

El perfil separa dues dimensions que no s’han de confondre:

- **etapa vital:** infant, adolescent, adult o adult gran;
- **experiència:** inicial, intermèdia o avançada.

Per tant, un infant de competició d’alt rendiment pot ser `child + advanced`, mentre que un adult sedentari serà `adult + novice`. El grup adopta l’envolupant més conservadora quan hi ha perfils diferents, i després crea ajustaments individuals quan correspon.

El motor no diagnostica. Les condicions confirmades tenen una semàntica operativa explícita:

- `stop`: bloqueja la generació;
- `avoid`: exclou candidats que coincideixen amb la regió afectada;
- `modify`: redueix dosi/intensitat i augmenta descans per al participant;
- `monitor`: manté el candidat amb una penalització de seguretat.

Si l’entrenador no té permís per consultar salut, la proposta mostra un advertiment i necessita revisió explícita.

## 6. Paper d’OpenAI

La integració usa directament la **Responses API**, sense afegir una dependència de client. La resposta es força amb **Structured Outputs** i un esquema JSON estricte.

OpenAI rep una versió minimitzada del context: no s’hi envien noms ni dates de naixement, sinó edat calculada, etapa, experiència, dades esportives rellevants i informació necessària per raonar. La crida usa `store: false`.

La cerca web integrada està habilitada perquè l’intèrpret pugui contrastar guies quan sigui rellevant. El prompt prioritza posicionaments professionals, consensos, federacions i literatura revisada, obliga a indicar l’aplicabilitat de la font i prohibeix presentar una guia d’adults com si fos específica per a infants.

El LLM pot:

- entendre llenguatge natural i sinònims;
- escollir valors del vocabulari ofert;
- detectar si falta una dada imprescindible;
- proposar objectiu, patrons, intensitat, preferències i restriccions;
- explicar breument la interpretació i aportar fonts.

El LLM no pot:

- consultar o modificar models Django directament;
- seleccionar IDs d’exercicis;
- inventar participants o material;
- superar el temps disponible;
- aplicar una proposta;
- aprovar una sessió;
- substituir una decisió clínica o professional.

## 7. Recuperació i puntuació d’exercicis

El recuperador consulta únicament variants actives dels catàlegs privats de la persona entrenadora. Exclou revisions retirades i aplica filtres obligatoris abans de puntuar:

1. estat editorial si s’ha demanat `validated_only`;
2. material obligatori disponible;
3. restriccions de pes corporal, salts o impacte;
4. regions afectades per condicions `avoid`;
5. indicacions `stop`;
6. una dificultat clarament incompatible amb l’experiència del grup.

Els candidats elegibles reben una puntuació explicable sobre 100:

| Component | Pes màxim |
|---|---:|
| coincidència amb objectiu i patró | 30 |
| adequació de dificultat i experiència | 20 |
| seguretat contextual | 15 |
| logística i material | 15 |
| cobertura del patró demanat | 10 |
| resposta recent dels participants | 10 |

Una revisió encara en esborrany rep una penalització editorial de 8 punts i genera un advertiment. Això permet provar el motor amb el catàleg actual, però una versió de sessió no es podrà aprovar fins que tots els exercicis principals, alternatius i substitutius estiguin validats editorialment.

La puntuació ordena candidats; no és una probabilitat clínica ni una mesura d’eficàcia. La confiança mostrada a la proposta deriva de la puntuació mitjana dels exercicis seleccionats.

## 8. Dosificació

El dosificador segueix dues capes:

1. `ExercisePrescriptionGuideline` específica, si n’hi ha una d’activa que coincideix amb etapa, experiència, objectiu i funció;
2. baseline professional versionada del motor, si no n’hi ha cap.

La baseline cobreix objectius de força general, força màxima, hipertròfia, resistència muscular, potència, control motor, mobilitat i preparació. Modula rangs segons:

- etapa vital;
- experiència real;
- execució dinàmica o isomètrica;
- modalitat d’escalfament;
- intensitat baixa, moderada o alta;
- funció de preparació o recuperació.

Les envolupants infantils, adolescents i d’adults grans conserven límits i regles de qualitat propis encara que l’esportista tingui experiència avançada. Un esportista avançat no és sinònim d’adult.

Les baselines incorporades declaren com a referències de govern la posició de la NSCA sobre entrenament de força en joves, el posicionament de l’ACSM sobre prescripció de força i el consens del CIO sobre desenvolupament atlètic juvenil. Són un punt de partida conservador i versionat, no substitueixen la revisió professional de cada exercici.

El motor ajusta el nombre d’exercicis i de sèries al pressupost temporal, estima preparació, treball i descans, i no persisteix una proposta que superi la durada del bloc. Quan usa una baseline general ho declara com a advertiment perquè es pugui crear una guia específica posteriorment.

## 9. Flux de la interfície

La UI és a la pàgina de detall de sessió:

1. l’entrenador crea una sessió i hi afegeix participants;
2. a **Generar un bloc**, escriu la petició, la durada i la funció;
3. mentre es genera, el botó queda bloquejat;
4. la proposta apareix fora de la llista de blocs i encara no modifica la sessió;
5. l’entrenador pot reformular-la amb una frase;
6. **Descartar** només tanca la proposta;
7. **Afegir a la sessió** crea el bloc i tot el seu graf de dades;
8. el bloc aplicat continua sent editable amb els formularis manuals existents;
9. la versió segueix el flux normal de proposta i aprovació.

Si no hi ha clau, la UI explica l’única configuració pendent i desactiva el botó de generació. La resta de creació manual continua operativa.

## 10. Configuració

L’únic secret necessari és la clau d’OpenAI. En desenvolupament s’ha de desar
únicament a `.env.dev.local`, un fitxer ignorat per Git que Docker Compose carrega
automàticament després de `.env.dev`:

```env
OPENAI_API_KEY=
```

Cal afegir-hi el valor i recrear el servei web amb `docker compose up -d web` perquè
rebi l’entorn. No cal indicar `--env-file`. Un simple `docker compose restart web`
no torna a llegir els fitxers d’entorn. La resta té valors per defecte a `.env.dev`:

```env
OPENAI_TRAINING_MODEL=gpt-5.6
OPENAI_TRAINING_TIMEOUT_SECONDS=90
OPENAI_TRAINING_REASONING_EFFORT=medium
OPENAI_TRAINING_WEB_SEARCH=true
```

No s’ha d’escriure la clau al codi, als tests, a `BlockGenerationRun` ni a cap document.

## 11. Fitxers de referència

- contractes: `iatrain/engine/contracts.py`;
- context temporal: `iatrain/engine/context.py`;
- interpretació OpenAI: `iatrain/engine/openai.py`;
- recuperació i puntuació: `iatrain/engine/scoring.py`;
- guies i perfils de prescripció: `iatrain/engine/guidelines.py`;
- dosificació i muntatge: `iatrain/engine/generation.py`;
- validació: `iatrain/engine/validation.py`;
- serialització: `iatrain/engine/serialization.py`;
- aplicació transaccional: `iatrain/engine/adapter.py`;
- orquestració i auditoria: `iatrain/engine/services.py`;
- model de run: `iatrain/training/models/generation.py`;
- vistes: `iatrain/views/engine/generation.py`;
- formulari: `iatrain/engine/forms.py`;
- plantilla: `iatrain/templates/iatrain/sessions/detail.html`;
- comportament de client: `iatrain/static/iatrain/session_generation.js`;
- estils: `iatrain/static/iatrain/overview.css`;
- proves principals: `iatrain/tests/test_engine_block_contracts.py` i `iatrain/tests/test_profile_session_ui.py`;
- migracions: `iatrain/migrations/0011_blockgenerationrun_equipment_codes.py` i `iatrain_exercises/migrations/0003_exerciseprescriptionguideline.py`.

## 12. Decisions que s’han de preservar

1. Tot continua dins del domini `iatrain`; no s’ha de crear una app paral·lela de sessions.
2. El llenguatge natural es conserva a la frontera humana, però el motor només consumeix un contracte validat.
3. OpenAI interpreta; el servidor autoritza, consulta, selecciona, dosifica, valida i persisteix.
4. Edat, etapa de desenvolupament i experiència són dimensions diferents.
5. Exercici, guia de dosificació i prescripció de sessió són conceptes diferents.
6. Una proposta automàtica no és una sessió aprovada.
7. Els avisos i les justificacions són dades funcionals, no decoració.
8. El planificat i l’executat no se sobreescriuen.
9. Les dades clíniques no s’han de deduir ni ampliar amb el LLM.
10. La futura part tècnica ha de compartir sessió, blocs i context, però tenir contractes i selectors especialitzats.

## 13. Buits coneguts i següents passos

La primera versió és funcional, però encara no és el motor final:

- completar la revisió editorial dels exercicis del catàleg;
- afegir guies específiques als exercicis prioritaris i un flux de revisió professional massiva;
- ampliar el mapa entre patrons i regions amb el graf anatòmic-cinemàtic, en lloc del mapa conservador actual;
- interpretar semànticament `ExerciseConstraint`; ara les crítiques penalitzen, però només les restriccions canòniques tenen garantia dura;
- incorporar fatiga i càrrega acumulada a escala de microcicle, no només respostes recents;
- millorar la selecció de grup amb estacions, material limitat i concurrència real;
- afegir edició directa d’una proposta abans d’aplicar-la, a més de la reformulació natural;
- crear avaluacions amb casos esperats i mètriques de selecció, seguretat, temps i estabilitat;
- verificar i normalitzar automàticament les referències retornades per la cerca abans de considerar-les evidència governada;
- dissenyar el motor tècnic i el contracte de connexió entre càrrega física i contingut tècnic;
- tancar el bucle amb `TrainingItemResult` perquè les respostes reals informin propostes futures, sempre amb revisió humana.

No s’ha d’afegir aprenentatge automàtic o generació completa de sessions abans de tenir aquestes avaluacions i una política editorial clara per a guies, exercicis i fonts.
