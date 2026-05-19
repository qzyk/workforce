"""
Integration tests pentru modulul Locatii proiect (Mapbox).

Acoperă:
  - CRUD endpoints
  - Bbox filter
  - GeoJSON response (Accept: application/json sau ?format=json)
  - Geocoding endpoint cu mock (NU face request real la Mapbox)
  - Graceful fallback când tokens lipsă
"""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest


@pytest.fixture
def proiect_loc(app):
    """Proiect dedicat pentru testele locatii."""
    from models import db, Proiect, LocatieProiect
    with app.app_context():
        LocatieProiect.query.filter(
            LocatieProiect.nume.like('LOC-%')
        ).delete()
        Proiect.query.filter_by(cod_proiect='LOC-PRJ').delete()
        db.session.commit()
        p = Proiect(cod_proiect='LOC-PRJ', nume='Loc Test',
                    data_start=date(2026, 1, 1), status='activ')
        db.session.add(p); db.session.commit()
        proiect_id = p.id  # salvez ID separat pentru cleanup post-yield
    yield proiect_id
    with app.app_context():
        LocatieProiect.query.filter(LocatieProiect.proiect_id == proiect_id).delete()
        Proiect.query.filter_by(id=proiect_id).delete()
        db.session.commit()


class TestCRUD:
    def test_lista_ok(self, authenticated_client, proiect_loc):
        r = authenticated_client.get(f'/locatii/proiect/{proiect_loc}')
        assert r.status_code == 200
        assert b'Locatii proiect' in r.data or b'Nicio locatie' in r.data

    def test_lista_json(self, app, authenticated_client, proiect_loc):
        """?format=json returneaza GeoJSON FeatureCollection."""
        from models import db, LocatieProiect
        with app.app_context():
            l = LocatieProiect(
                proiect_id=proiect_loc, nume='LOC-JSON-001',
                tip='santier', status='activ',
                latitudine=Decimal('44.426800'),
                longitudine=Decimal('26.102500'),
            )
            db.session.add(l); db.session.commit()
        r = authenticated_client.get(
            f'/locatii/proiect/{proiect_loc}?format=json'
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data['type'] == 'FeatureCollection'
        assert data['count_with_coords'] >= 1
        # Verific structura Feature
        f = data['features'][0]
        assert f['type'] == 'Feature'
        assert f['geometry']['type'] == 'Point'
        # GeoJSON: [lng, lat] ordine
        assert f['geometry']['coordinates'][0] == 26.1025
        assert f['geometry']['coordinates'][1] == 44.4268

    def test_creare_locatie(self, app, authenticated_client, proiect_loc):
        from models import LocatieProiect
        r = authenticated_client.post(
            f'/locatii/proiect/{proiect_loc}/nou',
            data={
                'nume': 'LOC-CRE-001',
                'tip': 'birou',
                'status': 'activ',
                'adresa_text': 'Strada Test 1',
                'judet': 'Bucuresti',
                'latitudine': '44.426800',
                'longitudine': '26.102500',
            },
            follow_redirects=False,
        )
        assert r.status_code in (302, 303)
        with app.app_context():
            l = LocatieProiect.query.filter_by(nume='LOC-CRE-001').first()
            assert l is not None
            assert l.tip == 'birou'
            assert l.are_coordonate
            assert l.latitudine == Decimal('44.426800')

    def test_editeaza(self, app, authenticated_client, proiect_loc):
        from models import db, LocatieProiect
        with app.app_context():
            l = LocatieProiect(
                proiect_id=proiect_loc, nume='LOC-EDIT-001',
                tip='santier', status='activ',
            )
            db.session.add(l); db.session.commit()
            lid = l.id
        r = authenticated_client.post(
            f'/locatii/{lid}/editeaza',
            data={
                'locatie_id': str(lid),
                'nume': 'LOC-EDIT-MODIFICAT',
                'tip': 'depozit',
                'status': 'inactiv',
                'latitudine': '45.0',
                'longitudine': '25.0',
            },
            follow_redirects=False,
        )
        assert r.status_code in (302, 303)
        with app.app_context():
            l = LocatieProiect.query.get(lid)
            assert l.nume == 'LOC-EDIT-MODIFICAT'
            assert l.tip == 'depozit'
            assert l.status == 'inactiv'

    def test_sterge(self, app, authenticated_client, proiect_loc):
        from models import db, LocatieProiect
        with app.app_context():
            l = LocatieProiect(
                proiect_id=proiect_loc, nume='LOC-DEL-001',
                tip='santier', status='activ',
            )
            db.session.add(l); db.session.commit()
            lid = l.id
        r = authenticated_client.post(f'/locatii/{lid}/sterge',
                                       follow_redirects=False)
        assert r.status_code in (302, 303)
        with app.app_context():
            assert LocatieProiect.query.get(lid) is None


class TestBboxFilter:
    def test_within_bounds(self, app, authenticated_client, proiect_loc):
        from models import db, LocatieProiect
        with app.app_context():
            # In Romania (lat 44-46, lng 25-27)
            l_inside = LocatieProiect(
                proiect_id=proiect_loc, nume='LOC-BBOX-IN',
                tip='santier', status='activ',
                latitudine=Decimal('44.5'), longitudine=Decimal('26.0'),
            )
            # In afara (Berlin)
            l_outside = LocatieProiect(
                proiect_id=proiect_loc, nume='LOC-BBOX-OUT',
                tip='santier', status='activ',
                latitudine=Decimal('52.5'), longitudine=Decimal('13.4'),
            )
            db.session.add_all([l_inside, l_outside]); db.session.commit()
        # Bbox Romania
        r = authenticated_client.get(
            f'/locatii/proiect/{proiect_loc}/within-bounds'
            f'?sw_lat=43&sw_lng=20&ne_lat=48&ne_lng=30'
        )
        assert r.status_code == 200
        data = r.get_json()
        nume_in_result = [f['properties']['nume'] for f in data['features']]
        assert 'LOC-BBOX-IN' in nume_in_result
        assert 'LOC-BBOX-OUT' not in nume_in_result

    def test_bbox_params_invalid(self, authenticated_client, proiect_loc):
        r = authenticated_client.get(
            f'/locatii/proiect/{proiect_loc}/within-bounds?sw_lat=abc'
        )
        assert r.status_code == 400


class TestGeocodingEndpoint:
    def test_geocode_503_fara_token(self, app, authenticated_client):
        """Fara MAPBOX_*_TOKEN setat -> 503 not_configured."""
        import os
        # Asigur ca tokenul NU e setat
        os.environ.pop('MAPBOX_PUBLIC_TOKEN', None)
        os.environ.pop('MAPBOX_SECRET_TOKEN', None)
        r = authenticated_client.post(
            '/locatii/api/geocode',
            json={'adresa': 'Strada Test'},
        )
        assert r.status_code == 503
        data = r.get_json()
        assert data['error'] == 'not_configured'

    def test_geocode_adresa_goala_400(self, authenticated_client):
        import os
        os.environ['MAPBOX_PUBLIC_TOKEN'] = 'pk.fake'
        try:
            r = authenticated_client.post(
                '/locatii/api/geocode',
                json={'adresa': ''},
            )
            assert r.status_code == 400
        finally:
            os.environ.pop('MAPBOX_PUBLIC_TOKEN', None)

    def test_geocode_success_cu_mock(self, authenticated_client):
        """Mock Mapbox response -> verific structura JSON returnata."""
        import os
        import json
        from io import BytesIO
        os.environ['MAPBOX_PUBLIC_TOKEN'] = 'pk.fake'

        mock_response_data = {
            'features': [{
                'place_name': 'Strada Stefan cel Mare 15, Bucuresti, Romania',
                'geometry': {'coordinates': [26.1025, 44.4268]},
                'context': [
                    {'id': 'region.123', 'text': 'Bucuresti'},
                    {'id': 'place.456', 'text': 'Bucuresti'},
                ],
            }]
        }

        class FakeResp:
            status = 200
            def read(self):
                return json.dumps(mock_response_data).encode('utf-8')
            def __enter__(self): return self
            def __exit__(self, *a): pass

        try:
            with patch('services.geocoding.urllib.request.urlopen',
                       return_value=FakeResp()):
                r = authenticated_client.post(
                    '/locatii/api/geocode',
                    json={'adresa': 'Strada Stefan cel Mare 15'},
                )
                assert r.status_code == 200
                data = r.get_json()
                assert data['lat'] == 44.4268
                assert data['lng'] == 26.1025
                assert 'Bucuresti' in data['normalized_address']
        finally:
            os.environ.pop('MAPBOX_PUBLIC_TOKEN', None)

    def test_geocode_no_results_404(self, authenticated_client):
        import os
        import json
        os.environ['MAPBOX_PUBLIC_TOKEN'] = 'pk.fake'

        class FakeRespEmpty:
            status = 200
            def read(self):
                return json.dumps({'features': []}).encode('utf-8')
            def __enter__(self): return self
            def __exit__(self, *a): pass

        try:
            with patch('services.geocoding.urllib.request.urlopen',
                       return_value=FakeRespEmpty()):
                r = authenticated_client.post(
                    '/locatii/api/geocode',
                    json={'adresa': 'Inexistent'},
                )
                assert r.status_code == 404
                assert r.get_json()['error'] == 'no_results'
        finally:
            os.environ.pop('MAPBOX_PUBLIC_TOKEN', None)


class TestModelHelpers:
    def test_to_geojson_feature_fara_coords(self, app, proiect_loc):
        from models import LocatieProiect
        with app.app_context():
            l = LocatieProiect(proiect_id=proiect_loc, nume='X',
                               tip='altul', status='activ')
            assert l.to_geojson_feature() is None
            assert l.are_coordonate is False

    def test_to_geojson_feature_cu_coords(self, app, proiect_loc):
        from models import LocatieProiect
        with app.app_context():
            l = LocatieProiect(
                proiect_id=proiect_loc, nume='Y', tip='birou', status='activ',
                latitudine=Decimal('45.0'), longitudine=Decimal('25.0'),
            )
            f = l.to_geojson_feature()
            assert f['type'] == 'Feature'
            assert f['geometry']['coordinates'] == [25.0, 45.0]  # lng, lat
            assert f['properties']['nume'] == 'Y'
