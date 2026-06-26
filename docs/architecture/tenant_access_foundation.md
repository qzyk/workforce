# Tenant Access Foundation

Data: 2026-06-26

Scop: acest document descrie stratul canonic de acces tenant-safe introdus pentru a reduce riscul de cross-tenant leakage in Edifico fara rewrite si fara schimbari de schema.

## 1. De ce exista acest layer

Auditurile Phase 0 au identificat `Proiect`, `RaportActivitate`, `Pontaj`, `Contract`, documentele si BIM ca zone cu risc ridicat de IDOR. Aplicatia avea deja `tenant.py`, `Tenant` si coloane `tenant_id` pe multe modele, dar rutele foloseau frecvent `Model.query` si `get_or_404` direct.

`services/security/tenant_access.py` este layer-ul opt-in prin care rutele si serviciile vor primi treptat query-uri si lookup-uri tenant-safe. Nu aplica filtre globale SQLAlchemy si nu schimba automat comportamentul rutelor care nu il folosesc.

## 2. Moduri suportate

| Mod | Comportament |
|---|---|
| `off` | Compatibilitate legacy single-tenant. Query-urile raman nefiltrate si lookup-urile se comporta ca inainte. |
| `optional` | Daca exista `tenant_id`, query-urile pentru modele cu `tenant_id` direct sunt filtrate. Randurile globale `tenant_id=NULL` intra doar cu `include_global=True`. Daca nu exista tenant curent, comportamentul ramane permisiv pentru perioada de migrare. |
| `strict` | Fail closed pentru user normal fara tenant. Modelele cu `tenant_id` direct returneaza doar randurile tenantului curent. Randurile `NULL` sunt excluse implicit. Super-adminul este explicit: admin fara `tenant_id` vede nefiltrat. |

## 3. Ce se aplica acum

Layer-ul expune:

- `get_current_tenant_id_safe()`
- `get_tenant_mode()`
- `is_super_admin(user)`
- `model_has_tenant_id(model)`
- `query_for_tenant(model, tenant_id=None, include_global=False)`
- `get_or_404_for_tenant(model, object_id, tenant_id=None, include_global=False)`
- `ensure_same_tenant(obj, tenant_id=None, include_global=False)`
- `require_same_tenant(obj, tenant_id=None, include_global=False)`
- `get_project_or_404(project_id, tenant_id=None)`
- `tenant_id_for_new_record_or_403()`
- `query_activities_for_tenant(tenant_id=None, include_global=False)`
- `get_activity_or_404(activity_id, tenant_id=None)`
- `ensure_activity_same_tenant(activity, tenant_id=None)`
- `require_activity_same_tenant(activity, tenant_id=None)`
- `ensure_activity_inputs_same_tenant(proiect_ids, angajat_ids=None, tenant_id=None)`
- `require_activity_inputs_same_tenant(proiect_ids, angajat_ids=None, tenant_id=None)`

Exceptiile de baza sunt:

- `TenantAccessError`
- `TenantScopeUnsupported`
- `TenantAccessDenied`

## 4. Ce nu se aplica inca

Acest layer nu:

- transforma automat toate rutele in tenant-safe;
- impune strict mode global;
- inventeaza ownership pentru modele fara `tenant_id` direct;
- rezolva complet `DocumentProiect`, `AngajatProiect` sau ierarhia BIM indirecta;
- rezolva complet toate legaturile nested din `RaportActivitate` catre Pontaj, BIM, documente sau Gantt;
- rezolva complet toate legaturile nested din `Pontaj` catre BIM, documente, masini/utilaje sau Gantt;
- schimba schema sau adauga migrari;
- introduce servicii noi de business pentru proiecte, activitati, pontaje sau contracte.

## 5. Cum se foloseste

Pentru proiecte:

```python
from services.security.tenant_access import get_project_or_404

proiect = get_project_or_404(id)
```

Pentru modele cu `tenant_id` direct:

```python
from services.security.tenant_access import query_for_tenant, get_or_404_for_tenant

proiecte = query_for_tenant(Proiect).all()
contract = get_or_404_for_tenant(Contract, contract_id)
```

Pentru create in rute:

```python
from services.security.tenant_access import tenant_id_for_new_record_or_403

tenant_id = tenant_id_for_new_record_or_403()
```

Pentru activitati:

```python
from services.security.tenant_access import get_activity_or_404, query_activities_for_tenant

activitate = get_activity_or_404(id)
activitati = query_activities_for_tenant().all()
```


## 6. Reguli pentru `include_global=True`

`include_global=True` include randuri cu `tenant_id=NULL` pe langa randurile tenantului curent. Se foloseste doar pentru cataloage/config globale sau date legacy validate explicit.

Pentru date operationale, default-ul ramane `include_global=False`.

## 7. Modele fara `tenant_id`

Modelele fara `tenant_id` direct ridica `TenantScopeUnsupported` cand se incearca scoping direct in `optional` cu tenant activ sau in `strict`. Ownership-ul indirect trebuie implementat separat, prin helpers dedicati care verifica lantul real de proprietate.

Exemple deferred:

- `AngajatProiect` prin `Proiect` si `Angajat`
- `DocumentProiect` prin `Proiect`
- `ElementBIM` prin `Santier` / `ModelBIM`

Exemple implementate partial:

- `RaportActivitate` prin `Proiect -> tenant_id`, cu verificare secundara pe `Angajat -> tenant_id`.

## T1.2 Project Route Integration

Rutele de proiect protejate acum:

| Ruta | Schimbare |
|---|---|
| `proiecte.lista` | Foloseste `query_for_tenant(Proiect)` pentru lista si statistici. |
| `proiecte.adauga` | Seteaza `tenant_id` pe proiect nou cand exista tenant curent in `optional`/`strict`; in `strict`, user normal fara tenant primeste 403. |
| `proiecte.detalii` | Foloseste `get_project_or_404(id)`. |
| `proiecte.hub` | Foloseste `get_project_or_404(id)`. |
| `proiecte.editeaza` | Foloseste `get_project_or_404(id)`. |
| `proiecte.schimba_status` | Foloseste `get_project_or_404(id)` inainte de mutatie. |
| `proiecte.export_excel` | Foloseste `get_project_or_404(id)` inainte de generare export. |

Comportament:

- in `off`, rutele raman compatibile cu single-tenant;
- in `optional`, rutele filtreaza cand exista tenant curent;
- in `strict`, proiectele altui tenant primesc 404, iar create fara tenant pentru user normal primeste 403;
- super-adminul ramane explicit: admin fara `tenant_id` vede proiectele nefiltrat si poate crea proiect global `tenant_id=NULL`.

## Ce ramane neprotejat in `routes/proiecte.py`

Acest PR nu protejeaza inca rutele nested sau agregarile din domenii copil:

- asignari angajati pe proiect (`AngajatProiect`);
- documente proiect legacy (`Document`);
- resurse si utilaje;
- link-uri BIM proiect-santier si BIM-deviz;
- EVM, raport proiect si alte agregari;
- contracte/Gantt/BIM/documente citite in interiorul `hub`.

Nested domains sunt amanate deoarece multe folosesc ownership indirect sau modele fara `tenant_id` direct. Ele au nevoie de helpers dedicate pentru fiecare lant de proprietate, nu doar de inlocuirea mecanica a unui `get_or_404`.

## Riscuri proiect urmatoare

Urmatoarele zone project-related trebuie tratate in PR-uri separate:

- project employee assignments;
- project documents;
- project resource/vehicle data;
- project BIM links;
- contract/Gantt data linked by `proiect_id`;
- manager dropdown si form choices tenant-scoped;
- exporturi si rapoarte care agrega modele fara `tenant_id` direct.

## T1.3 Activity Route Integration

`RaportActivitate` nu primeste inca `tenant_id` direct. Pentru T1.3 ownership-ul canonic este:

```text
RaportActivitate -> Proiect -> tenant_id
```

La creare/editare se verifica si angajatii selectati:

```text
RaportActivitate -> Angajat -> tenant_id
```

Rutele si zonele de activitati protejate acum:

| Zona | Schimbare |
|---|---|
| `activitati.panou` | Listeaza activitati, count aprobare si dropdown-uri angajati/proiecte prin helper-ele tenant-safe. |
| `activitati.adauga` / `activitati.adauga_rapida` | Dropdown-uri tenant-scoped; POST-ul valideaza proiectele si angajatii selectati. |
| `activitati.detaliu` | Foloseste `get_activity_or_404(id)`. |
| `activitati.editeaza` | Foloseste `get_activity_or_404(id)` si valideaza inputurile la salvare. |
| `activitati.trimite` | Foloseste `get_activity_or_404(id)` inainte de schimbarea statusului. |
| `activitati.aproba` / `activitati.respinge` | Folosesc `get_activity_or_404(id)` inainte de workflow approval. |
| `activitati.sterge` | Foloseste `get_activity_or_404(id)` inainte de delete. |
| `activitati.aprobare` | Listeaza doar activitatile tenantului curent. |
| `activitati.aprobare_masa` | In `strict`/`optional` respinge batch-uri care contin activitati inaccesibile. |
| `activitati.calendar` / API calendar | Listeaza activitati, proiecte si angajati tenant-scoped. |
| Rapoarte saptamanale/lunare/anuale activitati | Folosesc `query_activities_for_tenant()` pentru `RaportActivitate`. |
| Exporturi activitati | Helper-ele interne de export citesc activitati/proiecte/angajati prin query-uri tenant-safe. |

Comportament:

- in `off`, query-urile pentru activitati raman compatibile cu single-tenant;
- in `optional`, se filtreaza cand exista tenant curent; fara tenant curent ramane comportamentul de migrare;
- in `strict`, userii normali fara tenant nu vad activitati tenant-owned, iar ID-urile straine primesc 404;
- super-adminul ramane explicit: admin fara `tenant_id` vede activitatile nefiltrat.

Ce ramane neprotejat in T1.3:

- `Pontaj` citit in paginile de activitati ramane in afara scope-ului acestui PR;
- entitatile BIM selectate in formular (`Santier`, `Cladire`, `ElementBIM`, `Spatiu`, `Zona`) raman in afara scope-ului;
- legaturile catre TaskProgram, Gantt si Contracte nu sunt introduse sau modificate;
- atasamentele/documentele proof-of-work nu sunt schimbate;
- `RaportActivitate` ramane fara `tenant_id` direct pana la un PR separat cu migrare.

Nested domains sunt amanate deoarece au lanturi diferite de ownership si reguli de business proprii. Pentru Pontaj, BIM, documente si Gantt nu este suficienta inlocuirea mecanica a query-urilor din `routes/activitati.py`; fiecare are nevoie de helper dedicat, teste IDOR proprii si, unde lipseste ownership-ul, migrare separata.

Riscuri ramase dupa T1.3:

- Pontajele pot fi agregate separat de activitati in rapoarte lunare;
- proiectele din JSON legacy (`proiecte_ids`, `detalii_pe_zi`) sunt validate la salvare, dar datele istorice pot contine amestecuri vechi;
- BIM context selectat in activitati nu este inca tenant-scoped;
- exporturile pot deveni cross-domain daca viitoare coloane adauga Contract/Gantt/Pontaj fara helper dedicat;
- lipseste inca audit trail unificat pentru aprobarile de activitati.

