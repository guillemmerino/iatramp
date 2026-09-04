# Benchmark de models per al motor físic d’IA Train

Estat canònic del benchmark `1.2`, compatible amb el motor agentiu `3.10`, el
contracte de proposta `3.5` i el pla previ `1.1`.

## Objectiu

El benchmark executa el mateix context congelat, els mateixos vuit casos i el mateix
esforç de raonament amb cada model. L’ordre dels models es barreja de manera reproduïble
per reduir l’efecte de l’ordre i cada resultat conserva la run completa a la base de dades.

No s’ha d’escollir un model amb una única mitjana. La decisió combina:

1. porta dura de seguretat i validesa;
2. qualitat cega de la resposta;
3. fiabilitat entre repeticions;
4. cost real de producció;
5. latència i eficiència del procés.

## Preparació dels preus

La Responses API retorna tokens, però el benchmark no inventa tarifes. Copia
`docs/benchmarks/model_pricing.example.json` a `benchmark_pricing.local.json` i completa
les tarifes vigents per milió de tokens. El fitxer local està ignorat per Git.

El cost de producció suma planificador i revisor. El cost del jutge es registra a part,
perquè només existeix durant l’avaluació i no forma part del cost futur d’un bloc real.

## Preflight sense cost

```powershell
docker compose exec -T web python manage.py benchmark_training_models `
  --coach-username NOM_USUARI `
  --session-revision-id ID_VERSIO `
  --models gpt-5.6-luna gpt-5.6-terra gpt-5.6-sol `
  --repetitions 3 `
  --reuse-decisions-from-run ID_RUN_AMB_DECISIONS `
  --dry-run
```

El preflight comprova permisos, temps lliure, participants, decisions prèvies i casos.
No fa cap crida LLM. Cal usar una versió de sessió estable i amb almenys 15 minuts lliures.

## Smoke test mínim

Abans del benchmark complet, executa un únic cas i una repetició:

```powershell
docker compose exec -T web python manage.py benchmark_training_models `
  --coach-username NOM_USUARI `
  --session-revision-id ID_VERSIO `
  --models gpt-5.6-luna gpt-5.6-terra gpt-5.6-sol `
  --case base `
  --repetitions 1 `
  --review-model gpt-5.6-luna `
  --judge-model gpt-5.6-sol `
  --reuse-decisions-from-run ID_RUN_AMB_DECISIONS `
  --pricing-file benchmark_pricing.local.json `
  --run-name smoke-models
```

## Benchmark complet recomanat

```powershell
docker compose exec -T web python manage.py benchmark_training_models `
  --coach-username NOM_USUARI `
  --session-revision-id ID_VERSIO `
  --models gpt-5.6-luna gpt-5.6-terra gpt-5.6-sol `
  --repetitions 3 `
  --reasoning-effort medium `
  --review-model gpt-5.6-luna `
  --review-reasoning-effort medium `
  --judge-model gpt-5.6-sol `
  --judge-reasoning-effort high `
  --reuse-decisions-from-run ID_RUN_AMB_DECISIONS `
  --pricing-file benchmark_pricing.local.json `
  --run-name comparacio-models-v1
```

El revisor es manté fix per aïllar la qualitat del planificador. El jutge rep respostes
sense el nom del model. Com que un jutge LLM pot tenir biaixos, s’ha de validar manualment
una mostra cega, especialment les diferències petites o sorprenents.

Si el procés s’interromp, es reprèn sense repetir combinacions ja acabades:

```powershell
docker compose exec -T web python manage.py benchmark_training_models `
  --coach-username NOM_USUARI `
  --session-revision-id ID_VERSIO `
  --models gpt-5.6-luna gpt-5.6-terra gpt-5.6-sol `
  --repetitions 3 `
  --review-model gpt-5.6-luna `
  --judge-model gpt-5.6-sol `
  --reuse-decisions-from-run ID_RUN_AMB_DECISIONS `
  --pricing-file benchmark_pricing.local.json `
  --resume var/benchmarks/comparacio-models-v1
```

En reprendre, cal conservar també les mateixes opcions de revisor, jutge, raonament i
decisions de l’ordre original.

## Rúbrica de qualitat

La nota cega va de 0 a 100:

| Dimensió | Pes | Què avalua |
|---|---:|---|
| Seguretat | 30% | Restriccions, condicions, riscos i aclariments imprescindibles |
| Personalització | 25% | Ajustaments reals, cobertura individual i alternatives útils |
| Selecció i coherència | 20% | Relació entre premisses, objectius, exercicis i ordre |
| Dosi i temps | 15% | Volum, intensitat, descansos, progressió i pressupost temporal |
| Claredat i usabilitat | 10% | Capacitat de l’entrenador d’executar i supervisar la proposta |

Una incompatibilitat material, una participant ignorada o una sortida inadequada limita
la nota a 39. La porta dura exigeix, a més, estat esperat, aprovació del revisor i absència
d’error crític. Una pregunta necessària pot superar la porta en el cas ambigu; preguntar
per preferències evitables no.

`review_required` compta com una proposta generada i es continua puntuant, però no supera
la porta dura: necessita intervenció manual. El resum el separa de `proposed`, de manera
que es pot comparar quins models produeixen bons esborranys però traslladen més feina a
l'entrenador.

## Mètriques de procés

Cada run registra:

- estat final, latència i repetició;
- rondes, crides d’eina, cerques i alternatives;
- coincidències de catàleg, candidats únics retornats i candidats inspeccionats;
- recàlculs temporals i auditories;
- reparacions del servidor i devolucions del revisor;
- rondes dedicades a completar evidència de detalls, compatibilitat i dosificació;
- propostes `review_required` i pressupostos de reparació consumits;
- tokens totals i separats entre planificador i revisor;
- cost del planificador, revisor, producció i jutge;
- proposta, decisions, traça, validació i identificador de la run de base de dades.

## Fitxers resultants

Cada execució crea `var/benchmarks/NOM/`:

- `manifest.json`: configuració, casos, decisions i empremta del context;
- `runs.jsonl`: registre complet de cada intent;
- `summary.json`: resum per model i per model/cas;
- `summary.csv`: comparació compacta per model;
- `blind_review.jsonl`: respostes sense identitat del model;
- `blind_context.json`: context necessari per puntuar sense revelar identitats;
- `human_scores.csv`: plantilla de puntuació manual;
- `blind_key.json`: clau que només s’ha d’obrir després de la revisió humana.

El manifest i els fitxers cecs poden contenir context sensible de salut. Es desen sota
`var/benchmarks/`, que no es versiona, i no s’han de compartir sense anonimitzar-los.

## Lectura qualitat-preu

Les mètriques principals són:

- `hard_gate_rate`: fiabilitat de resultats acceptables;
- `quality_effective_mean`: qualitat mitjana comptant fallades com a zero;
- `production_cost_mean`: cost mitjà real del bloc, sense el jutge;
- `cost_per_hard_pass`: cost total dividit pels resultats que superen la porta;
- `value_points_per_cent`: punts de qualitat efectiva obtinguts per cada cèntim;
- `quality_stdev`: estabilitat entre repeticions;
- `latency_seconds_mean`: temps d’espera mitjà.

Primer s’ha de descartar qualsevol model amb seguretat o fiabilitat insuficient. Entre els
models restants, convé buscar la frontera de Pareto: cap altre model no hauria de ser alhora
més bo, més barat i més ràpid. Diferències petites s’han de confirmar amb més repeticions i
revisió humana cega abans de canviar el model de producció.
