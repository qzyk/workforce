"""
Unit tests pentru modelele workforce (Angajat, Proiect, Pontaj, RaportActivitate, Utilizator).
Focus pe properties + methods, fara dependinte de routes/templates.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest


# ============================================================
# UTILIZATOR
# ============================================================

class TestUtilizator:
    def test_set_check_password(self, app):
        from models import Utilizator
        with app.app_context():
            u = Utilizator(nume='X', prenume='Y', email='x@y.z', rol='admin')
            u.set_password('test123')
            assert u.parola_hash != 'test123'  # hashed
            assert u.check_password('test123') is True
            assert u.check_password('wrong') is False

    def test_get_full_name(self, app):
        from models import Utilizator
        with app.app_context():
            u = Utilizator(nume='Popescu', prenume='Ion', email='a@b.c', rol='operator')
            assert u.get_full_name() == 'Popescu Ion'

    def test_is_admin_property(self, app):
        from models import Utilizator
        with app.app_context():
            u_admin = Utilizator(nume='A', prenume='B', email='a@b.c', rol='admin')
            u_op = Utilizator(nume='A', prenume='B', email='a@b.c', rol='operator')
            assert u_admin.is_admin is True
            assert u_op.is_admin is False

    def test_is_manager_property(self, app):
        """is_manager == True pentru admin SI manager."""
        from models import Utilizator
        with app.app_context():
            u_admin = Utilizator(nume='A', prenume='B', email='a@b.c', rol='admin')
            u_mgr = Utilizator(nume='A', prenume='B', email='a@b.c', rol='manager')
            u_op = Utilizator(nume='A', prenume='B', email='a@b.c', rol='operator')
            assert u_admin.is_manager is True
            assert u_mgr.is_manager is True
            assert u_op.is_manager is False


# ============================================================
# ANGAJAT
# ============================================================

class TestAngajat:
    def test_nume_complet(self, app):
        from models import Angajat
        with app.app_context():
            a = Angajat(nume='Marin', prenume='Ion', cnp='1234567890123',
                       functie='Inginer', data_angajare=date(2024, 1, 1))
            assert a.nume_complet == 'Marin Ion'

    def test_tarif_orar_calculat_din_salariu(self, app):
        from models import Angajat
        with app.app_context():
            a = Angajat(nume='X', prenume='Y', cnp='1234567890123',
                       functie='Inginer', data_angajare=date(2024, 1, 1),
                       salariu_baza=Decimal('5040.00'))
            # 5040 / 168 = 30
            assert a.tarif_orar == 30.0

    def test_tarif_orar_zero_fara_salariu(self, app):
        from models import Angajat
        with app.app_context():
            a = Angajat(nume='X', prenume='Y', cnp='1234567890123',
                       functie='Inginer', data_angajare=date(2024, 1, 1))
            assert a.tarif_orar == 0

    def test_varsta_calculata(self, app):
        from models import Angajat
        with app.app_context():
            today = date.today()
            # Persoana de exact 30 ani
            data_n = date(today.year - 30, today.month, max(1, today.day - 1))
            a = Angajat(nume='X', prenume='Y', cnp='1234567890123',
                       functie='Inginer', data_angajare=date(2024, 1, 1),
                       data_nasterii=data_n)
            assert a.varsta == 30

    def test_varsta_none_fara_data_nasterii(self, app):
        from models import Angajat
        with app.app_context():
            a = Angajat(nume='X', prenume='Y', cnp='1234567890123',
                       functie='Inginer', data_angajare=date(2024, 1, 1))
            assert a.varsta is None


# ============================================================
# PROIECT
# ============================================================

class TestProiect:
    def test_progres_calculation(self, app):
        from models import Proiect
        with app.app_context():
            today = date.today()
            # Proiect inceput acum 50 zile, durata totala 100 zile -> progres 50%
            p = Proiect(cod_proiect='X', nume='X',
                       data_start=today - timedelta(days=50),
                       data_sfarsit_planificat=today + timedelta(days=50))
            assert 45 <= p.progres <= 55  # range pentru round-off

    def test_progres_100_dupa_termen(self, app):
        from models import Proiect
        with app.app_context():
            p = Proiect(cod_proiect='X', nume='X',
                       data_start=date(2020, 1, 1),
                       data_sfarsit_planificat=date(2020, 12, 31))
            assert p.progres == 100

    def test_progres_0_inainte_de_start(self, app):
        from models import Proiect
        with app.app_context():
            today = date.today()
            p = Proiect(cod_proiect='X', nume='X',
                       data_start=today + timedelta(days=10),
                       data_sfarsit_planificat=today + timedelta(days=110))
            assert p.progres == 0

    def test_zile_ramase(self, app):
        from models import Proiect
        with app.app_context():
            today = date.today()
            p = Proiect(cod_proiect='X', nume='X',
                       data_start=today,
                       data_sfarsit_planificat=today + timedelta(days=30))
            assert p.zile_ramase == 30

    def test_zile_ramase_dupa_termen(self, app):
        from models import Proiect
        with app.app_context():
            p = Proiect(cod_proiect='X', nume='X',
                       data_start=date(2020, 1, 1),
                       data_sfarsit_planificat=date(2020, 6, 1))
            assert p.zile_ramase == 0


# ============================================================
# PONTAJ - calcul ore
# ============================================================

class TestPontajCalculOre:
    def test_calcul_ore_normale(self, app):
        from models import Pontaj
        with app.app_context():
            p = Pontaj(angajat_id=1, proiect_id=1, data=date(2025, 9, 1),
                      ora_start='08:00', ora_sfarsit='17:00', tip_zi='lucratoare')
            p.calculeaza_ore()
            assert float(p.ore_lucrate) == 9.0
            assert float(p.ore_normale) == 8.0
            assert float(p.ore_suplimentare_50) == 1.0
            assert float(p.ore_suplimentare_100) == 0.0

    def test_calcul_ore_8h_fara_suplimentare(self, app):
        from models import Pontaj
        with app.app_context():
            p = Pontaj(angajat_id=1, proiect_id=1, data=date(2025, 9, 1),
                      ora_start='08:00', ora_sfarsit='16:00', tip_zi='lucratoare')
            p.calculeaza_ore()
            assert float(p.ore_lucrate) == 8.0
            assert float(p.ore_normale) == 8.0
            assert float(p.ore_suplimentare_50) == 0.0
            assert float(p.ore_suplimentare_100) == 0.0

    def test_calcul_ore_sambata_suplimentare_100(self, app):
        """Sambata: tot ce depaseste 8h e suplimentar 100%."""
        from models import Pontaj
        with app.app_context():
            p = Pontaj(angajat_id=1, proiect_id=1, data=date(2025, 9, 6),
                      ora_start='08:00', ora_sfarsit='18:00', tip_zi='sambata')
            p.calculeaza_ore()
            assert float(p.ore_lucrate) == 10.0
            assert float(p.ore_suplimentare_100) == 2.0
            assert float(p.ore_suplimentare_50) == 0.0

    def test_calcul_ore_duminica(self, app):
        from models import Pontaj
        with app.app_context():
            p = Pontaj(angajat_id=1, proiect_id=1, data=date(2025, 9, 7),
                      ora_start='08:00', ora_sfarsit='17:00', tip_zi='duminica')
            p.calculeaza_ore()
            assert float(p.ore_lucrate) == 9.0
            assert float(p.ore_suplimentare_100) == 1.0

    def test_calcul_ore_sarbatoare_legala(self, app):
        from models import Pontaj
        with app.app_context():
            p = Pontaj(angajat_id=1, proiect_id=1, data=date(2025, 12, 25),
                      ora_start='08:00', ora_sfarsit='17:00', tip_zi='sarbatoare_legala')
            p.calculeaza_ore()
            assert float(p.ore_suplimentare_100) == 1.0

    def test_calcul_ore_tura_de_noapte(self, app):
        """Daca ora_sfarsit < ora_start, e tura de noapte (+24h)."""
        from models import Pontaj
        with app.app_context():
            p = Pontaj(angajat_id=1, proiect_id=1, data=date(2025, 9, 1),
                      ora_start='22:00', ora_sfarsit='06:00', tip_zi='lucratoare')
            p.calculeaza_ore()
            assert float(p.ore_lucrate) == 8.0
            assert float(p.ore_normale) == 8.0


# ============================================================
# RAPORT ACTIVITATE
# ============================================================

class TestRaportActivitate:
    def test_calculeaza_perioada_saptamanala(self, app):
        from models import RaportActivitate
        with app.app_context():
            a = RaportActivitate(angajat_id=1, proiect_id=1, data=date(2025, 9, 1),  # luni
                                tip_activitate='saptamanala',
                                activitate_principala='X')
            a.calculeaza_perioada()
            # 2025-09-01 e ISO week 36
            assert a.numar_saptamana == 36

    def test_calculeaza_perioada_lunara(self, app):
        from models import RaportActivitate
        with app.app_context():
            a = RaportActivitate(angajat_id=1, proiect_id=1, data=date(2025, 9, 15),
                                tip_activitate='lunara',
                                activitate_principala='X')
            a.calculeaza_perioada()
            assert a.luna_an == '2025-09'

    def test_calculeaza_perioada_zilnica_no_change(self, app):
        from models import RaportActivitate
        with app.app_context():
            a = RaportActivitate(angajat_id=1, proiect_id=1, data=date(2025, 9, 15),
                                tip_activitate='zilnica',
                                activitate_principala='X')
            a.calculeaza_perioada()
            assert a.numar_saptamana is None
            assert a.luna_an is None

    def test_perioada_text_saptamanala(self, app):
        from models import RaportActivitate
        with app.app_context():
            a = RaportActivitate(angajat_id=1, proiect_id=1, data=date(2025, 9, 1),
                                tip_activitate='saptamanala',
                                activitate_principala='X', numar_saptamana=36)
            assert 'Saptamana 36' in a.perioada_text

    def test_perioada_text_lunara(self, app):
        from models import RaportActivitate
        with app.app_context():
            a = RaportActivitate(angajat_id=1, proiect_id=1, data=date(2025, 9, 15),
                                tip_activitate='lunara',
                                activitate_principala='X', luna_an='2025-09')
            assert 'Septembrie' in a.perioada_text or 'septembrie' in a.perioada_text.lower()
            assert '2025' in a.perioada_text

    def test_proiecte_lista_din_json(self, app):
        from models import RaportActivitate
        with app.app_context():
            a = RaportActivitate(angajat_id=1, proiect_id=1, data=date(2025, 9, 1),
                                tip_activitate='zilnica',
                                activitate_principala='X', proiecte_ids='[1, 2, 3]')
            assert a.proiecte_lista == [1, 2, 3]

    def test_proiecte_lista_fallback_la_proiect_id(self, app):
        from models import RaportActivitate
        with app.app_context():
            a = RaportActivitate(angajat_id=1, proiect_id=42, data=date(2025, 9, 1),
                                tip_activitate='zilnica',
                                activitate_principala='X', proiecte_ids=None)
            assert a.proiecte_lista == [42]

    def test_proiecte_lista_invalid_json(self, app):
        from models import RaportActivitate
        with app.app_context():
            a = RaportActivitate(angajat_id=1, proiect_id=42, data=date(2025, 9, 1),
                                tip_activitate='zilnica',
                                activitate_principala='X', proiecte_ids='not-json')
            assert a.proiecte_lista == [42]  # fallback

    def test_subordonati_lista(self, app):
        from models import RaportActivitate
        with app.app_context():
            a = RaportActivitate(angajat_id=1, proiect_id=1, data=date(2025, 9, 1),
                                tip_activitate='zilnica',
                                activitate_principala='X', subordonati_ids='[5, 7, 9]')
            assert a.subordonati_lista == [5, 7, 9]

    def test_detalii_pe_zi_lista(self, app):
        from models import RaportActivitate
        with app.app_context():
            data_str = '[{"data":"2025-09-01","text":"Lucru","ore":8}]'
            a = RaportActivitate(angajat_id=1, proiect_id=1, data=date(2025, 9, 1),
                                tip_activitate='saptamanala',
                                activitate_principala='X', detalii_pe_zi=data_str)
            lst = a.detalii_pe_zi_lista
            assert len(lst) == 1
            assert lst[0]['text'] == 'Lucru'
            assert lst[0]['ore'] == 8
            assert lst[0]['_data_obj'] == date(2025, 9, 1)

    def test_detalii_pentru_data_match(self, app):
        from models import RaportActivitate
        with app.app_context():
            data_str = '[{"data":"2025-09-01","text":"L"},{"data":"2025-09-02","text":"M"}]'
            a = RaportActivitate(angajat_id=1, proiect_id=1, data=date(2025, 9, 1),
                                tip_activitate='saptamanala',
                                activitate_principala='X', detalii_pe_zi=data_str)
            det = a.detalii_pentru_data(date(2025, 9, 2))
            assert det is not None
            assert det['text'] == 'M'
            assert a.detalii_pentru_data(date(2025, 9, 10)) is None

    def test_status_executie_badge_class(self, app):
        from models import RaportActivitate
        with app.app_context():
            a = RaportActivitate(angajat_id=1, proiect_id=1, data=date(2025, 9, 1),
                                tip_activitate='zilnica',
                                activitate_principala='X', status_executie='finalizata')
            assert a.status_executie_badge_class == 'badge-aprobat'

    def test_tip_badge_class(self, app):
        from models import RaportActivitate
        with app.app_context():
            for tip, exp in [('zilnica', 'badge-tip-zilnica'),
                            ('saptamanala', 'badge-tip-saptamanala'),
                            ('lunara', 'badge-tip-lunara')]:
                a = RaportActivitate(angajat_id=1, proiect_id=1, data=date(2025, 9, 1),
                                    tip_activitate=tip,
                                    activitate_principala='X')
                assert a.tip_badge_class == exp

    def test_activitate_scurta_truncates(self, app):
        from models import RaportActivitate
        with app.app_context():
            text_lung = 'A' * 100
            a = RaportActivitate(angajat_id=1, proiect_id=1, data=date(2025, 9, 1),
                                tip_activitate='zilnica',
                                activitate_principala=text_lung)
            assert len(a.activitate_scurta) <= 80
            assert a.activitate_scurta.endswith('...')
