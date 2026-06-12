"""
Teste unitare pentru calendarul de lucru Gantt (services/gantt/calendar.py) si
pentru exporturile cu date calendaristice (services/gantt/export.py).
Nu necesita aplicatia Flask - testeaza direct functiile pure.
"""
from datetime import date

import xml.etree.ElementTree as ET

from services.gantt.calendar import CalendarLucru
from services.gantt import diagrama, export as export_engine
from services.gantt.modele import Activitate, Dependenta
from services.gantt.program import programeaza
from services.gantt.wbs import genereaza_wbs

# referinte: 2026-06-01 = luni, 2026-06-06/07 = sambata/duminica
LUNI = date(2026, 6, 1)
MARTI = date(2026, 6, 2)
SAMBATA = date(2026, 6, 6)
DUMINICA = date(2026, 6, 7)


# ------------------------------------------------------------- CalendarLucru
def test_calendar_weekend():
    c = CalendarLucru()
    assert c.este_lucratoare(LUNI)
    assert not c.este_lucratoare(SAMBATA)
    assert not c.este_lucratoare(DUMINICA)
    assert c.urmatoarea_zi_lucratoare(SAMBATA) == date(2026, 6, 8)   # lunea urmatoare


def test_calendar_sarbatoare_din_exceptii():
    c = CalendarLucru(exceptii={MARTI: False})        # marti = sarbatoare
    assert not c.este_lucratoare(MARTI)
    assert c.este_lucratoare(LUNI)
    # urmatoarea zi lucratoare de la sarbatoare = miercuri
    assert c.urmatoarea_zi_lucratoare(MARTI) == date(2026, 6, 3)


def test_calendar_exceptie_lucratoare_sambata():
    c = CalendarLucru(exceptii={SAMBATA: True})       # sambata lucratoare (recuperare)
    assert c.este_lucratoare(SAMBATA)
    assert not c.este_lucratoare(DUMINICA)
    # vineri + 1 zi lucratoare = sambata (nu luni)
    assert c.adauga_zile(date(2026, 6, 5), 1) == SAMBATA


def test_calendar_adauga_zile_peste_sarbatori():
    c = CalendarLucru(exceptii={MARTI: False})
    # luni + 1 zi lucratoare: sare marti (sarbatoare) -> miercuri
    assert c.adauga_zile(LUNI, 1) == date(2026, 6, 3)
    # luni + 4 zile lucratoare: mi, jo, vi, apoi sare weekendul -> luni 8
    assert c.adauga_zile(LUNI, 4) == date(2026, 6, 8)
    # start in weekend -> ancorat la prima zi lucratoare
    assert c.adauga_zile(SAMBATA, 0) == date(2026, 6, 8)


def test_calendar_zile_lucratoare_intre():
    c = CalendarLucru(exceptii={MARTI: False})
    # [luni, luni+7): lu(1), ma=sarbatoare(0), mi+jo+vi(3), weekend(0) = 4
    assert c.zile_lucratoare_intre(LUNI, date(2026, 6, 8)) == 4
    assert c.zile_lucratoare_intre(LUNI, LUNI) == 0
    assert c.zile_lucratoare_intre(date(2026, 6, 8), LUNI) == 0   # interval inversat


def test_calendar_sablon_invalid_cade_pe_lu_vi():
    for sablon in ('', '11', '1111100x', '0000000', None):
        c = CalendarLucru(zile_lucratoare=sablon)
        assert c.zile_lucratoare == '1111100'


def test_lista_zile_identica_cu_calendar_lucrator_istoric():
    """Regresie: CalendarLucru() fara exceptii = exact _calendar_lucrator istoric."""
    for start in (LUNI, SAMBATA, date(2026, 12, 28)):
        for n in (0, 1, 5, 23):
            assert CalendarLucru().lista_zile(start, n) == \
                diagrama._calendar_lucrator(start, n)


def test_lista_zile_sare_sarbatorile():
    c = CalendarLucru(exceptii={MARTI: False})
    zile = c.lista_zile(LUNI, 4)
    assert MARTI not in zile
    assert zile[0] == LUNI and zile[1] == date(2026, 6, 3)


# ------------------------------------------------- export cu date calendaristice
def _plan_demo():
    """Doua activitati FS programate + noduri WBS (minim pentru export)."""
    a = Activitate(id='A000001', cod='1', nume='Sapatura mecanizata',
                   categorie_tehnologica='SAPATURA', obiect='Retea',
                   tronson='Strada A', durata=2)
    b = Activitate(id='A000002', cod='2', nume='Pozare conducta',
                   categorie_tehnologica='POZARE_CONDUCTA', obiect='Retea',
                   tronson='Strada A', durata=3)
    b.predecesori.append(Dependenta('A000001', 'FS', 0))
    programeaza([a, b])
    noduri = genereaza_wbs([a, b], ['SAPATURA', 'POZARE_CONDUCTA'])
    return [a, b], noduri


def test_export_msp_cu_date_sare_sarbatoarea():
    acts, noduri = _plan_demo()
    cal = CalendarLucru(exceptii={MARTI: False})      # marti 02.06 = sarbatoare
    data = export_engine.export_msproject_xml(acts, noduri, data_start=LUNI,
                                              calendar=cal)
    root = ET.fromstring(data)
    ns = '{http://schemas.microsoft.com/project}'
    # proiectul are StartDate ancorat pe prima zi lucratoare
    assert root.find(f'{ns}StartDate').text == '2026-06-01T08:00:00'
    starturi = {}
    for t in root.find(f'{ns}Tasks'):
        s, f = t.find(f'{ns}Start'), t.find(f'{ns}Finish')
        if s is not None:
            starturi[t.find(f'{ns}Name').text] = (s.text, f.text)
    # A: zilele 0-1 -> 01.06 si 03.06 (sare sarbatoarea de marti)
    assert starturi['Sapatura mecanizata'] == ('2026-06-01T08:00:00',
                                               '2026-06-03T16:00:00')
    # B: zilele 2-4 -> 04.06 .. 08.06 (sare si weekendul)
    assert starturi['Pozare conducta'] == ('2026-06-04T08:00:00',
                                           '2026-06-08T16:00:00')


def test_export_p6_cu_date():
    acts, noduri = _plan_demo()
    cal = CalendarLucru(exceptii={MARTI: False})
    data = export_engine.export_primavera_xml(acts, noduri, data_start=LUNI,
                                              calendar=cal)
    root = ET.fromstring(data)
    a0 = root.find('.//Activity')
    assert a0.find('PlannedStartDate').text == '2026-06-01T08:00:00'
    assert a0.find('PlannedFinishDate').text == '2026-06-03T16:00:00'


def test_export_csv_cu_date():
    acts, noduri = _plan_demo()
    cal = CalendarLucru(exceptii={MARTI: False})
    text = export_engine.export_csv(acts, noduri, data_start=LUNI,
                                    calendar=cal).decode('utf-8-sig')
    linii = text.splitlines()
    assert linii[0].endswith('Start,Finish')
    assert linii[1].endswith('2026-06-01,2026-06-03')
    assert linii[2].endswith('2026-06-04,2026-06-08')


def test_export_fara_data_start_identic_cu_istoricul():
    """Regresie flag OFF: fara data_start/calendar, output IDENTIC byte-cu-byte."""
    acts, noduri = _plan_demo()
    cal = CalendarLucru(exceptii={MARTI: False})
    # apel istoric (pozitional) vs apel nou cu parametrii None -> identic
    assert export_engine.export_msproject_xml(acts, noduri) == \
        export_engine.export_msproject_xml(acts, noduri, data_start=None, calendar=cal)
    assert export_engine.export_csv(acts, noduri) == \
        export_engine.export_csv(acts, noduri, data_start=None, calendar=cal)
    assert export_engine.export_primavera_xml(acts, noduri) == \
        export_engine.export_primavera_xml(acts, noduri, data_start=None, calendar=cal)
    # si nu exista niciun element de data in output-ul istoric
    msp = export_engine.export_msproject_xml(acts, noduri)
    assert b'<Start>' not in msp and b'<Finish>' not in msp and b'<StartDate>' not in msp
    p6 = export_engine.export_primavera_xml(acts, noduri)
    assert b'PlannedStartDate' not in p6
    csv_ = export_engine.export_csv(acts, noduri).decode('utf-8-sig')
    assert 'Start' not in csv_.splitlines()[0]


def test_sarcini_gantt_fara_calendar_identic_cu_istoricul():
    """Regresie: sarcini_gantt cu calendar=None / CalendarLucru() gol = istoric."""
    from services.gantt.modele import RezultatPlanificare
    acts, noduri = _plan_demo()
    rez = RezultatPlanificare(activitati=acts, noduri_wbs=noduri,
                              statistici={'durata_totala_zile': 5})
    istoric = diagrama.sarcini_gantt(rez, LUNI)
    assert diagrama.sarcini_gantt(rez, LUNI, calendar=None) == istoric
    assert diagrama.sarcini_gantt(rez, LUNI, calendar=CalendarLucru()) == istoric


def test_sarcini_gantt_cu_calendar_sare_sarbatoarea():
    from services.gantt.modele import RezultatPlanificare
    acts, noduri = _plan_demo()
    rez = RezultatPlanificare(activitati=acts, noduri_wbs=noduri,
                              statistici={'durata_totala_zile': 5})
    cal = CalendarLucru(exceptii={MARTI: False})
    d = diagrama.sarcini_gantt(rez, LUNI, calendar=cal)
    toate_zilele = {s['start'] for s in d['sarcini']} | {s['end'] for s in d['sarcini']}
    assert '2026-06-02' not in toate_zilele          # sarbatoarea e sarita
    assert d['sarcini'][0]['start'] == '2026-06-01'
