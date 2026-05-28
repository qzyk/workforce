"""
Regression: import IFC leaga elementele de structura spatiala (cladire/nivel).
Fara asta, elementele raman orfane si 4D/5D/clash (filtreaza pe cladire_id) nu le vad.
Foloseste fixture-ul minimal.ifc (are 1 IfcWall continut intr-un IfcBuildingStorey).
"""

from pathlib import Path

MINIMAL = Path(__file__).parent.parent / 'fixtures' / 'ifc' / 'minimal.ifc'


class TestIfcSpatialLinking:
    def test_import_leaga_elementele_de_structura(self, app):
        from services import ifc_import
        from models import ElementBIM
        with app.app_context():
            res = ifc_import.import_ifc(str(MINIMAL))
            assert res['status'] == 'ok', res.get('mesaj')
            # cel putin un element capturat
            elems = ElementBIM.query.all()
            assert elems, 'niciun element importat'
            # peretele e continut in storey -> trebuie legat de nivel + cladire
            pereti = [e for e in elems if e.tip_element == 'wall']
            assert pereti, 'niciun perete importat'
            assert any(p.nivel_id for p in pereti), 'peretele nu e legat de nivel'
            assert any(p.cladire_id for p in pereti), 'peretele nu e legat de cladire'
            # stat de legare expus
            assert res['statistici'].get('elemente_legate', 0) >= 1

    def test_reimport_releaga_orfanii_fara_duplicate(self, app):
        """Re-import: nu duplica elementele + re-leaga orfanii (date vechi)."""
        from services import ifc_import
        from models import db, ElementBIM
        with app.app_context():
            ifc_import.import_ifc(str(MINIMAL))
            n1 = ElementBIM.query.count()
            # simulez date vechi orfane
            for e in ElementBIM.query.all():
                e.cladire_id = None
                e.nivel_id = None
                e.spatiu_id = None
            db.session.commit()
            # re-import
            ifc_import.import_ifc(str(MINIMAL))
            assert ElementBIM.query.count() == n1, 're-importul a duplicat elemente'
            pereti = [e for e in ElementBIM.query.all() if e.tip_element == 'wall']
            assert any(p.nivel_id for p in pereti), 're-importul nu a re-legat peretele'

    def test_dryrun_nu_scrie_dar_numara(self, app):
        from services import ifc_import
        from models import ElementBIM
        with app.app_context():
            inainte = ElementBIM.query.count()
            res = ifc_import.import_ifc(str(MINIMAL), dry_run=True)
            assert res['status'] == 'ok'
            assert res['statistici']['elemente_create'] >= 1
            # dry_run nu scrie nimic
            assert ElementBIM.query.count() == inainte
