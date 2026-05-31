# Edifico Workforce — Feedback & Preferences

> **Auto-loaded** by Claude in every session. Updated 2026-05-17.
> Reads of this file are how I "remember" the user between sessions.

---

## User snapshot

- **Name**: Albert (`@qzyk97` on GitHub, `qzyk97` on PythonAnywhere)
- **Repo**: `github.com/qzyk/workforce` (the app rebrand-ed from "INNOVA" → "Edifico")
- **Production**: `https://www.edifico.space` (PythonAnywhere, paid Developer plan, 1 webapp slot)
- **Local**: macOS, Python 3.14, no `brew`, no LibreOffice, no `gh` CLI
- **PA Python**: 3.11 in venv `workforce-env` at `/home/qzyk97/.virtualenvs/workforce-env`
- **DB**: SQLite on prod (NOT MySQL despite the code supporting it — `DATABASE_URL` env var not set on PA's WSGI)
- **Communication**: Romanian, brief, direct. Says "da" / "merge" / "continua" — minimalist.
- **Tech level**: Mid. Asked "nu ma pricep" when guiding through PA migration. **Needs explicit copy-paste commands**, not just descriptions.

---

## Hard preferences (do these by default)

### Code & language
- **All code text in Romanian**: variable names, table names (`angajati`, `proiecte`, `pontaje`, `santiere`), status values (`activ`, `inactiv`, `deschis`, `inchis`), Jinja templates.
- **Comments and docstrings in Romanian** — match existing style.
- **No accents on identifiers** (`santier` not `șantier`, `cladire` not `clădire`) — easier to type, consistent with existing schema.
- **English allowed only in**: brand names ("Edifico"), tagline ("One platform, all your sites"), foreign technical terms (BIM, IFC, BCF, COBie, RBAC, OpenAPI).

### Workflow
- **PRs and TODOs in repo only** (no Jira/Linear).
- **Phased branches** named `feat/phaseN-<topic>` (we did 8 phases). Each phase = 1 PR = small + shippable.
- **Strict aditiv** — backward compatible always. No giant refactors. Feature flags default OFF.
- **Backup before any DB change** (`scripts/backup_before_alembic.sh`). User explicitly said: "vreau sa pastrez neaparat datele".
- **Show me the plan before touching code** for any new phase. Wait for "da" / "confirm".
- **Self-hosted ethos** — no SaaS dependencies, data stays on user's PA. Open standards (IFC, BCF, COBie, ISO 19650). No vendor lock-in.

### Brand identity (Edifico)
- **Champagne gold** `#C9A961` (with gradient `#E0BB6E → #C9A961 → #A8893D`)
- **Navy obsidian** `#0B1426` (warmer than pure black)
- **Cream** `#F5F1E8` (paper white)
- **Typography**: `Cinzel` (latin imperial serif) for wordmarks/titles + `Inter` (sans) for body
- **Tagline**: "One platform, all your sites"
- **Tone**: premium / lux. User said "fa ceva premium si luxis".
- Logo assets at `static/img/edifico-*.svg` + `static/favicon.svg` + `static/img/pwa/icon-*.png`

### Architecture conventions
- **Flask blueprints** in `routes/` (one file per module: `bim.py`, `angajati.py`, etc.)
- **Single big `models.py`** — don't split it
- **WTForms in `forms/`** (one per module: `angajati_forms.py`)
- **Services in `services/`** for cross-cutting logic (audit, rbac, ifc_import, iot_ingest, etc.)
- **Templates in `templates/<module>/`** following `lista.html`, `formular.html`, `detalii.html` pattern
- **Alembic migrations** numbered `0001`-`0008` (8 done). All strict aditiv. Migration env reads `DATABASE_URL` from `config.Config`.
- **Audit log on everything sensitive** — BIM CRUD, role changes, token rotations, version transitions, etc. (use `services/audit.py`)
- **Multi-tenant ready** — every new BIM table has nullable `tenant_id` FK
- **Feature flags via `services/feature_flags.py`** — catalog of known flags in `KNOWN_FLAGS` dict. UI gates on `feature_enabled('flag-name')` Jinja helper.

### i18n
- **Custom dict** in `i18n.py` (NOT Flask-Babel — user wanted zero new deps)
- **Helper**: `{{ _('Romanian text') }}` in templates, `t('text', 'en')` in Python
- **Lang switcher** in header (flags 🇷🇴🇬🇧) — already in `templates/base.html`
- **EN coverage**: ~95% of `base.html` (sidebar/header/profile) + login + angajati lista/formular + proiecte detalii. Pagini interioare detaliate rămân în RO ca fallback.
- **Extend gradually** — add keys to `TRANSLATIONS` dict + wrap text in templates with `{{ _() }}`. Don't try to translate everything at once.

---

## PythonAnywhere specifics (critical)

These tripped us up — write them down once:

1. **Pip install must be in venv**: `pip install X` în consola Bash globală **NU** ajunge la app-ul Flask. Mereu:
   ```bash
   source ~/.virtualenvs/workforce-env/bin/activate
   pip install X
   deactivate
   ```
   Sau direct: `~/.virtualenvs/workforce-env/bin/pip install X`

2. **Reload required after .py changes**: Web → Reload din UI PA. **Templates** se reîncarcă automat (Jinja auto-reload), `.py` NU.

3. **WSGI vs UI mismatch**: PA UI field "Source code" e doar informativ. WSGI file (`/var/www/qzyk97_pythonanywhere_com_wsgi.py`) e ce contează cu adevărat. Nu te baza pe UI.

4. **No native WebSockets** → SSE cu max 30s stream, client reconnects with `since=<id>`. Faza 7 ne-a obligat la asta.

5. **No TimescaleDB** → MySQL partitioning idea was scrapped; Faza 6 IoT folosește SQLite cu `Integer` PK (NU BigInteger — SQLite nu auto-increment-ează BigInteger).

6. **1 webapp slot** pe Developer plan. Migrare la domain custom = **delete old + create new** (datele rămân pe disk, nu sunt în webapp config).

7. **CNAME `webapp-XXXXXX.pythonanywhere.com`** pentru subdomain (`www.`). Pentru apex (`edifico.space`) folosim URL Redirect Record la Namecheap → `https://www.edifico.space`.

8. **HTTPS Let's Encrypt** gratuit + auto-renew. Force HTTPS toggle ON după setup cert.

9. **GitHub Personal Access Token must have `workflow` scope** ca să poată push fișiere `.github/workflows/*`. Dacă nu, mutăm template-ul în `docs/ci-templates/` ca workaround.

10. **Alembic pe prod e DESINCRONIZAT de schema reală.** Prod era la `0006_iot` în `alembic_version`, dar tabelele 0007–0011 existau deja (create de `db.create_all()` din comenzi CLI, NU prin replay de migrații). Deci `alembic upgrade head` pe prod EȘUEAZĂ cu `table ... already exists`. **Pentru tabele noi pe prod: `db.create_all()` (idempotent, prin `python -c "from app import app; ..."`) + `alembic stamp head` (mută doar pointerul, fără DDL/date). NICIODATĂ `alembic upgrade` pe prod.** `create_all` rulează doar în comenzi CLI (`flask init-db`, `migrate-bim`), NU la Web→Reload — deci tabelele noi trebuie create manual cu snippet-ul de mai sus.

---

## Concrete corrections / "I'd do differently"

### Process
- **Read repo state FIRST** in any new session: `git status`, `git log -5 --oneline`, `git branch`. Don't assume.
- **For multi-step manual user processes** (PA migration, DNS setup): walk user through ONE step at a time, have them paste output, verify before moving on. He explicitly needed this.
- **Check git auth scope** before trying to push workflow files. PAT may lack `workflow` scope.
- **For binary files** like `.pptx`: add `~$*.pptx` and `~$*.docx` to `.gitignore` upfront. Office lock files leak into commits.

### Code patterns to remember
- **SQLite + auto-increment**: always use `db.Integer` for PK, never `BigInteger`. Document inline.
- **Soft-delete UX**: when something gets `data_sfarsit = today`, ensure filter is `IS NULL` not `>= today` (off-by-one — angajatul rămânea afișat o zi).
- **Sed mass-replace for rebrand**: 3 commands case-preserving (UPPER → UPPER, Title → Title, lower → lower). Verify with grep AFTER to confirm zero residuals.
- **Flask URL build errors**: always grep for `url_for('endpoint.name')` after renaming a view function. `proiecte.detaliu` vs `proiecte.detalii` cost us a debug cycle.
- **Token-auth API endpoints**: explicit `csrf.exempt(view_function)` in `app.py` after blueprint register. Don't expect Flask-WTF to skip token routes automatically.
- **For Alembic migrations**: always test `alembic upgrade head` on fresh empty DB AND verify resulting schema == `db.create_all()` schema (parity test).
- **Static files mapping on PA**: configure under Web tab (`/static/` → `/home/qzyk97/workforce/static`) for performance — Flask doesn't need to serve them.

### Tools I should NOT assume are available
- `brew` (no Homebrew on this Mac)
- `soffice` / LibreOffice (no .pptx → PDF conversion possible)
- `gh` CLI (no PR creation from terminal — give user the URL)
- `ifcopenshell` in PA venv (always direct user to `~/.virtualenvs/workforce-env/bin/pip install ifcopenshell`)

### Tools available
- `qlmanage` on Mac (Quick Look — gets first thumbnail of .pptx)
- `Pillow` everywhere (use for image gen instead of Node-based tools)
- `pptxgenjs` via global npm (Node 24 installed)
- `python-pptx` not installed by default; for animations need XML manipulation directly
- `alembic` installed in workforce-env (1.18.4)
- `xeokit-sdk` via ES modules from jsdelivr (no npm bundle needed for Flask)

### UX patterns user appreciated
- **Premium dark + gold splash pages** (login, offline, splash) — go strong on Cinzel typography + gold accents
- **Two-section tables** for soft-deleted items: active (visible) + `<details>` collapsible "Istoric" (history)
- **Re-aloca + Sterge definitiv** buttons in history (re-activate vs hard delete)
- **Flash messages with explanation**: "Angajatul X dezalocat. Apare în tab Istoric și poate fi re-alocat oricând" — explain *what* happened and *how to undo*

### When something "doesn't work" per user report
Always run an audit FIRST before guessing root cause:
- Write a quick integration test that exercises the suspicious flow
- For BIM-wide issues, run `/tmp/bim_audit.py` style script (60 routes status codes)
- Check `/bim/diagnostics` for env state (Python path, libs, flag status)
- Look for off-by-one in filters (`>= today` vs `IS NULL`)
- Look for endpoint name mismatch (Flask BuildError)
- Look for missing template variables (`current_lang`, `today`, `_()`)

---

## Edifico roadmap status (as of 2026-05-17)

| Faza | Tema | Status | Branch |
|---|---|---|---|
| 1 | Foundation: Alembic + audit + flags + CI | **Live prod** | `feat/phase1-foundation` (merge-pending) |
| 2 | 3D Viewer xeokit + APS adapter | Live (branch) | `feat/phase2-viewer` |
| 3 | CDE Workflow + Federation (ISO 19650) | Live (branch) | `feat/phase3-versioning` |
| 4 | Rule Engine + Clash Detection | Live (branch) | `feat/phase4-clash-rules` |
| 5 | 4D Schedule + 5D Cost | Live (branch) | `feat/phase5-4d-5d` |
| 6 | Digital Twin / IoT (sensori, time-series) | Live (branch) | `feat/phase6-digital-twin` |
| 7 | Real-time SSE + Kanban issue board | Live (branch) | `feat/phase7-realtime-kanban` |
| 8 | Governance: RBAC + Tokens + COBie + BCF | Live (branch) | `feat/phase8-governance` |
| — | Rebrand INNOVA → Edifico + brand identity | Live | `rebrand/innova-to-edifico` |
| — | PWA install iOS/Android | Live | `feat/pwa-mobile-install` |
| — | Pitch deck (20 slides PPTX) | Done | `feat/pwa-mobile-install/docs/pitch/` |
| — | Fix santiere + i18n + dezalocare UX + ifcopenshell diag | Live | `fix/angajat-proiect-i18n` |

**8 Alembic migrations** done (`0001_baseline` → `0008_governance`).
**401 teste verzi** (suite-ul complet).
**Domain**: `www.edifico.space` (Let's Encrypt HTTPS forced, namecheap DNS).

---

## Things user explicitly said NO to

- **Another PA subscription** ("nu vreau sa platesc alta subscriptie pe PA") — single webapp slot strategy
- **Custom domain in addition** (deleted old `qzyk97.pythonanywhere.com`, kept only `www.edifico.space`)
- **PostgreSQL on PA** (use SQLite for dev, MySQL ready in code but not migrated yet)
- **Node.js for IFC conversion** (PA has no Node → xeokit via ES module CDN instead)
- **TimescaleDB** (PA limitation → MySQL partitioning idea + Integer PK)

---

## Things user explicitly said YES to

- **Premium luxury branding** — Cinzel + gold + cream
- **Tagline**: "One platform, all your sites"
- **PWA mobile install** (no native iOS/Android apps)
- **Pitch deck cu animații + video export** — chose pptxgenjs + XML manip for transitions
- **Standardele AEC**: ISO 19650, IFC, BCF 2.1, COBie 2.4
- **8 faze BIM** — one PR per phase, feature flags default OFF
- **i18n custom Python dict** (NOT Flask-Babel — zero new deps)

---

## Communication style notes

- **Don't over-explain**. User reads quickly. Bullet points > paragraphs.
- **No emojis in templates / commits** — but OK in chat responses.
- **Use markdown tables** for compare/contrast (he reads them).
- **Show concrete commands** to copy-paste, not pseudo-code.
- **Show test results** as proof of fix ("201/201 verzi", "60 rute auditate, 0 erori 500").
- **Romanian for explanations** when discussing app behavior; English fine for technical jargon.
- **End with**: "Spune-mi după ce testezi" — invite feedback before declaring done.

---

## Quick reference: useful commands

```bash
# On Mac local
PY=/Library/Frameworks/Python.framework/Versions/3.14/bin/python3
$PY -m pytest tests/unit/ tests/integration/test_smoke.py -q   # full quick check
$PY scripts/build_pwa_icons.py                                  # regen PWA icons
$PY scripts/backup_before_alembic.sh                            # DB safety backup

# On PythonAnywhere
cd ~/workforce && git fetch && git checkout <branch>
source ~/.virtualenvs/workforce-env/bin/activate
pip install <lib>      # MUST be in venv
deactivate
# Then: Web → Reload www.edifico.space from PA UI

# Alembic
alembic upgrade head   # apply pending migrations (on fresh DB)
alembic stamp head     # mark existing DB as up-to-date (NO data change)
alembic revision --autogenerate -m "description"

# Audit BIM routes
$PY /tmp/bim_audit.py  # quick health check (60 routes status codes)
```

---

## Open items / future work the user may ask about

- **MySQL migration on PA**: user has the code ready but uses SQLite on prod. `DATABASE_URL` env var in WSGI would trigger MySQL.
- **i18n full coverage**: only ~95% of base.html + login + 2 modules translated. Could extend to all 80 templates.
- **Activate feature flags on prod**: currently all OFF. User needs to activate per-feature via Python REPL in PA.
- **PR merges to main**: most phases are on branches but not merged to main. User pulls from branches directly.
- **APS Viewer real implementation**: Faza 2 has only stub `services/aps_viewer.py`. If user gets APS_CLIENT_ID, finish it.
- **min_clearance rule type**: placeholder in `services/bim_rules.py`. Needs geometric implementation when bbox data available.
