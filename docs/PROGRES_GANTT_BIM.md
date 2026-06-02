# Progres sesiune — modul Gantt + conexiuni BIM/cost (Edifico)

> Rezumat al lucrului din aceasta sesiune lunga. Stack: Flask 3 + SQLAlchemy +
> Jinja + WTForms, Python 3.14, SQLite, prod pe PythonAnywhere.
> Branch de lucru: `fix/export-rapoarte-stilizat` (consolidat in `main`).
> Stare: **696 teste verzi**, totul pe `main`.

## 1. Modulul Planificare Gantt (F3 -> program + cost)

| Faza | Ce |
|---|---|
| Import tolerant | multi-sheet, antet pe orice rand, detectie format pe magic bytes (.xls binar / HTML / SpreadsheetML deghizat), mapare coloane pe scor, `cod` optional, filtrare randuri pret/total/NOTA |
| F2 — config in DB | migratia **0012**: `gantt_sinonim_coloana`, `gantt_clasificare_regula`, `gantt_relatie_template`, `gantt_profil_mapare`. Overlay DB-suprascrie-JSON (fallback la JSON). Wizard de mapare care invata (profiluri pe semnatura antet). Admin `/gantt/config` (sinonime / reguli / tarife / profiluri, audit-logat) |
| F3 — dictionar | calibrat pe devize reale (81.5% gresit -> **97.9% corect**); categorii noi (ARMATURI, OBIECTE_SANITARE, IZOLATII, DEMONTARI, TRANSPORT, APARATURA_AMC); clasificare pe **prefix de cod** (indicativ eDevize) |
| 5D — cost | tarife lei/UM pe categorie (`tarife_categorie` disciplina='gantt'), descompunere material/manopera, curba S |
| 4D — vizual | diagrama Gantt (frappe-gantt) + drum critic (forward/backward pass), date lucratoare |
| Randamente | editabile din admin (`disciplina='gantt-randament'`) -> regleaza duratele |
| Faza 6 — planuri | migratia **0013** `gantt_plan`: salvezi planuri pe proiect, re-rulezi pipeline la deschidere, export |

## 2. Fix-uri

- **CSRF** „Bad Request — session token missing": sesiune expirata (hard-refresh). Hardening `session.permanent` flaguit ca task separat.
- **Notificari** (2 teste pre-existente): idempotenta compara `date.today()` local cu `data_creare` UTC -> in UTC+N dimineata duplica. Fix: fereastra pe `utcnow().date()`.

## 3. Conexiuni reale (roadmap, lucrat autonom noaptea)

| # | Conexiune | Detaliu |
|---|---|---|
| 4D pe BIM | punte Gantt -> `bim_task_schedules` + player in viewer xeokit (coloreaza elemente pe GlobalId in timp). **Verificat pe IFC reale** (Hala Fundeni, structurale): reparat link element->nivel la import + mod **auto-secventiere** (independent de categorii) |
| #2 Proiect 360 | `/proiecte/<id>/hub` — agrega contracte/oferte/Gantt/situatii/angajati/documente/BIM |
| #3 EVM | `/proiecte/<id>/evm` — PV (curba S) vs EV/AC (situatii) -> SPI/CPI; **+ manopera reala din pontaje** (ore x tarif) |
| #4 5D real | cost activitati din `pozitii_boq` (match cod -> denumire), nu tarife plate |
| #5 IFC -> QTO | antemasuratoare din model -> CSV F3 -> upload in Gantt/deviz (inchide bucla) |
| proiecte<->santiere | migratia **0014** `proiect_santier` (many-to-many) |

## 4. Migratii noi (toate strict aditiv)

- **0012** gantt config (4 tabele) · **0013** `gantt_plan` · **0014** `proiect_santier`
- Pe prod: `db.create_all()` + `alembic stamp head` (NU `upgrade` — schema gestionata de create_all; vezi CLAUDE.md #10).

## 5. De facut / in lucru

- **Tema A (in curs):** dashboard executiv cross-modul + navigare/activare flag-uri BIM.
- Teme B-E recomandate: alerte proactive (EVM/termene), hardening CSRF, finisaj stub-uri (APS/min_clearance), IFC mare async, QTO geometric, i18n complet, CI verde, backup automat.
- Deploy pe PA al tuturor pieselor (git pull + create_all/stamp pentru 0013/0014 + sync gantt config + reload).
