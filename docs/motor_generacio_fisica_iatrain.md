# Motor agentiu de generació física d’IA Train

Estat canònic del motor agentiu `3.10`, sobre el contracte de proposta `3.5`, el pla
previ `1.1` i les eines `1.9`.

Aquest document explica la línia vigent d’IA Train: el model raonador és el motor de
planificació del bloc; el servidor li dona context professional i eines segures, comprova
invariants i només persisteix una proposta després de la confirmació de l’entrenador.

## 1. Resultat actual

Des de la versió en esborrany d’una sessió, l’entrenador pot descriure el bloc en llenguatge
natural. IA Train crea una execució auditable que:

1. construeix una fotografia minimitzada de la sessió, els participants i el material;
2. resol abans de l’agent qualsevol indicació explícita `stop`;
3. obliga el model a registrar un pla previ sense exercicis concrets;
4. valida objectiu, cobertura, abast, temps i estratègia abans de cercar;
5. dona al model eines de lectura sobre el catàleg privat, perfils i guies;
6. comprova els identificadors, l'alineació amb el pla, la compatibilitat i el temps;
7. mostra en directe el progrés segur de l’anàlisi, les cerques i les validacions;
8. presenta la proposta, les personalitzacions i un resum auditable de la cerca;
9. no modifica la sessió fins que l’entrenador prem **Afegir a la sessió**.

La configuració inicial usa `gpt-5.6-luna`. La comparació amb altres models i la cerca web
queden fora d’aquesta fase.

## 2. Principi arquitectònic vigent

```text
petició i premisses de l’entrenador
                 ↓
context viu i minimitzat de la sessió
                 ↓
preflight del servidor per a STOP explícits
        ↙                    ↘
decisió humana          participants actius
        ↓                    ↓
        └────── agent LLM amb function calling ──────┐
                                                     │
 conceptes professionals ←→ search_exercises ←→ details + knowledge support
          ↑                                      ↕
          └──────── accions/músculs/contracció   guidance/compatibility
          ↑                         ↓               ↓
          └──── alternatives compatibles ──── timing/audit
                                                     ↓
                              BlockGenerationProposal 3.5
                                                     ↓
                          validador canònic del servidor
                                                     ↓
                           revisor LLM independent
                 ↙ risc crític   ↘ error local   ↘ aprova
              bloqueig          review_required  proposta final
                                      ↓              ↓
                         previsualització i confirmació
                                                     ↓
                              adaptador transaccional
```

La integració segueix el patró de custom function calling de la Responses API. Amb
`store: false`, l’aplicació conserva durant la petició tots els output items i els retorna
en les iteracions següents, inclòs el contingut de raonament xifrat. IA Train no desa una
cadena de pensament llegible.

Referències d’implementació:

- [Responses API: create a model response](https://developers.openai.com/api/reference/cli/resources/responses/methods/create)
- [OpenAI model guidance](https://developers.openai.com/api/docs/guides/latest-model)

## 3. Repartiment d’autoritat

### 3.1. Decisions del LLM

El model és responsable de:

- interpretar objectius, preferències i premisses narratives;
- decidir quants exercicis necessita el bloc;
- decidir quantes cerques fer, quins filtres provar i quan paginar o ampliar la cerca;
- comparar candidats del catàleg professional;
- seleccionar exercicis principals i alternatives;
- decidir l’ordre, el mode d’execució i el nombre de rondes;
- decidir sèries, repeticions, durades, intensitat i descansos;
- decidir si una base compartida és adequada;
- crear modificacions, substitucions o omissions individuals;
- ajustar el volum perquè el bloc càpiga en el temps;
- explicar de manera breu i visible com les premisses han afectat la proposta.

La guia de dosificació és una envolupant professional consultable. Ja no és una fórmula que
imposa automàticament una dosi concreta.

### 3.2. Autoritat del servidor

El servidor conserva exclusivament:

- autenticació, autorització i separació entre catàlegs;
- versió de sessió, funció del bloc, temps màxim i participants reals;
- inventari de material disponible;
- execució de consultes mitjançant l’ORM;
- bloqueig d’una indicació explícita `stop` no resolta;
- propagació explícita de les dades absents com a incertesa no bloquejant;
- càlcul temporal exacte;
- existència, estat editorial i propietat dels identificadors;
- comprovació de dosis, participants, restriccions i cobertura;
- persistència transaccional després de l’acceptació humana.

El servidor no torna a puntuar candidats ni decideix quants exercicis s’han de seleccionar.
Les regles deterministes són controls o eines, no el motor de decisió.

## 4. Eines disponibles per a l’agent

Les eines viuen a `iatrain/engine/agent_tools.py`. Són de lectura o càlcul i tenen esquemes
JSON estrictes.

### `search_professional_concepts`

Resol llenguatge natural en conceptes canònics validats del graf anatòmic-cinemàtic:
segments, articulacions, accions, músculs i grups musculars. Els codis retornats formen
una allowlist de la run; el model no pot inventar codis per filtrar el catàleg.

### `search_exercises`

Cerca variants del catàleg privat de l’entrenador. Admet text lliure, objectiu, patrons,
modalitats, dificultat, accions, músculs, contraccions previstes, estat editorial,
compatibilitat de material i paginació. Els termes
de text s’apliquen com a alternatives, no com una intersecció impossible de totes les
paraules. Si una cerca queda buida, retorna pistes explícites perquè l’agent ampliï
progressivament patró, modalitat, material o estat editorial.

Retorna:

- nombre total de coincidències;
- offset, quantitat retornada i indicador de més resultats;
- dades descriptives de cada candidat;
- objectius, material i estat editorial;
- consideracions factuals per participant.

L’ordre és estable per nom. No hi ha una puntuació global que decideixi per al model.

### `get_exercise_details`

Amplia només candidats retornats anteriorment. Inclou descripció, preparació, execució,
consignes, seguretat i restriccions. No inclou claims professionals, per evitar duplicar
el mateix paquet quan es valida un finalista.

### `get_exercise_knowledge_support`

Recupera explícitament el paquet professional per lots de fins a vuit finalistes presents
a l'allowlist. Només utilitza dependències professionals validades i exclou connexions
privades pendents. El servidor no torna a enviar un exercici ja carregat.

### `get_prescription_guidance`

Resol l’envolupant de dosificació específica o la baseline professional per exercici,
participant, objectiu i funció del bloc. Retorna rangs i fonts, no una recepta final.

### `check_participant_compatibility`

Retorna condicions rellevants `avoid`, `modify` o `monitor`, etapa, experiència, edat
coneguda o desconeguda i respostes recents. La compatibilitat distingeix `compatible`,
`monitor`, `requires_modification`, `requires_risk_resolution`, `incompatible` i
`uncertain`. `avoid` ja no equival automàticament a incompatible: indica que el model ha
d'explicitar com elimina el risc. Una condició sense regió tampoc no es considera
silenciosament aplicable a tot el cos.

### `find_compatible_alternatives`

Busca substitucions per a una gimnasta i un exercici base. Pot conservar el patró o
ampliar-lo, respecta el material i l’estat editorial, descarta indicacions `stop` i
incompatibilitats estructurals conegudes, i retorna els motius de rebuig. Una alternativa
no es descarta només perquè comparteixi regió amb la condició: el model i el revisor han de
comprovar si redueix el risc concret. Els candidats vàlids s’incorporen a l’allowlist de la run.
L’agent l’ha de cridar abans de proposar qualsevol omissió individual.

### `calculate_block_timing`

Calcula preparació, treball, descans entre sèries, descans posterior, rondes i descans entre
rondes. La durada final declarada pel model ha de coincidir amb l’últim càlcul.

### `audit_block_draft`

Permet comprovar un esborrany complet contra el contracte del servidor abans de lliurar-lo.
Accepta tant l’esquema `plan` produït pel model com el payload canònic `request`; tots dos
passen pel mateix adaptador de serialització. Això elimina la divergència que feia fallar
l’auditoria tot i que la resposta final sí que es podia transformar. El servidor repeteix
igualment la validació després de la resposta final.

## 5. Seguretat i límits de les eines

- L’agent no rep cap eina d’escriptura.
- No pot executar SQL.
- Totes les consultes queden limitades al propietari del catàleg i a la sessió actual.
- Només pot demanar detalls de candidats obtinguts mitjançant `search_exercises`.
- La proposta final només pot referenciar identificadors presents a l’allowlist de la run.
- Les revisions retirades no apareixen a la cerca.
- Els límits de rondes, crides i candidats eviten bucles sense control.
- Qualsevol error de contracte activa un màxim d’intents de reparació.
- Una proposta parcial o invàlida no es pot aplicar.
- Cap participant actiu pot ometre tots els exercicis físics del bloc.
- Un exercici en esborrany només es pot usar després d’una autorització visible de
  l’entrenador.
- Una participant `personalized` necessita almenys un `athlete_adjustment`, i qualsevol
  ajustament obliga a marcar-la com a personalitzada.
- Les notes compartides no poden contenir instruccions dirigides a una participant.
- Cada condició `avoid` o `modify` necessita una decisió estructurada; `avoid` es pot
  resoldre amb `modify`, `replace` o `skip`, sempre amb un ajustament corresponent que
  expliqui quin risc elimina i com ho fa.
- Tots els exercicis finals han de tenir detalls, compatibilitat i guia consultats per a
  les participants a qui s’apliquen.
- Dosi, rondes, descansos, preparació i durada visible han de coincidir exactament amb
  l’últim càlcul temporal.

### Autorització editorial estructurada

Si el catàleg privat no conté cap revisió validada però sí revisions en esborrany, el
servidor atura la run abans de cridar l’LLM i presenta **Permetre cercar i utilitzar
esborranys**. La resposta es desa com
`catalog_drafts=allow_draft_exercises` dins de la mateixa run.

Quan es reprèn, les eines apliquen el permís de manera efectiva: encara que el model demani
`validated_only=true`, la cerca s’amplia als esborranys autoritzats i ho registra a la
traça amb els filtres demanat i efectiu. Si conviuen revisions validades i esborranys, les
validades continuen apareixent primer. Ja no s’ha de respondre «sí» en el camp lliure de
reformulació, perquè això creava una run nova sense conservar una decisió editorial.

## 6. Participants i personalització

`stop` continua sent una frontera dura del servidor. La run passa a `awaiting_decision` i
l’entrenador pot excloure la gimnasta només del bloc o actualitzar el perfil abans de
continuar. Després de l’exclusió, el model torna a planificar amb el grup real resultant.

Cada condició té un abast `regional`, `global` o `unknown`. Una condició `avoid` o `modify`
amb abast desconegut no es converteix en una prohibició global i ja no interromp el
preflight: l'agent continua prudentment, redueix confiança o afegeix un avís si és rellevant.
L'entrenador encara pot excloure explícitament la participant del bloc o corregir el perfil.
Des del perfil, **Corregir dades** crea una versió pendent que substitueix la condició
anterior quan és confirmada, mantenint l’historial.

La resta d’informació arriba a l’agent:

- `avoid`: ha d'eliminar el risc concret mitjançant modificació, substitució o, com a última
  via, `skip` individual;
- `modify`: pot modificar dosi, intensitat, descans o exercici;
- `monitor`: pot mantenir l’exercici amb seguiment explícit;
- qualsevol dada desconeguda —edat, experiència, càrrega o abast corporal— és una incertesa
  que el model ha de gestionar prudentment, però no interromp automàticament el flux;
- inactivitat, estat anímic, experiència i càrrega recent: són premisses de planificació i
  cerca, no simples advertiments finals.

«Compartit» significa que aquella gimnasta usa la prescripció base. Si rep qualsevol canvi,
substitució o omissió, la seva assignació és `personalized`. La impossibilitat de compartir
un exercici no atura el bloc: l’agent busca una sortida individual i segueix endavant.
Un `skip` vol dir que la gimnasta no fa aquell ítem; no és una etiqueta de compatibilitat.
Ara només és acceptable després d’haver cercat alternatives i mai pot deixar una
participant activa sense cap exposició física. Si el catàleg no permet una sortida segura,
la run demana una decisió a l’entrenador en lloc d’amagar l’impediment.

## 7. Contracte 3.5 i pla previ 1.1

`BlockGenerationProposal` continua sent LLM-agnòstic i compatible amb l’adaptador existent.
La versió `3.0` va afegir:

- `planning_summary`: justificació observable i concisa;
- `premise_effects`: efectes concrets de les premisses;
- `search_summary`: resum narratiu de l’exploració.

La versió `3.1` afegeix:

- `setup_seconds` a cada ítem, perquè preparació, treball, descans i temps total siguin
  visibles i verificables;
- `condition_decisions` per participant, amb condició, acció, justificació i ítems afectats;
- correspondència obligatòria entre `personalized` i `athlete_adjustments` reals;
- prohibició de posar indicacions individuals dins de notes compartides.

La versió `3.2` afegeix `station_remainder_action` (`rest`, `reset` o `monitor`) als
ajustaments individuals. En un circuit, estació, paral·lel o supersèrie, una dosi
individual més curta és temps de treball dins de l'estació comuna: cal explicar l'ús del
temps restant i mai es pot allargar més que la durada compartida.

La versió `3.3` afegeix `knowledge_support` a cada ítem físic. Pot ser `grounded`,
`hypothesis` o `not_applicable`. Un suport fonamentat cita identificadors exactes retornats
per les eines i cobreix l'exercici principal, les alternatives i les substitucions. Una
hipòtesi conserva llibertat de decisió davant un buit, però no es presenta com un fet. El
servidor rebutja identificadors, fonts o limitacions alterats pel model.

La versió `3.4` afegeix `professional_justification` a cada ajustament individual. La
cadena conserva condicions o factors del perfil, claims i fases professionals, la
rellevància biomecànica inferida, l'objectiu de l'adaptació i criteris de monitoratge i
aturada. Les condicions `monitor` requereixen una decisió estructurada encara que la dosi
comuna es mantingui. `planned_duration_seconds` queda definit com el total d'una passada
per l'ítem i inclou preparació, treball, descansos entre sèries i descans posterior.

La versió `3.5` vincula la proposta amb un `BlockPlanningBrief 1.1` acceptat abans de la
cerca. El pla no tria exercicis: declara criteris d'èxit, cobertura, intensitat, temps,
restriccions amb abast i estratègia de recuperació. El servidor compara els patrons i
dominis reals dels exercicis amb aquest pla, exigeix que les dosis unilaterals indiquin si
són totals o per costat i conserva la lateralitat de les condicions als criteris
individuals. El context inicial és compacte i el detall s'amplia amb
`get_participant_context` només quan cal.

El model proposa nom, objectiu, intensitat, mode, rondes, ítems, dosis, variants, càrrega,
cobertura i participació. El servidor injecta o limita les dades autoritatives: revision,
ordre, funció, durada, participants, exclusions i material.

Els lectors de serialització continuen admetent els contractes `1.0`, `2.0`, `3.0`, `3.1`, `3.2`, `3.3` i `3.4`
que ja poguessin estar desats.

## 8. Traçabilitat de `BlockGenerationRun`

La run incorpora:

- `planning_payload`: pla acceptat abans de consultar el catàleg;
- `agent_trace`: nom de cada eina, arguments, estat, recompte i IDs retornats;
- `response_ids`: identificadors de les respostes de l’API;
- `usage_payload`: tokens d’entrada, sortida, total i cachejats;
- `validation_payload`: intents, alineació del pla, mètriques de context, allowlist i temps;
- model i versions de prompt, motor, eines i contracte;
- proposta completa i decisions de l’entrenador.

No s’hi desen la clau API ni raonaments interns llegibles. La UI mostra un resum amb model,
nombre de cerques, candidats únics, seleccionats, crides d’eina i verificació temporal.
La traça també diferencia les cerques generals de les alternatives individuals i conserva
els recomptes de candidats rebutjats, però no copia la proposta completa dins de cada fita.

### Revisió independent i reparació

Una proposta que supera el contracte encara no arriba directament a l’entrenador. Una
segona crida, sense l’historial del planificador i amb instruccions exclusivament crítiques,
revisa cobertura real, nivell, inactivitat, dosi, seguretat, condicions individuals,
alternatives i coherència entre justificacions i ajustaments.

El revisor retorna `pass`, `revise` o `needs_clarification`, i classifica cada incidència
com a `critical`, `error` o `warning`:

- `pass`: la proposta es pot mostrar;
- `revise`: disposa d'un pressupost de reparació propi, separat dels errors estructurals;
- `needs_clarification`: només per una dada imprescindible absent o perquè no existeix una
  sortida viable; aleshores intervé l’entrenador.

Després de consumir les reparacions del revisor, un risc `critical` continua bloquejant.
Un `error` local no descarta la resta del bloc: la run queda en `review_required`, mostra
participants i ítems afectats i només es pot afegir com a esborrany editable després d'una
confirmació explícita. L'entrenador pot editar cada adaptació individual ja persistida.
Els `warning` són informatius. Les impossibilitats estructurals, un temps físicament
impossible i la manca d'una sortida segura continuen bloquejant o demanant una decisió.

Cada reparació comença amb un paquet compacte: petició original, proposta actual, errors,
evidència dels exercicis seleccionats, allowlist i últim càlcul temporal. No reenvia tot
l'historial acumulat. Les consultes independents de detalls, guies i compatibilitat es
poden retornar com a múltiples function calls en una sola ronda de Responses. El servidor
les processa i retorna tots els resultats abans de la ronda següent. Això redueix context
repetit sense eliminar l'auditoria persistent.

El veredicte, severitats, participants, ítems, intents, comptadors de reparació i IDs de
resposta queden a `validation_payload`. La UI mostra el resum i les correccions pendents.

### Progrés visible durant la generació

La petició web ja no queda bloquejada mentre l’agent treballa. En crear o reprendre una
generació:

1. el servidor crea la run en estat `processing` i retorna immediatament la pantalla;
2. un worker Celery executa el bucle agentiu en segon pla;
3. cada fita segura queda desada a `progress_payload`, juntament amb la traça acumulada;
4. la pantalla consulta l’endpoint d’estat cada 1,5 segons;
5. quan la run acaba, la pantalla carrega automàticament la proposta, la decisió pendent o
   l’error recuperable.

Durant l’espera, l’entrenador pot veure el temps transcorregut, les cerques fetes, els
candidats únics recuperats, les crides d’eina, les iteracions i una cronologia operativa:
anàlisi de premisses, cerca al catàleg, comparació, dosificació, personalització, càlcul del
temps, validació i possibles correccions.

Els missatges són fites definides pel sistema. No exposen la cadena de pensament del model,
arguments complets de les eines ni informació mèdica de participants. La visualització no
fa crides addicionals; el revisor sí que és una crida LLM funcional i auditada.

Quan s’aplica la proposta, la font de veritat és el graf relacional normal:

```text
TrainingBlock
├── BlockParticipantAssignment + condition_decisions
└── TrainingSessionItem
    ├── setup_seconds
    ├── PhysicalExercisePrescription
    ├── SessionItemAlternative
    └── SessionItemAthleteAdjustment
```

## 9. Paper del motor determinista anterior

El desenvolupament anterior no s’ha descartat:

- `context.py` continua construint el context viu;
- `guidelines.py` continua resolent guies professionals;
- els mapes conservadors de regions i compatibilitat alimenten les eines;
- `validation.py` continua protegint el contracte;
- `adapter.py` continua sent l’única via d’aplicació;
- models, formularis, UI i persistència es reutilitzen íntegrament.

`generation.py` i el rànquing de `scoring.py` es conserven temporalment per compatibilitat,
proves històriques i reversibilitat. Ja no són cridats pel flux autoritatiu de
`generate_block_run`. Després de validar el nou enfocament amb casos reals es podrà retirar
el codi de selecció que no tingui cap altre consumidor.

## 10. Configuració

La clau continua únicament a `.env.dev.local`, ignorat per Git:

```env
OPENAI_API_KEY=...
```

La configuració versionada de la fase actual és:

```env
OPENAI_TRAINING_MODEL=gpt-5.6-luna
OPENAI_TRAINING_TIMEOUT_SECONDS=120
OPENAI_TRAINING_REASONING_EFFORT=medium
OPENAI_TRAINING_WEB_SEARCH=false
OPENAI_TRAINING_MAX_TOOL_ROUNDS=20
OPENAI_TRAINING_MAX_TOOL_CALLS=50
OPENAI_TRAINING_MAX_RESULTS_PER_SEARCH=20
OPENAI_TRAINING_MAX_UNIQUE_CANDIDATES=100
OPENAI_TRAINING_MAX_REPAIRS=2
OPENAI_TRAINING_MAX_EVIDENCE_ROUNDS=3
OPENAI_TRAINING_MAX_REVIEW_REPAIRS=1
OPENAI_TRAINING_MAX_OUTPUT_TOKENS=9000
OPENAI_TRAINING_MAX_LIVE_HISTORY_BYTES=100000
OPENAI_TRAINING_MAX_RATE_LIMIT_RETRIES=2
OPENAI_TRAINING_MAX_RATE_LIMIT_WAIT_SECONDS=60
OPENAI_TRAINING_REVIEW_ENABLED=true
OPENAI_TRAINING_REVIEW_MODEL=gpt-5.6-luna
OPENAI_TRAINING_REVIEW_REASONING_EFFORT=medium
OPENAI_TRAINING_REVIEW_MAX_OUTPUT_TOKENS=3500
```

Docker Compose carrega `.env.dev` i, després, `.env.dev.local`. `docker compose up` o
`docker compose up -d` inicia també el worker; no cal especificar cap fitxer d’entorn.
Quan canvia qualsevol valor d’entorn cal recrear `web` i `worker` amb
`docker compose up -d web worker`; un simple restart no rellegeix els fitxers.

## 11. Fitxers principals

- orquestrador agentiu: `iatrain/engine/agent.py`;
- eines: `iatrain/engine/agent_tools.py`;
- context: `iatrain/engine/context.py`;
- preflight `stop`: `iatrain/engine/eligibility.py`;
- contractes: `iatrain/engine/contracts.py`;
- guies: `iatrain/engine/guidelines.py`;
- validació: `iatrain/engine/validation.py`;
- serialització: `iatrain/engine/serialization.py`;
- aplicació: `iatrain/engine/adapter.py`;
- serveis de run: `iatrain/engine/services.py`;
- tasca en segon pla: `iatrain/tasks.py`;
- configuració del worker: `iatramp/celery.py` i `docker-compose.yml`;
- auditoria persistent: `iatrain/training/models/generation.py`;
- migracions: `iatrain/migrations/0013_agentic_block_generation.py` i
  `iatrain/migrations/0014_blockgenerationrun_progress_payload.py` per a la run, i
  `iatrain/migrations/0015_athletecondition_applicability_scope.py` per a l’abast de les
  condicions; `0016_trainingsessionitem_setup_seconds.py` fa visible la preparació i
  `0017_blockparticipantassignment_condition_decisions.py` conserva les decisions;
  `0018_sessionitemathleteadjustment_station_remainder_action_and_more.py` afegeix el
  temps restant individual i l'estat `review_required`;
- previsualització: `iatrain/views/sessions.py` i
  `iatrain/templates/iatrain/sessions/detail.html`;
- endpoint i client de progrés: `iatrain/views/engine/generation.py` i
  `iatrain/static/iatrain/session_generation.js`;
- proves agentives: `iatrain/tests/test_agent_block_generation.py`.

## 12. Verificació actual

La infraestructura té proves per comprovar:

- cerca limitada al catàleg privat;
- prohibició de consultar IDs no retornats;
- continuació del bucle amb function calls;
- emissió de fites de progrés durant el bucle agentiu;
- càlcul temporal abans de la proposta final;
- cerca obligatòria d’alternatives abans d’una omissió;
- bloqueig d’una proposta que deixa una participant sense cap exercici;
- decisió visible davant d’una condició amb abast desconegut;
- permís explícit abans d’usar revisions en esborrany;
- auditoria equivalent per als esquemes del model i del servidor;
- contracte `3.2` i validació del servidor;
- correspondència bloquejant entre participació personalitzada i ajustaments;
- resposta estructurada per a cada condició `avoid` o `modify`;
- cobertura obligatòria de detalls, compatibilitat i guies per als exercicis finals;
- coherència exacta entre dosificació final i càlcul temporal visible;
- revisor independent, devolució al planificador i segona aprovació;
- conservació d'errors locals com a proposta `review_required`, amb confirmació humana;
- bloqueig separat de riscos crítics i pressupostos independents de reparació;
- context compacte de reparació i equivalència regional de substitucions;
- coherència entre dosi individual i temps restant d'una estació;
- edició manual posterior de les adaptacions individuals;
- persistència de runs fallides;
- preflight i exclusió d’una participant amb `stop`;
- creació asíncrona, endpoint d’estat i pantalla de seguiment;
- compatibilitat amb l’adaptador i les personalitzacions existents.

Aquestes proves comproven la mecànica. Encara no són una comparació de qualitat entre models.

### Diagnòstic de la run 7 i correccions

La run 7 va revelar tres problemes diferents: condicions antigues sense regió interpretades
com a globals, participants que quedaven en `skip` a tots els ítems i una auditoria que
esperava l’esquema intern del servidor en comptes de l’esquema real del model. També va
mostrar una exploració cara: 11 rondes, 16 eines i massa context repetit.

El motor `3.1` corregeix aquestes causes: abast explícit i decisió visible, cerca específica
d’alternatives, prohibició del `skip` total, serialització canònica compartida i respostes
d’eina més compactes. La run 7 queda com a evidència històrica i no es modifica; cal crear
una run nova per observar el comportament corregit.

### Diagnòstic de les runs 8–11: bucle d’esborranys

La run 8 va detectar 11 candidats en esborrany, però el model va retornar una aclariment de
text lliure. Les respostes posteriors `si`, `si` i `usa esborranys com si fossin validats`
van crear les runs 9–11 com a reformulacions; cap d’elles va desar
`catalog_drafts=allow_draft_exercises`. Per això totes tornaven a executar cerques amb el
filtre efectiu `validated_only=true` i mostraven zero resultats.

El motor `3.2` converteix aquest cas en una decisió estructurada abans de la crida LLM i
vincula el permís directament a l’executor de les eines. Això elimina el bucle i també evita
el cost de repetir una exploració que el servidor ja sap que no pot retornar validats.

### Diagnòstic de la run 12: personalització només narrativa

La run 12 va recuperar 21 candidats, en va examinar 8 i va seleccionar 4, però declarava
quatre participants com a `personalized` amb tots els `athlete_adjustments` buits. Les
indicacions individuals estaven amagades a `execution_notes` compartides. També va escollir
un bird dog intermedi per a una participant novell, no va consultar-ne la guia, va declarar
«full body» amb cobertura superior insuficient i mostrava 500 segons d’instruccions mentre
el càlcul n’incloïa 660 per preparacions no visibles. L’auditoria estructural `3.0` ho va
acceptar perquè aquestes relacions no eren invariants.

El motor `3.3` i el contracte `3.1` bloquegen aquestes discrepàncies, obliguen a reparar-les
i afegeixen una revisió semàntica independent abans de mostrar la proposta. La run 12 es
manté com a evidència històrica i no es modifica.

### Diagnòstic de la run 13: reparació local que descartava el bloc

La run 13 va superar la validació estructural, però el revisor va detectar una substitució
d'espatlla per maluc funcionalment incoherent i una dosi individual de 20 segons dins una
estació comuna de 30 segons sense explicar els 10 segons restants. Els dos intents globals
de reparació ja s'havien consumit i la run completa va acabar en `failed`, tot i que els
errors afectaven una submostra petita.

El motor `3.4`, el contracte `3.2` i les eines `1.4` ho corregeixen en quatre nivells:

- les alternatives conserven com a mínim la regió corporal i prioritzen el mateix patró;
- el contracte expressa el temps de treball individual i l'ús de la resta de l'estació;
- les reparacions estructurals i les del revisor tenen pressupostos independents;
- si després de reparar només queden errors locals, es conserva la proposta com a
  `review_required` en comptes de perdre tot el bloc.

La run 13 continua sent evidència històrica i no es modifica retroactivament.

### Diagnòstic de la run 14: evidència descoberta per etapes

La run 14 va consultar correctament la guia de l'exercici 53 per a la participant 11. En
una reparació posterior va reutilitzar el mateix exercici per a les participants 9, 10,
13 i 14. El validador va informar primer de les compatibilitats pendents; el model les va
consultar, però només a la validació següent va descobrir que també faltaven les quatre
guies de dosificació. En aquell moment ja havia consumit les dues reparacions de proposta.

El motor `3.5` tracta els buits de detalls, compatibilitat i guia com una fase pròpia:

- agrega totes les parelles pendents en un sol diagnòstic estructurat;
- valida abans la coherència de la proposta per no consultar evidència d'un pla invàlid;
- genera una llista exacta de function calls que es poden retornar en una mateixa ronda;
- disposa de `OPENAI_TRAINING_MAX_EVIDENCE_ROUNDS`, independent de les reparacions del
  servidor i del revisor;
- conserva a `validation_payload.evidence_attempts` què faltava i com es va completar.

Per tant, completar una guia o una compatibilitat que falta ja no gasta una reparació de
la proposta. Continua sent una exigència bloquejant de seguretat si, després de les rondes
d'evidència, el model no l'obté.

### Diagnòstic de la run 15: regles de risc massa àmplies i context incomplet del revisor

La run 15 va mostrar que el servidor equiparava `avoid` amb l'obligació de `replace` o
`skip`. Això va rebutjar modificacions que podien eliminar el risc i va empènyer el model a
substitucions de la mateixa demanda, com una frontissa per una altra frontissa. La cerca
d'alternatives també descartava qualsevol candidat de la mateixa regió corporal, encara que
el risc real fos més específic —hiperextensió, impacte, palanca llarga o càrrega alta.

El revisor, a més, rebia la proposta i els perfils però no la petició original. Per això va
interpretar erròniament com a individual una premissa de dos mesos d'inactivitat que
l'entrenador havia declarat per a tot el grup.

El motor `3.6` i les eines `1.5` ho corregeixen així:

- `avoid` admet `modify`, `replace` o `skip`; es valida la correspondència estructural i el
  revisor avalua si l'explicació resol el risc concret;
- compartir regió o patró ja no converteix automàticament una alternativa en incompatible;
- `check_participant_compatibility` retorna `requires_risk_resolution` en comptes de forçar
  una exclusió semàntica;
- la manca de dades no bloqueja el preflight ni justifica per si sola un aclariment;
- el revisor rep la petició original, refinaments, decisions humanes, autoritat del servidor,
  objectius de sessió i advertiments de context.

La frontera dura continua sent una indicació `stop` explícita o l'absència de qualsevol
sortida executable segura, no la simple absència d'una dada.

### Smoke test real amb Luna

La primera prova real completa del contracte `3.0` va crear una proposta no aplicada amb:

- model `gpt-5.6-luna`;
- 7 cerques i 32 candidats únics recuperats;
- 4 exercicis seleccionats;
- durada calculada de 550 segons dins un pressupost de 10 minuts;
- una proposta inicial rebutjada perquè repetia el principal com a alternativa;
- una reparació posterior validada pel servidor;
- cap `TrainingBlock` nou fins a confirmació humana.

La run va necessitar 15 respostes i 19 crides d’eina. La major part dels tokens d’entrada
van ser cachejats, però la latència i el volum de context encara són elevats. Després del
smoke test, `audit_block_draft` ha quedat limitat a dues crides per run i les eines
independents poden agrupar-se en una mateixa ronda. Cal tornar a mesurar latència i cost en els
benchmarks posteriors; això és independent de la futura comparació de qualitat entre models.

## 13. Línia futura

La comparació reproduïble entre Luna, Terra i Sol ja disposa de l’ordre
`benchmark_training_models`, amb casos fixos, context congelat, jutge cec, mètriques de
procés, cost separat i exportació per a revisió humana. El protocol complet és a
`docs/benchmark_models_iatrain.md`.

L’ordre recomanat a partir d’aquest punt és:

1. enriquir progressivament regions i abasts dels perfils sense convertir-ne l'absència en
   un bloqueig;
2. executar de nou el cas de la run 12 amb Luna i revisar ajustaments, cobertura i revisor;
3. construir un conjunt d’avaluació estable amb peticions, grups i criteris esperats;
4. comparar Luna, Terra i Sol mantenint exactament el mateix context i eines;
5. mesurar seguretat, adequació, personalització, temps, estabilitat, latència i cost,
   separant planificador, reparacions i revisor;
6. millorar la recuperació semàntica del catàleg sense canviar el contracte de l’eina;
7. afegir cerca web real com una eina separada, amb fonts capturades per l’API;
8. governar com una font externa pot influir en guies i propostes;
9. incorporar càrrega de microcicle i resultats executats com a nou context;
10. retirar definitivament el selector determinista antic quan les avaluacions confirmin el
   nou motor;
11. dissenyar el motor tècnic amb el mateix patró agentiu i contractes especialitzats.

No s’ha d’afegir cerca web, embeddings o generació completa de sessions només perquè la
infraestructura ho permeti. Cada ampliació ha de conservar traçabilitat, revisió humana i
avaluacions representatives.
