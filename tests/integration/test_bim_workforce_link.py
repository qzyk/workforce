"""
Integration tests pentru linkarea workforce <-> BIM:
- Activitate creata cu element_bim_id / spatiu_id / zona_id (FK populated)
- Filtre BIM pe panou: santier_id, cladire_id, tip_element
- Auto-derivare zona din spatiu
- Search global BIM
- Quick navigation (alte elemente in aceeasi zona)
"""

from datetime import date
import pytest


class TestActivitateLinkareBIM:
    """Salvare + citire activitate cu link BIM."""

    def test_create_activitate_cu_element_bim(self, app, authenticated_client,
                                               full_bim_hierarchy, workforce_basic):
        from models import db, RaportActivitate

        resp = authenticated_client.post('/activitati/adauga', data={
            'angajat_id': workforce_basic['angajat_id'],
            'proiect_ids[]': [workforce_basic['proiect_id']],
            'data': '2025-09-01',
            'tip_activitate': 'zilnica',
            'activitate_principala': 'TEST_BIM_LINK_E',
            'status_executie': 'planificata',
            'bim_element_id': full_bim_hierarchy['element_ahu'],
            'actiune': 'draft',
        }, follow_redirects=False)
        assert resp.status_code in (200, 302)

        with app.app_context():
            a = RaportActivitate.query.filter_by(
                activitate_principala='TEST_BIM_LINK_E'
            ).first()
            assert a is not None
            assert a.element_bim_id == full_bim_hierarchy['element_ahu']

    def test_create_activitate_cu_spatiu_si_auto_zona(self, app, authenticated_client,
                                                        full_bim_hierarchy, workforce_basic):
        """Cand se seteaza spatiu_id, zona_id se ia automat din spatiu."""
        from models import db, RaportActivitate, Spatiu, Zona
        # Pregatesc o zona si o atasez la spatiul lobby
        with app.app_context():
            sp = Spatiu.query.get(full_bim_hierarchy['spatiu_lobby'])
            cladire_id = sp.nivel.cladire_id
            z = Zona(cladire_id=cladire_id, nivel_id=sp.nivel_id,
                     cod='Z-PUB-T', nume='Zona Public Test')
            db.session.add(z); db.session.commit()
            sp.zona_id = z.id
            db.session.commit()
            zona_id = z.id

        resp = authenticated_client.post('/activitati/adauga', data={
            'angajat_id': workforce_basic['angajat_id'],
            'proiect_ids[]': [workforce_basic['proiect_id']],
            'data': '2025-09-01',
            'tip_activitate': 'zilnica',
            'activitate_principala': 'TEST_BIM_LINK_AUTO_Z',
            'status_executie': 'planificata',
            'bim_spatiu_id': full_bim_hierarchy['spatiu_lobby'],
            # bim_zona_id nu e setat -> trebuie auto-derivata
            'actiune': 'draft',
        }, follow_redirects=False)

        with app.app_context():
            a = RaportActivitate.query.filter_by(
                activitate_principala='TEST_BIM_LINK_AUTO_Z'
            ).first()
            assert a is not None
            assert a.spatiu_id == full_bim_hierarchy['spatiu_lobby']
            assert a.zona_id == zona_id  # auto-derivata

    def test_detaliu_activitate_afiseaza_context_bim(self, app, authenticated_client,
                                                       full_bim_hierarchy, workforce_basic):
        """Activitate cu element_bim_id setat -> detaliul afiseaza Context BIM."""
        from models import db, RaportActivitate

        # Create direct in DB (mai sigur decat prin form-ul testat)
        with app.app_context():
            a = RaportActivitate(
                angajat_id=workforce_basic['angajat_id'],
                proiect_id=workforce_basic['proiect_id'],
                data=None,
                tip_activitate='zilnica',
                activitate_principala='TEST_BIM_DETAIL',
                status='draft', status_executie='planificata',
                element_bim_id=full_bim_hierarchy['element_ahu'],
            )
            from datetime import date
            a.data = date(2025, 9, 1)
            db.session.add(a); db.session.commit()
            aid = a.id

        resp = authenticated_client.get(f'/activitati/{aid}')
        assert resp.status_code == 200
        # Cauta "Context BIM" sau codul element
        body = resp.data.decode('utf-8')
        # Aceasta sectiune apare DOAR daca activitate.element_bim e nu None
        assert 'Context BIM' in body or 'AHU-01' in body, \
            f'Context BIM nu apare in pagina detaliu (element_bim_id={full_bim_hierarchy["element_ahu"]})'


class TestPanouFiltreBIM:
    """Filtre BIM pe /activitati."""

    def test_filtru_santier(self, authenticated_client, full_bim_hierarchy):
        sid = full_bim_hierarchy['santier']
        resp = authenticated_client.get(f'/activitati/?santier_id={sid}')
        assert resp.status_code == 200

    def test_filtru_cladire(self, authenticated_client, full_bim_hierarchy):
        cid = full_bim_hierarchy['cladire']
        resp = authenticated_client.get(f'/activitati/?cladire_id={cid}')
        assert resp.status_code == 200

    def test_filtru_tip_element(self, authenticated_client, full_bim_hierarchy):
        resp = authenticated_client.get('/activitati/?tip_element=AHU')
        assert resp.status_code == 200

    def test_filtru_element_bim_id(self, authenticated_client, full_bim_hierarchy):
        eid = full_bim_hierarchy['element_ahu']
        resp = authenticated_client.get(f'/activitati/?element_bim_id={eid}')
        assert resp.status_code == 200

    def test_filtre_bim_combinate(self, authenticated_client, full_bim_hierarchy):
        """Multiple filtre BIM simultan - JOIN trebuie sa nu duplice."""
        resp = authenticated_client.get(
            f'/activitati/?santier_id={full_bim_hierarchy["santier"]}'
            f'&cladire_id={full_bim_hierarchy["cladire"]}'
            f'&tip_element=AHU'
        )
        assert resp.status_code == 200


class TestSearchGlobalBIM:
    """API-ul /bim/api/search."""

    def test_search_query_prea_scurt(self, authenticated_client):
        resp = authenticated_client.get('/bim/api/search?q=a')
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_search_dupa_cod_element(self, authenticated_client, full_bim_hierarchy):
        resp = authenticated_client.get('/bim/api/search?q=AHU')
        assert resp.status_code == 200
        items = resp.get_json()
        # Avem AHU-01 in fixture
        codes = [it['cod'] for it in items]
        assert any('AHU' in c for c in codes)

    def test_search_returneaza_url_navigare(self, authenticated_client, full_bim_hierarchy):
        resp = authenticated_client.get('/bim/api/search?q=AHU')
        items = resp.get_json()
        for it in items:
            assert 'url' in it
            assert 'tip' in it


class TestElementDetalii:
    """Pagina element detaliu cu quick navigation."""

    def test_element_detaliu_se_incarca(self, authenticated_client, full_bim_hierarchy):
        eid = full_bim_hierarchy['element_ahu']
        resp = authenticated_client.get(f'/bim/element/{eid}')
        assert resp.status_code == 200

    def test_element_detaliu_arata_quick_jump(self, app, authenticated_client,
                                                full_bim_hierarchy):
        """Daca exista alte elemente in acelasi nivel/cladire, apare quick navigation."""
        from models import db, ElementBIM
        # Adaug un element extra in acelasi nivel ca AHU-01
        with app.app_context():
            ahu = ElementBIM.query.get(full_bim_hierarchy['element_ahu'])
            extra = ElementBIM(
                cod='WALL-LOBBY-01', tip_element='wall',
                nume='Perete extra',
                spatiu_id=ahu.spatiu_id, nivel_id=ahu.nivel_id,
                cladire_id=ahu.cladire_id, status='proiectat',
            )
            db.session.add(extra); db.session.commit()
            extra_id = extra.id

        resp = authenticated_client.get(f'/bim/element/{full_bim_hierarchy["element_ahu"]}')
        assert resp.status_code == 200
        # Quick jump section apare
        assert b'WALL-LOBBY-01' in resp.data or b'Navigare rapida' in resp.data

        with app.app_context():
            db.session.delete(ElementBIM.query.get(extra_id))
            db.session.commit()


class TestApiCascadeBim:
    """API-uri de cascada folosite de bim_context_picker.html."""

    def test_cascade_cladiri(self, authenticated_client, full_bim_hierarchy):
        sid = full_bim_hierarchy['santier']
        resp = authenticated_client.get(f'/bim/api/santier/{sid}/cladiri')
        assert resp.status_code == 200
        cladiri = resp.get_json()
        assert len(cladiri) >= 1
        assert all('id' in c and 'cod' in c for c in cladiri)

    def test_cascade_niveluri(self, authenticated_client, full_bim_hierarchy):
        cid = full_bim_hierarchy['cladire']
        resp = authenticated_client.get(f'/bim/api/cladire/{cid}/niveluri')
        assert resp.status_code == 200
        niveluri = resp.get_json()
        assert len(niveluri) >= 3  # subsol, parter, etaj 1

    def test_cascade_spatii(self, authenticated_client, full_bim_hierarchy):
        nid = full_bim_hierarchy['nivel_parter']
        resp = authenticated_client.get(f'/bim/api/nivel/{nid}/spatii')
        assert resp.status_code == 200
        spatii = resp.get_json()
        assert len(spatii) >= 1
        assert any('LOBBY' in sp['cod'] for sp in spatii)

    def test_cascade_elemente_filtrate_pe_spatiu(self, authenticated_client,
                                                   full_bim_hierarchy):
        spid = full_bim_hierarchy['spatiu_lobby']
        resp = authenticated_client.get(f'/bim/api/elemente?spatiu_id={spid}')
        assert resp.status_code == 200
        elemente = resp.get_json()
        # AHU-01 e in spatiu_lobby
        codes = [e['cod'] for e in elemente]
        assert 'AHU-01' in codes
