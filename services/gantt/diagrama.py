"""
Pregateste datele pentru diagrama Gantt vizuala (frappe-gantt).

Mapeaza indecsii de zi (start_zi/finish_zi din scheduler) pe date calendaristice
reale, sarind weekend-urile (zile lucratoare), pornind de la o data de start.
Activitatile critice primesc clasa 'gz-critic'. Pentru planuri mari nu trimite
sagetile de dependenta (zgomot vizual + performanta).
"""
from __future__ import annotations

from datetime import date, timedelta

_MAX_CAL = 20000   # plafon pentru calendarul precalculat (zile lucratoare)


def _calendar_lucrator(data_start: date, nr_zile: int, calendar=None) -> list:
    """Lista de date lucratoare (Lu-Vi) incepand de la prima zi lucratoare >= data_start.

    `calendar` (optional, CalendarLucru): cand e dat, foloseste calendarul de lucru
    real (sare si sarbatorile / respecta exceptiile). None = comportamentul istoric.
    """
    if calendar is not None:
        return calendar.lista_zile(data_start, nr_zile)
    n = min(max(nr_zile, 1) + 2, _MAX_CAL)
    cal = []
    cur = data_start
    while cur.weekday() >= 5:        # sari pana la luni
        cur += timedelta(days=1)
    while len(cal) < n:
        if cur.weekday() < 5:
            cal.append(cur)
        cur += timedelta(days=1)
    return cal


def sarcini_gantt(rezultat, data_start: date, max_sarcini: int = 600,
                  calendar=None, progrese: dict = None, baseline: dict = None) -> dict:
    """Construieste sarcinile pentru frappe-gantt din activitatile programate.

    `calendar` (optional): calendar de lucru real; None = doar Lu-Vi (istoric).
    `progrese` (optional, Faza 2 tracking): dict {cheie_activitate: procent 0..100} -
        cand e dat, bara primeste progresul real (nu mai e 0 hardcodat). None = istoric.
    `baseline` (optional, Faza 2 tracking): snapshot {'activitati': {cheie: {start_zi,
        finish_zi,...}}} - cand e dat, se intorc si bare-fantoma de baseline (overlay).
    """
    durata = int((rezultat.statistici or {}).get('durata_totala_zile', 0) or 0)
    base_acts = (baseline or {}).get('activitati', {}) if baseline else {}
    if base_acts:
        durata = max(durata, max((int(b.get('finish_zi', 0) or 0)
                                  for b in base_acts.values()), default=0))
    cal = _calendar_lucrator(data_start, durata, calendar)
    progrese = progrese or {}

    def dz(i: int) -> str:
        i = max(0, min(int(i), len(cal) - 1))
        return cal[i].isoformat()

    acts = rezultat.activitati or []
    cu_dependente = len(acts) <= 200      # peste -> doar bare (fara sageti)
    sarcini = []
    barele_baseline = []
    for a in acts[:max_sarcini]:
        end_idx = max(a.finish_zi - 1, a.start_zi)
        ck = getattr(a, 'cheie', '') or ''
        pct = progrese.get(ck, 0) if ck else 0
        try:
            pct = max(0, min(100, int(round(float(pct)))))
        except (TypeError, ValueError):
            pct = 0
        s = {
            'id': a.id,
            'name': (f'{a.wbs_id}  {a.nume}')[:70],
            'start': dz(a.start_zi),
            'end': dz(end_idx),
            'progress': pct,
            'custom_class': 'gz-critic' if a.critic else 'gz-act',
        }
        if cu_dependente and a.predecesori:
            dep = ','.join(d.predecesor_id for d in a.predecesori if d.predecesor_id)
            if dep:
                s['dependencies'] = dep
        sarcini.append(s)
        # bara-fantoma de baseline (overlay), daca activitatea exista in baseline
        if base_acts and ck in base_acts:
            b = base_acts[ck]
            b_end = max(int(b.get('finish_zi', 0) or 0) - 1, int(b.get('start_zi', 0) or 0))
            barele_baseline.append({
                'id': 'bl_' + a.id,
                'cheie': ck,
                'start': dz(int(b.get('start_zi', 0) or 0)),
                'end': dz(b_end),
            })

    return {
        'sarcini': sarcini,
        'baseline': barele_baseline,
        'total': len(acts),
        'trunchiat': len(acts) > max_sarcini,
        'cu_dependente': cu_dependente,
        'data_start': (cal[0].isoformat() if cal else data_start.isoformat()),
    }
