# Testing strategy

Acest document descrie strategia de testare a aplicatiei workforce + BIM.

## Quick start

```bash
# Toate unit + integration (rapide, ~15s, no browser)
pytest tests/ --ignore=tests/e2e

# Cu coverage report HTML
pytest tests/ --ignore=tests/e2e --cov --cov-report=html
open htmlcov/index.html

# E2E (necesita Playwright + browser)
pip install pytest-playwright
playwright install chromium
PLAYWRIGHT_E2E=1 pytest tests/e2e/

# Doar testele dintr-un modul
pytest tests/integration/test_workforce_activitati.py -v
```

## Structura

```
tests/
├── conftest.py               # fixtures globale (app, client, admin_user, full_bim_hierarchy, ...)
├── fixtures/
│   ├── data.py               # factory: make_proiect, make_angajat, setup_full_bim_hierarchy
│   └── ifc/
│       └── minimal.ifc       # IFC valid (1.8KB) cu site/building/storey/space/wall/door/AHU
├── unit/                     # 44 teste unit (modele, services, i18n)
│   ├── test_models_workforce.py    # Utilizator, Angajat, Proiect, Pontaj, RaportActivitate
│   ├── test_models_bim.py          # ierarhie BIM, helpers
│   └── test_i18n.py                # t(), get_current_lang
├── integration/              # 110+ teste integration (Flask test client)
│   ├── test_smoke.py               # rute principale, redirect-uri auth
│   ├── test_workforce_activitati.py # CRUD activitate + workflow draft->aprobat
│   ├── test_workforce_export_innova.py # export xlsx structura
│   ├── test_bim_routes.py          # rute /bim/* + IFC + BCF + viewer
│   ├── test_bim_workforce_link.py  # linkare workforce <-> BIM
│   ├── test_bim_data_quality.py    # ExternalMapping + quality reports
│   ├── test_permissions.py         # operator vs admin restrictions
│   └── test_migrations.py          # CLI idempotency
└── e2e/                      # 5 E2E flows critice (opt-in)
    ├── conftest.py                 # server live + Playwright fixtures
    └── test_critical_journeys.py   # login, activitate, export, BIM, search
```

## Pyramid

| Layer | Cont | Tool | Run time |
|---|---:|---|---|
| **Unit** | 44 | pytest, no DB I/O | <1s |
| **Integration** | 121 | pytest + test_client + SQLite tmp | ~12s |
| **E2E** | 5 | Playwright + Chromium | ~30s (opt-in) |
| **TOTAL** | 170 | — | ~15s (fara E2E) |

## Coverage

| Modul | Acoperire |
|---|---:|
| `models.py` | 81% |
| `routes/bim.py` | 80% |
| `routes/dashboard.py` | 82% |
| `routes/activitati.py` | 28% (16h+ feature, dificil de scalat) |
| `services/bim_quality.py` | 70% |
| `services/ifc_import.py` | 21% (necesita lib + IFC real) |
| **Total** | **38%** |

## Fixtures cheie

### `admin_user` / `authenticated_client`
User admin de test + test client autentificat.

### `operator_user` / `operator_client`
La fel pentru operator (testeaza permisiuni).

### `full_bim_hierarchy`
Ierarhie BIM completa: santier > cladire > 3 niveluri > 2 spatii > 2 elemente (AHU, door).
Returneaza dict cu ID-uri.

### `workforce_basic`
1 proiect + 1 angajat de test, returneaza ID-uri.

### `minimal_ifc_path`
Path catre `tests/fixtures/ifc/minimal.ifc` - IFC valid 1.8KB
cu IfcSite, IfcBuilding, IfcBuildingStorey, IfcSpace, IfcWall, IfcDoor, IfcUnitaryEquipment.

### `cleanup_test_data` (autouse)
Sterge automat dupa fiecare test:
- Toate entitatile BIM (santiere, cladiri, niveluri, zone, spatii, elemente, assets, issues, modele, mappings)
- Activitatile cu nume `__*`, `TEST_*`, `SMOKE_*`
- Tenant-urile cu cod `test-*`

## Markers

```python
@pytest.mark.unit       # rapid, no DB
@pytest.mark.integration  # implicit pentru tests/integration
@pytest.mark.e2e        # browser + server real (opt-in via PLAYWRIGHT_E2E=1)
@pytest.mark.slow       # >1s, excluded by default
```

## CI (GitHub Actions)

Template-ul de workflow se afla in `docs/ci-templates/github-actions-test.yml`.

**Instalare** (necesita scope `workflow` pe Personal Access Token):

```bash
mkdir -p .github/workflows
cp docs/ci-templates/github-actions-test.yml .github/workflows/test.yml
git add .github/workflows/test.yml
git commit -m "Add GitHub Actions test workflow"
git push  # PAT cu scope workflow
```

Sau direct prin UI: GitHub repo → Actions → New workflow → paste continutul fisierului.

Workflow-ul are 3 job-uri:

1. **`unit-and-integration`** — Python 3.11 + 3.12 matrix, ruleaza la fiecare push
2. **`validate-bim-cli`** — verifica `flask migrate-bim` + `flask validate-bim --exit-code`
3. **`e2e`** — Playwright, opt-in (commit message contains `[e2e]` sau pull request)

Coverage HTML uploaded ca artifact pe ultima rulare cu Python 3.12.

## Adaugare test nou

1. **Unit test pentru un model property nou**:

   ```python
   # tests/unit/test_models_workforce.py
   def test_proprietate_noua(app):
       from models import Proiect
       with app.app_context():
           p = Proiect(cod_proiect='X', nume='X', data_start=date(2025,1,1))
           assert p.proprietate_noua == ...
   ```

2. **Integration test pentru o ruta noua**:

   ```python
   # tests/integration/test_<modul>.py
   def test_ruta_noua(authenticated_client):
       resp = authenticated_client.get('/ruta/noua')
       assert resp.status_code == 200
   ```

3. **E2E pentru un flow critic** — vezi `tests/e2e/test_critical_journeys.py`

## Best practices

- **Hard-coded fixtures** preferred peste `factory_boy` pana ajungem la 200+ teste cu setup repetat
- **No prod DB**: pytest foloseste SQLite in tmpfile (auto creat/sters)
- **Test isolation**: `cleanup_test_data` autouse curata BIM tabele dupa fiecare test
- **Skip pe deps lipsa**: `ifcopenshell`, `playwright` daca lipsesc, testele relevante sar gracefully
- **Coverage minim per critical path**: 95% pentru auth, export, permissions
