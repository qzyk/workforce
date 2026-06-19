"""
Integrare: sporul de noapte se persista corect prin ruta de pontaj in masa,
gated pe flag-ul 'pontaj-spor-noapte'.

- Flag OFF (default): pontajul de noapte se salveaza cu spor_noapte NULL
  (comportament istoric, identic cu inainte de Faza 2).
- Flag ON: acelasi pontaj de noapte salveaza orele din fereastra 22:00-06:00
  in coloana spor_noapte.

Restul cheilor de ore (lucrate / normale / supl) raman neschimbate in ambele
cazuri - sporul de noapte e strict aditiv.
"""

from datetime import date

import pytest

from services import feature_flags as ff


def _adauga_pontaj_noapte(client, proiect_id, angajat_id, data_str):
    """Posteaza un pontaj de noapte (22:00-06:00) prin ruta adauga-multiplu."""
    return client.post('/pontaje/adauga-multiplu', data={
        'proiect_id': str(proiect_id),
        'data': data_str,
        'actiune': 'draft',
        'angajat_ids': [str(angajat_id)],
        f'ora_start_{angajat_id}': '22:00',
        f'ora_sfarsit_{angajat_id}': '06:00',
        f'tip_zi_{angajat_id}': 'lucratoare',
    }, follow_redirects=False)


class TestSporNoapteRuta:
    def test_flag_off_spor_noapte_nul(self, app, authenticated_client, workforce_basic):
        """Cu flag OFF, pontajul de noapte se salveaza fara spor (NULL)."""
        from models import db, Pontaj
        with app.app_context():
            ff.set_flag('pontaj-spor-noapte', False)
            # Curatam eventuale pontaje pe ziua de test
            Pontaj.query.filter_by(
                angajat_id=workforce_basic['angajat_id'],
                data=date(2025, 9, 8),
            ).delete()
            db.session.commit()

        resp = _adauga_pontaj_noapte(
            authenticated_client,
            workforce_basic['proiect_id'],
            workforce_basic['angajat_id'],
            '2025-09-08',
        )
        assert resp.status_code in (302, 200)

        with app.app_context():
            p = Pontaj.query.filter_by(
                angajat_id=workforce_basic['angajat_id'],
                data=date(2025, 9, 8),
            ).first()
            assert p is not None
            assert p.spor_noapte is None  # comportament istoric
            # orele de baza calculate corect (8h brut - 30min pauza = 7.5h)
            assert float(p.ore_lucrate) == 7.5
            # cleanup
            db.session.delete(p)
            db.session.commit()

    def test_flag_on_spor_noapte_calculat(self, app, authenticated_client, workforce_basic):
        """Cu flag ON, pontajul de noapte salveaza orele din fereastra 22-06."""
        from models import db, Pontaj
        with app.app_context():
            ff.set_flag('pontaj-spor-noapte', True)
            Pontaj.query.filter_by(
                angajat_id=workforce_basic['angajat_id'],
                data=date(2025, 9, 9),
            ).delete()
            db.session.commit()

        try:
            resp = _adauga_pontaj_noapte(
                authenticated_client,
                workforce_basic['proiect_id'],
                workforce_basic['angajat_id'],
                '2025-09-09',
            )
            assert resp.status_code in (302, 200)

            with app.app_context():
                p = Pontaj.query.filter_by(
                    angajat_id=workforce_basic['angajat_id'],
                    data=date(2025, 9, 9),
                ).first()
                assert p is not None
                # 22:00-06:00 = 8h integral in fereastra de noapte
                assert float(p.spor_noapte) == 8.0
                # orele de baza neschimbate fata de flag OFF
                assert float(p.ore_lucrate) == 7.5
                db.session.delete(p)
                db.session.commit()
        finally:
            with app.app_context():
                ff.set_flag('pontaj-spor-noapte', False)
