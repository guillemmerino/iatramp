# Extracció del domini `organizations`

## Estat

Les fases 1 i 2 es van implementar el 7 d'agost de 2026. `organizations` és ara el propietari real del domini transversal d'organitzacions; `core` conserva exclusivament la identitat.

```text
core                    organizations                 iatrain
identitat               clubs i membres              producte d'entrenament
Person              <-  domini compartit         <-  façana visual actual
```

Una organització no pertany funcionalment a IA Train: futurs mòduls, com el de jutges, també la podran consumir. IA Train continua sent la façana visual actual, no la font de veritat del domini.

## Fase 1: frontera d'aplicació

La primera fase va registrar l'aplicació Django `organizations` i hi va centralitzar:

- `organizations.selectors`: consultes de vigència, organitzacions revisables i sol·licituds;
- `organizations.policies`: rols sol·licitables, permisos efectius i autorització;
- `organizations.services`: organitzacions, membres, rols, sol·licituds i accessos;
- `organizations.identity`: consolidació de dades quan Core fusiona persones;
- `organizations.forms`: formularis del domini.

Durant aquesta fase, `organizations.models` era una façana sobre els models físics de Core. Els consumidors de producció ja es van adaptar a la nova API abans de canviar la propietat Django.

El helper `person_for_user` viu a `core.identity`, perquè resoldre la identitat autenticada continua sent responsabilitat de Core.

## Fase 2: propietat física dels models

La segona fase ha traslladat a `organizations.models`:

1. `Organization`;
2. `Membership`;
3. `MembershipRole`;
4. `MembershipPermission`;
5. `OrganizationMembershipRequest`;
6. `OrganizationMembershipRequestRole`.

`Person`, `PersonClaimInvitation` i `PersonMergeRecord` continuen a Core.

### Decisió de persistència

Els models tenen `app_label = "organizations"`, però conserven els noms físics històrics:

```text
core_organization
core_membership
core_membershiprole
core_membershippermission
core_organizationmembershiprequest
core_organizationmembershiprequestrole
```

També es conserven claus primàries, columnes, constraints i índexs `core_*`. Canviar aquests noms no aporta valor funcional i hauria incrementat el risc.

### Migracions aplicades

La migració no utilitza un `DeleteModel`/`CreateModel` físic. La propietat s'ha canviat amb operacions manuals:

- `organizations.0001_adopt_core_organization_models`: crea els sis models només a l'estat Django;
- `iatrain.0006_retarget_organization_relations`: redirigeix només l'estat de les relacions cap a `organizations.Organization`;
- `core.0006_release_organization_relations`: allibera relacions antigues només de l'estat de Core;
- `core.0007_release_organization_models`: elimina els models antics només de l'estat de Core;
- `organizations.0002_move_content_types`: mou els `ContentType` de `core` a `organizations` conservant-ne els IDs.

Les quatre migracions estructurals utilitzen `SeparateDatabaseAndState` amb `database_operations=[]`. No creen, eliminen ni alteren taules.

La migració de `ContentType` falla explícitament si detecta una col·lisió. Els permisos Django continuen vinculats als mateixos IDs de `ContentType`.

### Compatibilitat temporal

Els imports antics de serveis i formularis continuen disponibles a `core.services` i `core.forms`. Són reexportacions; la implementació resideix a `organizations`.

Es poden eliminar quan no quedin consumidors externs coneguts. No s'han de tornar a afegir models d'organització a `core.models`.

### Contracte d'importació

El codi nou ha d'utilitzar:

```python
from organizations.models import Organization, Membership, MembershipRole
from organizations.policies import has_organization_permission
from organizations.selectors import current_membership_filter
from organizations.services import create_organization_for_user
```

Les migracions històriques de Core i IA Train no s'han de reescriure: són necessàries perquè una base nova construeixi primer les taules històriques i després en transfereixi la propietat d'estat.

IA Train conserva els selectors esportius. Decidir en quins clubs una persona pot actuar com a entrenador pertany a IA Train; decidir si és membre o si pot administrar rols pertany a `organizations`.

## Validació i regressions futures

Qualsevol canvi posterior sobre aquests models ha de comprovar:

- `python manage.py check`;
- `python manage.py makemigrations --check --dry-run`;
- migració des d'una base situada a `core.0005` i `iatrain.0005`;
- instal·lació completa des de zero;
- conservació d'IDs, recomptes, rols, permisos i relacions;
- `ContentType.app_label == "organizations"` per als sis models;
- absència de `Organization` entre els models de l'aplicació Core;
- suites `core.tests`, `organizations.tests` i `iatrain.tests`.

El test `organizations.tests.test_migrations` cobreix l'adopció de files històriques, la conservació de claus primàries, les relacions d'IA Train i el canvi de `ContentType`.

### Resultat de la validació de l'extracció

- Les cinc migracions s'han aplicat correctament sobre la base de desenvolupament existent.
- Els recomptes i les claus primàries dels sis models s'han conservat.
- Els `ContentType` han mantingut els IDs existents i ara utilitzen `app_label = "organizations"`.
- Cada model conserva quatre permisos Django.
- Les quatre relacions d'IA Train apunten a `organizations.Organization`.
- Core només registra `Person`, `PersonClaimInvitation` i `PersonMergeRecord`.
- `makemigrations --check --dry-run` no detecta canvis.
- Les 96 proves dirigides de Core, Organizations i IA Train passen sobre el graf final.

## Passos funcionals futurs

### Unificació de la UI a IA Train

La propietat de backend ja està resolta, però encara queda eliminar la doble façana visual:

1. Fer de `/iatrain/organitzacions/` l'entrada principal.
2. Integrar-hi creació, edició, membres, rols, permisos i sol·licituds.
3. Organitzar el detall amb `Resum`, `Grups`, `Gimnastes`, `Gimnasos`, `Membres`, `Sol·licituds` i `Configuració`.
4. Retirar l'enllaç d'IA Train cap a «Administració» de Core.
5. Convertir les URLs antigues `/organitzacions/...` en redireccions temporals.
6. Actualitzar Home, perfil, navegació i notificacions perquè apuntin a IA Train.
7. Eliminar els templates d'organitzacions de Core quan no quedin consumidors.

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

## Criteri de finalització

L'extracció de backend està completa quan:

- Core només és propietari de la identitat;
- `organizations` és propietari real dels models, dades, regles i serveis;
- altres mòduls poden consumir `organizations` sense dependre d'IA Train.

La reorganització de producte quedarà completa quan IA Train sigui també la façana visual principal i ja no hi hagi pantalles duplicades a Core.
