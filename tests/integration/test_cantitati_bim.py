"""
Faza 1 auto-pricing: extragere cantitati (Qto + fallback geometric) + material.
Test puternic = opt-in pe ModelRVT26 (are geometrie + material).
"""
import os
from pathlib import Path

import pytest

MINIMAL = Path(__file__).parent.parent / 'fixtures' / 'ifc' / 'minimal.ifc'
RVT = os.path.expanduser('~/Downloads/ModelRVT26_HalaFundeni.ifc')


class TestCantitatiBim:
    def test_extrage_graceful(self, app):
        """Serviciul ruleaza fara crash + status ok (chiar daca minimal.ifc n-are geometrie)."""
        from services import ifc_import, cantitati_bim
        from models import db, ModelBIM
        with app.app_context():
            ifc_import.import_ifc(str(MINIMAL))
            m = ModelBIM(nume='min', tip='ifc', fisier_path=str(MINIMAL))
            db.session.add(m); db.session.commit()
            res = cantitati_bim.extrage_cantitati(m.id)
            assert res['status'] == 'ok'
            assert 'stats' in res

    def test_model_inexistent_eroare(self, app):
        from services import cantitati_bim
        with app.app_context():
            assert cantitati_bim.extrage_cantitati(999999)['status'] == 'eroare'


@pytest.mark.skipif(not os.path.exists(RVT), reason='ModelRVT26 absent - test optional')
class TestCantitatiReal:
    def test_geom_si_material(self, app):
        from services import ifc_import, cantitati_bim
        from models import db, ModelBIM, ElementBIM
        with app.app_context():
            imp = ifc_import.import_ifc(RVT)
            m = ModelBIM(nume='RVT26', tip='ifc',
                         santier_id=imp['santier_id'], fisier_path=RVT)
            db.session.add(m); db.session.commit()
            res = cantitati_bim.extrage_cantitati(m.id)
            assert res['status'] == 'ok', res['mesaj']
            assert res['stats']['din_geom'] > 50, res['stats']
            cu_cant = ElementBIM.query.filter(ElementBIM.cantitate.isnot(None)).count()
            assert cu_cant > 50
            # material extras la import (Beton C25/30, S355, BST500s...)
            assert ElementBIM.query.filter(ElementBIM.material.isnot(None)).count() > 0
