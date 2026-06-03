"""Test A: histograma resurse + cash-flow esalonat in timp din planul Gantt."""
from datetime import date
from io import BytesIO


def test_histograma_resurse(app):
    from services.gantt.pipeline import MotorPlanificare
    from services.gantt.resurse_timp import histograma_resurse
    csv = (b"cod_articol;denumire;um;cantitate;pret unitar;pret material;pret manopera\n"
           b"A;Sapatura mecanizata;mc;10;100;60;40\n"
           b"B;Pozare conducta;m;20;50;30;20\n")
    with app.app_context():
        rez, _ = MotorPlanificare().genereaza_din_fisier(csv, '.csv', clasifica=False)
        h = histograma_resurse(rez, date(2026, 1, 5))
    assert h['luna'] and h['bac'] > 0
    p = h['luna'][0]
    assert {'eticheta', 'material', 'manopera', 'utilaj', 'total', 'cumulat',
            'ore_manopera'} <= set(p)
    # cash-flow cumulat ajunge la BAC; exista si granularitate saptamanala + varf
    assert abs(h['luna'][-1]['cumulat'] - h['bac']) < 2
    assert h['saptamana'] and h['varf'] is not None


def test_rezultat_afiseaza_histograma(authenticated_client):
    csv = (b"cod_articol;denumire;um;cantitate;pret unitar\n"
           b"A;Sapatura;mc;10;100\nB;Pozare;m;20;50\n")
    r = authenticated_client.post('/gantt/genereaza',
                                  data={'fisier': (BytesIO(csv), 'f.csv')},
                                  content_type='multipart/form-data', follow_redirects=True)
    assert r.status_code == 200
    assert b'chartResurse' in r.data and b'Resurse in timp' in r.data
