# Planificació prèvia i context del motor físic

> **Estat canònic:** motor `3.10`, eines `1.9`, proposta `3.5` i pla previ `1.1`.

## Finalitat

El motor separa dues decisions que abans es produïen alhora:

1. **pla previ:** què ha d'aconseguir el bloc;
2. **proposta:** quins exercicis, dosis i variants ho implementen.

El pla previ limita els resultats exigibles, però no conté identificadors d'exercici. Per
això no converteix el catàleg en un camí rígid ni redueix la llibertat de comparar
solucions.

## Estat del flux

```text
preflight de participants
  → context inicial compacte
  → submit_block_planning_brief
  → validació determinista del pla
  → conceptes professionals quan la intenció ho requereix
  → cerca i comparació d'exercicis
  → detalls individuals sota demanda
  → evidència professional, compatibilitat, dosi i temps
  → proposta 3.5
  → alineació proposta ↔ pla
  → revisor independent
  → revisió i confirmació humana
```

Quan `OPENAI_TRAINING_PLANNING_BRIEF_ENABLED=True`, qualsevol eina diferent de
`submit_block_planning_brief` queda bloquejada fins que el pla sigui acceptat. La bandera
existeix per poder revertir el desplegament; està activada per defecte.

## Contracte `BlockPlanningBrief 1.1`

El pla desa:

- objectiu observable i criteris d'èxit;
- mode i dominis de cobertura;
- patrons obligatoris explícits, patrons preferits, intensitat i estratègia de càrrega;
- pressupost exacte en segons;
- estratègia compartida i prioritats individuals;
- restriccions globals i preferències amb font explícita;
- preguntes per a la base professional;
- estratègia de cerca i incerteses.

Una prioritat individual només pot referenciar participants actius i condicions actives.
La lateralitat declarada ha de coincidir amb la condició. Les peticions explícites de
`full body`, `cos sencer`, `tot el cos` o `cos complet` exigeixen tren inferior, tren
superior i tronc.

Un full-body genèric no pot convertir squat, hinge, push, pull, locomoció o turmell en
set obligacions simultànies. Només els patrons literalment demanats per l'entrenador són
obligatoris; la resta són preferències. Les restriccions dures també han de venir de la
petició o d'una proposta anterior. Precaucions inferides com baix impacte o pes corporal
queden com a preferències, i `validated_only` és incompatible amb una autorització
explícita d'esborranys.

## Alineació final

Abans del revisor, el servidor comprova que:

- intensitat i restriccions dures del pla es conserven;
- els patrons i dominis obligatoris apareixen en exercicis reals seleccionats;
- una dosi unilateral o alternant diu si les repeticions són totals o per costat;
- una condició esquerra o dreta manté el costat als criteris individuals;
- la proposta continua superant els invariants de catàleg, evidència i temps.

Una discrepància entra al pressupost de reparació estructural. No es pot ocultar amb un
resum narratiu de cobertura.

## Context per capes

La fotografia completa continua al servidor dins de `BlockEngineContext`. El primer torn
rep només targetes compactes amb nivell, condicions, insights confirmats, tres
observacions recents, tres respostes recents, recompte i data de l'últim entrenament.

`get_participant_context` amplia sota demanda una participant activa i només les seccions
sol·licitades: perfil esportiu, condicions, observacions, respostes, mesures o insights.
`get_group_training_summary` permet recuperar de nou el resum factual del grup sense
reenviar els historials individuals.
Les condicions i avisos de seguretat mai no s'oculten del context inicial.

Quan el model cita un `claim_id`, el servidor substitueix els camps copiats per la versió
canònica recuperada i genera el resum factual a partir d'aquests claims. Això evita que una
reparació alteri accidentalment músculs, fases, fonts, limitacions o que el resum afirmi
més accions de les realment citades.

`get_exercise_details` ja no inclou claims. `get_exercise_knowledge_support` els retorna
una sola vegada per finalista; una repetició respon només que el servidor ja els conserva.
Les cerques ometen participants completament compatibles, les guies idèntiques s'agrupen
i la compatibilitat retorna sobretot excepcions individuals.

Quan l'historial viu supera `OPENAI_TRAINING_MAX_LIVE_HISTORY_BYTES`, el motor substitueix
la transcripció acumulada per un ledger compacte de candidats, claims, guies,
compatibilitats i temps. Davant un `429`, espera el `Retry-After`, compacta aquest ledger i
reintenta fins al límit configurat; una espera superior al màxim deixa la run fallida sense
fer bucles indefinits.

## Persistència i observabilitat

`BlockGenerationRun.planning_payload` conserva el pla acceptat. La traça registra la seva
versió, mode de cobertura, mida de cada resultat d'eina i consultes de context individual.
`validation_payload.context_metrics` desa la mida del payload inicial, bytes retornats per
les eines i nombre d'ampliacions individuals. El benchmark inclou el pla juntament amb la
proposta i la validació.

La UI mostra el pla previ, els seus criteris d'èxit, cobertura i estratègia. No mostra ni
demana una cadena de pensament interna.

## Compatibilitat

Els lectors continuen acceptant propostes fins a `3.4`. Amb la bandera desactivada, el
motor pot produir temporalment `3.4`; les runs ordinàries noves produeixen `3.5` i queden
vinculades al pla `1.1`.

## Verificació mínima

1. La cerca queda rebutjada sense pla quan el control està actiu.
2. Un `full body` incomplet queda rebutjat abans del revisor.
3. La proposta final ha de coincidir amb intensitat, patrons explícits i dominis del pla.
4. Les dosis unilaterals expliciten l'abast de les repeticions.
5. El detall individual només es recupera sota demanda.
6. El pla, la traça i les mètriques queden persistits i entren al benchmark.
7. Els claims no es retornen dues vegades i un `429` temporal es reintenta com a màxim
   dues vegades.
