# BIM Data Integration & Quality

Acest document descrie strategia de integrare a workforce-app cu sisteme BIM externe
și mecanismele de asigurare a calității datelor.

## Identificatori cross-system

Fiecare entitate BIM expune **trei niveluri de identificatori**:

| Nivel | Coloană | Folosire |
|---|---|---|
| **Intern** | `id` (PK) | În workforce-app, niciodată exportat |
| **Cod uzual** | `cod` | Citit de utilizatori (ex: `AHU-03`, `BLD-A`, `N00`) |
| **External** | `extern_id` + `source_system` | Stable ID din IFC/Revit/Trimble/etc. |

Plus, `ElementBIM` are un câmp dedicat: `ifc_global_id` (specific IFC).

### De ce `(extern_id, source_system)` și nu doar `extern_id`?

Același obiect fizic poate exista în mai multe sisteme cu ID-uri diferite:
- în IFC: GUID `1Wy_z3K2FBgAAAAAAAA0gP` (IfcWall.GlobalId)
- în Revit: `123456` (ElementId)
- în Trimble Connect: `obj-abc-789`

Cu perechea `(source_system, extern_id)` ne asigurăm că putem face lookup invers
într-o singură interogare, și nu confundăm un GUID din Revit cu unul din IFC.

## Tabelul `bim_external_mappings`

Pentru cazurile **multi-system** (același element în 3-4 sisteme externe simultan),
avem un tabel polymorphic:

```sql
CREATE TABLE bim_external_mappings (
    id INTEGER PRIMARY KEY,
    tenant_id INTEGER REFERENCES tenants(id),
    entity_type VARCHAR(30) NOT NULL,  -- 'element_bim', 'spatiu', 'santier', ...
    entity_id INTEGER NOT NULL,
    source_system VARCHAR(30) NOT NULL,
    extern_id VARCHAR(200) NOT NULL,
    model_bim_id INTEGER REFERENCES bim_modele(id),
    metadata_json TEXT,
    last_synced_at DATETIME,
    data_creare DATETIME,
    UNIQUE (entity_type, entity_id, source_system, extern_id)
);

CREATE INDEX ix_extmap_lookup ON bim_external_mappings (source_system, extern_id);
CREATE INDEX ix_extmap_entity ON bim_external_mappings (entity_type, entity_id);
```

### Exemplu workflow integrare

```python
from models import db, ElementBIM, ExternalMapping

# La import din IFC
e = ElementBIM(cod='AHU-03', tip_element='AHU', ifc_global_id='1Wy_z3...')
db.session.add(e); db.session.flush()

ExternalMapping.add_or_update(
    entity_type='element_bim', entity_id=e.id,
    source_system='ifc', extern_id='1Wy_z3...',
    metadata={'source_file': 'building_a.ifc', 'ifc_class': 'IfcUnitaryEquipment'},
)

# Mai târziu, sincronizare cu Revit (același obiect)
ExternalMapping.add_or_update(
    entity_type='element_bim', entity_id=e.id,
    source_system='revit', extern_id='123456',
    metadata={'family': 'Daikin VRV', 'project_url': 'rvt://...'},
)

# Lookup invers (de la Revit ID la entitate workforce)
et, eid = ExternalMapping.find_entity('revit', '123456')
assert et == 'element_bim' and eid == e.id

db.session.commit()
```

## API endpoints pentru integrare

| Endpoint | Metoda | Scop |
|---|---|---|
| `/bim/api/external-mapping` | GET | Lookup invers `?source_system=X&extern_id=Y` |
| `/bim/api/external-mapping` | POST | Adaugă/actualizează mapping |
| `/bim/api/elemente/catalog` | GET | Export complet catalog elemente cu mapping-uri |
| `/bim/api/quality` | GET | JSON cu raport de calitate (admin only) |

## Validare cross-entity

`ElementBIM.validation_warnings` returnează lista de avertismente:

| Warning | Cauză |
|---|---|
| `Spatiu si nivel din locatii diferite` | `element.spatiu.nivel_id != element.nivel_id` |
| `Spatiu si cladire mismatch` | `element.spatiu.nivel.cladire_id != element.cladire_id` |
| `Nivel si cladire mismatch` | `element.nivel.cladire_id != element.cladire_id` |
| `Element importat din IFC fara GlobalId` | `source_system == 'ifc' and ifc_global_id IS NULL` |

Un element ideal:
```python
element.validation_warnings == []
```

## Service `bim_quality`

`services/bim_quality.py` expune funcția `run_all_reports()` care rulează:

1. **`elemente_fara_ifc_guid`** — elemente importate IFC fără GlobalId (probabil import incomplet)
2. **`elemente_orfane`** — fără context spațial (cladire/nivel/spatiu)
3. **`elemente_inconsistente`** — cu warnings cross-entity
4. **`activitati_link_inconsistent`** — task workforce cu BIM links din clădiri diferite
5. **`duplicate_extern_id`** — același IFC GUID folosit de 2+ entități
6. **`mappings_orfane`** — `ExternalMapping` către entități șterse
7. **`elemente_nesincronizate`** — IFC elements neresincronizate de >30 zile

### Rulare

**Web UI**: `/bim/quality` (admin only)

**CLI**:
```bash
flask validate-bim
flask validate-bim --exit-code  # iese cu cod 1 daca exista probleme severe
```

Util pentru:
- CI/CD: blochează deploy dacă `--exit-code` returnează 1
- Cron: rulare zilnică cu rezumat email

## Migration strategy

### Pași incrementali (idempotenți)

```bash
# 1. Migrare schema BIM (creează tabele + adaugă FK + extern_id/source_system pe toate)
flask migrate-bim

# 2. Validare imediat după migrare (verifică integritatea)
flask validate-bim
```

### Mapare entități workforce existente la BIM

Scenariu: ai 60 angajați + 9 proiecte deja în DB. Vrei să le legi cu BIM:

**Step 1** — Creezi șantierele manual sau importi IFC:
```bash
flask migrate-bim
# UI: BIM → Șantier nou → asociezi cu Proiect existent
# SAU: BIM → Import IFC → creează automat Santier + Cladire + ...
```

**Step 2** — Activitățile existente rămân **fără linkuri BIM** (toate FK BIM = NULL).
Aplicația funcționează identic.

**Step 3** — Treptat, utilizatorii editează activități și completează `Context BIM` în formular.

**Step 4** — Pentru sincronizări automate (workforce ↔ Revit/Trimble):
- POST către `/bim/api/external-mapping` la fiecare sincronizare
- Cron job care rulează `flask validate-bim` zilnic

### Rollback

Dacă apar probleme post-deploy:

```bash
# 1. Restaurare DB din backup
cp ~/workforce_safe_<timestamp>/workforce.db ~/workforce/database/

# 2. Revert cod
git checkout main && git reset --hard origin/main

# 3. Reload WSGI
touch /var/www/<user>_pythonanywhere_com_wsgi.py
```

Tabelele `bim_*` și `bim_external_mappings` rămân în DB dar nu mai produc efect
fără cod. Pot fi șterse manual cu `DROP TABLE` dacă e nevoie (ireversibil — pierdere date BIM).

## Constraint-uri DB pentru integritate

### Existente (active)

```sql
-- Unicitate cod per parinte
UNIQUE (santier_id, cod) ON bim_cladiri
UNIQUE (cladire_id, cod) ON bim_niveluri
UNIQUE (cladire_id, cod) ON bim_zone
UNIQUE (nivel_id, cod) ON bim_spatii

-- Asset 1:1 cu ElementBIM
UNIQUE (element_bim_id) ON bim_assets

-- ExternalMapping no-duplicate
UNIQUE (entity_type, entity_id, source_system, extern_id)

-- Cascade delete
ON DELETE CASCADE: santier->cladiri->niveluri->spatii
```

### De adăugat ulterior (app-level validation)

Aceste reguli **nu** sunt enforced la nivel de DB (prea restrictiv pentru sistem
multi-source). În schimb, sunt verificate prin `bim_quality`:

- `RaportActivitate.element_bim` și `RaportActivitate.spatiu` trebuie să fie din aceeași clădire
- `RaportActivitate.proiect_id` ar trebui să se potrivească cu `element_bim.cladire.santier.proiect_id` (când e setat)
- Element nu poate fi setat fără cel puțin o coordonată spațială (cladire / nivel / spatiu)

Recomandare: rulează `flask validate-bim` zilnic + monitorizează `/bim/quality` în UI.

## Hooks pentru import/export viitor

### Import hook tipic (Python)

```python
def import_revit_model(rvt_file_path, santier_id):
    # 1. Parser Revit (pyRevit, RevitAPI, sau open-source)
    revit_data = parse_revit(rvt_file_path)
    
    # 2. Map la entitățile noastre + creează ExternalMapping
    for revit_element in revit_data['elements']:
        # Lookup: există deja in DB?
        et, eid = ExternalMapping.find_entity('revit', revit_element.id)
        if et:
            # Update existent
            element = ElementBIM.query.get(eid)
        else:
            # Create new
            element = ElementBIM(
                cod=revit_element.code,
                tip_element=map_revit_to_ifc_type(revit_element.category),
                source_system='revit',
                extern_id=revit_element.id,
                last_synced_at=datetime.utcnow(),
            )
            db.session.add(element)
            db.session.flush()
            ExternalMapping.add_or_update(
                entity_type='element_bim', entity_id=element.id,
                source_system='revit', extern_id=revit_element.id,
                metadata={'family': revit_element.family},
            )
    db.session.commit()
```

### Export hook BCF (deja implementat)

Issues BIM se exportă ca fișier `.bcf` (BIM Collaboration Format) compatibil cu
Solibri/BIMcollab/Navisworks: `GET /bim/export/bcf`.

### Webhook viitor (recomandare)

Pentru sincronizare bidirectionala:

```python
@bim_bp.route('/webhook/<source_system>/elements', methods=['POST'])
def webhook_external_change(source_system):
    """Apelat de sistemul extern cand un element s-a modificat."""
    data = request.get_json()
    extern_id = data['id']
    et, eid = ExternalMapping.find_entity(source_system, extern_id)
    if not et:
        return {'status': 'unknown'}, 404
    # Update last_synced_at
    if et == 'element_bim':
        e = ElementBIM.query.get(eid)
        e.last_synced_at = datetime.utcnow()
        db.session.commit()
    return {'status': 'ok'}
```

## Concluzii

Această schemă oferă:
- **Identificatori stabili** prin `extern_id + source_system` și `ifc_global_id`
- **Multi-system** prin `bim_external_mappings`
- **Audit trail** prin `last_synced_at`
- **Validare cross-entity** prin `validation_warnings` și `bim_quality`
- **Migrare sigură** prin CLI idempotent
- **Reports admin** prin `/bim/quality` și `flask validate-bim`

Următoarele etape (în afara cadrului foundation):
- Worker pentru import IFC asincron (pentru fișiere mari)
- Webhook pentru sincronizare bidirectională cu Trimble/Revit
- Versionare modele (când Revit-ul se actualizează, păstrăm istoric)
- Integrare BCF cu round-trip (export issues → workflow extern → import înapoi)
