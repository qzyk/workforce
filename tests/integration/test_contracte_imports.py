"""
Integration tests pentru endpoint-urile de import (Faza 11):
  - POST /contracte/<id>/program/import (MS Project XML)
  - POST /contracte/<id>/oferta/import  (eDevize XML / Excel XLSX)
  - GET  /contracte/program/<id>
  - GET  /contracte/oferta/<id>

Verifica flux end-to-end: upload -> parser -> DB write -> audit.
"""

import io
import os
from datetime import date
from pathlib import Path

import openpyxl
import pytest


FIXTURES_DIR = Path(__file__).parent.parent / 'fixtures' / 'imports'

REAL_MPP_PATH = os.path.expanduser('~/Downloads/GRAFIC TURDA-.mpp')


def _mpp_toolchain_ok() -> bool:
    """True daca jpype + jar-uri MPXJ + un JVM sunt disponibile local."""
    try:
        import jpype  # noqa: F401
    except ImportError:
        return False
    from services.parsers.msproject_mpp_parser import (
        _mpxj_jars, _resolve_jvm_path,
    )
    return bool(_mpxj_jars()) and bool(_resolve_jvm_path()[0])


@pytest.fixture
def flag_on(app):
    """Activeaza ambele flag-uri (modul + import MSP) pe durata testului."""
    from services.feature_flags import set_flag
    with app.app_context():
        set_flag('controale-contract', True, commit=True)
        set_flag('controale-contract-import-msproject', True, commit=True)
    yield
    with app.app_context():
        set_flag('controale-contract', False, commit=True)
        set_flag('controale-contract-import-msproject', False, commit=True)
        # Cleanup entitati Faza 11 + 10 create in teste
        from models import (
            db, PozitieBoQ, OfertaContract, TaskProgram, ProgramReferinta,
            TermenContract, ProcesVerbal, Contract, Proiect,
        )
        PozitieBoQ.query.delete()
        OfertaContract.query.delete()
        TaskProgram.query.delete()
        ProgramReferinta.query.delete()
        TermenContract.query.delete()
        ProcesVerbal.query.delete()
        Contract.query.filter(Contract.parinte_contract_id.isnot(None)).delete()
        Contract.query.delete()
        Proiect.query.filter(Proiect.cod_proiect.like('F11-PRJ-%')).delete()
        db.session.commit()


@pytest.fixture
def contract_f11(app):
    """Proiect + Contract pentru testele Faza 11. Idempotent (re-use if exists)."""
    from models import db, Proiect, Contract
    with app.app_context():
        p = Proiect.query.filter_by(cod_proiect='F11-PRJ-001').first()
        if p is None:
            p = Proiect(cod_proiect='F11-PRJ-001', nume='F11 Test',
                        data_start=date(2025, 1, 1), status='activ')
            db.session.add(p); db.session.commit()
        c = Contract.query.filter_by(proiect_id=p.id,
                                     nr_contract='F11-CTR-001').first()
        if c is None:
            c = Contract(proiect_id=p.id, nr_contract='F11-CTR-001',
                         data_semnare=date(2025, 1, 15), status='activ')
            db.session.add(c); db.session.commit()
        yield {'proiect_id': p.id, 'contract_id': c.id}


# ============================================================
# MS Project XML import
# ============================================================

class TestProgramImport:
    def test_get_form_with_flag_on(self, authenticated_client, flag_on, contract_f11):
        r = authenticated_client.get(
            f'/contracte/{contract_f11["contract_id"]}/program/import'
        )
        assert r.status_code == 200
        assert b'MS Project' in r.data or b'XML' in r.data

    def test_upload_valid_xml_creates_program_and_tasks(
        self, app, authenticated_client, flag_on, contract_f11
    ):
        from models import ProgramReferinta, TaskProgram, AuditLog
        xml_path = FIXTURES_DIR / 'msproject_minimal.xml'
        with open(xml_path, 'rb') as f:
            xml_bytes = f.read()
        r = authenticated_client.post(
            f'/contracte/{contract_f11["contract_id"]}/program/import',
            data={
                'fisier': (io.BytesIO(xml_bytes), 'msproject_minimal.xml'),
            },
            content_type='multipart/form-data',
            follow_redirects=False,
        )
        assert r.status_code in (302, 303), f'Status {r.status_code}, data: {r.data[:500]}'

        with app.app_context():
            programs = ProgramReferinta.query.filter_by(
                contract_id=contract_f11['contract_id']
            ).all()
            assert len(programs) == 1
            prog = programs[0]
            assert prog.versiune == 1
            assert prog.sursa_import == 'msproject_xml'
            # Fixture: 5 taskuri non-root
            tasks = TaskProgram.query.filter_by(program_id=prog.id).all()
            assert len(tasks) == 5
            # Audit
            audits = AuditLog.query.filter_by(
                entity_type='program_referinta', action='create'
            ).all()
            assert len(audits) >= 1

    def test_upload_versioned_increments(
        self, app, authenticated_client, flag_on, contract_f11
    ):
        from models import ProgramReferinta
        xml_path = FIXTURES_DIR / 'msproject_minimal.xml'
        # Primul import
        with open(xml_path, 'rb') as f:
            authenticated_client.post(
                f'/contracte/{contract_f11["contract_id"]}/program/import',
                data={'fisier': (f, 'p1.xml')},
                content_type='multipart/form-data',
            )
        # Al doilea
        with open(xml_path, 'rb') as f:
            authenticated_client.post(
                f'/contracte/{contract_f11["contract_id"]}/program/import',
                data={'fisier': (f, 'p2.xml')},
                content_type='multipart/form-data',
            )
        with app.app_context():
            programs = ProgramReferinta.query.filter_by(
                contract_id=contract_f11['contract_id']
            ).order_by(ProgramReferinta.versiune).all()
            assert len(programs) == 2
            assert [p.versiune for p in programs] == [1, 2]

    def test_upload_rejects_non_xml(self, authenticated_client, flag_on, contract_f11):
        r = authenticated_client.post(
            f'/contracte/{contract_f11["contract_id"]}/program/import',
            data={'fisier': (io.BytesIO(b'not xml'), 'random.txt')},
            content_type='multipart/form-data',
        )
        # Trebuie raspuns 200 cu mesaj flash (nu crash, nu redirect)
        assert r.status_code == 200
        assert b'nepermisa' in r.data or b'Anulare' in r.data

    @pytest.mark.skipif(
        not (os.path.exists(REAL_MPP_PATH) and _mpp_toolchain_ok()),
        reason='Fisier .mpp real sau toolchain MPXJ/JVM absent - test optional',
    )
    def test_upload_real_mpp_creates_program(
        self, app, authenticated_client, flag_on, contract_f11
    ):
        """Upload .mpp real -> MPXJ -> MSPDI -> program + taskuri + audit."""
        from models import ProgramReferinta, TaskProgram
        with open(REAL_MPP_PATH, 'rb') as f:
            mpp_bytes = f.read()
        r = authenticated_client.post(
            f'/contracte/{contract_f11["contract_id"]}/program/import',
            data={'fisier': (io.BytesIO(mpp_bytes), 'GRAFIC TURDA-.mpp')},
            content_type='multipart/form-data',
            follow_redirects=False,
        )
        assert r.status_code in (302, 303), f'Status {r.status_code}, data: {r.data[:500]}'
        with app.app_context():
            prog = ProgramReferinta.query.filter_by(
                contract_id=contract_f11['contract_id'],
                sursa_import='msproject_mpp',
            ).first()
            assert prog is not None
            tasks = TaskProgram.query.filter_by(program_id=prog.id).all()
            assert len(tasks) > 100  # GRAFIC TURDA ~208 taskuri

    def test_flag_msp_off_blocks_import(
        self, app, authenticated_client, contract_f11
    ):
        """Cu doar 'controale-contract' on dar 'import-msproject' off -> redirect cu warning."""
        from services.feature_flags import set_flag
        with app.app_context():
            set_flag('controale-contract', True, commit=True)
            set_flag('controale-contract-import-msproject', False, commit=True)
        try:
            r = authenticated_client.get(
                f'/contracte/{contract_f11["contract_id"]}/program/import',
                follow_redirects=False,
            )
            assert r.status_code in (302, 303)
        finally:
            with app.app_context():
                set_flag('controale-contract', False, commit=True)

    def test_program_detalii_view(
        self, app, authenticated_client, flag_on, contract_f11
    ):
        from models import db, ProgramReferinta
        with app.app_context():
            p = ProgramReferinta(
                proiect_id=contract_f11['proiect_id'],
                contract_id=contract_f11['contract_id'],
                versiune=1, denumire='Test Program',
                data_emitere=date(2025, 1, 20),
                sursa_import='manual',
            )
            db.session.add(p); db.session.commit()
            pid = p.id
        r = authenticated_client.get(f'/contracte/program/{pid}')
        assert r.status_code == 200
        assert b'Test Program' in r.data


# ============================================================
# eDevize XML / Excel import
# ============================================================

class TestOfertaImport:
    def test_get_form(self, authenticated_client, flag_on, contract_f11):
        r = authenticated_client.get(
            f'/contracte/{contract_f11["contract_id"]}/oferta/import'
        )
        assert r.status_code == 200
        assert b'eDevize' in r.data or b'Excel' in r.data

    def test_upload_edevize_xml(self, app, authenticated_client, flag_on, contract_f11):
        from models import OfertaContract, PozitieBoQ, AuditLog
        xml_path = FIXTURES_DIR / 'edevize_minimal.xml'
        with open(xml_path, 'rb') as f:
            r = authenticated_client.post(
                f'/contracte/{contract_f11["contract_id"]}/oferta/import',
                data={
                    'tip_parser': 'edevize_xml',
                    'fisier': (f, 'edevize.xml'),
                },
                content_type='multipart/form-data',
                follow_redirects=False,
            )
        assert r.status_code in (302, 303), f'Status {r.status_code}'
        with app.app_context():
            oferte = OfertaContract.query.filter_by(
                contract_id=contract_f11['contract_id']
            ).all()
            assert len(oferte) == 1
            of = oferte[0]
            assert of.sursa_import == 'edevize_xml'
            pozitii = PozitieBoQ.query.filter_by(oferta_id=of.id).all()
            assert len(pozitii) == 5
            audits = AuditLog.query.filter_by(
                entity_type='oferta_contract', action='create'
            ).all()
            assert len(audits) >= 1

    def test_upload_edevize_pdf(self, app, authenticated_client, flag_on, contract_f11, tmp_path):
        """Upload PDF eDevize sintetic -> creeaza OfertaContract + PozitieBoQ-uri."""
        from tests.fixtures.imports.build_sample_edevize_pdf import build_sample_pdf
        from models import OfertaContract, PozitieBoQ
        pdf_path = build_sample_pdf(str(tmp_path / 'edevize_test.pdf'))

        with open(pdf_path, 'rb') as f:
            r = authenticated_client.post(
                f'/contracte/{contract_f11["contract_id"]}/oferta/import',
                data={
                    'tip_parser': 'edevize_pdf',
                    'fisier': (f, 'deviz.pdf'),
                },
                content_type='multipart/form-data',
                follow_redirects=False,
            )
        assert r.status_code in (302, 303), f'Status {r.status_code}, data: {r.data[:500]}'
        with app.app_context():
            oferte = OfertaContract.query.filter_by(
                contract_id=contract_f11['contract_id'], sursa_import='edevize_pdf'
            ).all()
            assert len(oferte) == 1
            pozitii = PozitieBoQ.query.filter_by(oferta_id=oferte[0].id).all()
            # Fixture sintetic are 5 articole
            assert len(pozitii) == 5
            # Verific ca sufixele speciale sunt pastrate
            codes = {p.cod_articol for p in pozitii}
            assert 'CR06A%' in codes
            assert 'CK03B02^' in codes

    def test_upload_excel_xlsx(self, app, authenticated_client, flag_on, contract_f11, tmp_path):
        from models import OfertaContract, PozitieBoQ
        # Construiesc XLSX inline
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(['cod', 'cap', 'denumire', 'um', 'cant', 'pret', 'cat'])
        ws.append(['A01', 'A', 'Articol 1', 'mc', 100, 50, 'materiale'])
        ws.append(['A02', 'A', 'Articol 2', 'kg', 50, 10, 'manopera'])
        xlsx_path = tmp_path / 'boq.xlsx'
        wb.save(xlsx_path)

        with open(xlsx_path, 'rb') as f:
            r = authenticated_client.post(
                f'/contracte/{contract_f11["contract_id"]}/oferta/import',
                data={
                    'tip_parser': 'excel_xlsx',
                    'fisier': (f, 'boq.xlsx'),
                },
                content_type='multipart/form-data',
                follow_redirects=False,
            )
        assert r.status_code in (302, 303)
        with app.app_context():
            oferte = OfertaContract.query.filter_by(
                contract_id=contract_f11['contract_id'], sursa_import='excel_xlsx'
            ).all()
            assert len(oferte) == 1
            pozitii = PozitieBoQ.query.filter_by(oferta_id=oferte[0].id).all()
            assert len(pozitii) == 2

    def test_oferta_detalii_view(self, app, authenticated_client, flag_on, contract_f11):
        from models import db, OfertaContract
        with app.app_context():
            o = OfertaContract(
                contract_id=contract_f11['contract_id'],
                proiect_id=contract_f11['proiect_id'],
                versiune=1, data_emitere=date(2025, 1, 1),
                sursa_import='manual',
            )
            db.session.add(o); db.session.commit()
            oid = o.id
        r = authenticated_client.get(f'/contracte/oferta/{oid}')
        assert r.status_code == 200


# ============================================================
# Flag OFF cu import - tot modulul 404
# ============================================================

def test_program_import_404_with_flag_off(authenticated_client, contract_f11):
    """Cu flag-ul principal off, endpoint-urile import sunt 404."""
    r = authenticated_client.get(
        f'/contracte/{contract_f11["contract_id"]}/program/import'
    )
    assert r.status_code == 404
