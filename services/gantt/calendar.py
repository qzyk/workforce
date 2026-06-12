"""
Calendar de lucru pentru motorul Gantt (pur Python, FARA importuri Flask/DB).

CalendarLucru stie ce zile sunt lucratoare pe baza unui sablon saptamanal
(string de 7 caractere, Luni..Duminica, '1' = lucratoare) si a unui dict de
exceptii pe date concrete:
    False = zi nelucratoare (ex. sarbatoare legala)
    True  = zi lucratoare   (ex. sambata lucratoare, recuperare)

Calendarul implicit (fara argumente) = Luni-Vineri fara exceptii, adica exact
comportamentul istoric al lui diagrama._calendar_lucrator (zero regresie).
"""
from __future__ import annotations

from datetime import date, timedelta

# plafon pentru calendarul precalculat (zile lucratoare) - identic cu diagrama._MAX_CAL
_MAX_CAL = 20000
# plafon de scanare pe zile calendaristice consecutive (siguranta anti-bucla infinita)
_MAX_SCAN = 366 * 8


class CalendarLucru:
    """Calendar de lucru cu sablon saptamanal + exceptii pe date.

    zile_lucratoare: string de 7 caractere ('0'/'1'), index 0 = Luni .. 6 = Duminica.
    exceptii: dict {date: bool} - False = nelucratoare, True = lucratoare.
    """

    def __init__(self, zile_lucratoare: str = '1111100', exceptii: dict = None):
        zl = str(zile_lucratoare or '1111100')
        # sablon invalid sau fara nicio zi lucratoare -> Lu-Vi (siguranta)
        if len(zl) != 7 or any(c not in '01' for c in zl) or '1' not in zl:
            zl = '1111100'
        self.zile_lucratoare = zl
        self.exceptii = dict(exceptii or {})

    def este_lucratoare(self, d: date) -> bool:
        """True daca ziua d e lucratoare (exceptia pe data bate sablonul saptamanal)."""
        if d in self.exceptii:
            return bool(self.exceptii[d])
        return self.zile_lucratoare[d.weekday()] == '1'

    def urmatoarea_zi_lucratoare(self, d: date) -> date:
        """Prima zi lucratoare >= d (inclusiv d daca e lucratoare)."""
        cur = d
        for _ in range(_MAX_SCAN):
            if self.este_lucratoare(cur):
                return cur
            cur += timedelta(days=1)
        return d   # fallback teoretic (sablonul are mereu cel putin o zi lucratoare)

    def adauga_zile(self, d: date, n: int) -> date:
        """A n-a zi lucratoare pornind de la prima zi lucratoare >= d.
        n=0 -> prima zi lucratoare >= d (aceeasi semantica de index ca in motor)."""
        cur = self.urmatoarea_zi_lucratoare(d)
        for _ in range(max(0, int(n))):
            cur = self.urmatoarea_zi_lucratoare(cur + timedelta(days=1))
        return cur

    def zile_lucratoare_intre(self, d1: date, d2: date) -> int:
        """Numarul de zile lucratoare din intervalul [d1, d2) - d2 exclusiv."""
        if d2 <= d1:
            return 0
        nr = 0
        cur = d1
        while cur < d2:
            if self.este_lucratoare(cur):
                nr += 1
            cur += timedelta(days=1)
        return nr

    def lista_zile(self, data_start: date, nr_zile: int) -> list:
        """Lista de date lucratoare incepand de la prima zi lucratoare >= data_start.

        Echivalentul lui diagrama._calendar_lucrator, dar sarind si exceptiile
        nelucratoare (sarbatori). Pastreaza plafonul de siguranta (_MAX_CAL) si
        bufferul de +2 zile al implementarii istorice.
        """
        n = min(max(int(nr_zile or 0), 1) + 2, _MAX_CAL)
        cal = []
        cur = self.urmatoarea_zi_lucratoare(data_start)
        while len(cal) < n:
            if self.este_lucratoare(cur):
                cal.append(cur)
            cur += timedelta(days=1)
        return cal
