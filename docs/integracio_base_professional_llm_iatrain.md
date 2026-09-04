# Integració de la base professional amb l'LLM d'IA Train

> **Estat canònic:** motor físic `3.10`, eines `1.9`, contracte `3.5`, pla previ `1.1`.

## Objectiu

El model conserva l'autoritat de planificació, però la base professional és l'autoritat
dels fets anatòmics i biomecànics. La integració no impedeix proposar alternatives noves:
separa afirmacions fonamentades de les hipòtesis que encara no tenen cobertura.

## Flux

```text
petició de l'entrenador
  → submit_block_planning_brief
  → objectius, cobertura i criteris d'èxit validats
  → search_professional_concepts
  → codis canònics validats
  → search_exercises per acció/múscul/contracció
  → get_exercise_details / get_exercise_knowledge_support
  → claims professionals exactes
  → knowledge_support de cada ítem
  → professional_justification de cada adaptació individual
  → validador del servidor
  → revisor independent
  → previsualització i confirmació humana
```

`get_exercise_details` retorna només metadades i instruccions compactes.
`get_exercise_knowledge_support` consulta després el suport professional una única vegada
per finalista. Això manté la consulta obligatòria sense duplicar claims, fonts i limitacions.

## Contracte epistemològic

- `grounded`: tots els claims provenen de les eines i cobreixen cada exercici referenciat.
- `hypothesis`: la base és insuficient; el resum declara el buit i la proposta no es
  presenta com un fet professional.
- `not_applicable`: la justificació no formula cap afirmació anatòmica, tot i que el paquet
  professional s'ha consultat igualment.

Cada claim conserva exercici, fase, acció, múscul, funció, contracció prevista, estat de
verificació, codis d'evidència i limitacions. El servidor compara aquests camps amb la
sortida exacta de les eines: citar un `claim_id` real però alterar-ne el múscul, la
contracció, les fonts o les limitacions també és invàlid.
En el contracte `3.5`, el servidor hidrata de nou els camps canònics dels `claim_id`
recuperats i construeix el resum factual a partir d'ells abans de validar. Els identificadors
desconeguts continuen sent rebutjats.

## Justificació de variants individuals

Cada `athlete_adjustment` dels contractes `3.4` i `3.5` incorpora una cadena explícita:

```text
condició o factor del perfil
  → claims professionals de l'exercici
  → fases afectades
  → rellevància biomecànica inferida
  → objectiu de la modificació
  → criteris de monitoratge
  → criteris d'aturada o canvi
```

`grounded` significa que els fets sobre l'exercici i les fases provenen de la base; no
significa que la font anatòmica demostri una contraindicació clínica. Aquest pont queda
identificat com una inferència de planificació. `hypothesis` permet continuar quan falta
un camí suficient, però obliga a mostrar el buit, una confiança explícita i un avís.

Les condicions amb impacte `monitor` ja no poden desaparèixer durant una reparació. Han de
tenir una `condition_decision`: `monitor` si es conserva la dosi amb criteris operatius,
o `modify`, `replace` o `skip` quan cal canviar l'exposició.

## Política de recuperació

- Només conceptes i funcions professionals `validated`.
- Connexions privades `pending` excloses dels claims fonamentats.
- Exercicis en esborrany subjectes a l'autorització específica ja existent.
- Cap inferència funcional equival a activació muscular observada.
- Una absència és un buit de coneixement, no una prohibició.
- La contracció és pròpia d'una fase i una funció muscular prevista, no una etiqueta
  absoluta de tot l'exercici.

## Persistència i traçabilitat

`BlockGenerationRun.planning_payload` conserva què es volia aconseguir abans de cercar.
`BlockGenerationRun.agent_trace` conserva les consultes, conceptes, exercicis i claims.
`source_references` conserva les fonts professionals utilitzades. Cada
`TrainingSessionItem` desa el seu `knowledge_support`; una edició manual posterior el
buida per evitar mantenir evidència potencialment obsoleta. Cada
`SessionItemAthleteAdjustment` desa `professional_justification`; una edició manual la
buida pel mateix motiu.

## Convenció temporal

`planned_duration_seconds` és el total d'una passada per l'ítem:

```text
setup + treball + descansos entre sèries + rest_after
```

Els components ja estan inclosos i no es tornen a sumar. El revisor rep aquesta convenció,
l'equació i el resultat del validador temporal determinista; només pot declarar un error
numèric si la validació del servidor falla.

## Criteris de verificació

1. Una proposta `3.5` sense `knowledge_support` és invàlida.
2. Tots els exercicis finals han de tenir el paquet professional consultat.
3. Un claim inventat o alterat és rebutjat.
4. Els buits es poden representar com a hipòtesi.
5. La recuperació continua limitada al catàleg privat de l'entrenador.
6. Peticions com «exercicis concèntrics de cames» es resolen per conceptes validats i per
   fases amb `expected_contraction=concentric`, no per coincidència textual lliure.
7. Cada variant individual necessita una cadena professional estructurada i verificable.
8. Una condició `monitor` necessita decisió i criteris de seguiment i aturada.
9. La proposta ha de complir la cobertura, intensitat i restriccions del pla previ.

La planificació prèvia i el context per capes es documenten a
[`planificacio_context_agent_fisic.md`](planificacio_context_agent_fisic.md).
