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
                  calendar=None) -> dict:
    """Construieste sarcinile pentru frappe-gantt din activitatile programate.
    `calendar` (optional): calendar de lucru real; None = doar Lu-Vi (istoric)."""
    durata = int((rezultat.statistici or {}).get('durata_totala_zile', 0) or 0)
    cal = _calendar_lucrator(data_start, durata, calendar)

    def dz(i: int) -> str:
        i = max(0, min(int(i), len(cal) - 1))
        return cal[i].isoformat()

    acts = rezultat.activitati or []
    cu_dependente = len(acts) <= 200      # peste -> doar bare (fara sageti)
    sarcini = []
    for a in acts[:max_sarcini]:
        end_idx = max(a.finish_zi - 1, a.start_zi)
        s = {
            'id': a.id,
            'name': (f'{a.wbs_id}  {a.nume}')[:70],
            'start': dz(a.start_zi),
            'end': dz(end_idx),
            'progress': 0,
            'custom_class': 'gz-critic' if a.critic else 'gz-act',
        }
        if cu_dependente and a.predecesori:
            dep = ','.join(d.predecesor_id for d in a.predecesori if d.predecesor_id)
            if dep:
                s['dependencies'] = dep
        sarcini.append(s)

    return {
        'sarcini': sarcini,
        'total': len(acts),
        'trunchiat': len(acts) > max_sarcini,
        'cu_dependente': cu_dependente,
        'data_start': (cal[0].isoformat() if cal else data_start.isoformat()),
    }
