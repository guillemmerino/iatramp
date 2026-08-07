# Entrega 1: identitat i organitzacions

## Estat

Implementada el 3 d'agost de 2026 a `core`. Aquesta entrega no connecta ni modifica el domini de `competicions_trampoli`.

L'objectiu és permetre que una persona autenticada completi la identitat Iatramp, creï una organització o demani unir-se a una d'existent, i que els responsables o administradors gestionin les sol·licituds, els rols i els permisos dels membres.

## Decisions de domini

### Persona creadora i administració

- `Organization.created_by` identifica una sola persona creadora.
- La persona creadora rep automàticament el rol `owner`.
- El rol `admin` no és únic: una organització pot tenir múltiples administradors.
- També hi pot haver múltiples responsables, però els serveis impedeixen retirar l'últim `owner` actiu.
- Ser creador és una dada històrica; els permisos operatius provenen de la pertinença, els rols i les excepcions de permisos.

### Pertinença i rols

Hi ha una sola `Membership` per parella persona-organització. La pertinença conté l'estat i la vigència del vincle.

Els rols es desen separadament a `MembershipRole`, de manera que un mateix membre pot ser, per exemple, entrenador i administrador alhora. Els rols disponibles són:

- `owner`
- `admin`
- `coach`
- `athlete`
- `judge`
- `staff`
- `member`

### Permisos

Els permisos de gestió són:

- `manage_organization`
- `manage_members`
- `review_requests`
- `manage_roles`

`owner` i `admin` reben aquests permisos per defecte. `MembershipPermission` permet afegir o denegar permisos concrets per membre. El responsable conserva sempre tots els permisos mentre manté el rol `owner`.

Aquesta combinació permet tenir múltiples administradors amb responsabilitats diferents sense crear rols artificials per a cada variant.

### Sol·licituds d'entrada

Una sol·licitud pendent no crea una pertinença i no dona accés.

`OrganizationMembershipRequest` manté la persona, l'organització, el missatge, l'estat, qui l'ha resolt i la traça temporal. Els rols demanats es normalitzen a `OrganizationMembershipRequestRole`.

Des de l'autoservei només es poden demanar rols no administratius. `owner` i `admin` s'han d'assignar posteriorment des de la gestió de membres.

## Implementació realitzada

### Models i migració

S'ha afegit la migració `core.0002_organization_membership_workflows`.

La migració:

1. Afegeix la persona creadora a l'organització.
2. Crea els models de rols, permisos i sol·licituds.
3. Agrupa les antigues files de `Membership` per persona i organització.
4. Conserva els rols antics com a files de `MembershipRole`.
5. Estableix la unicitat final de persona i organització.

La migració és reversible i es va aplicar correctament sobre PostgreSQL amb dades existents.

### Serveis

`core.services` concentra les operacions transaccionals:

- crear una organització i el seu responsable;
- concedir una pertinença o un rol;
- crear i cancel·lar sol·licituds;
- aprovar o rebutjar sol·licituds;
- calcular permisos efectius;
- actualitzar rols i excepcions de permisos;
- impedir que una organització perdi l'últim responsable.

Les vistes no creen directament pertinences, rols o resolucions de sol·licitud.

### Interfície

S'han incorporat els fluxos següents:

- `/perfil/`: espai unificat d’identitat, organitzacions i preferències; l’alta i edició de `Person` es fa en un modal.
- `/configuracio/`: redirecció de compatibilitat cap al perfil unificat.
- `/organitzacions/`: directori, cerca i estat personal.
- `/organitzacions/nova/`: creació d'una organització.
- `/organitzacions/<slug>/`: pertinença, membres i sol·licituds.
- `/organitzacions/<slug>/editar/`: edició bàsica per qui tingui permís.
- `/organitzacions/<slug>/membres/<id>/accessos/`: rols i permisos efectius.

El perfil unificat i la navegació global enllacen els nous espais. La navegació avisa de les sol·licituds pendents que la persona autenticada pot revisar, respectant rols, vigència i excepcions de permisos. Les mutacions requereixen autenticació, perfil actiu, CSRF i els permisos d'organització corresponents.

### Administració Django

L'administració permet inspeccionar i editar:

- persona creadora de l'organització;
- pertinença única;
- múltiples rols;
- excepcions de permisos;
- sol·licituds i rols demanats.

### Proves

La cobertura incorporada comprova:

- creació i vinculació del perfil;
- creació d'organització i assignació del responsable;
- múltiples administradors simultanis;
- múltiples rols per membre;
- excepcions individuals als permisos d'un administrador;
- sol·licituds sense accés prematur;
- aprovació per responsable o administrador;
- rebuig d'aprovacions fetes per membres normals;
- protecció de l'últim responsable;
- flux complet de creació, sol·licitud i aprovació des de la UI.

Validació executada:

```text
python manage.py check
python manage.py makemigrations core --check --dry-run
python manage.py test core.tests iatrain.tests --verbosity 1 --keepdb
```

Resultat de la suite dirigida: 59 proves correctes.

## Límits conscients de l'entrega

Encara no s'ha implementat:

- registre públic de comptes;
- invitacions iniciades per una organització;
- notificacions per correu;
- verificació formal de clubs o federacions;
- fusió o reclamació d'organitzacions duplicades;
- baixa voluntària, suspensió o expulsió des de la UI;
- historial visible de canvis de rols i permisos;
- tutors legals per a persones menors;
- interfície d’activació dels perfils esportius d’IA Train;
- consentiment visible de relacions entrenador-gimnasta;
- creació de contextos d'entrenament des d'IA Train.

## Passos futurs

### Entrega 1.1: operativa d'organització

1. Afegir invitacions i acceptació per part de la persona convidada.
2. Afegir baixa, suspensió i reactivació de membres.
3. Incorporar un registre d'auditoria consultable.
4. Afegir notificacions internes i, després, correu.
5. Definir verificació d'organitzacions i gestió de duplicats.
6. Incorporar controls específics per a menors i tutors legals.

### Entrega 2: perfils i relacions esportives

1. Exposar a la UI l’activació dels perfils `CoachProfile` i `AthleteProfile`, que ja existeixen al domini.
2. Afegir dades específiques només quan el domini estigui definit: llicències, disciplines o acreditacions.
3. Exposar el cicle ja implementat de creació, invitació i reclamació de gimnastes.
4. Validar que les dues persones siguin membres vigents de l'organització contextual.

### Entrega 3: IA Train

1. Crear i editar `TrainingContext` des d'IA Train.
2. Limitar els gimnastes seleccionables a relacions actives i consentides.
3. Permetre que el gimnasta consulti els seus contextos autoritzats.
4. Revalidar permisos en cada consulta i mutació.

`competicions_trampoli` queda explícitament fora d'aquestes entregues fins que es defineixi una integració independent i compatible amb participants externs i accessos per QR.
