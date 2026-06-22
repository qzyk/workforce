"""
Integration tests pentru Faza 12 - situatii lunare:
  - GET lista situatii per contract
  - POST genereaza situatie (din cantitati validate)
  - GET detalii cu totaluri
  - POST schimba status (workflow)
  - GET export XLSX + PDF
"""

import os
from datetime import date
from decimal import Decimal

import pytest


@pytest.fixture
def setup_pentru_situatii(app, admin_user):
    """Setup contract + oferta + cantitati executate VALIDATE pentru testare."""
    from models import (
        db, Proiect, Contract, OfertaContract, PozitieBoQ,
        CantitateExecutataLunara, SituatieLunara,
    )
    from services.feature_flags import set_flag

    with app.app_context():
        set_flag('controale-contract', True, commit=True)
        # Cleanup
        SituatieLunara.query.delete()
        CantitateExecutataLunara.query.delete()
        PozitieBoQ.query.filter(PozitieBoQ.cod_articol.like('SIT-%')).delete()
        OfertaContract.query.delete()
        Contract.query.delete()
        Proiect.query.filter(Proiect.cod_proiect == 'SIT-PRJ').delete()
        db.session.commit()

        p = Proiect(cod_proiect='SIT-PRJ', nume='Sit Test',
                    data_start=date(2026, 1, 1), status='activ')
        db.session.add(p); db.session.commit()
        c = Contract(proiect_id=p.id, nr_contract='SIT-CTR-001',
                     data_semnare=date(2026, 1, 15), status='activ',
                     valoare_totala=Decimal('50000'), moneda='RON')
        db.session.add(c); db.session.commit()
        o = OfertaContract(contract_id=c.id, proiect_id=p.id, versiune=1,
                           data_emitere=date(2026, 1, 20),
                           valoare_totala=Decimal('50000'),
                           sursa_import='manual', aprobata=True)
        db.session.add(o); db.session.commit()
        # 2 pozitii BoQ
        pz1 = PozitieBoQ(oferta_id=o.id, proiect_id=p.id,
                         cod_articol='SIT-001', denumire='Test 1',
                         um='mc', cantitate_oferta=Decimal('100'),
                         pret_unitar=Decimal('200'), categorie='mixt', ordine=1)
        pz2 = PozitieBoQ(oferta_id=o.id, proiect_id=p.id,
                         cod_articol='SIT-002', denumire='Test 2',
                         um='kg', cantitate_oferta=Decimal('500'),
                         pret_unitar=Decimal('30'), categorie='mixt', ordine=2)
        db.session.add(pz1); db.session.add(pz2); db.session.commit()
        # Cantitati executate validate pentru luna 3/2026
        c1 = CantitateExecutataLunara(
            pozitie_boq_id=pz1.id, proiect_id=p.id, an=2026, luna=3,
            cantitate_executata=Decimal('25'), valoare_calculata=Decimal('5000'),
            validat=True, validat_de_id=admin_user.id,
        )
        c2 = CantitateExecutataLunara(
            pozitie_boq_id=pz2.id, proiect_id=p.id, an=2026, luna=3,
            cantitate_executata=Decimal('100'), valoare_calculata=Decimal('3000'),
            validat=True, validat_de_id=admin_user.id,
        )
        db.session.add(c1); db.session.add(c2); db.session.commit()
        yield {
            'proiect_id': p.id, 'contract_id': c.id, 'oferta_id': o.id,
            'pz_ids': [pz1.id, pz2.id],
        }
    with app.app_context():
        set_flag('controale-contract', False, commit=True)
        SituatieLunara.query.delete()
        CantitateExecutataLunara.query.delete()
        PozitieBoQ.query.filter(PozitieBoQ.cod_articol.like('SIT-%')).delete()
        OfertaContract.query.delete()
        Contract.query.delete()
        Proiect.query.filter(Proiect.cod_proiect == 'SIT-PRJ').delete()
        db.session.commit()


class TestSituatiiCRUD:
    def test_lista_ok(self, authenticated_client, setup_pentru_situatii):
        r = authenticated_client.get(
            f'/contracte/{setup_pentru_situatii["contract_id"]}/situatii'
        )
        assert r.status_code == 200

    def test_genereaza_situatie_calculeaza_totaluri(
        self, app, authenticated_client, setup_pentru_situatii
    ):
        """POST formular -> SituatieLunara cu valoare 8000 (5000+3000)."""
        from models import SituatieLunara
        r = authenticated_client.post(
            f'/contracte/{setup_pentru_situatii["contract_id"]}/situatie/nou',
            data={
                'an': '2026', 'luna': '3',
                'numar_situatie': 'TEST-S-001',
                'status': 'draft',
            },
            follow_redirects=False,
        )
        assert r.status_code in (302, 303), f'Status {r.status_code}, data: {r.data[:500]}'
        with app.app_context():
            s = SituatieLunara.query.filter_by(
                contract_id=setup_pentru_situatii['contract_id'],
                an=2026, luna=3,
            ).first()
            assert s is not None
            # Cantitati validate: 25 * 200 + 100 * 30 = 5000 + 3000 = 8000
            assert s.valoare_totala_luna == Decimal('8000.00')
            assert s.valoare_cumulat_la_zi == Decimal('8000.00')
            # Procent: 8000 / 50000 * 100 = 16%
            assert s.procent_avans_total == Decimal('16.00')
            assert s.numar_situatie == 'TEST-S-001'

    def test_detalii_ok(self, app, authenticated_client, setup_pentru_situatii):
        from models import db, SituatieLunara
        with app.app_context():
            s = SituatieLunara(
                proiect_id=setup_pentru_situatii['proiect_id'],
                contract_id=setup_pentru_situatii['contract_id'],
                an=2026, luna=4, status='draft',
                valoare_totala_luna=Decimal('100'),
            )
            db.session.add(s); db.session.commit()
            sid = s.id
        r = authenticated_client.get(f'/contracte/situatie/{sid}')
        assert r.status_code == 200

    def test_schimba_status_workflow(
        self, app, authenticated_client, setup_pentru_situatii
    ):
        from models import db, SituatieLunara
        with app.app_context():
            s = SituatieLunara(
                proiect_id=setup_pentru_situatii['proiect_id'],
                contract_id=setup_pentru_situatii['contract_id'],
                an=2026, luna=5, status='draft',
            )
            db.session.add(s); db.session.commit()
            sid = s.id
        # draft -> emisa
        r = authenticated_client.post(
            f'/contracte/situatie/{sid}/status',
            data={'nou_status': 'emisa'},
            follow_redirects=False,
        )
        assert r.status_code in (302, 303)
        with app.app_context():
            assert SituatieLunara.query.get(sid).status == 'emisa'
        # emisa -> aprobata_beneficiar
        authenticated_client.post(
            f'/contracte/situatie/{sid}/status',
            data={'nou_status': 'aprobata_beneficiar'},
        )
        with app.app_context():
            s_after = SituatieLunara.query.get(sid)
            assert s_after.status == 'aprobata_beneficiar'
            assert s_after.aprobat_de_id is not None

    def test_export_xlsx(self, app, authenticated_client, setup_pentru_situatii):
        from models import db, SituatieLunara
        with app.app_context():
            s = SituatieLunara(
                proiect_id=setup_pentru_situatii['proiect_id'],
                contract_id=setup_pentru_situatii['contract_id'],
                an=2026, luna=3, status='emisa',
                valoare_totala_luna=Decimal('8000'),
                valoare_cumulat_la_zi=Decimal('8000'),
                procent_avans_total=Decimal('16'),
                numar_situatie='X-001',
            )
            db.session.add(s); db.session.commit()
            sid = s.id
        r = authenticated_client.get(f'/contracte/situatie/{sid}/export/xlsx')
        assert r.status_code == 200
        assert r.headers['Content-Type'].startswith(
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        # XLSX e ZIP - verific magic bytes PK
        assert r.data[:2] == b'PK'

    def test_export_pdf(self, app, authenticated_client, setup_pentru_situatii):
        from models import db, SituatieLunara
        with app.app_context():
            s = SituatieLunara(
                proiect_id=setup_pentru_situatii['proiect_id'],
                contract_id=setup_pentru_situatii['contract_id'],
                an=2026, luna=3, status='emisa',
                valoare_totala_luna=Decimal('8000'),
                numar_situatie='X-002',
            )
            db.session.add(s); db.session.commit()
            sid = s.id
        r = authenticated_client.get(f'/contracte/situatie/{sid}/export/pdf')
        assert r.status_code == 200
        assert r.headers['Content-Type'].startswith('application/pdf')
        assert r.data[:4] == b'%PDF'

    def test_situatie_doar_cantitati_validate(
        self, app, authenticated_client, setup_pentru_situatii
    ):
        """Cantitatile non-validate NU intra in situatie."""
        from models import db, CantitateExecutataLunara, SituatieLunara
        # Adaug o cantitate NEVALIDATA pentru luna 4
        with app.app_context():
            c = CantitateExecutataLunara(
                pozitie_boq_id=setup_pentru_situatii['pz_ids'][0],
                proiect_id=setup_pentru_situatii['proiect_id'],
                an=2026, luna=4,
                cantitate_executata=Decimal('999'),
                valoare_calculata=Decimal('199800'),
                validat=False,
            )
            db.session.add(c); db.session.commit()
        # Genereaza situatie pentru luna 4 - trebuie sa fie 0
        authenticated_client.post(
            f'/contracte/{setup_pentru_situatii["contract_id"]}/situatie/nou',
            data={'an': '2026', 'luna': '4', 'status': 'draft'},
        )
        with app.app_context():
            s = SituatieLunara.query.filter_by(an=2026, luna=4).first()
            assert s is not None
            assert s.valoare_totala_luna == Decimal('0')  # nimic validat in luna 4


class TestSituatiiRetentii:
    """Deviz Faza 3 - retentii + garantii pe situatie (route + flag gate)."""

    def _creeaza_situatie(self, app, setup, valoare=Decimal('100000')):
        from models import db, SituatieLunara
        with app.app_context():
            s = SituatieLunara(
                proiect_id=setup['proiect_id'],
                contract_id=setup['contract_id'],
                an=2026, luna=6, status='draft',
                valoare_totala_luna=valoare,
            )
            db.session.add(s); db.session.commit()
            return s.id

    def test_retentii_flag_off_404(self, app, authenticated_client, setup_pentru_situatii):
        """Cu flag 'situatii-retentii' OFF, POST retentii -> 404 (sectiune invizibila)."""
        sid = self._creeaza_situatie(app, setup_pentru_situatii)
        r = authenticated_client.post(
            f'/contracte/situatie/{sid}/retentii',
            data={'retentie_procent': '5', 'garantie_bex_procent': '5',
                  'avans_recuperat': '10000'},
            follow_redirects=False,
        )
        assert r.status_code == 404

    def test_retentii_post_calculeaza_plata_neta(
        self, app, authenticated_client, setup_pentru_situatii
    ):
        """
        Cu flag ON, POST retentii calculeaza plata neta:
        100k - 5% retentie (5000) - 5% garantie (5000) - 10k avans = 80000.
        """
        from models import db, SituatieLunara
        from services.feature_flags import set_flag
        sid = self._creeaza_situatie(app, setup_pentru_situatii)
        with app.app_context():
            set_flag('situatii-retentii', True, commit=True)
        r = authenticated_client.post(
            f'/contracte/situatie/{sid}/retentii',
            data={'retentie_procent': '5', 'garantie_bex_procent': '5',
                  'avans_recuperat': '10000'},
            follow_redirects=False,
        )
        assert r.status_code in (302, 303)
        with app.app_context():
            s = SituatieLunara.query.get(sid)
            assert s.retentie_suma == Decimal('5000.00')
            assert s.garantie_bex_suma == Decimal('5000.00')
            assert s.avans_recuperat == Decimal('10000.00')
            assert s.plata_neta == Decimal('80000.00')

    def test_detalii_afiseaza_sectiune_retentii_cu_flag(
        self, app, authenticated_client, setup_pentru_situatii
    ):
        """Cu flag ON, pagina de detalii contine sectiunea de retentii."""
        from services.feature_flags import set_flag
        sid = self._creeaza_situatie(app, setup_pentru_situatii)
        with app.app_context():
            set_flag('situatii-retentii', True, commit=True)
        r = authenticated_client.get(f'/contracte/situatie/{sid}')
        assert r.status_code == 200
        assert b'Retentii si garantii' in r.data or b'Plata neta' in r.data

    def test_editare_manuala_via_ruta_pastrata_la_regenerare(
        self, app, authenticated_client, setup_pentru_situatii
    ):
        """
        Editarea via POST /retentii marcheaza retentii_editate_manual=True;
        o regenerare ulterioara a situatiei NU suprascrie sumele manuale (doar
        recalculeaza plata neta). Fara marcaj, regenerarea ar recalcula din procent.
        """
        from models import db, SituatieLunara
        from services.feature_flags import set_flag
        from services.situatii import genereaza_situatie
        cid = setup_pentru_situatii['contract_id']
        with app.app_context():
            set_flag('situatii-retentii', True, commit=True)
            # Generam situatia pe luna 3/2026 (valoare 8000 din fixture).
            s = genereaza_situatie(cid, 2026, 3)
            sid = s.id
        # Editare manuala via ruta: retentie 10%, garantie 0, avans 0.
        r = authenticated_client.post(
            f'/contracte/situatie/{sid}/retentii',
            data={'retentie_procent': '10', 'garantie_bex_procent': '0',
                  'avans_recuperat': '0'},
            follow_redirects=False,
        )
        assert r.status_code in (302, 303)
        with app.app_context():
            s = SituatieLunara.query.get(sid)
            assert s.retentii_editate_manual is True
            assert s.retentie_suma == Decimal('800.00')  # 8000 * 10%
            # Suprascriem manual o suma "non-procentuala" si regeneram.
            s.retentie_suma = Decimal('1234.00')
            db.session.commit()
            genereaza_situatie(cid, 2026, 3)
            s = SituatieLunara.query.get(sid)
            # Suma manuala pastrata, nu recalculata din 10% * 8000.
            assert s.retentie_suma == Decimal('1234.00')
            # plata neta reconciliata din suma pastrata: 8000 - 1234 - 0 - 0.
            assert s.plata_neta == Decimal('6766.00')
