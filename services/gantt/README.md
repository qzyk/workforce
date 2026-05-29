# Planificare Gantt din F3 (modul Edifico)

Genereaza automat o structura de planificare (WBS + activitati + dependente tehnologice)
dintr-o lista de cantitati / deviz (F3) si o exporta catre MS Project / Primavera P6 / CSV.
Elimina legarea manuala a predecesorilor pentru proiecte mari (10.000–100.000+ activitati).

Integrat in aplicatia Flask Edifico (nu e un serviciu separat): blueprint `routes/gantt.py`
+ pachetul de servicii `services/gantt/`. Fara dependinte noi grele — **pur Python + openpyxl**.
`networkx` / `pandas` sunt **acceleratoare optionale** (nu sunt necesare).

## Pipeline

```
F3 (XLSX/CSV) → import → clasificare tehnologica → durate → WBS → dependente → validare → export
```

| Pas | Modul | Ce face |
|-----|-------|---------|
| Import | `import_engine.py` | citire streaming xlsx/csv, auto-detectie antet, mapare coloane, dedup, validare null |
| Clasificare | `clasificare.py` | regex/keyword + fuzzy (difflib), insensibil la diacritice, sinonime, scor de incredere |
| Durate | `durate.py` | `ceil(cantitate / randament_zi)` per categorie (config), minim 1 zi |
| WBS | `wbs.py` | Obiect → Tronson → Categorie → Activitate, ID-uri `1.1.2.3`, niveluri 1..4 |
| Dependente | `dependinte.py` | lant tehnologic FS/SS/FF/SF + decalaj, **replicat pe fiecare tronson**, cu fallback de conectivitate |
| Validare | `validare.py` | cicluri (DFS / networkx), orfani, ID-uri duplicate, predecesori lipsa, tipuri invalide, neclasificate |
| Export | `export.py` | CSV, MS Project 2003 XML, Primavera P6 XML (subset), JSON |
| Orchestrare | `pipeline.py` | `MotorPlanificare` — leaga toti pasii, statistici, timing |

## Performanta

100.000 activitati: pipeline complet **~0.6 s**, export CSV ~0.3 s, export MS Project XML ~2 s
(Python 3.11/3.14, fara pandas/networkx). Clasificatorul are cache pe denumirea normalizata.

## Configurare (externalizata)

Toate regulile de business sunt in `config/gantt/*.json` (JSON sau YAML daca `pyyaml` e instalat).
Daca un fisier lipseste, se folosesc valorile implicite din `config_loader.py`.

- `clasificare.json` — `{CATEGORIE: [cuvinte-cheie]}`
- `dependinte.json` — `ordine_categorii`, `intra_categorie`, `relatii: [{from, to, tip, decalaj}]`
- `setari.json` — `ore_pe_zi`, `randamente` (durate), `coloane` (sinonime antet), `sinonime` (termeni)

## UI

- `GET /gantt/` — pagina de upload F3
- `POST /gantt/genereaza` — upload → pipeline → preview (statistici, WBS, validare, activitati)
- `GET /gantt/export/<token>/<fmt>` — descarca `csv` | `msproject` | `primavera` | `json`

Link in meniu si gating via feature flag **`planificare-gantt`** (vezi mai jos).

## REST API (JSON, stateless — exceptat CSRF)

| Metoda | Ruta | Input | Output |
|--------|------|-------|--------|
| POST | `/gantt/api/import` | multipart `fisier` | `{articole, raport}` |
| POST | `/gantt/api/classify` | `{articole:[...]}` | `{activitati:[...]}` |
| POST | `/gantt/api/generate-wbs` | `{activitati:[...]}` | `{activitati, noduri_wbs}` |
| POST | `/gantt/api/generate-dependencies` | `{activitati:[...]}` | `{activitati, nr_dependente}` |
| POST | `/gantt/api/validate` | `{activitati:[...]}` | raport validare |
| POST | `/gantt/api/export` | `{activitati:[...], format}` | fisier |
| POST | `/gantt/api/pipeline` | multipart `fisier` | rezultat complet |

## Formate de export

- **CSV**: `ID | WBS | Activity Name | Duration | Predecessors | Category | Quantity | UM`
  (predecesori stil MS Project: `12FS`, `12FS+2 days`, `12SS-1 day`)
- **MS Project 2003 XML**: importabil direct (Tasks, OutlineLevel/WBS, PredecessorLink, tipuri 0–3)
- **Primavera P6 XML**: subset compatibil (Project / WBS / Activity / Relationship)
- **JSON**: structura completa (statistici, WBS, activitati, raport)

## Activare (feature flag)

Implicit dezactivat in meniu (convenția Edifico: flag-uri default OFF). Rutele functioneaza la
`/gantt/`. Pentru a afisa link-ul in meniu, activeaza flag-ul `planificare-gantt`:

```python
from services.feature_flags import set_flag
set_flag('planificare-gantt', True)   # global
```

## Date de test

`config/gantt/sample_f3.csv` — retea apa + canalizare, 20 articole, 3 tronsoane.

## Extindere (proiectat pentru viitor)

- clasificare LLM / similaritate semantica: implementeaza o clasa cu `clasifica(denumire)->(cat,scor)`
  si inlocuieste `Clasificator` in `MotorPlanificare`.
- backend pandas/polars pentru import (interfata `importa()` ramane neschimbata).
- `networkx` pentru analize avansate de graf (detectia ciclurilor il foloseste automat daca e instalat).
- normele de productivitate existente (`planificare_bim`) se pot conecta in `durate.py`.
