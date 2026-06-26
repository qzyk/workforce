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
- `query_timesheets_for_tenant(tenant_id=None, include_global=False)`
- `get_timesheet_or_404(timesheet_id, tenant_id=None)`
- `ensure_timesheet_same_tenant(timesheet, tenant_id=None)`
- `require_timesheet_same_tenant(timesheet, tenant_id=None)`
- `ensure_timesheet_inputs_same_tenant(proiect_id=None, angajat_id=None, tenant_id=None)`
- `require_timesheet_inputs_same_tenant(proiect_id=None, angajat_id=None, tenant_id=None)`

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

Pentru pontaje:

```python
from services.security.tenant_access import get_timesheet_or_404, query_timesheets_for_tenant

pontaj = get_timesheet_or_404(id)
pontaje = query_timesheets_for_tenant().all()
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
- `Pontaj` prin `Proiect -> tenant_id`, cu verificare secundara pe `Angajat -> tenant_id`.

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

## T1.4 Timesheet Route Integration

`Pontaj` nu primeste inca `tenant_id` direct. Pentru T1.4 ownership-ul canonic este:

```text
Pontaj -> Proiect -> tenant_id
```

Se valideaza secundar si angajatul:

```text
Pontaj -> Angajat -> tenant_id
```

Rutele si zonele de pontaje protejate acum:

| Zona | Schimbare |
|---|---|
| `pontaje.lista` | Statistici, calendar lunar, lista si dropdown-uri angajati/proiecte folosesc helper-ele tenant-safe. |
| `pontaje.adauga` | Dropdown-uri tenant-scoped prin `PontajForm`; POST-ul valideaza proiectul si angajatul selectat. |
| `pontaje.adauga_multiplu` | Valideaza proiectul si fiecare angajat inainte de creare; duplicatele se cauta tenant-scoped. |
| `pontaje.angajati_proiect` | Verifica proiectul cu `get_project_or_404()` si returneaza doar angajati vizibili tenantului curent. |
| `pontaje.verificare_duplicat` | Nu dezvaluie pontaje pentru angajati inaccesibili si cauta duplicatele tenant-scoped. |
| `pontaje.situatie_zilnica` | Returneaza doar pontajele tenantului curent pentru ziua ceruta. |
| `pontaje.calendar` | Dropdown-ul si pontajele lunare sunt tenant-scoped. |
| `pontaje.aprobare` | Listeaza doar pontajele `trimis` ale tenantului curent. |
| `pontaje.aproba` / `pontaje.respinge` | Folosesc `get_timesheet_or_404(id)` inainte de workflow approval. |
| `pontaje.trimite` | Foloseste `get_timesheet_or_404(id)` inainte de schimbarea statusului. |
| `pontaje.editeaza` | Foloseste `get_timesheet_or_404(id)` si valideaza proiectul/angajatul la salvare. |
| `pontaje.sterge` | Foloseste `get_timesheet_or_404(id)` inainte de delete. |
| `pontaje.aproba_multiplu` | In `strict`/`optional` respinge batch-uri care contin pontaje inaccesibile. |
| `pontaje.export_lunar` | Exporta doar pontajele tenantului curent si valideaza `proiect_id` cu `get_project_or_404()`. |
| `pontaje.import_excel` | CNP-ul angajatului, codul proiectului si duplicatele sunt rezolvate tenant-scoped. |
| `teren.pontaj` | Listeaza proiecte/angajati tenant-scoped si valideaza inputurile inainte de creare Pontaj rapid. |

Comportament:

- in `off`, query-urile pentru pontaje raman compatibile cu single-tenant;
- in `optional`, se filtreaza cand exista tenant curent; fara tenant curent ramane comportamentul de migrare;
- in `strict`, userii normali fara tenant nu vad pontaje tenant-owned, iar ID-urile straine primesc 404;
- super-adminul ramane explicit: admin fara `tenant_id` vede pontajele nefiltrat.

Batch/import/export:

- batch approval pastreaza comportamentul legacy in `off`;
- in `optional`/`strict`, batch approval respinge intregul request daca include un ID inaccesibil;
- importul Excel nu rezolva CNP-uri sau coduri de proiect din alt tenant;
- exportul lunar fara filtru de proiect include doar pontajele tenantului curent in `optional`/`strict`;
- exportul lunar cu `proiect_id` strain returneaza 404 inainte de generarea workbook-ului.

Ce ramane neprotejat in T1.4:

- `Pontaj` ramane fara `tenant_id` direct pana la o migrare separata;
- legaturile BIM optionale de pe pontaj (`element_bim_id`, `spatiu_id`) nu sunt tenant-scoped in acest PR;
- `AngajatProiect` nu primeste inca helper propriu complet;
- rapoartele din servicii externe care citesc `Pontaj` direct nu sunt refactorizate;
- logica de calcul ore, ore suplimentare, duplicate si workflow ramane in ruta pana la `timesheet_service.py`.

Nu s-a adaugat migrare deoarece T1.4 foloseste ownership indirect existent si nu adauga coloane. Nu s-a creat `timesheet_service.py` deoarece acest PR este doar security/access-control; extragerea logicii de business ramane pentru S1.2.

Riscuri ramase dupa T1.4:

- servicii precum EVM/rapoarte lucrari pot citi `Pontaj` direct daca ruta nu le furnizeaza obiecte/ID-uri deja scopate;
- BIM context si documentele atasate viitoare trebuie protejate separat;
- importurile/rapoartele cross-domain trebuie revizuite din nou cand se extrage `timesheet_service.py`;
- audit trail pentru aprobarile Pontaj ramane neuniform.

## T1.5 Contract Route Integration

T1.5 protejeaza accesul la rutele principale din domeniul Contract fara migrari si fara extragere de servicii. Ownership-ul canonic foloseste coloanele `tenant_id` deja existente pe modelele contractuale, plus validarea proiectului/contractului parinte inainte de import, export sau mutatie.

Helpers adaugate sau completate:

- `query_contracts_for_tenant()`
- `get_contract_or_404()`
- `ensure_contract_same_tenant()` / `require_contract_same_tenant()`
- `get_program_referinta_or_404()`
- `get_task_program_or_404()`
- `get_oferta_contract_or_404()`
- `get_pozitie_boq_or_404()`
- `get_situatie_lunara_or_404()`
- `get_revendicare_or_404()`
- `get_revendicare_termen_or_404()`
- `get_revendicare_task_or_404()`
- `get_revendicare_cantitate_or_404()`
- `get_termen_contract_or_404()`
- `get_cantitate_executata_lunara_or_404()`
- `get_proces_verbal_or_404()`
- `get_raport_lucrari_proiect_or_404()`
- `get_corespondenta_or_404()`
- `get_regula_notificare_or_404()`
- `query_tarife_categorie_for_tenant()`
- `ensure_contract_inputs_same_tenant()` / `require_contract_inputs_same_tenant()`

Ownership paths folosite:

| Model | Ownership |
|---|---|
| `Contract` | `Contract.tenant_id`, validat cu `Proiect` la create/edit. |
| `ProgramReferinta` / `TaskProgram` | `tenant_id` direct, derivat din contractul validat la import. |
| `OfertaContract` / `PozitieBoQ` | `tenant_id` direct, derivat din contractul validat la import. |
| `CantitateExecutataLunara` | `tenant_id` direct, plus `PozitieBoQ -> OfertaContract` in rutele bulk. |
| `SituatieLunara` | `tenant_id` direct, validat inainte de detalii/export/status. |
| `Revendicare` si link-uri M:N | `tenant_id` direct pe revendicare si pe link. Link target-urile se valideaza inainte de creare/stergere. |
| `ProcesVerbal` | `tenant_id` direct, derivat din proiect/contract la create/edit. |
| `RaportLucrariProiect` | `tenant_id` direct, proiectul este validat inainte de generare/listare. |
| `Corespondenta` / `ReguliNotificareProiect` | `tenant_id` direct, proiect/contract validat la create/edit. |
| `TarifCategorie` | `tenant_id` direct; `proiect_id=NULL` cu `tenant_id=NULL` este catalog global default explicit, iar override-urile de proiect sunt filtrate prin tenant si proiect validat. |

Rute protejate:

- `Contract` lista/detalii/create/edit/delete si dropdown-uri.
- `TermenContract` create/edit/delete.
- `ProgramReferinta` import si detalii program/taskuri.
- `OfertaContract`, `PozitieBoQ`, cantitati lunare si clasificare manuala.
- `SituatieLunara` lista/create/detalii/status/export XLSX/export PDF.
- `RaportLucrariProiect` lista/generare/detalii.
- `Corespondenta` lista/create/edit/delete/detalii.
- `Revendicare` lista/create/edit/delete/detalii si link-uri catre termen/task/cantitate.
- `ProcesVerbal` lista/create/edit/delete/export DOCX/export PDF.
- `ReguliNotificareProiect` lista/create/edit/delete.
- `TarifCategorie` lista si salvare override.
- `Centralizator` si `Deviz General` view/export prin proiect validat.

Import behavior:

- importul MS Project valideaza contractul cu `get_contract_or_404()` inainte de procesarea fisierului;
- importul Oferta/BoQ valideaza contractul cu `get_contract_or_404()` inainte de procesarea fisierului;
- randurile create primesc `tenant_id` din contractul deja scopat cand mode-ul nu este `off`;
- contract strain returneaza 404 inainte de parser/file workflow.

Export behavior:

- `SituatieLunara` XLSX/PDF valideaza sursa cu `get_situatie_lunara_or_404()` inainte de generare;
- `ProcesVerbal` DOCX/PDF valideaza sursa cu `get_proces_verbal_or_404()` inainte de generare;
- `Centralizator` si `Deviz General` valideaza proiectul cu `get_project_or_404()` inainte de apelul serviciului;
- exporturile nu schimba layout-ul, formatul fisierelor sau calculul existent.

Claim link behavior:

- claim-ul parinte este validat cu `get_revendicare_or_404()`;
- target-ul link-ului este validat cu helper-ul dedicat (`get_termen_contract_or_404()`, `get_task_program_or_404()`, `get_cantitate_executata_lunara_or_404()`);
- stergerea link-urilor foloseste helper dedicat pentru `RevendicareTermen`, `RevendicareTask` si `RevendicareCantitate`;
- link strain sau link care nu apartine revendicarii curente returneaza 404 si nu sterge partial.

Comportament pe moduri:

- in `off`, rutele pastreaza compatibilitatea legacy si query-urile raman permisive;
- in `optional`, datele sunt filtrate cand exista tenant curent, iar fara tenant curent ramane modul de migrare;
- in `strict`, user normal fara tenant esueaza inchis pentru date contractuale, iar ID-urile straine primesc 404;
- super-adminul fara tenant ramane explicit si nefiltrat.

Service boundary limitation:

- `services/situatii.py`, `services/centralizator.py`, `services/pv_generator.py`, `services/conflict_revendicare.py`, `services/rapoarte_lucrari.py` si `services/deviz_pricing.py` inca presupun validare la nivel de ruta;
- T1.5 evita refactorizarea acestor servicii si le apeleaza doar dupa validarea obiectului/proiectului sursa;
- pentru `deviz_pricing`, rutele folosesc tarife tenant-safe cand calculeaza pricing, dar functiile publice ale serviciului nu sunt inca security boundary daca sunt apelate direct din alta parte.

Ce ramane neprotejat dupa T1.5:

- serviciile contractuale listate mai sus nu sunt inca harden-uite ca boundary independente;
- `TermenUrmarit` este accesat doar prin sursa corespondentei validate, fara helper dedicat de ruta pe ID;
- eventualele apeluri viitoare directe catre servicii trebuie sa primeasca helper dedicat sau parametru tenant;
- import parsers si generatoarele XLSX/PDF raman componente de business/format, nu componente de autorizare.

Nu s-a adaugat migrare deoarece toate modelele contractuale folosite au deja `tenant_id` sau ownership prin proiect/contract existent. Nu s-au creat `contract_service.py`, `baseline_service.py` sau `claims_service.py` deoarece acest PR este strict tenant guard; extragerea serviciilor ar schimba boundary-ul de business si trebuie facuta intr-un PR separat.

Urmatorul PR recomandat: `T1.6 Document Tenant Guard`. Daca apelurile directe catre serviciile contractuale devin necesare inainte de T1.6, se recomanda mai intai `T1.5B Contract Service Boundary Hardening`.

## T1.6 Document Route Integration

T1.6 protejeaza accesul la documente si la raspunsurile de tip fisier fara sa schimbe schema, layout-ul de fisiere sau workflow-ul documentelor. Documentele nu sunt execution spine, dar sunt artefacte high-risk: o ruta IDOR poate expune fisiere HR, contractuale sau de proiect.

Helpers adaugate:

- `query_project_documents_for_tenant()`
- `get_project_document_or_404()`
- `query_project_document_revisions_for_tenant()`
- `get_project_document_revision_or_404()`
- `ensure_project_document_same_tenant()` / `require_project_document_same_tenant()`
- `query_legacy_documents_for_tenant()`
- `get_legacy_document_or_404()`
- `ensure_legacy_document_same_tenant()` / `require_legacy_document_same_tenant()`

Ownership paths:

| Model | Ownership |
|---|---|
| `DocumentProiect` | `DocumentProiect -> Proiect -> tenant_id`. |
| `RevizieDocument` | `RevizieDocument -> DocumentProiect -> Proiect -> tenant_id`. |
| `Document` legacy/HR/proiect | `Document -> Proiect -> tenant_id` cand `proiect_id` exista si `Document -> Angajat -> tenant_id` cand `angajat_id` exista. Daca ambele exista, ambele trebuie sa apartina tenantului curent. |

Rute protejate:

- `routes/documente.py`: panou, lista generala, lista angajat, upload, editare metadata, download, preview, stergere, expirate, export Excel si API alerte.
- `routes/documente_proiecte.py`: index proiect, listare pe instalatie, upload, detaliu, editare, upload revizie, download, preview, stergere, aprobare/respingere, export index, verificare completitudine, API tipuri documente si download revizie.
- `routes/proiecte.py`: tab-ul de documente legacy din detalii/hub, upload document proiect legacy, download si stergere document legacy atasat proiectului.

File-serving rule:

- fiecare `send_file()` pentru document sau revizie este precedat de lookup tenant-safe;
- path-ul fisierului nu este construit pentru documente straine;
- documentele straine returneaza 404 pentru a evita enumerarea ID-urilor;
- fisierele fizice se sterg doar dupa autorizarea randului DB, pastrand comportamentul existent.

Comportament pe moduri:

- in `off`, query-urile documentelor raman compatibile cu legacy single-tenant;
- in `optional`, userii cu `tenant_id` vad doar documentele tenantului lor, iar userii fara tenant pastreaza comportamentul migration-friendly;
- in `strict`, user normal fara tenant esueaza inchis, iar documentele/reviziile straine returneaza 404;
- super-adminul fara tenant ramane explicit si nefiltrat, consecvent cu restul layer-ului.

Upload/create:

- upload-ul HR valideaza angajatul selectat prin `Angajat -> tenant_id` inainte de salvarea fisierului;
- proiectul optional selectat pe document legacy este validat cu `get_project_or_404()`;
- upload-ul pe documente proiect valideaza proiectul cu `get_project_or_404()` inainte de orice salvare;
- nu s-au schimbat extensiile permise, folder-ele sau numele generate.

Export:

- exportul Excel al documentelor HR foloseste doar documente si angajati vizibili tenantului curent;
- exportul indexului de documente proiect valideaza proiectul si foloseste query-ul tenant-safe pentru `DocumentProiect`;
- nu s-a schimbat formatul workbook-urilor.

Ce ramane neprotejat dupa T1.6:

- `Document` legacy fara `proiect_id` si fara `angajat_id` nu are ownership sigur si nu este vizibil in moduri scoped;
- tabelele de configurare document (`TipInstalatie`, `TipDocumentProiect`) raman globale;
- rutele din `routes/proiecte.py` au multe agregari non-document ramase in afara T1.6;
- nu exista inca un `document_service.py`, deci rutele raman boundary-ul principal de autorizare pentru documente.

Nu s-a adaugat migrare deoarece T1.6 foloseste ownership-ul existent prin `Proiect` si `Angajat`. Nu s-a creat `document_service.py` deoarece acest PR este strict security/access-control; extragerea workflow-ului de documente trebuie sa ramana separata.

Urmatorul PR recomandat: `T1.7 BIM Tenant Guard`, deoarece fisierele/modelarea BIM raman urmatorul domeniu cu risc mare de file/metadata leakage. Daca prioritatea operationala devine planificarea, alternativa este `T1.7 Gantt Tenant Guard`.

## T1.7 BIM Route Integration

T1.7 protejeaza accesul la datele BIM fara sa transforme BIM intr-un produs separat si fara sa extraga `bim_service.py`. BIM ramane context layer pentru Execution Spine; acest PR inchide suprafetele evidente de IDOR pe rute, API-uri, metadata si fisiere model.

Helpers adaugate:

- `query_sites_for_tenant()` / `get_site_or_404()`
- `query_bim_buildings_for_tenant()` / `get_bim_building_or_404()`
- `query_bim_levels_for_tenant()` / `get_bim_level_or_404()`
- `query_bim_spaces_for_tenant()` / `get_bim_space_or_404()`
- `query_bim_models_for_tenant()` / `get_bim_model_or_404()`
- `query_bim_model_versions_for_tenant()` / `get_bim_model_version_or_404()`
- `query_bim_elements_for_tenant()` / `get_bim_element_or_404()`
- `query_bim_issues_for_tenant()` / `get_bim_issue_or_404()`
- `ensure_bim_record_same_tenant()` / `require_bim_record_same_tenant()`

Ownership paths:

| Model | Ownership |
|---|---|
| `Santier` | `tenant_id` direct; daca lipseste, `Santier -> Proiect -> tenant_id`. |
| `Cladire` | `Cladire -> Santier -> tenant_id / Proiect`. |
| `Nivel` | `Nivel -> Cladire -> Santier`. |
| `Zona` | `Zona -> Cladire / Nivel -> Santier`. |
| `Spatiu` | `Spatiu -> Nivel / Zona -> Santier`. |
| `ModelBIM` | `tenant_id` direct; daca lipseste, `ModelBIM -> Santier / Cladire -> Santier`. |
| `BIMModelVersion` | `tenant_id` direct; daca lipseste, `BIMModelVersion -> ModelBIM`. |
| `ElementBIM` | `ModelBIM` cand `model_bim_id` exista; altfel ierarhia `Spatiu/Nivel/Cladire -> Santier`. |
| `IssueBIM` | `tenant_id` direct; daca lipseste, contextul `ElementBIM/Spatiu/Nivel/Cladire`. |

Regula fail-closed:

- un `tenant_id` direct, cand exista, este autoritativ;
- pentru recorduri fara `tenant_id`, toti parintii expliciti disponibili trebuie sa fie vizibili tenantului curent;
- recordurile operationale BIM fara owner sigur nu sunt tratate ca globale in `optional` cu tenant activ sau in `strict`.

Rute si API-uri protejate:

- dashboard BIM, liste santiere/modele/elemente/issues si metrici;
- `api/tree`, cascade APIs pentru cladiri/niveluri/spatii, search si catalog elemente;
- detalii Santier, ElementBIM, ModelBIM si versioning CDE;
- viewer IFC, viewer federat si fisierele `ModelBIM` / `BIMModelVersion`;
- import IFC si creare model extern prin validarea santierului/cladirii/proiectului inainte de salvare;
- BCF export legacy, BCF `.bcfzip` export all si export pe `ids`;
- COBie export prin santier validat;
- kanban issues, schimbare status, comentarii si API comments;
- rules/clash/4D/5D pe intrarile `santier_id`, `model_id`, `element_id`, `run_id` si `schedule_id`;
- `routes/teren.py` pentru creare issue din teren;
- `routes/proiecte.py` doar pentru legare/dezlegare santier si count-uri BIM in hub.

File-serving rule:

- `viewer_file()` foloseste `get_bim_model_or_404()` inainte de `fisier_path`;
- `api_model_version_file()` foloseste `get_bim_model_version_or_404()` inainte de `fisier_path`;
- QTO CSV valideaza modelul inainte de a citi fisierul;
- exporturile COBie/BCF valideaza recordurile sursa inainte de generator.

Dashboard/API scoping:

- dashboard-ul numara doar santiere, cladiri, elemente si issues vizibile tenantului curent;
- tree/search/catalog nu returneaza coduri, nume, GUID-uri sau metadata din alt tenant;
- cascade APIs returneaza 404 cand parintele cerut nu este vizibil.

BCF/COBie/export behavior:

- BCF all exporta doar issues vizibile tenantului curent;
- BCF pe `ids` respinge intreg exportul cu 404 daca lista contine un issue inaccesibil;
- importul BCF creeaza issue-uri cu `tenant_id` cand ruta are tenant activ si nu actualizeaza un topic BCF existent din alt tenant cand tenantul este cunoscut;
- COBie valideaza `Santier` inainte de workbook generation;
- formatele generate nu au fost modificate.

Create/import behavior:

- `Santier` nou primeste `tenant_id` cand modul este `optional`/`strict` si exista tenant curent;
- importul IFC valideaza `santier_id` inainte de `file.save()` si transmite `tenant_id` catre randurile noi cu suport direct;
- modelul extern valideaza `santier_id` si `cladire_id` inainte de creare/editare;
- field issue din `routes/teren.py` valideaza santierul ales si seteaza `tenant_id` pe `IssueBIM`;
- nu s-au schimbat parserul IFC, naming-ul fisierelor, folder-ele de upload sau viewer behavior, in afara accesului.

Comportament pe moduri:

- in `off`, query-urile BIM raman compatibile cu single-tenant si fisierele existente pot fi servite ca inainte;
- in `optional`, userii cu `tenant_id` sunt scopati, iar userii fara tenant pastreaza comportamentul migration-friendly;
- in `strict`, user normal fara `tenant_id` esueaza inchis, iar ID-urile straine primesc 404;
- super-adminul fara tenant ramane explicit si nefiltrat, conform foundation layer.

Ce ramane neprotejat dupa T1.7:

- `services/ifc_import.py`, `services/bim_4d.py`, `services/bim_5d.py`, `services/bcf_io.py`, `services/bim_rules.py`, `services/clash_detection.py`, `services/cobie_export.py` si serviciile IoT nu sunt inca security boundaries independente;
- unele servicii interne inca folosesc query-uri brute si trebuie apelate numai dupa validarea rutei;
- ierarhia importata din IFC ramane dependenta de santier/model validat la nivel de ruta;
- IoT/Digital Twin ramane partial route-validated si trebuie tratat intr-un PR separat daca devine domeniu prioritar.

Nu s-a adaugat migrare deoarece modelele BIM relevante au deja `tenant_id` direct sau ownership existent prin `Santier`, `ModelBIM`, `Proiect` si ierarhia BIM. Nu s-au creat `bim_service.py`, `bim_issue_service.py` sau `bim_import_service.py` deoarece T1.7 este strict security/access-control; extragerea serviciilor ar schimba boundary-ul de business si trebuie facuta ulterior.

Urmatorul PR recomandat: `T1.8 Gantt Tenant Guard`. Daca se prioritizeaza suprafata operationala agregata, alternativa este `T1.8 Dashboard/Reporting Guard`.

## T1.8 Gantt Route Integration

T1.8 protejeaza planurile Gantt salvate, nodurile WBS editabile, save/create, exporturile pe plan salvat, configurarea Gantt si punctele directe BIM/Proiect care primesc sau afiseaza `GanttPlan`. PR-ul nu transforma `GanttPlan` in baseline contractual si nu introduce integrare `ProgramReferinta` / `TaskProgram`.

Helpers adaugate:

- `query_gantt_plans_for_tenant()` / `get_gantt_plan_or_404()`
- `ensure_gantt_plan_same_tenant()` / `require_gantt_plan_same_tenant()`
- `query_gantt_wbs_nodes_for_tenant()` / `get_gantt_wbs_node_or_404()`
- `ensure_gantt_inputs_same_tenant()` / `require_gantt_inputs_same_tenant()`
- `query_gantt_profiles_for_tenant()`
- `query_gantt_synonyms_for_tenant()`
- `query_gantt_classification_rules_for_tenant()`
- `query_gantt_relation_templates_for_tenant()`

Ownership paths:

| Model | Ownership |
|---|---|
| `GanttPlan` | `tenant_id` direct; daca lipseste, `GanttPlan -> Proiect -> tenant_id`. Cand exista si `tenant_id`, si `proiect_id`, ambele trebuie sa fie compatibile. |
| `GanttWbsNod` | `GanttWbsNod -> GanttPlan -> tenant_id / Proiect`; `tenant_id` direct pe nod trebuie sa fie compatibil cand exista. |
| `GanttProfilMapare` | `tenant_id` sau rand global default (`tenant_id=NULL`). |
| `GanttSinonimColoana` | `tenant_id` sau rand global default (`tenant_id=NULL`). |
| `GanttClasificareRegula` | `tenant_id` sau rand global default (`tenant_id=NULL`). |
| `GanttRelatieTemplate` | `tenant_id` sau rand global default (`tenant_id=NULL`). |

Regula pentru `NULL`:

- planurile Gantt salvate sunt date operationale si nu devin globale doar pentru ca `tenant_id=NULL`;
- un plan legacy cu `tenant_id=NULL` este vizibil unui tenant doar daca are proiect parinte vizibil;
- randurile Gantt de configurare cu `tenant_id=NULL` raman globale doar ca defaults shared;
- userii tenant-scoped pot citi defaults globale, dar scriu numai randuri tenant-specific si nu modifica/delete global defaults.

Rute/API-uri protejate:

- `routes/gantt.py`: lista planuri salvate, detaliu plan, stergere plan, export plan, seeding/listare WBS si operatii WBS (`redenumeste`, `sus/jos`, `muta`, `adauga`, `sterge`, `reset`);
- `routes/gantt.py`: dropdown-ul de proiecte din preview foloseste proiecte tenant-safe;
- `routes/gantt.py`: save/create valideaza `proiect_id` inainte de creare si seteaza `tenant_id` pe planul nou cand modul are tenant activ;
- `routes/gantt.py`: pagina `/gantt/config` listeaza tenant + global defaults, fara randuri din alt tenant;
- `routes/gantt.py`: write-urile de config (`sinonim`, `regula`, `mapare`, `tarif`, `profil`) folosesc `tenant_id_for_new_record_or_403()`;
- `routes/bim.py`: viewer-ul BIM filtreaza lista de planuri Gantt si `genereaza-4d` valideaza `plan_id` cu `get_gantt_plan_or_404()` inainte de generarea 4D;
- `routes/proiecte.py`: hub-ul proiectului foloseste query-uri Gantt tenant-safe pentru count/cost, ultimul plan si detectia WBS.

Save/create behavior:

- `/gantt/salveaza` verifica fisierul temporar existent, apoi valideaza `proiect_id` cu `require_gantt_inputs_same_tenant()` inainte de a rula create;
- in `off`, planul nou pastreaza comportamentul legacy (`tenant_id=NULL`);
- in `optional`/`strict` cu tenant activ, planul nou primeste tenantul curent;
- un proiect strain returneaza 404 si nu creeaza plan.

Export behavior:

- exportul din plan salvat (`/gantt/plan/<id>/export/<fmt>`) valideaza planul cu `get_gantt_plan_or_404()` inainte de pipeline si inainte de `send_file()`;
- exporturile de preview pe token temporar raman compatibile si nu sunt legate de un `GanttPlan` salvat;
- formatele CSV/MS Project/Primavera/JSON si layout-ul fisierelor generate nu au fost schimbate.

WBS editor behavior:

- planul parinte este validat inainte de seeding, randare si operatii;
- `nod_id`, `grup_id` si `parinte_id` sunt validate prin `get_gantt_wbs_node_or_404()` si trebuie sa apartina aceluiasi plan;
- mutarea sub un nod non-grup returneaza 404;
- reset-ul ramane plan-scoped si nu schimba algoritmul de WBS automat.

Config/global default behavior:

- listele de config includ randuri globale si randuri ale tenantului curent, dar nu randuri din alt tenant;
- write-urile de config creeaza/updateaza randuri tenant-specific pentru user tenant-scoped;
- `services/gantt/store.py` refuza toggle/delete/rename pe randuri globale cand apelul vine cu `tenant_id` de tenant;
- super-admin/global behavior ramane explicit cand apelul ajunge cu `tenant_id=None`;
- in `strict`, user normal fara tenant esueaza inchis la write prin `tenant_id_for_new_record_or_403()`.

Comportament pe moduri:

- in `off`, query-urile Gantt raman compatibile cu legacy single-tenant;
- in `optional`, userii cu `tenant_id` sunt scopati, iar userii fara tenant pastreaza comportamentul migration-friendly;
- in `strict`, user normal fara `tenant_id` esueaza inchis pentru planuri salvate si create/write, iar ID-urile straine primesc 404;
- super-adminul fara tenant ramane explicit si nefiltrat, conform foundation layer.

Ce ramane neprotejat dupa T1.8:

- `services/gantt/pipeline.py`, `services/gantt/program.py`, `services/gantt/wbs_editor.py`, `services/gantt/config_loader.py` si generatoarele de export nu sunt inca security boundaries independente;
- rutele Gantt raman boundary-ul principal pentru planuri salvate, WBS si config;
- API-urile stateless care primesc doar payload de activitati/articole nu au ownership DB si raman compatibile;
- tokenurile temporare de preview nu sunt planuri salvate si nu sunt scoping boundary multi-tenant;
- dashboard/reporting general inca are agregari Gantt brute si este recomandat pentru T1.9.

Nu s-a adaugat migrare deoarece modelele Gantt relevante au deja `tenant_id` si/sau ownership prin `Proiect`. Nu s-a creat `gantt_plan_service.py` deoarece T1.8 este strict security/access-control; service extraction ar schimba boundary-ul de business si trebuie facuta ulterior. Nu s-a implementat sincronizare `ProgramReferinta` / `TaskProgram` si nu s-a introdus baseline approval.

Urmatorul PR recomandat: `T1.9 Dashboard/Reporting Tenant Guard`.

## T1.9 Dashboard / Reporting Route Integration

T1.9 protejeaza dashboard-urile agregate, cautarea globala si modulul legacy de rapoarte. PR-ul ramane security/access-control: nu schimba formulele KPI, layout-urile XLSX/PDF, folderele de export, schema DB sau fluxurile de business.

Helpers adaugate:

- `query_reports_for_tenant()` / `get_report_or_404()`
- `ensure_report_same_tenant()` / `require_report_same_tenant()`
- `ensure_reporting_project_scope()` / `require_reporting_project_scope()`

Ownership paths:

| Model | Ownership |
|---|---|
| `Raport` | nu are `tenant_id`; acces punctual prin `parametri.proiect_id` / `parametri.angajat_id`, apoi prin `Raport.generator -> Utilizator.tenant_id`. |
| `Dashboard project stats` | `Proiect.tenant_id` prin `query_for_tenant(Proiect)`. |
| `Dashboard timesheet stats` | `Pontaj -> Proiect/Angajat -> tenant_id` prin `query_timesheets_for_tenant()`. |
| `Dashboard legacy documents` | `Document -> Proiect/Angajat -> tenant_id` prin `query_legacy_documents_for_tenant()`. |
| `Dashboard contracts` | `Contract.tenant_id` prin `query_contracts_for_tenant()`. |
| `Dashboard BIM` | helperii BIM T1.7 (`query_sites_for_tenant`, `query_bim_*_for_tenant`). |
| `Dashboard Gantt` | helperii Gantt T1.8 (`query_gantt_plans_for_tenant`). |

Rute/API-uri protejate:

- `routes/dashboard.py`: dashboard principal, API stats, dashboard executiv, cautare globala si trigger manual EVM;
- `routes/rapoarte.py`: panou rapoarte, istoric, descarcare raport, stergere raport;
- generare rapoarte pe proiect (`foaie_prezenta`, `situatie_proiect`) prin `get_project_or_404()` inainte de generator;
- generare rapoarte pe angajat (`pontaj_individual`) prin angajat tenant-safe inainte de generator;
- generare rapoarte all-project/all-employee (`stat_plata`, `centralizator_ore`, `documente_expirate`, `prezenta_zilnica`, `raport_ssm`) cu `tenant_id` transmis catre generator.

Import/export/file-serving behavior:

- `Raport` este validat cu `get_report_or_404()` inainte de `send_file()`;
- exporturile XLSX/PDF pastreaza layout-ul si naming-ul existent;
- rutele cu `proiect_id` resping proiectele straine cu 404 inainte de generare;
- rutele all-project/all-employee filtreaza randurile din workbook/PDF dupa tenant cand modul are tenant activ;
- trigger-ul manual EVM primeste un query de proiecte deja tenant-scoped si nu mai scaneaza intreg portofoliul din ruta.

Comportament pe moduri:

- in `off`, dashboard-urile, istoricul si exporturile raman compatibile cu single-tenant;
- in `optional`, userii cu `tenant_id` sunt scopati, iar userii fara tenant pastreaza comportamentul migration-friendly;
- in `strict`, user normal fara `tenant_id` esueaza inchis pentru download/generare si vede agregari goale;
- super-adminul fara tenant ramane explicit si nefiltrat, conform foundation layer.

Service boundary limitation:

- `rapoarte/excel_generator.py` si `rapoarte/pdf_generator.py` au primit parametri `tenant_id` doar unde generau agregari fara proiect parinte;
- generatorii si serviciile de dashboard/reporting nu sunt inca security boundaries independente;
- rutele raman boundary-ul principal pentru validarea proiectelor, angajatilor si fisierelor servite;
- serviciile `services/evm.py`, `services/notificari_job.py` si generatoarele de export trebuie tratate ca route-validated pana la un PR de hardening separat.

Ce ramane neprotejat dupa T1.9:

- generatorii project-specific (`foaie_prezenta`, `situatie_proiect`) inca presupun ca ruta a validat proiectul inainte de apel;
- `Raport` nu are `tenant_id` direct, deci istoricul este listat prin generator si accesul punctual prin parametri salvati;
- rapoartele vechi fara `parametri` si fara generator tenant-safe nu sunt vizibile tenantilor in strict mode;
- serviciile de raportare nu au fost extrase intr-un `reporting_service.py`.

Nu s-a adaugat migrare deoarece `Raport` este protejat prin ownership existent (`parametri` + `Utilizator.tenant_id`), iar T1.x nu introduce coloane noi. Nu s-a creat `reporting_service.py` sau `dashboard_service.py` deoarece T1.9 este strict security/access-control; service extraction ar schimba boundary-ul de business si trebuie facuta ulterior.

Urmatorul PR recomandat: `T1.10 Notifications/Admin Tenant Guard`. Daca serviciile de raportare vor fi apelate direct din joburi/API-uri noi, alternativa este `T1.9B Reporting Service Boundary Hardening`.

## Urmatoarele integrari recomandate dupa T1.9

1. `T1.10 Notifications/Admin Tenant Guard` pentru suprafete administrative si notificari ramase.
2. `T1.9B Reporting Service Boundary Hardening` daca generatoarele de rapoarte vor fi apelate direct din afara rutelor.
3. `T1.8B Gantt Service Boundary Hardening` daca serviciile Gantt vor fi apelate direct din afara rutelor.
4. `T1.7B BIM Service Boundary Hardening` daca serviciile BIM vor fi apelate direct din afara rutelor.
5. `T1.5B Contract Service Boundary Hardening` daca serviciile contractuale vor fi apelate direct din afara rutelor.
6. S1.1/S1.2: extragere `activity_service.py` / `timesheet_service.py` dupa ce tenant guard-urile principale sunt stabile.
