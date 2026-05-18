"""
Integration tests pentru Faza 12 - cantitati executate lunare:
  - GET matrice cu filtre
  - POST bulk save
  - Validare cantitate (manager)
  - Stergere cantitate
"""

from datetime import date
from decimal import Decimal

import pytest


@pytest.fixture
def setup_oferta_f12(app, admin_user):
    """Setup Proiect + Contract + Oferta + 5 PozitieBoQ pentru teste Faza 12."""
    from models import (
        db, Proiect, Contract, OfertaContract, PozitieBoQ,
        CantitateExecutataLunara,
    )
    from services.feature_flags import set_flag

    with app.app_context():
        set_flag('controale-contract', True, commit=True)

        # Cleanup pre-existent
        CantitateExecutataLunara.query.delete()
        PozitieBoQ.query.filter(PozitieBoQ.cod_articol.like('F12-%')).delete()
        OfertaContract.query.delete()
        Contract.query.delete()
        Proiect.query.filter(Proiect.cod_proiect == 'F12-PRJ').delete()
        db.session.commit()

        p = Proiect(cod_proiect='F12-PRJ', nume='F12 Test',
                    data_start=date(2026, 1, 1), status='activ')
        db.session.add(p); db.session.commit()
        c = Contract(proiect_id=p.id, nr_contract='F12-CTR-001',
                     data_semnare=date(2026, 1, 15), status='activ',
                     valoare_totala=Decimal('100000'), moneda='RON')
        db.session.add(c); db.session.commit()
        o = OfertaContract(contract_id=c.id, proiect_id=p.id, versiune=1,
                           data_emitere=date(2026, 1, 20),
                           valoare_totala=Decimal('100000'),
                           sursa_import='manual', aprobata=True)
        db.session.add(o); db.session.commit()
        # 5 pozitii BoQ
        pozitii = []
        for i in range(1, 6):
            pz = PozitieBoQ(
                oferta_id=o.id, proiect_id=p.id,
                cod_articol=f'F12-{i:03d}',
                cod_capitol='F12-CAP' if i <= 3 else 'F12-CAP2',
                denumire=f'Articol F12 nr {i}',
                um='mc', cantitate_oferta=Decimal('100'),
                pret_unitar=Decimal('50'),
                categorie='mixt', ordine=i,
            )
            db.session.add(pz)
            pozitii.append(pz)
        db.session.commit()
        yield {
            'proiect_id': p.id, 'contract_id': c.id, 'oferta_id': o.id,
            'pozitii_ids': [pz.id for pz in pozitii],
        }
    with app.app_context():
        set_flag('controale-contract', False, commit=True)
        CantitateExecutataLunara.query.delete()
        PozitieBoQ.query.filter(PozitieBoQ.cod_articol.like('F12-%')).delete()
        OfertaContract.query.delete()
        Contract.query.delete()
        Proiect.query.filter(Proiect.cod_proiect == 'F12-PRJ').delete()
        db.session.commit()


class TestCantitatiMatrice:
    def test_get_matrice_ok(self, authenticated_client, setup_oferta_f12):
        r = authenticated_client.get(
            f'/contracte/oferta/{setup_oferta_f12["oferta_id"]}/cantitati'
        )
        assert r.status_code == 200
        # Verific ca cele 5 cod articol apar
        for i in range(1, 6):
            assert f'F12-{i:03d}'.encode() in r.data

    def test_get_matrice_filter_capitol(self, authenticated_client, setup_oferta_f12):
        r = authenticated_client.get(
            f'/contracte/oferta/{setup_oferta_f12["oferta_id"]}/cantitati?capitol=F12-CAP2'
        )
        assert r.status_code == 200
        # Doar pozitiile 4 si 5 din F12-CAP2 trebuie sa apara
        assert b'F12-004' in r.data
        assert b'F12-005' in r.data

    def test_post_bulk_save_create(self, app, authenticated_client, setup_oferta_f12):
        from models import CantitateExecutataLunara
        pid1, pid2 = setup_oferta_f12['pozitii_ids'][0], setup_oferta_f12['pozitii_ids'][1]
        r = authenticated_client.post(
            f'/contracte/oferta/{setup_oferta_f12["oferta_id"]}/cantitati?an=2026&luna=3',
            data={
                f'cantitate_{pid1}': '25.5',
                f'note_{pid1}': 'test',
                f'cantitate_{pid2}': '50.0',
            },
            follow_redirects=False,
        )
        assert r.status_code in (302, 303)
        with app.app_context():
            cs = CantitateExecutataLunara.query.filter(
                CantitateExecutataLunara.pozitie_boq_id.in_([pid1, pid2]),
                CantitateExecutataLunara.an == 2026,
                CantitateExecutataLunara.luna == 3,
            ).all()
            assert len(cs) == 2
            by_pid = {c.pozitie_boq_id: c for c in cs}
            assert by_pid[pid1].cantitate_executata == Decimal('25.5')
            assert by_pid[pid1].valoare_calculata == Decimal('25.5') * Decimal('50')
            assert by_pid[pid1].note == 'test'
            assert by_pid[pid2].cantitate_executata == Decimal('50.0')

    def test_post_bulk_update_existing(self, app, authenticated_client, setup_oferta_f12):
        """Reapelarea POST cu acceasi (pid, an, luna) ACTUALIZEAZA, nu duplica."""
        from models import db, CantitateExecutataLunara
        pid = setup_oferta_f12['pozitii_ids'][0]
        # Insert initial
        with app.app_context():
            c = CantitateExecutataLunara(
                pozitie_boq_id=pid, proiect_id=setup_oferta_f12['proiect_id'],
                an=2026, luna=5, cantitate_executata=Decimal('10'),
                valoare_calculata=Decimal('500'),
            )
            db.session.add(c); db.session.commit()
        # POST cu valoare diferita
        authenticated_client.post(
            f'/contracte/oferta/{setup_oferta_f12["oferta_id"]}/cantitati?an=2026&luna=5',
            data={f'cantitate_{pid}': '20'},
            follow_redirects=False,
        )
        with app.app_context():
            cs = CantitateExecutataLunara.query.filter_by(
                pozitie_boq_id=pid, an=2026, luna=5
            ).all()
            assert len(cs) == 1  # NU duplicat
            assert cs[0].cantitate_executata == Decimal('20')

    def test_post_skips_invalid_pid(self, app, authenticated_client, setup_oferta_f12):
        """Pozitie inexistenta / din alta oferta -> skip silent."""
        from models import CantitateExecutataLunara
        r = authenticated_client.post(
            f'/contracte/oferta/{setup_oferta_f12["oferta_id"]}/cantitati?an=2026&luna=4',
            data={'cantitate_99999': '100'},
            follow_redirects=False,
        )
        assert r.status_code in (302, 303)
        with app.app_context():
            assert CantitateExecutataLunara.query.filter_by(an=2026, luna=4).count() == 0

    def test_valideaza_cantitate_admin(self, app, authenticated_client, setup_oferta_f12):
        from models import db, CantitateExecutataLunara
        pid = setup_oferta_f12['pozitii_ids'][0]
        with app.app_context():
            c = CantitateExecutataLunara(
                pozitie_boq_id=pid, proiect_id=setup_oferta_f12['proiect_id'],
                an=2026, luna=6, cantitate_executata=Decimal('30'),
                valoare_calculata=Decimal('1500'),
            )
            db.session.add(c); db.session.commit()
            cid = c.id
        r = authenticated_client.post(
            f'/contracte/cantitate/{cid}/valideaza',
            follow_redirects=False,
        )
        assert r.status_code in (302, 303)
        with app.app_context():
            assert CantitateExecutataLunara.query.get(cid).validat is True

    def test_sterge_cantitate(self, app, authenticated_client, setup_oferta_f12):
        from models import db, CantitateExecutataLunara
        pid = setup_oferta_f12['pozitii_ids'][2]
        with app.app_context():
            c = CantitateExecutataLunara(
                pozitie_boq_id=pid, proiect_id=setup_oferta_f12['proiect_id'],
                an=2026, luna=7, cantitate_executata=Decimal('5'),
                valoare_calculata=Decimal('250'),
            )
            db.session.add(c); db.session.commit()
            cid = c.id
        r = authenticated_client.post(
            f'/contracte/cantitate/{cid}/sterge',
            follow_redirects=False,
        )
        assert r.status_code in (302, 303)
        with app.app_context():
            assert CantitateExecutataLunara.query.get(cid) is None
