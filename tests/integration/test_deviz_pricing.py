"""
Tests pentru auto-pricing devize (services/deviz_pricing.py + endpoints).

Acopera:
  - Clasificator pe keywords (+ gotchas: probe inainte de echipament)
  - idem carry-forward
  - Σ pozitii == total (reconciliere, toleranta rounding)
  - Split material/manopera pe %
  - Division guards (cantitate 0)
  - Seed tarife default
  - Endpoints pricing + tarife
  - Test pe SAPUNARI real (opt-in)
"""

import os
from datetime import date
from decimal import Decimal

import pytest

from services import deviz_pricing


REAL_SAPUNARI = os.path.expanduser('~/Downloads/DEVIZ SAPUNARI.pdf')


# ============================================================
# Clasificator (unit, fara DB)
# ============================================================

class TestClasificator:
    def test_deduce_disciplina(self):
        assert deviz_pricing.deduce_disciplina('1 REZISTENTA') == 'structural'
        assert deviz_pricing.deduce_disciplina('2 ARHITECTURA') == 'arhitectura'
        assert deviz_pricing.deduce_disciplina('3 ELECTRICE CT') == 'electrice'
        assert deviz_pricing.deduce_disciplina('5 SANITARE') == 'sanitare'
        assert deviz_pricing.deduce_disciplina('6 TERMICE') == 'hvac'
        assert deviz_pricing.deduce_disciplina(None) == 'general'

    def test_clasifica_beton_armatura(self):
        assert deviz_pricing.clasifica_pozitie('Beton C25/30', disciplina='structural') == 'beton'
        assert deviz_pricing.clasifica_pozitie('Armaturi BST500', disciplina='structural') == 'armatura'
        assert deviz_pricing.clasifica_pozitie('Sapatura manuala', disciplina='structural') == 'terasamente'

    def test_gotcha_probe_inainte_de_echipament(self):
        """'incercare tablouri' -> probe, NU tablou (gotcha din playbook)."""
        cat = deviz_pricing.clasifica_pozitie('Incercare tablouri electrice', disciplina='electrice')
        assert cat == 'probe_verificari'

    def test_gotcha_corp_iluminat_inainte_de_sursa(self):
        cat = deviz_pricing.clasifica_pozitie('Corp de iluminat cu sursa LED', disciplina='electrice')
        assert cat == 'corpuri_iluminat'

    def test_pdu_cu_prize_e_cs_nu_aparataj(self):
        """'PDU cu 8 prize' -> echipamente_cs, nu aparataj (prize)."""
        cat = deviz_pricing.clasifica_pozitie('PDU power distribution unit cu 8 prize', disciplina='electrice')
        assert cat == 'echipamente_cs'

    def test_fallback_diverse_um(self):
        cat = deviz_pricing.clasifica_pozitie('Articol necunoscut xyz', disciplina='general', um='buc')
        assert cat == 'diverse_buc'


# ============================================================
# DB-backed: clasificare oferta + pricing
# ============================================================

@pytest.fixture
def oferta_test(app, admin_user):
    from models import (db, Proiect, Contract, OfertaContract, PozitieBoQ,
                        TarifCategorie)
    from services.feature_flags import set_flag
    with app.app_context():
        set_flag('controale-contract', True, commit=True)
        PozitieBoQ.query.filter(PozitieBoQ.cod_articol.like('PRC-%')).delete()
        OfertaContract.query.delete()
        Contract.query.delete()
        Proiect.query.filter_by(cod_proiect='PRC-PRJ').delete()
        db.session.commit()
        deviz_pricing.seed_tarife_default()
        p = Proiect(cod_proiect='PRC-PRJ', nume='Pricing Test',
                    data_start=date(2026, 1, 1), status='activ')
        db.session.add(p); db.session.commit()
        c = Contract(proiect_id=p.id, nr_contract='PRC-CTR', data_semnare=date(2026, 1, 1),
                     status='activ')
        db.session.add(c); db.session.commit()
        o = OfertaContract(contract_id=c.id, proiect_id=p.id, versiune=1,
                           data_emitere=date(2026, 1, 1), sursa_import='manual')
        db.session.add(o); db.session.commit()
        # 4 pozitii cu cantitati, fara pret
        specs = [
            ('PRC-001', '1 REZISTENTA', 'Sapatura manuala', 'mc', 100),
            ('PRC-002', '1 REZISTENTA', 'Beton C25/30', 'mc', 50),
            ('PRC-003', '1 REZISTENTA', 'idem', 'mc', 20),  # idem -> carry beton
            ('PRC-004', '2 ARHITECTURA', 'Tencuiala interioara', 'mp', 200),
        ]
        for cod, cap, den, um, cant in specs:
            db.session.add(PozitieBoQ(
                oferta_id=o.id, proiect_id=p.id, cod_articol=cod, cod_capitol=cap,
                denumire=den, um=um, cantitate_oferta=Decimal(str(cant)),
                pret_unitar=Decimal('0'), categorie='mixt',
                ordine=int(cod[-1])))
        db.session.commit()
        yield {'oferta_id': o.id, 'proiect_id': p.id, 'contract_id': c.id}
    with app.app_context():
        from models import db, Proiect, Contract, OfertaContract, PozitieBoQ
        from services.feature_flags import set_flag
        set_flag('controale-contract', False, commit=True)
        PozitieBoQ.query.filter(PozitieBoQ.cod_articol.like('PRC-%')).delete()
        OfertaContract.query.delete()
        Contract.query.delete()
        Proiect.query.filter_by(cod_proiect='PRC-PRJ').delete()
        db.session.commit()


class TestPricingDB:
    def test_seed_tarife_idempotent(self, app):
        from models import TarifCategorie
        with app.app_context():
            n1 = deviz_pricing.seed_tarife_default()
            n2 = deviz_pricing.seed_tarife_default()  # a doua oara nu adauga
            assert n2 == 0
            assert TarifCategorie.query.filter_by(proiect_id=None).count() > 0

    def test_clasifica_oferta_idem_carry_forward(self, app, oferta_test):
        from models import OfertaContract, PozitieBoQ
        with app.app_context():
            o = OfertaContract.query.get(oferta_test['oferta_id'])
            deviz_pricing.clasifica_oferta(o)
            poz = {p.cod_articol: p for p in o.pozitii.all()}
            assert poz['PRC-002'].categorie_lucrare == 'beton'
            # PRC-003 = 'idem' -> mosteneste beton
            assert poz['PRC-003'].categorie_lucrare == 'beton'
            assert poz['PRC-001'].categorie_lucrare == 'terasamente'

    def test_aplica_pricing_suma_egala_total(self, app, oferta_test):
        from models import OfertaContract
        with app.app_context():
            o = OfertaContract.query.get(oferta_test['oferta_id'])
            total = Decimal('100000.00')
            stats = deviz_pricing.aplica_pricing(o, total, procent_material=Decimal('0.65'))
            assert stats['pozitii_pretuite'] == 4
            # Re-sum din DB: Σ(pret_unitar x cant) ~ total (toleranta rounding mica)
            suma = sum((p.pret_unitar * p.cantitate_oferta).quantize(Decimal('0.01'))
                       for p in o.pozitii.all())
            assert abs(suma - total) < Decimal('0.10')

    def test_split_material_manopera(self, app, oferta_test):
        from models import OfertaContract
        with app.app_context():
            o = OfertaContract.query.get(oferta_test['oferta_id'])
            deviz_pricing.aplica_pricing(o, Decimal('100000'), procent_material=Decimal('0.65'))
            for p in o.pozitii.all():
                # material + manopera == pret_unitar (cu toleranta rounding 4 zecimale)
                s = (p.valoare_materiale_unitar or 0) + (p.valoare_manopera_unitar or 0)
                assert abs(s - p.pret_unitar) < Decimal('0.001')
                # material ~ 65%
                if p.pret_unitar > 0:
                    ratio = p.valoare_materiale_unitar / p.pret_unitar
                    assert Decimal('0.60') < ratio < Decimal('0.70')

    def test_division_guard_cantitate_zero(self, app, oferta_test):
        from models import db, OfertaContract, PozitieBoQ
        with app.app_context():
            o = OfertaContract.query.get(oferta_test['oferta_id'])
            # Adaug o pozitie cu cantitate 0
            db.session.add(PozitieBoQ(
                oferta_id=o.id, proiect_id=oferta_test['proiect_id'],
                cod_articol='PRC-ZERO', cod_capitol='1 REZISTENTA',
                denumire='Cant zero', um='buc', cantitate_oferta=Decimal('0'),
                pret_unitar=Decimal('0'), categorie='mixt', ordine=99))
            db.session.commit()
            stats = deviz_pricing.aplica_pricing(o, Decimal('100000'))
            # Pozitia cu cant 0 e numarata separat, NU crapa
            assert stats['pozitii_zero_cant'] == 1
            assert stats['pozitii_pretuite'] == 4


class TestPricingEndpoints:
    def test_pricing_preview_json(self, app, authenticated_client, oferta_test):
        r = authenticated_client.get(
            f'/contracte/oferta/{oferta_test["oferta_id"]}/pricing/preview'
        )
        assert r.status_code == 200
        data = r.get_json()
        assert 'distributie' in data
        assert data['total_pozitii'] == 4

    def test_pricing_form_get(self, authenticated_client, oferta_test):
        r = authenticated_client.get(
            f'/contracte/oferta/{oferta_test["oferta_id"]}/pricing'
        )
        assert r.status_code == 200
        assert b'pricing' in r.data.lower()

    def test_pricing_apply_post(self, app, authenticated_client, oferta_test):
        from models import OfertaContract
        r = authenticated_client.post(
            f'/contracte/oferta/{oferta_test["oferta_id"]}/pricing',
            data={'total_global': '100000', 'procent_material': '65', 'seed': '42'},
            follow_redirects=False,
        )
        assert r.status_code in (302, 303)
        with app.app_context():
            o = OfertaContract.query.get(oferta_test['oferta_id'])
            assert o.valoare_totala == Decimal('100000')
            assert all(p.pret_unitar > 0 for p in o.pozitii.all())

    def test_tarife_lista(self, authenticated_client, oferta_test):
        r = authenticated_client.get(
            f'/contracte/proiect/{oferta_test["proiect_id"]}/tarife'
        )
        assert r.status_code == 200

    def test_tarife_salveaza_override(self, app, authenticated_client, oferta_test):
        from models import TarifCategorie
        r = authenticated_client.post(
            f'/contracte/proiect/{oferta_test["proiect_id"]}/tarife/salveaza',
            data={'tarif_structural__beton': '999.50'},
            follow_redirects=False,
        )
        assert r.status_code in (302, 303)
        with app.app_context():
            t = TarifCategorie.query.filter_by(
                proiect_id=oferta_test['proiect_id'],
                disciplina='structural', categorie_lucrare='beton'
            ).first()
            assert t is not None
            assert t.tarif_baza == Decimal('999.5000')


@pytest.mark.skipif(not os.path.exists(REAL_SAPUNARI),
                    reason='SAPUNARI PDF nu e in Downloads')
class TestPricingSapunariReal:
    def test_clasificare_sub_5_la_suta_diverse(self, app):
        """Pe SAPUNARI real (490 articole): Diverse trebuie < 5%."""
        from models import (db, Proiect, Contract, OfertaContract, PozitieBoQ)
        from services.parsers.edevize_pdf_parser import EDevizePDFParser
        with app.app_context():
            PozitieBoQ.query.filter(PozitieBoQ.cod_articol.like('SAPRC%')).delete()
            db.session.commit()
            p = Proiect.query.filter_by(cod_proiect='SAPRC').first()
            if not p:
                p = Proiect(cod_proiect='SAPRC', nume='Sap', data_start=date(2026,1,1), status='activ')
                db.session.add(p); db.session.commit()
            c = Contract(proiect_id=p.id, nr_contract='SAPRC-C', data_semnare=date(2026,1,1), status='activ')
            db.session.add(c); db.session.commit()
            o = OfertaContract(contract_id=c.id, proiect_id=p.id, versiune=1,
                               data_emitere=date(2026,1,1), sursa_import='edevize_pdf')
            db.session.add(o); db.session.commit()
            r = EDevizePDFParser().parse(REAL_SAPUNARI)
            for e in r.entities:
                db.session.add(PozitieBoQ(
                    oferta_id=o.id, proiect_id=p.id, cod_articol='SAPRC' + e['cod_articol'][:40],
                    cod_capitol=e.get('cod_capitol'), denumire=e['denumire'], um=e['um'],
                    cantitate_oferta=e['cantitate_oferta'], pret_unitar=Decimal('0'),
                    categorie=e['categorie'], ordine=e['ordine']))
            db.session.commit()
            dry = deviz_pricing.dry_run_clasificare(o)
            assert dry['procent_diverse'] < 5.0, f'Diverse {dry["procent_diverse"]}% prea mare'
            # Cleanup
            PozitieBoQ.query.filter_by(oferta_id=o.id).delete()
            db.session.delete(o); db.session.delete(c); db.session.delete(p)
            db.session.commit()
