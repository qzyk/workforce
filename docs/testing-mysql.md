# MySQL testing strategy

Acest document descrie cum sa testezi compatibilitatea aplicatiei workforce cu MySQL,
in continuarea migrarii de la PostgreSQL la MySQL.

## Quick start

### Local — fara MySQL

Toate testele MySQL skip elegant:

```
pytest tests/ --ignore=tests/e2e
# 190 passed, 31 skipped (cele cu @pytest.mark.mysql)
```

### Local — cu MySQL via Docker

```
# 1. Porneste MySQL test container
docker compose -f docker-compose.test.yml up -d

# 2. Asteapta sa fie ready (~15s) si exporta URL-ul
export MYSQL_TEST_URL='mysql+pymysql://workforce:workforce_pass@127.0.0.1:3307/workforce_test'

# 3. Ruleaza testele MySQL specifice
pytest tests/integration/test_mysql_compatibility.py -v
pytest tests/integration/test_mysql_query_semantics.py -v
pytest tests/integration/test_mysql_migration_script.py -v

# 4. Re-ruleaza testele existente sub MySQL (via subprocess wrapper)
pytest tests/integration/test_mysql_existing_suite_runner.py -v -s

# 5. Cleanup
docker compose -f docker-compose.test.yml down -v
```

### Local — toate testele (SQLite + MySQL)

```
docker compose -f docker-compose.test.yml up -d
export MYSQL_TEST_URL='mysql+pymysql://workforce:workforce_pass@127.0.0.1:3307/workforce_test'

pytest tests/ --ignore=tests/e2e -v
# 190 passed (SQLite) + 28 passed (MySQL specific) + 8 dual-mode wrappers
```

## Structura testelor MySQL

| Fisier | Tip | Cont | Scop |
|---|---|---:|---|
| `tests/integration/test_mysql_compatibility.py` | P1 | 13 | Boolean/Datetime/Decimal/JSON Unicode roundtrip + UNIQUE + CASCADE + NULL |
| `tests/integration/test_mysql_query_semantics.py` | P2 | 8 | Case sensitivity, ILIKE, GROUP BY strict, ORDER BY, LIMIT, NULL in IN |
| `tests/integration/test_mysql_migration_script.py` | P1 | 4 | E2E migration SQLite -> MySQL cu 50+ randuri sample |
| `tests/integration/test_mysql_existing_suite_runner.py` | dual-mode | 8 | Re-ruleaza cele 190 teste existente pe MySQL via subprocess |
| `tests/e2e/test_critical_journeys_mysql.py` | E2E | 5 | Login + CRUD + Export EDIFICO + BIM dashboard pe MySQL real |

**Total**: ~36 teste noi specifice MySQL (skip default fara `MYSQL_TEST_URL`)

## Riscuri PostgreSQL -> MySQL acoperite

| Risc | Test |
|---|---|
| Boolean: TINYINT(1) ↔ Python bool | `test_bool_true`, `test_bool_false`, `test_bool_filter_query` |
| Datetime: microseconds, default utcnow, onupdate | `test_datetime_*` |
| Decimal precision (10,2) si (12,2) | `test_decimal_*` |
| Unicode + emoji in TEXT (JSON) | `test_json_text_unicode_emoji`, `test_subordonati_ids_json_text` |
| Diacritice romanesti utf8mb4 | `test_varchar_diacritice` |
| UNIQUE cu NULL | `test_unique_*` |
| FK CASCADE InnoDB | `test_cascade_delete_santier` |
| Email login case-insensitive | `test_email_lookup_case_insensitive` |
| LIKE search in /bim/api/search | `test_like_search_case_insensitive`, `test_ilike_works_on_mysql` |
| GROUP BY ONLY_FULL_GROUP_BY | `test_count_distinct_in_quality_report`, `test_quality_report_route_no_group_by_error` |
| ORDER BY collation diacritice | `test_order_by_diacritice` |
| LIMIT/OFFSET pagination | `test_limit_n` |
| NOT IN cu NULL | `test_not_in_excludes_null` |
| Migration end-to-end | `test_migration_full_pipeline`, `test_migration_preserves_data`, `test_migration_idempotent` |
| AUTO_INCREMENT post-migrare | `test_auto_increment_after_migration` |

## Skip mechanism (autouse + marker mysql)

In `tests/conftest.py`:

```python
def pytest_collection_modifyitems(config, items):
    """Skip teste @pytest.mark.mysql daca MYSQL_TEST_URL lipseste."""
    if _mysql_available():
        return
    skip_mysql = pytest.mark.skip(reason='MYSQL_TEST_URL nu e setat')
    for item in items:
        if 'mysql' in item.keywords:
            item.add_marker(skip_mysql)
```

Asta inseamna ca pe dev local fara MySQL, suite-ul ramane verde si rapid.

## CI cu GitHub Actions

Workflow-ul (`docs/ci-templates/github-actions-test.yml`) are 4 job-uri:

1. **`unit-and-integration-sqlite`** — Python 3.11 + 3.12 matrix, ruleaza pe SQLite default.
2. **`unit-and-integration-mysql`** — Python 3.12 cu service container `mysql:8.0`,
   ruleaza testele MySQL specifice + dual-mode runner.
3. **`validate-bim-cli`** — verifica `flask migrate-bim` + `flask validate-bim --exit-code`.
4. **`e2e`** — Playwright opt-in (commit message contains `[e2e]` sau pull_request).

Pentru a activa:

```bash
mkdir -p .github/workflows
cp docs/ci-templates/github-actions-test.yml .github/workflows/test.yml
git add .github/workflows/test.yml
git commit -m "Activate GitHub Actions test workflow"
git push  # PAT cu scope workflow
```

## Caveats MySQL specifice (descoperite/preventive)

### 1. utf8mb4 + indecsi lungi (1071 Specified key was too long)

InnoDB are limita 3072 bytes pe index. Cu utf8mb4 (4 bytes/char), `VARCHAR(800)` indexat
ar fi 3200 bytes -> eroare. **Mitigare**: in models.py, indecsii sunt pe campuri
<= 200 chars (= 800 bytes utf8mb4). OK.

### 2. ONLY_FULL_GROUP_BY

MySQL 5.7+ default. Toate query-urile cu GROUP BY trebuie sa aiba toate coloanele
SELECT in GROUP BY sau in functii agregate. **Acoperit prin** `test_quality_report_route_no_group_by_error`.

### 3. DATETIME fara fractional seconds

MySQL 5.7 DATETIME default precision = 0 (drop microseconds). Pentru aplicatia noastra
nu e o problema (folosim doar pana la secunda). **Acoperit prin** `test_datetime_microseconds_preserved`
care doar verifica valori la nivel de secunda.

### 4. Connection drop dupa idle

PA inchide conexiuni MySQL idle dupa ~5 min. **Mitigare**: `pool_pre_ping=True` +
`pool_recycle=280` setat in `config.py` cand URL contine 'mysql'.

### 5. Empty string vs NULL

Atat MySQL cat si PG trateaza `''` si `NULL` diferit. Form-urile Flask trimit `''`
care rezulta in string gol in DB (nu NULL). Comportament consistent cu PG. OK.

### 6. AUTO_INCREMENT vs sequences

MySQL gestioneaza automat. Dupa migrare cu IDs explicite, scriptul reseteaza cu
`ALTER TABLE ... AUTO_INCREMENT = max(id)+1`. **Acoperit prin** `test_auto_increment_after_migration`.

### 7. Reserved words

Numele de coloane ca `data` (DATE-like in unele dialecte) — verificat, nu e reserved
in MySQL 8.0. OK.

## Cum interpretezi un fail in CI

Daca job-ul `unit-and-integration-mysql` esueaza:

1. **Test din `test_mysql_compatibility.py`** — bug data integrity, atentie. Rezolva
   inainte de a deploy-ui pe productie MySQL.
2. **Test din `test_mysql_query_semantics.py`** — diferenta dialect. Verifica
   query-ul SQLAlchemy pentru cross-dialect compat.
3. **Test din `test_mysql_existing_suite_runner.py`** — un suite mai vechi nu merge
   pe MySQL. Verifica subprocess output pentru testul exact.
4. **Test din `test_mysql_migration_script.py`** — script-ul `migrate-to-mysql` nu
   transfera corect datele. Verifica sample data + AUTO_INCREMENT.

## Roadmap (post-foundation)

Pe masura ce app-ul creste, sugerez:

- **Performance testing** — bulk insert 10k rânduri, pagination peste 100k records
- **Concurrent writes** — 2+ requests simultane, lock conflicts
- **Stress test conexiuni** — pool exhaustion (50+ conexiuni)
- **Backup/restore E2E** — `mysqldump` + restore pe alt MySQL
- **Schema migration tools** — Alembic in loc de `db.create_all()`
