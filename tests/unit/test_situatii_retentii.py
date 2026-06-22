"""
Teste pentru retentii + garantii pe situatii lunare - Deviz Faza 3.

Acopera:
  - plata_neta cu valori concrete (100k, retentie 5%, garantie 5%, avans 10k -> 80k)
  - regenerarea populeaza coloanele cand flag 'situatii-retentii' ON
  - regresie: cu flag OFF, coloanele raman NULL (situatie identica cu cea istorica)
  - coloanele exista pe modele (ALTER aditiv)
  - retentia/garantia URMARESC valoarea lunii la regenerare (nu se ingheata)
  - editarea manuala (retentii_editate_manual) e pastrata la o regenerare ulterioara

Formula RO:
    retentie_suma    = valoare_luna * retentie_procent / 100
    garantie_bex_suma= valoare_luna * garantie_bex_procent / 100
    plata_neta       = valoare_luna - retentie - garantie - avans_recuperat
"""
from datetime import date
from decimal import Decimal

import pytest

from services.feature_flags import set_flag


def _curata_seed(db, Proiect, Contract, OfertaContract, PozitieBoQ,
                 CantitateExecutataLunara):
    """Sterge datele de test RET-* (copiii inainte de parinti). Idempotent."""
    from models import SituatieLunara
    pr = Proiect.query.filter_by(cod_proiect='RET-PRJ').first()
    if pr is not None:
        SituatieLunara.query.filter_by(proiect_id=pr.id).delete()
    CantitateExecutataLunara.query.filter(
        CantitateExecutataLunara.pozitie_boq_id.in_(
            db.session.query(PozitieBoQ.id).filter(
                PozitieBoQ.cod_articol.like('RET-%')))).delete(
        synchronize_session=False)
    PozitieBoQ.query.filter(PozitieBoQ.cod_articol.like('RET-%')).delete(
        synchronize_session=False)
    OfertaContract.query.filter(
        OfertaContract.contract_id.in_(
            db.session.query(Contract.id).filter(
                Contract.nr_contract.like('RET-%')))).delete(
        synchronize_session=False)
    Contract.query.filter(Contract.nr_contract.like('RET-%')).delete(
        synchronize_session=False)
    Proiect.query.filter(Proiect.cod_proiect == 'RET-PRJ').delete()
    db.session.commit()


def _seed_contract_cu_cantitati(db, Proiect, Contract, OfertaContract,
                                PozitieBoQ, CantitateExecutataLunara,
                                admin_user_id, valoare_luna=100000,
                                retentie_pct=5, garantie_pct=5):
    """
    Construieste un contract cu o pozitie BoQ a carei cantitate validata pe
    luna 3/2026 da exact `valoare_luna` (pret 1 RON/unitate -> cantitate = valoare).
    """
    _curata_seed(db, Proiect, Contract, OfertaContract, PozitieBoQ,
                 CantitateExecutataLunara)
    p = Proiect(cod_proiect='RET-PRJ', nume='Retentii test',
                data_start=date(2026, 1, 1), status='activ')
    db.session.add(p); db.session.flush()
    c = Contract(proiect_id=p.id, nr_contract='RET-CTR-001',
                 data_semnare=date(2026, 1, 15), status='activ',
                 valoare_totala=Decimal('500000'), moneda='RON',
                 retentie_procent_default=Decimal(str(retentie_pct)),
                 garantie_bex_procent=Decimal(str(garantie_pct)))
    db.session.add(c); db.session.flush()
    o = OfertaContract(contract_id=c.id, proiect_id=p.id, versiune=1,
                       data_emitere=date(2026, 1, 20),
                       valoare_totala=Decimal('500000'),
                       sursa_import='manual', aprobata=True)
    db.session.add(o); db.session.flush()
    pz = PozitieBoQ(oferta_id=o.id, proiect_id=p.id,
                    cod_articol='RET-001', denumire='Lucrare test',
                    um='mc', cantitate_oferta=Decimal('500000'),
                    pret_unitar=Decimal('1'), categorie='mixt', ordine=1)
    db.session.add(pz); db.session.flush()
    cant = CantitateExecutataLunara(
        pozitie_boq_id=pz.id, proiect_id=p.id, an=2026, luna=3,
        cantitate_executata=Decimal(str(valoare_luna)),
        valoare_calculata=Decimal(str(valoare_luna)),
        validat=True, validat_de_id=admin_user_id,
    )
    db.session.add(cant); db.session.commit()
    return c.id


def _seteaza_valoare_luna(db, PozitieBoQ, CantitateExecutataLunara, valoare_luna):
    """
    Modifica cantitatea validata a pozitiei RET-001 pe luna 3/2026 la `valoare_luna`
    (pret 1 RON/unitate -> cantitate = valoare). Simuleaza validarea de cantitati
    noi inainte de o regenerare a situatiei.
    """
    pz = PozitieBoQ.query.filter_by(cod_articol='RET-001').first()
    cant = CantitateExecutataLunara.query.filter_by(
        pozitie_boq_id=pz.id, an=2026, luna=3).first()
    cant.cantitate_executata = Decimal(str(valoare_luna))
    cant.valoare_calculata = Decimal(str(valoare_luna))
    db.session.commit()


def test_modele_au_coloane_retentii(app):
    """Coloanele aditive exista pe SituatieLunara si Contract."""
    from models import SituatieLunara, Contract
    for col in ('retentie_procent', 'retentie_suma', 'garantie_bex_suma',
                'avans_recuperat', 'plata_neta'):
        assert hasattr(SituatieLunara, col), f'lipseste SituatieLunara.{col}'
    for col in ('retentie_procent_default', 'garantie_bex_procent'):
        assert hasattr(Contract, col), f'lipseste Contract.{col}'


def test_plata_neta_valori_concrete(app, admin_user):
    """
    100k valoare luna, retentie 5%, garantie 5%, avans recuperat 10k -> 80k.
      retentie  = 100000 * 5% = 5000
      garantie  = 100000 * 5% = 5000
      plata neta= 100000 - 5000 - 5000 - 10000 = 80000
    """
    from models import (
        db, Proiect, Contract, OfertaContract, PozitieBoQ,
        CantitateExecutataLunara, SituatieLunara,
    )
    from services.situatii import genereaza_situatie
    from models import Utilizator
    with app.app_context():
        uid = Utilizator.query.filter_by(email='admin_test@test.local').first().id
        set_flag('situatii-retentii', True, commit=True)
        cid = _seed_contract_cu_cantitati(
            db, Proiect, Contract, OfertaContract, PozitieBoQ,
            CantitateExecutataLunara, uid,
            valoare_luna=100000, retentie_pct=5, garantie_pct=5)
        s = genereaza_situatie(cid, 2026, 3, uid)
        # Avansul recuperat e o decizie comerciala -> il setam pe situatie si
        # regeneram pentru a recalcula plata neta cu avansul inclus.
        s.avans_recuperat = Decimal('10000')
        db.session.commit()
        s = genereaza_situatie(cid, 2026, 3, uid)

        assert s.valoare_totala_luna == Decimal('100000.00')
        assert s.retentie_procent == Decimal('5.00')
        assert s.retentie_suma == Decimal('5000.00')
        assert s.garantie_bex_suma == Decimal('5000.00')
        assert s.avans_recuperat == Decimal('10000.00')
        assert s.plata_neta == Decimal('80000.00')


def test_regenerare_populeaza_coloanele(app, admin_user):
    """Cu flag ON, regenerarea populeaza retentie/garantie/plata neta din contract."""
    from models import (
        db, Proiect, Contract, OfertaContract, PozitieBoQ,
        CantitateExecutataLunara, SituatieLunara,
    )
    from services.situatii import genereaza_situatie
    from models import Utilizator
    with app.app_context():
        uid = Utilizator.query.filter_by(email='admin_test@test.local').first().id
        set_flag('situatii-retentii', True, commit=True)
        cid = _seed_contract_cu_cantitati(
            db, Proiect, Contract, OfertaContract, PozitieBoQ,
            CantitateExecutataLunara, uid,
            valoare_luna=20000, retentie_pct=10, garantie_pct=0)
        s = genereaza_situatie(cid, 2026, 3, uid)
        # 20000 * 10% = 2000 retentie; garantie 0; avans 0 -> plata neta 18000
        assert s.retentie_suma == Decimal('2000.00')
        assert s.garantie_bex_suma == Decimal('0.00')
        assert s.plata_neta == Decimal('18000.00')


def test_regresie_flag_off_coloane_null(app, admin_user):
    """
    Regresie: cu flag 'situatii-retentii' OFF, coloanele noi raman NULL si
    situatia ramane identica cu cea istorica (valoare_luna neschimbata).
    """
    from models import (
        db, Proiect, Contract, OfertaContract, PozitieBoQ,
        CantitateExecutataLunara, SituatieLunara,
    )
    from services.situatii import genereaza_situatie
    from models import Utilizator
    with app.app_context():
        uid = Utilizator.query.filter_by(email='admin_test@test.local').first().id
        # Flag explicit OFF (default oricum, dar fim expliciti)
        set_flag('situatii-retentii', False, commit=True)
        cid = _seed_contract_cu_cantitati(
            db, Proiect, Contract, OfertaContract, PozitieBoQ,
            CantitateExecutataLunara, uid,
            valoare_luna=100000, retentie_pct=5, garantie_pct=5)
        s = genereaza_situatie(cid, 2026, 3, uid)

        # Calculul istoric ramane intact
        assert s.valoare_totala_luna == Decimal('100000.00')
        # Coloanele noi NU sunt atinse cu flag OFF
        assert s.retentie_procent is None
        assert s.retentie_suma is None
        assert s.garantie_bex_suma is None
        assert s.avans_recuperat is None
        assert s.plata_neta is None


def test_regenerare_dupa_crestere_valoare_recalculeaza_sumele(app, admin_user):
    """
    Regresie financiara (bug CRITIC): la regenerare dupa cresterea valorii lunii,
    retentia + garantia trebuie sa URMAREASCA noua valoare, nu sa ramana inghetate
    la valoarea primei generari.

    gen1: 100k @ 5% retentie / 10% garantie -> retentie 5000, garantie 10000.
    Validam cantitati noi -> valoare luna 200k. Regeneram.
    Asteptat: retentie 10000, garantie 20000, plata neta 170000.
    (Codul vechi inghetase: retentie 5000, garantie 10000, plata neta 185000.)
    """
    from models import (
        db, Proiect, Contract, OfertaContract, PozitieBoQ,
        CantitateExecutataLunara, SituatieLunara,
    )
    from services.situatii import genereaza_situatie
    from models import Utilizator
    with app.app_context():
        uid = Utilizator.query.filter_by(email='admin_test@test.local').first().id
        set_flag('situatii-retentii', True, commit=True)
        cid = _seed_contract_cu_cantitati(
            db, Proiect, Contract, OfertaContract, PozitieBoQ,
            CantitateExecutataLunara, uid,
            valoare_luna=100000, retentie_pct=5, garantie_pct=10)
        s = genereaza_situatie(cid, 2026, 3, uid)
        assert s.retentie_suma == Decimal('5000.00')
        assert s.garantie_bex_suma == Decimal('10000.00')
        assert s.plata_neta == Decimal('85000.00')

        # Validare cantitati noi -> valoare luna creste la 200k; regeneram.
        _seteaza_valoare_luna(db, PozitieBoQ, CantitateExecutataLunara, 200000)
        s = genereaza_situatie(cid, 2026, 3, uid)

        assert s.valoare_totala_luna == Decimal('200000.00')
        assert s.retentie_suma == Decimal('10000.00')
        assert s.garantie_bex_suma == Decimal('20000.00')
        # plata neta se reconciliaza: 200000 - 10000 - 20000 - 0 = 170000
        assert s.plata_neta == Decimal('170000.00')


def test_regenerare_fara_garantie_recalculeaza_retentia(app, admin_user):
    """
    Acelasi bug, scenariu fara garantie (garantie 0%), valoare 100k -> 300k @ 5%:
    retentia trebuie sa devina 15000 (300000*5%), nu sa ramana 5000.
    """
    from models import (
        db, Proiect, Contract, OfertaContract, PozitieBoQ,
        CantitateExecutataLunara, SituatieLunara,
    )
    from services.situatii import genereaza_situatie
    from models import Utilizator
    with app.app_context():
        uid = Utilizator.query.filter_by(email='admin_test@test.local').first().id
        set_flag('situatii-retentii', True, commit=True)
        cid = _seed_contract_cu_cantitati(
            db, Proiect, Contract, OfertaContract, PozitieBoQ,
            CantitateExecutataLunara, uid,
            valoare_luna=100000, retentie_pct=5, garantie_pct=0)
        s = genereaza_situatie(cid, 2026, 3, uid)
        assert s.retentie_suma == Decimal('5000.00')

        _seteaza_valoare_luna(db, PozitieBoQ, CantitateExecutataLunara, 300000)
        s = genereaza_situatie(cid, 2026, 3, uid)

        assert s.valoare_totala_luna == Decimal('300000.00')
        assert s.retentie_suma == Decimal('15000.00')
        assert s.plata_neta == Decimal('285000.00')


def test_editare_manuala_pastrata_la_regenerare(app, admin_user):
    """
    O editare manuala reala (marcata cu retentii_editate_manual=True) NU e
    suprascrisa din procent * valoare_luna la o regenerare ulterioara: sumele
    introduse manual se pastreaza si se recalculeaza doar plata neta din noua
    valoare a lunii.

    Simulam editarea manuala setand sumele + flag-ul (ca ruta situatie_retentii).
    """
    from models import (
        db, Proiect, Contract, OfertaContract, PozitieBoQ,
        CantitateExecutataLunara, SituatieLunara,
    )
    from services.situatii import genereaza_situatie
    from models import Utilizator
    with app.app_context():
        uid = Utilizator.query.filter_by(email='admin_test@test.local').first().id
        set_flag('situatii-retentii', True, commit=True)
        cid = _seed_contract_cu_cantitati(
            db, Proiect, Contract, OfertaContract, PozitieBoQ,
            CantitateExecutataLunara, uid,
            valoare_luna=100000, retentie_pct=5, garantie_pct=10)
        s = genereaza_situatie(cid, 2026, 3, uid)

        # Editare manuala: sume fixate (ex. acord cu beneficiarul), flag ON.
        s.retentie_procent = Decimal('5.00')
        s.retentie_suma = Decimal('7777.00')
        s.garantie_bex_suma = Decimal('3333.00')
        s.avans_recuperat = Decimal('0')
        s.retentii_editate_manual = True
        db.session.commit()

        # Regenerare la valoare schimbata: sumele manuale raman; doar plata neta
        # se recalculeaza din noua valoare a lunii.
        _seteaza_valoare_luna(db, PozitieBoQ, CantitateExecutataLunara, 200000)
        s = genereaza_situatie(cid, 2026, 3, uid)

        assert s.valoare_totala_luna == Decimal('200000.00')
        assert s.retentie_suma == Decimal('7777.00')
        assert s.garantie_bex_suma == Decimal('3333.00')
        # plata neta = 200000 - 7777 - 3333 - 0 = 188890
        assert s.plata_neta == Decimal('188890.00')
