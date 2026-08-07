# Extracció del domini `organizations`

## Estat i objectiu

La fase 1 es va implementar el 7 d'agost de 2026. L'objectiu és separar el domini transversal d'organitzacions de la identitat de `core` sense moure encara models, taules ni dades.

La decisió arquitectònica és:

```text
core                    organizations                 iatrain
identitat               clubs i membres              producte d'entrenament
Person              <-  domini compartit         <-  façana visual actual
```

Una organització no pertany funcionalment a IA Train: futurs mòduls, com el de jutges, també la podran consumir. IA Train és la façana visual actual, no la font de veritat del domini.

## Fase 1: frontera de domini sense migració de dades

### Implementat

S'ha registrat l'aplicació Django `organizations` i s'hi ha centralitzat l'API pública:

- `organizations.models`: façana temporal dels models que encara viuen físicament a `core.models`;
- `organizations.selectors`: consultes de vigència, organitzacions revisables i sol·licituds pendents;
- `organizations.policies`: rols sol·licitables, permisos efectius i autorització;
- `organizations.services`: creació d'organitzacions, membres, rols, sol·licituds i gestió d'accessos;
- `organizations.identity`: consolidació de membresies i sol·licituds quan Core fusiona dues persones;
- `organizations.forms`: formularis del domini d'organització.

Els consumidors de producció de Core i IA Train importen aquestes peces des de `organizations`. Els imports antics de formularis i serveis a través de `core` es mantenen com a compatibilitat temporal.

El helper `person_for_user` s'ha separat a `core.identity`, ja que resoldre la identitat autenticada continua sent responsabilitat de Core.

### Contracte d'importació des d'ara

El codi nou ha d'utilitzar:

```python
from organizations.models import Organization, Membership, MembershipRole
from organizations.policies import has_organization_permission
from organizations.selectors import current_membership_filter
from organizations.services import create_organization_for_user
```

No s'han d'afegir imports nous de models o serveis d'organització des de `core`. Les excepcions són les migracions històriques i els tests que comproven expressament la compatibilitat de la fase 1.

IA Train conserva els selectors i regles esportives. Per exemple, decidir en quins clubs una persona pot actuar com a entrenador pertany a IA Train; decidir si és membre o si pot administrar rols pertany a `organizations`.

### Què no ha canviat

- Els sis models encara tenen `app_label = "core"`.
- Les taules continuen tenint noms `core_*`.
- Les migracions existents de Core no s'han modificat.
- No s'ha creat cap migració nova.
- Les dades i claus foranes no s'han mogut.
- Les URLs i templates antics de Core continuen disponibles.
- La UI encara no s'ha unificat completament dins d'IA Train.

Aquestes limitacions són deliberades: permeten validar la nova frontera abans d'una migració sensible de l'estat de Django.

## Fase 2 pendent: propietat física dels models

La fase 2 ha de moure a `organizations`:

1. `Organization`;
2. `Membership`;
3. `MembershipRole`;
4. `MembershipPermission`;
5. `OrganizationMembershipRequest`;
6. `OrganizationMembershipRequestRole`.

`Person`, `PersonClaimInvitation` i `PersonMergeRecord` han de continuar a Core.

### Precondicions

Abans de començar:

1. Confirmar que no queden imports de producció des de `core`:

   ```text
   rg "from core\.(models|services|forms) import" core iatrain organizations
   ```

2. Executar la suite de Core, Organizations i IA Train en verd.
3. Fer una còpia de seguretat de la base de dades utilitzada per validar la migració.
4. Inventariar `ContentType`, permisos Django, grups i qualsevol referència genèrica als sis models.
5. No modificar ni reescriure les migracions històriques de Core.

### Estratègia de migració recomanada

No s'ha d'utilitzar una seqüència automàtica que interpreti el canvi com `DeleteModel` més `CreateModel`: podria intentar eliminar i recrear taules amb dades.

Cal escriure migracions manuals i revisar-ne el SQL:

1. Definir els models reals a `organizations.models` amb les mateixes columnes, restriccions i relacions.
2. Preservar explícitament els noms de taula actuals amb `Meta.db_table` (`core_organization`, `core_membership`, etc.).
3. Crear l'estat dels models a l'aplicació nova amb `SeparateDatabaseAndState`, sense operacions de base de dades que creïn taules ja existents.
4. Actualitzar l'estat de les claus foranes d'IA Train perquè apuntin a `organizations.Organization`; si columna i taula són les mateixes, el canvi hauria de ser només d'estat.
5. Eliminar els models de l'estat de Core, també sense esborrar les taules físiques.
6. Migrar de manera controlada els `django_content_type` i permisos del `app_label` `core` a `organizations`. Cal resoldre possibles col·lisions abans d'actualitzar-los.
7. Mantenir inicialment els noms de constraints i índexs `core_*`; canviar-los no aporta valor funcional i augmenta el risc.
8. Substituir `organizations.models` —que a la fase 1 és una façana— pels models reals.
9. Adaptar l'admin i la consolidació d'identitats perquè consumeixin hooks públics del domini, sense introduir `core -> organizations` com a dependència estructural.
10. Eliminar les exportacions de compatibilitat de `core.forms` i `core.services` quan no quedin consumidors.

### Validació obligatòria de la fase 2

Abans de desplegar:

- `python manage.py check` sense errors;
- `python manage.py makemigrations --check --dry-run` sense canvis inesperats;
- revisar `python manage.py sqlmigrate ...` i confirmar que no hi ha `DROP TABLE`, recreacions ni pèrdua de columnes;
- executar les migracions sobre una còpia de dades realista;
- comparar recomptes i claus primàries dels sis models abans i després;
- comprovar rols, permisos, sol·licituds i propietaris;
- provar migració endavant i rollback en un entorn descartable;
- executar `core.tests`, `organizations.tests` i `iatrain.tests`.

La fase 2 no s'ha de considerar completa només perquè `migrate` finalitzi: les dades, `ContentType`, permisos i relacions han de conservar la mateixa semàntica.

## Passos funcionals futurs

### Unificació de la UI a IA Train

Després de consolidar l'API —pot fer-se abans o després de la fase 2 física— cal eliminar la doble façana visual:

1. Fer de `/iatrain/organitzacions/` l'entrada principal.
2. Integrar-hi creació, edició, membres, rols, permisos i sol·licituds.
3. Organitzar el detall amb seccions com `Resum`, `Grups`, `Gimnastes`, `Gimnasos`, `Membres`, `Sol·licituds` i `Configuració`.
4. Retirar l'enllaç d'IA Train cap a «Administració» de Core.
5. Convertir les URLs antigues `/organitzacions/...` en redireccions temporals.
6. Actualitzar Home, perfil, navegació i notificacions perquè apuntin a la façana d'IA Train.
7. Eliminar els templates d'organitzacions de Core quan no quedin enllaços ni proves dependents.

La UI pot viure a IA Train encara que models i regles visquin a `organizations`. Les vistes han de cridar serveis del domini i no mutar directament rols o permisos amb l'ORM.

### Perfils futurs

El selector de perfil s'ha de representar com un valor extensible (`coach`, `athlete` i, en el futur, `judge`), no com un booleà. El perfil actiu només canvia la façana renderitzada; els permisos continuen derivant de membresies i rols.

Un futur mòdul de jutges ha de consumir la mateixa `Organization` i pot oferir una façana pròpia sense duplicar dades ni regles.

### Millores de domini pendents

- baixa, suspensió i reactivació de membres;
- auditoria de canvis de rols i permisos;
- verificació de clubs i federacions;
- detecció i fusió d'organitzacions duplicades;
- invitacions iniciades per una organització;
- notificacions internes i per correu;
- controls específics per a menors i tutors legals.

## Criteri de finalització global

L'extracció completa haurà acabat quan:

- Core només sigui propietari de la identitat;
- `organizations` sigui propietari real dels models, dades, regles i serveis;
- IA Train sigui la façana visual principal actual;
- no hi hagi pantalles duplicades a Core;
- altres mòduls puguin consumir `organizations` sense dependre d'IA Train.
