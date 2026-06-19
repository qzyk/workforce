"""
Unit tests pentru services/sporuri.py (Workforce Faza 2).

Doua obiective:
1. ECHIVALENTA: noua functie calcul_ore(...) produce EXACT acelasi rezultat ca
   vechea logica de calcul ore (oracolul _calcul_ore_vechi de mai jos, copie
   fidela a fostei routes.pontaje.calculate_hours) pe cazurile istorice:
   ziua normala, ore suplimentare, sambata, duminica, sarbatoare legala, tura
   de noapte, tipuri speciale (co/cm/invoiere), input invalid.
2. SPOR NOAPTE: cand include_spor_noapte=True, orele din fereastra 22:00-06:00
   sunt calculate corect; cand False (sau flag OFF prin wrapper), spor_noapte
   ramane None si restul rezultatului e neschimbat (regresie).
"""

from datetime import date

import pytest

from services.sporuri import calcul_ore, detecteaza_tip_zi, este_tura_noapte


# ============================================================
# ORACOL - copia fidela a vechii routes.pontaje.calculate_hours
# (inainte de extragerea in serviciu). Folosit ca referinta de echivalenta.
# NU consulta sarbatori (le pasam separat la cazurile fara data).
# ============================================================

def _calcul_ore_vechi(ora_start, ora_sfarsit, tip_zi, is_sarbatoare=False,
                      data_pontaj=None):
    try:
        h1, m1 = map(int, ora_start.split(':'))
        h2, m2 = map(int, ora_sfarsit.split(':'))
    except (ValueError, AttributeError):
        return {'ore_lucrate': 0, 'ore_normale': 0, 'ore_supl_50': 0, 'ore_supl_100': 0}

    total_min = (h2 * 60 + m2) - (h1 * 60 + m1)
    if total_min <= 0:
        total_min += 24 * 60  # tura de noapte

    if total_min > 12 * 60:
        total_min = 12 * 60

    if total_min > 6 * 60:
        total_min -= 30

    ore_lucrate = round(total_min / 60, 2)

    if data_pontaj and tip_zi == 'lucratoare':
        dow = data_pontaj.weekday()
        if is_sarbatoare:
            tip_zi = 'sarbatoare_legala'
        elif dow == 5:
            tip_zi = 'sambata'
        elif dow == 6:
            tip_zi = 'duminica'

    ore_normale = 0
    ore_supl_50 = 0
    ore_supl_100 = 0

    if tip_zi in ('duminica', 'sarbatoare_legala'):
        ore_supl_100 = ore_lucrate
    elif tip_zi == 'sambata':
        ore_supl_50 = ore_lucrate
    elif tip_zi in ('co', 'cm', 'invoiere'):
        ore_normale = ore_lucrate
    else:
        ore_normale = min(8, ore_lucrate)
        extra = max(0, ore_lucrate - 8)
        if extra > 0:
            ore_supl_50 = min(2, extra)
            ore_supl_100 = max(0, extra - 2)

    return {
        'ore_lucrate': ore_lucrate,
        'ore_normale': round(ore_normale, 2),
        'ore_supl_50': round(ore_supl_50, 2),
        'ore_supl_100': round(ore_supl_100, 2),
        'tip_zi': tip_zi,
    }


# Grila de cazuri istorice (fara data => fara detectie automata, deci nu
# atingem DB-ul de sarbatori; tip_zi e explicit).
_CAZURI_FARA_DATA = [
    # (ora_start, ora_sfarsit, tip_zi)
    ('08:00', '16:00', 'lucratoare'),   # exact 8h, fara suplimentare
    ('08:00', '17:00', 'lucratoare'),   # 9h -> 8 normale + 1 supl 50
    ('08:00', '19:00', 'lucratoare'),   # 11h cu pauza -> supl 50 + 100
    ('08:00', '22:00', 'lucratoare'),   # depaseste 12h -> plafonat
    ('08:00', '18:00', 'sambata'),      # sambata -> tot 50
    ('08:00', '17:00', 'duminica'),     # duminica -> tot 100
    ('08:00', '17:00', 'sarbatoare_legala'),  # sarbatoare -> tot 100
    ('08:00', '16:00', 'co'),           # concediu odihna - speciala
    ('08:00', '16:00', 'cm'),           # concediu medical - speciala
    ('08:00', '16:00', 'invoiere'),     # invoiere - speciala
    ('22:00', '06:00', 'lucratoare'),   # tura de noapte (wrap +24h)
    ('06:00', '06:00', 'lucratoare'),   # 0 -> wrap la 24h, plafonat 12h
    ('bad', 'input', 'lucratoare'),     # format invalid
    ('08:00', None, 'lucratoare'),      # None -> AttributeError guard
]


class TestEchivalentaCalculOre:
    """Noua calcul_ore == vechea logica pe cazurile istorice (fara spor noapte)."""

    @pytest.mark.parametrize('ora_start,ora_sfarsit,tip_zi', _CAZURI_FARA_DATA)
    def test_echivalenta_fara_data(self, ora_start, ora_sfarsit, tip_zi):
        vechi = _calcul_ore_vechi(ora_start, ora_sfarsit, tip_zi)
        nou = calcul_ore(ora_start, ora_sfarsit, tip_zi)
        # Comparam toate cheile istorice; ignoram spor_noapte (nou, additiv).
        for cheie in ('ore_lucrate', 'ore_normale', 'ore_supl_50', 'ore_supl_100'):
            assert nou.get(cheie) == vechi.get(cheie), (
                f'cheie {cheie}: nou={nou.get(cheie)} vechi={vechi.get(cheie)} '
                f'pentru {ora_start}-{ora_sfarsit} {tip_zi}'
            )
        # tip_zi exista in ambele pentru cazurile valide
        if 'tip_zi' in vechi:
            assert nou.get('tip_zi') == vechi.get('tip_zi')

    def test_echivalenta_cu_detectie_data_lucratoare(self, app):
        """Cu data, fara sarbatoare: detectie automata sambata/duminica identica."""
        with app.app_context():
            # Luni 2025-09-01 (lucratoare)
            d = date(2025, 9, 1)
            vechi = _calcul_ore_vechi('08:00', '17:00', 'lucratoare',
                                      is_sarbatoare=False, data_pontaj=d)
            nou = calcul_ore('08:00', '17:00', 'lucratoare', d)
            assert nou['tip_zi'] == vechi['tip_zi'] == 'lucratoare'
            assert nou['ore_normale'] == vechi['ore_normale']

    def test_echivalenta_detectie_sambata(self, app):
        with app.app_context():
            d = date(2025, 9, 6)  # sambata
            vechi = _calcul_ore_vechi('08:00', '18:00', 'lucratoare',
                                      is_sarbatoare=False, data_pontaj=d)
            nou = calcul_ore('08:00', '18:00', 'lucratoare', d)
            assert nou['tip_zi'] == vechi['tip_zi'] == 'sambata'
            assert nou['ore_supl_50'] == vechi['ore_supl_50']

    def test_echivalenta_detectie_duminica(self, app):
        with app.app_context():
            d = date(2025, 9, 7)  # duminica
            vechi = _calcul_ore_vechi('08:00', '17:00', 'lucratoare',
                                      is_sarbatoare=False, data_pontaj=d)
            nou = calcul_ore('08:00', '17:00', 'lucratoare', d)
            assert nou['tip_zi'] == vechi['tip_zi'] == 'duminica'
            assert nou['ore_supl_100'] == vechi['ore_supl_100']


class TestValoriCunoscute:
    """Valori concrete pe cazurile istorice (siguranta suplimentara)."""

    def test_ore_8_la_16_cu_pauza(self):
        # 08:00-16:00 = 8h brut > 6h -> se deduce pauza 30min = 7.5h
        # (comportament identic cu vechiul calculate_hours)
        r = calcul_ore('08:00', '16:00', 'lucratoare')
        assert r['ore_lucrate'] == 7.5
        assert r['ore_normale'] == 7.5
        assert r['ore_supl_50'] == 0
        assert r['ore_supl_100'] == 0

    def test_ore_normale_exact_8_fara_pauza(self):
        # Pentru a obtine 8h nete fara suplimentare: 08:00-16:30 = 8.5h brut
        # -30 pauza = 8h, toate normale.
        r = calcul_ore('08:00', '16:30', 'lucratoare')
        assert r['ore_lucrate'] == 8.0
        assert r['ore_normale'] == 8.0
        assert r['ore_supl_50'] == 0
        assert r['ore_supl_100'] == 0

    def test_ore_suplimentare_50(self):
        # 09:00-19:00 = 10h brut, -30min pauza = 9.5h -> 8 normale + 1.5 supl 50
        r = calcul_ore('09:00', '19:00', 'lucratoare')
        assert r['ore_lucrate'] == 9.5
        assert r['ore_normale'] == 8.0
        assert r['ore_supl_50'] == 1.5
        assert r['ore_supl_100'] == 0

    def test_ore_suplimentare_50_si_100(self):
        # 06:00-19:00 = 13h -> plafon 12h -> -30 pauza = 11.5h
        # 8 normale, extra 3.5 -> supl_50=2, supl_100=1.5
        r = calcul_ore('06:00', '19:00', 'lucratoare')
        assert r['ore_lucrate'] == 11.5
        assert r['ore_normale'] == 8.0
        assert r['ore_supl_50'] == 2.0
        assert r['ore_supl_100'] == 1.5

    def test_sambata_tot_50(self):
        r = calcul_ore('08:00', '18:00', 'sambata')
        # 10h - 30min = 9.5h, toate 50%
        assert r['ore_supl_50'] == 9.5
        assert r['ore_supl_100'] == 0

    def test_duminica_tot_100(self):
        r = calcul_ore('08:00', '17:00', 'duminica')
        # 9h - 30 = 8.5h, toate 100%
        assert r['ore_supl_100'] == 8.5
        assert r['ore_supl_50'] == 0

    def test_input_invalid(self):
        r = calcul_ore('xx', 'yy', 'lucratoare')
        assert r['ore_lucrate'] == 0
        assert r['spor_noapte'] is None


class TestSporNoapte:
    """Calculul orelor de noapte (fereastra 22:00-06:00)."""

    def test_spor_noapte_none_implicit(self):
        """Fara include_spor_noapte, spor_noapte e None (comportament istoric)."""
        r = calcul_ore('22:00', '06:00', 'lucratoare')
        assert r['spor_noapte'] is None

    def test_spor_noapte_none_pe_zi(self):
        """Zi normala 08-16, chiar cu flag pe calcul: 0 ore de noapte."""
        r = calcul_ore('08:00', '16:00', 'lucratoare', include_spor_noapte=True)
        assert r['spor_noapte'] == 0.0

    def test_spor_noapte_tura_completa_noapte(self):
        """22:00-06:00 = 8h brut, integral in fereastra de noapte.
        Orele de noapte se masoara INAINTE de pauza (8h), dar ore_lucrate scade
        cu pauza (7.5h)."""
        r = calcul_ore('22:00', '06:00', 'lucratoare', include_spor_noapte=True)
        assert r['spor_noapte'] == 8.0
        assert r['ore_lucrate'] == 7.5  # 8h - 30min pauza

    def test_spor_noapte_partial_seara(self):
        """20:00-24:00: doar 22:00-24:00 sunt de noapte = 2h.
        Brut 4h <= 6h deci fara deducere pauza."""
        r = calcul_ore('20:00', '24:00', 'lucratoare', include_spor_noapte=True)
        assert r['spor_noapte'] == 2.0

    def test_spor_noapte_partial_dimineata(self):
        """04:00-10:00: doar 04:00-06:00 sunt de noapte = 2h."""
        r = calcul_ore('04:00', '10:00', 'lucratoare', include_spor_noapte=True)
        assert r['spor_noapte'] == 2.0

    def test_spor_noapte_zi_fara_noapte(self):
        """09:00-17:00: nicio ora de noapte."""
        r = calcul_ore('09:00', '17:00', 'lucratoare', include_spor_noapte=True)
        assert r['spor_noapte'] == 0.0

    def test_spor_noapte_nu_schimba_orele(self):
        """Activarea sporului de noapte NU schimba ore_lucrate/normale/supl."""
        fara = calcul_ore('22:00', '06:00', 'lucratoare', include_spor_noapte=False)
        cu = calcul_ore('22:00', '06:00', 'lucratoare', include_spor_noapte=True)
        for cheie in ('ore_lucrate', 'ore_normale', 'ore_supl_50',
                      'ore_supl_100', 'tip_zi'):
            assert fara[cheie] == cu[cheie]
        assert fara['spor_noapte'] is None
        assert cu['spor_noapte'] == 8.0

    def test_este_tura_noapte(self):
        assert este_tura_noapte('22:00', '06:00') is True
        assert este_tura_noapte('20:00', '23:00') is True   # atinge 22-24
        assert este_tura_noapte('08:00', '16:00') is False
        assert este_tura_noapte('bad', 'input') is False


class TestDetecteazaTipZi:
    """detecteaza_tip_zi == vechiul _detect_tip_zi."""

    def test_none_data(self, app):
        with app.app_context():
            assert detecteaza_tip_zi(None) == 'lucratoare'

    def test_sambata(self, app):
        with app.app_context():
            assert detecteaza_tip_zi(date(2025, 9, 6)) == 'sambata'

    def test_duminica(self, app):
        with app.app_context():
            assert detecteaza_tip_zi(date(2025, 9, 7)) == 'duminica'

    def test_lucratoare(self, app):
        with app.app_context():
            assert detecteaza_tip_zi(date(2025, 9, 1)) == 'lucratoare'

    def test_sarbatoare_legala(self, app):
        """Cu o sarbatoare in DB, detectia o prinde."""
        from models import db, SarbatoareLegala
        with app.app_context():
            d = date(2031, 1, 1)  # an indepartat ca sa nu fie deja in DB
            existenta = SarbatoareLegala.query.filter_by(data=d).first()
            creata = False
            if not existenta:
                s = SarbatoareLegala(data=d, denumire='Test Anul Nou', an=2031)
                db.session.add(s)
                db.session.commit()
                creata = True
            try:
                assert detecteaza_tip_zi(d) == 'sarbatoare_legala'
            finally:
                if creata:
                    s2 = SarbatoareLegala.query.filter_by(data=d).first()
                    if s2:
                        db.session.delete(s2)
                        db.session.commit()


class TestWrapperFlagOFF:
    """
    Wrapper-ul routes.pontaje.calculate_hours respecta flag-ul (regresie).

    Flag-urile se evalueaza per tenant/request, deci folosim test_request_context()
    ca sa reproducem fidel mediul de productie (apel din interiorul unei rute).
    """

    def test_wrapper_flag_off_spor_none(self, app):
        from routes.pontaje import calculate_hours
        from services import feature_flags as ff
        with app.app_context():
            ff.set_flag('pontaj-spor-noapte', False)
        with app.test_request_context('/'):
            r = calculate_hours('22:00', '06:00', 'lucratoare')
            # Flag OFF -> spor_noapte None, comportament istoric
            assert r['spor_noapte'] is None
            assert r['ore_lucrate'] == 7.5

    def test_wrapper_flag_off_identic_cu_vechi(self, app):
        """Cu flag OFF, wrapper-ul == oracolul vechi pe cheile istorice."""
        from routes.pontaje import calculate_hours
        from services import feature_flags as ff
        with app.app_context():
            ff.set_flag('pontaj-spor-noapte', False)
        with app.test_request_context('/'):
            for ora_start, ora_sfarsit, tip_zi in _CAZURI_FARA_DATA:
                vechi = _calcul_ore_vechi(ora_start, ora_sfarsit, tip_zi)
                nou = calculate_hours(ora_start, ora_sfarsit, tip_zi)
                for cheie in ('ore_lucrate', 'ore_normale',
                              'ore_supl_50', 'ore_supl_100'):
                    assert nou.get(cheie) == vechi.get(cheie)

    def test_wrapper_flag_on_calculeaza_spor(self, app):
        from routes.pontaje import calculate_hours
        from services import feature_flags as ff
        with app.app_context():
            ff.set_flag('pontaj-spor-noapte', True)
        try:
            with app.test_request_context('/'):
                r = calculate_hours('22:00', '06:00', 'lucratoare')
                assert r['spor_noapte'] == 8.0
                # restul neschimbat
                assert r['ore_lucrate'] == 7.5
        finally:
            with app.app_context():
                ff.set_flag('pontaj-spor-noapte', False)

    def test_spor_noapte_activ_failsafe_off(self, app):
        """
        Helper-ul intern _spor_noapte_activ() degradeaza la False (OFF) daca
        evaluarea flag-ului ridica o exceptie (fail-safe), pastrand comportamentul
        istoric in afara unui context valid.
        """
        from routes import pontaje as rp
        with app.app_context():
            # Simulam o evaluare care esueaza (ex. context invalid).
            original = rp.is_enabled

            def _explodeaza(_key):
                raise RuntimeError('fara context')

            rp.is_enabled = _explodeaza
            try:
                assert rp._spor_noapte_activ() is False
            finally:
                rp.is_enabled = original
