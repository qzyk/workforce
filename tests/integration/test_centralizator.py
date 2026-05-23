"""
Integration tests pentru clasificare proiect + centralizator + deviz general.
"""

from datetime import date
from decimal import Decimal

import pytest


@pytest.fixture
def proiect_cu_oferte(app, admin_user):
    """Proiect cu contract + 2 oferte cu pozitii (structural + arhitectura)."""
    from models import (
        db, Proiect, Contract, OfertaContract, PozitieBoQ,
    )
    from services.feature_flags import set_flag
    with app.app_context():
        set_flag('controale-contract', True, commit=True)
        PozitieBoQ.query.filter(PozitieBoQ.cod_articol.like('CTR-%')).delete()
        OfertaContract.query.delete()
        Contract.query.delete()
        Proiect.query.filter_by(cod_proiect='CTR-PRJ').delete()
        db.session.commit()

        p = Proiect(cod_proiect='CTR-PRJ', nume='Centralizator Test',
                    data_start=date(2026, 1, 1), status='activ')
        db.session.add(p); db.session.commit()
        c = Contract(proiect_id=p.id, nr_contract='CTR-001',
                     data_semnare=date(2026, 1, 15), status='activ')
        db.session.add(c); db.session.commit()
        # Oferta 1 - structural
        o1 = OfertaContract(contract_id=c.id, proiect_id=p.id, versiune=1,
                            data_emitere=date(2026, 1, 20), sursa_import='manual')
        db.session.add(o1); db.session.commit()
        for i, (den, um, cant, pret) in enumerate([
            ('Beton C25/30 fundatie', 'mc', 100, 600),
            ('Armatura S500C', 'kg', 5000, 6),
            ('Cofraj metalic', 'mp', 200, 50),
            ('Ceva ciudat nedefinit xyz', 'buc', 10, 100),  # -> diverse
        ], start=1):
            db.session.add(PozitieBoQ(
                oferta_id=o1.id, proiect_id=p.id, cod_articol=f'CTR-S{i}',
                cod_capitol='Rezistenta', denumire=den, um=um,
                cantitate_oferta=Decimal(str(cant)), pret_unitar=Decimal(str(pret)),
                categorie='mixt', ordine=i,
            ))
        # Oferta 2 - arhitectura
        o2 = OfertaContract(contract_id=c.id, proiect_id=p.id, versiune=2,
                            data_emitere=date(2026, 2, 1), sursa_import='manual')
        db.session.add(o2); db.session.commit()
        for i, (den, um, cant, pret) in enumerate([
            ('Tencuiala interioara', 'mp', 500, 30),
            ('Gresie portelanata', 'mp', 150, 80),
        ], start=1):
            db.session.add(PozitieBoQ(
                oferta_id=o2.id, proiect_id=p.id, cod_articol=f'CTR-A{i}',
                cod_capitol='Arhitectura', denumire=den, um=um,
                cantitate_oferta=Decimal(str(cant)), pret_unitar=Decimal(str(pret)),
                categorie='mixt', ordine=i,
            ))
        db.session.commit()
        yield {'proiect_id': p.id, 'contract_id': c.id,
               'oferta1_id': o1.id, 'oferta2_id': o2.id}
    with app.app_context():
        set_flag('controale-contract', False, commit=True)
        PozitieBoQ.query.filter(PozitieBoQ.cod_articol.like('CTR-%')).delete()
        OfertaContract.query.delete()
        Contract.query.delete()
        Proiect.query.filter_by(cod_proiect='CTR-PRJ').delete()
        db.session.commit()


class TestClasificareProiect:
    def test_clasifica_bulk(self, app, authenticated_client, proiect_cu_oferte):
        from models import PozitieBoQ
        r = authenticated_client.post(
            f'/contracte/proiect/{proiect_cu_oferte["proiect_id"]}/clasifica-oferte',
            data={}, follow_redirects=False)
        assert r.status_code in (302, 303)
        with app.app_context():
            # Beton -> beton, Armatura -> armatura, Cofraj -> cofraje
            poz = {p.cod_articol: p for p in PozitieBoQ.query.filter(
                PozitieBoQ.cod_articol.like('CTR-%')).all()}
            assert poz['CTR-S1'].categorie_lucrare == 'beton'
            assert poz['CTR-S2'].categorie_lucrare == 'armatura'
            assert poz['CTR-S3'].categorie_lucrare == 'cofraje'

    def test_manual_override_survives_reclassify(self, app, authenticated_client, proiect_cu_oferte):
        """Editare manuala -> re-clasificare bulk NU o suprascrie."""
        from models import db, PozitieBoQ
        # Clasific bulk intai
        authenticated_client.post(
            f'/contracte/proiect/{proiect_cu_oferte["proiect_id"]}/clasifica-oferte', data={})
        # Setez manual categoria pozitiei "diverse"
        with app.app_context():
            pz = PozitieBoQ.query.filter_by(cod_articol='CTR-S4').first()
            pid = pz.id
        authenticated_client.post(
            f'/contracte/oferta/{proiect_cu_oferte["oferta1_id"]}/clasificare-manuala',
            data={f'categorie_{pid}': 'confectii_metalice'})
        with app.app_context():
            assert PozitieBoQ.query.get(pid).categorie_lucrare == 'confectii_metalice'
        # Re-clasific bulk (doar_neclasificate=True default) -> nu suprascrie
        authenticated_client.post(
            f'/contracte/proiect/{proiect_cu_oferte["proiect_id"]}/clasifica-oferte', data={})
        with app.app_context():
            assert PozitieBoQ.query.get(pid).categorie_lucrare == 'confectii_metalice'

    def test_clasificare_manuala_get(self, authenticated_client, proiect_cu_oferte):
        r = authenticated_client.get(
            f'/contracte/oferta/{proiect_cu_oferte["oferta1_id"]}/clasificare-manuala')
        assert r.status_code == 200
        assert b'CTR-S1' in r.data

    def test_clasificare_manuala_doar_diverse(self, app, authenticated_client, proiect_cu_oferte):
        # Clasific intai
        authenticated_client.post(
            f'/contracte/proiect/{proiect_cu_oferte["proiect_id"]}/clasifica-oferte', data={})
        r = authenticated_client.get(
            f'/contracte/oferta/{proiect_cu_oferte["oferta1_id"]}/clasificare-manuala?doar_diverse=1')
        assert r.status_code == 200
        # CTR-S4 (diverse) trebuie sa apara; CTR-S1 (beton) NU
        assert b'CTR-S4' in r.data
        assert b'CTR-S1' not in r.data


class TestCentralizator:
    def test_centralizator_view(self, app, authenticated_client, proiect_cu_oferte):
        authenticated_client.post(
            f'/contracte/proiect/{proiect_cu_oferte["proiect_id"]}/clasifica-oferte', data={})
        r = authenticated_client.get(
            f'/contracte/proiect/{proiect_cu_oferte["proiect_id"]}/centralizator')
        assert r.status_code == 200
        assert b'Centralizator' in r.data

    def test_centralizator_totals(self, app, proiect_cu_oferte):
        from services.centralizator import genereaza_centralizator
        with app.app_context():
            data = genereaza_centralizator(proiect_cu_oferte['proiect_id'])
            # Total = beton 60000 + armatura 30000 + cofraj 10000 + divers 1000
            #       + tencuiala 15000 + gresie 12000 = 128000
            assert data['total_general'] == Decimal('128000.00')
            assert data['nr_pozitii'] == 6

    def test_centralizator_export_xlsx(self, app, authenticated_client, proiect_cu_oferte):
        r = authenticated_client.get(
            f'/contracte/proiect/{proiect_cu_oferte["proiect_id"]}/centralizator/export')
        assert r.status_code == 200
        assert r.data[:2] == b'PK'  # xlsx = zip


class TestDevizGeneral:
    def test_deviz_general_view(self, authenticated_client, proiect_cu_oferte):
        r = authenticated_client.get(
            f'/contracte/proiect/{proiect_cu_oferte["proiect_id"]}/deviz-general')
        assert r.status_code == 200
        assert b'Deviz general' in r.data or b'HG907' in r.data

    def test_deviz_general_tva(self, app, proiect_cu_oferte):
        from services.centralizator import genereaza_deviz_general
        with app.app_context():
            data = genereaza_deviz_general(proiect_cu_oferte['proiect_id'], cota_tva=21)
            # Total fara TVA = 128000
            assert data['total_fara_tva'] == Decimal('128000.00')
            # TVA 21% = 26880
            assert data['tva'] == Decimal('26880.00')
            assert data['total_cu_tva'] == Decimal('154880.00')

    def test_deviz_general_capitole_hg907(self, app, proiect_cu_oferte):
        """Disciplinele tehnice -> 4.1; toate intr-un singur capitol aici."""
        from services.centralizator import genereaza_deviz_general
        with app.app_context():
            data = genereaza_deviz_general(proiect_cu_oferte['proiect_id'])
            coduri = {r['cod'] for r in data['randuri']}
            assert '4.1' in coduri

    def test_deviz_general_export_xlsx(self, authenticated_client, proiect_cu_oferte):
        r = authenticated_client.get(
            f'/contracte/proiect/{proiect_cu_oferte["proiect_id"]}/deviz-general/export')
        assert r.status_code == 200
        assert r.data[:2] == b'PK'
