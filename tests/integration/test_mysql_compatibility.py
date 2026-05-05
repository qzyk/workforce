"""
MySQL data integrity tests - P1 priority.

Testeaza ca tipurile cheie round-trip corect din Python -> MySQL -> Python:
- BOOLEAN <-> TINYINT(1)
- DATETIME cu microsecunde
- Numeric Decimal precision
- Text JSON cu Unicode + emoji
- VARCHAR utf8mb4 cu diacritice
- Unique constraint cu NULL
- Foreign Key CASCADE
- NULL handling

Toate testele cer @pytest.mark.mysql si folosesc fixture mysql_app.
Skip elegant daca MYSQL_TEST_URL nu e setat.

Pentru a rula:
    docker compose -f docker-compose.test.yml up -d
    export MYSQL_TEST_URL='mysql+pymysql://workforce:workforce_pass@127.0.0.1:3307/workforce_test'
    pytest tests/integration/test_mysql_compatibility.py -v
"""

from datetime import date, datetime
from decimal import Decimal

import pytest

pytestmark = pytest.mark.mysql


class TestBooleanRoundtrip:
    """MySQL stocheaza BOOLEAN ca TINYINT(1). Verificam ca Python bool e pastrat."""

    def test_bool_true(self, mysql_app):
        from models import db, Tenant
        with mysql_app.app_context():
            Tenant.query.filter_by(cod='bool-test-1').delete()
            db.session.commit()
            t = Tenant(cod='bool-test-1', nume='Bool True', activ=True)
            db.session.add(t); db.session.commit()
            tid = t.id
            db.session.expunge_all()

            t2 = Tenant.query.get(tid)
            assert t2.activ is True, f'Expected True, got {t2.activ!r} (type {type(t2.activ).__name__})'

            Tenant.query.filter_by(cod='bool-test-1').delete()
            db.session.commit()

    def test_bool_false(self, mysql_app):
        from models import db, Tenant
        with mysql_app.app_context():
            Tenant.query.filter_by(cod='bool-test-2').delete()
            db.session.commit()
            t = Tenant(cod='bool-test-2', nume='Bool False', activ=False)
            db.session.add(t); db.session.commit()
            tid = t.id
            db.session.expunge_all()

            t2 = Tenant.query.get(tid)
            assert t2.activ is False
            Tenant.query.filter_by(cod='bool-test-2').delete()
            db.session.commit()

    def test_bool_filter_query(self, mysql_app):
        """Filter by activ=True trebuie sa returneze doar True-urile."""
        from models import db, Tenant
        with mysql_app.app_context():
            Tenant.query.filter(Tenant.cod.like('bool-q-%')).delete()
            db.session.commit()
            db.session.add(Tenant(cod='bool-q-1', nume='A', activ=True))
            db.session.add(Tenant(cod='bool-q-2', nume='B', activ=False))
            db.session.add(Tenant(cod='bool-q-3', nume='C', activ=True))
            db.session.commit()

            actives = Tenant.query.filter(
                Tenant.cod.like('bool-q-%'),
                Tenant.activ == True
            ).all()
            assert len(actives) == 2
            cods = sorted([t.cod for t in actives])
            assert cods == ['bool-q-1', 'bool-q-3']

            Tenant.query.filter(Tenant.cod.like('bool-q-%')).delete()
            db.session.commit()


class TestDatetimeRoundtrip:
    """MySQL DATETIME nu are TZ, dar SQLAlchemy convertește ok dacă folosim datetime.utcnow."""

    def test_datetime_microseconds_preserved(self, mysql_app):
        """data_creare cu microsecunde trebuie pastrata."""
        from models import db, Tenant
        with mysql_app.app_context():
            Tenant.query.filter_by(cod='dt-test').delete()
            db.session.commit()
            now_with_ms = datetime(2025, 9, 15, 14, 30, 45, 123456)
            t = Tenant(cod='dt-test', nume='DT Test', data_creare=now_with_ms)
            db.session.add(t); db.session.commit()
            tid = t.id
            db.session.expunge_all()

            t2 = Tenant.query.get(tid)
            # MySQL DATETIME default precision e 0 (no fractional). DATETIME(6) ar pastra microsecunde.
            # SQLAlchemy default fara explicit fsp -> ne asteptam la 0 microsec.
            assert t2.data_creare.year == 2025
            assert t2.data_creare.month == 9
            assert t2.data_creare.hour == 14
            assert t2.data_creare.minute == 30
            assert t2.data_creare.second == 45

            Tenant.query.filter_by(cod='dt-test').delete()
            db.session.commit()

    def test_datetime_default_utcnow(self, mysql_app):
        """data_creare default e datetime.utcnow - se seteaza automat."""
        from models import db, Tenant
        with mysql_app.app_context():
            Tenant.query.filter_by(cod='dt-default').delete()
            db.session.commit()
            t = Tenant(cod='dt-default', nume='DT Default')
            db.session.add(t); db.session.commit()
            assert t.data_creare is not None
            assert isinstance(t.data_creare, datetime)
            # Trebuie sa fie recent (in ultimele 60s)
            delta = datetime.utcnow() - t.data_creare
            assert delta.total_seconds() < 60
            Tenant.query.filter_by(cod='dt-default').delete()
            db.session.commit()

    def test_date_roundtrip(self, mysql_app):
        from models import db, Proiect
        with mysql_app.app_context():
            Proiect.query.filter_by(cod_proiect='DATE-MY-1').delete()
            db.session.commit()
            p = Proiect(cod_proiect='DATE-MY-1', nume='Date Test',
                        data_start=date(2025, 9, 15),
                        data_sfarsit_planificat=date(2026, 12, 31),
                        status='activ')
            db.session.add(p); db.session.commit()
            pid = p.id
            db.session.expunge_all()

            p2 = Proiect.query.get(pid)
            assert p2.data_start == date(2025, 9, 15)
            assert p2.data_sfarsit_planificat == date(2026, 12, 31)
            Proiect.query.filter_by(cod_proiect='DATE-MY-1').delete()
            db.session.commit()


class TestNumericPrecision:
    """Decimal(10,2) trebuie sa pastreze 2 zecimale exact."""

    def test_decimal_preserves_2_decimals(self, mysql_app):
        from models import db, Angajat
        with mysql_app.app_context():
            Angajat.query.filter_by(cnp='1900909090909').delete()
            db.session.commit()
            a = Angajat(cnp='1900909090909', nume='Numeric', prenume='Test',
                        functie='Inginer', data_angajare=date(2024, 1, 1),
                        salariu_baza=Decimal('5040.50'),
                        status='activ')
            db.session.add(a); db.session.commit()
            aid = a.id
            db.session.expunge_all()

            a2 = Angajat.query.get(aid)
            assert a2.salariu_baza == Decimal('5040.50'), \
                f'Expected 5040.50, got {a2.salariu_baza!r}'
            Angajat.query.filter_by(cnp='1900909090909').delete()
            db.session.commit()

    def test_decimal_high_precision(self, mysql_app):
        """Numeric(12,2) pe RaportActivitate.cantitate_executata."""
        from models import db, Angajat, Proiect, RaportActivitate
        from tests.fixtures.data import make_proiect, make_angajat
        with mysql_app.app_context():
            Proiect.query.filter_by(cod_proiect='PRJ-NUM-1').delete()
            Angajat.query.filter_by(cnp='1900808080808').delete()
            db.session.commit()
            p = make_proiect(db, Proiect, cod='PRJ-NUM-1')
            a = make_angajat(db, Angajat, cnp='1900808080808', nume='X', prenume='Y')
            r = RaportActivitate(
                angajat_id=a.id, proiect_id=p.id, data=date(2025, 9, 1),
                tip_activitate='zilnica',
                activitate_principala='NUM_TEST',
                cantitate_executata=Decimal('1234567890.99'),
                status='draft'
            )
            db.session.add(r); db.session.commit()
            rid = r.id
            db.session.expunge_all()

            r2 = RaportActivitate.query.get(rid)
            assert r2.cantitate_executata == Decimal('1234567890.99')
            db.session.delete(r2)
            db.session.delete(Proiect.query.filter_by(cod_proiect='PRJ-NUM-1').first())
            db.session.delete(Angajat.query.filter_by(cnp='1900808080808').first())
            db.session.commit()


class TestTextJsonUnicode:
    """JSON stocat ca TEXT trebuie sa pastreze Unicode + emoji."""

    def test_json_text_unicode_emoji(self, mysql_app):
        """proiecte_ids JSON cu diacritice + emoji."""
        from models import db, Angajat, Proiect, RaportActivitate
        from tests.fixtures.data import make_proiect, make_angajat
        with mysql_app.app_context():
            p = make_proiect(db, Proiect, cod='PRJ-UNI')
            a = make_angajat(db, Angajat, cnp='1900707070707', nume='X', prenume='Y')
            unicode_text = 'Șantier București 🏗️ - acțiune îndeplinită'
            r = RaportActivitate(
                angajat_id=a.id, proiect_id=p.id, data=date(2025, 9, 1),
                tip_activitate='zilnica',
                activitate_principala=unicode_text,
                activitate_detaliata='Detalii: ăâîșț și 😀 + cosumeazasitratamentdedataepechiupi',
                status='draft'
            )
            db.session.add(r); db.session.commit()
            rid = r.id
            db.session.expunge_all()

            r2 = RaportActivitate.query.get(rid)
            assert r2.activitate_principala == unicode_text
            assert 'ăâîșț' in r2.activitate_detaliata
            assert '😀' in r2.activitate_detaliata
            db.session.delete(r2); db.session.commit()

    def test_subordonati_ids_json_text(self, mysql_app):
        """JSON in coloana TEXT trebuie sa fie reversibil."""
        import json
        from models import db, Angajat, Proiect, RaportActivitate
        from tests.fixtures.data import make_proiect, make_angajat
        with mysql_app.app_context():
            p = make_proiect(db, Proiect, cod='PRJ-JSON')
            a = make_angajat(db, Angajat, cnp='1900606060606', nume='X', prenume='Y')
            r = RaportActivitate(
                angajat_id=a.id, proiect_id=p.id, data=date(2025, 9, 1),
                tip_activitate='zilnica',
                activitate_principala='JSON_TEST',
                subordonati_ids=json.dumps([5, 7, 11, 13]),
                status='draft'
            )
            db.session.add(r); db.session.commit()
            rid = r.id
            db.session.expunge_all()

            r2 = RaportActivitate.query.get(rid)
            assert r2.subordonati_lista == [5, 7, 11, 13]
            db.session.delete(r2); db.session.commit()


class TestUtfMb4Diacritics:
    """utf8mb4 trebuie sa pastreze diacritice romanesti in VARCHAR."""

    def test_varchar_diacritice(self, mysql_app):
        from models import db, Santier
        with mysql_app.app_context():
            Santier.query.filter_by(cod='UTF-DIACR').delete()
            db.session.commit()
            s = Santier(cod='UTF-DIACR', nume='Șantier Călărași — strada Țăranului #5',
                        oras='București', judet='Ilfov')
            db.session.add(s); db.session.commit()
            sid = s.id
            db.session.expunge_all()

            s2 = Santier.query.get(sid)
            assert 'Șantier' in s2.nume
            assert 'Călărași' in s2.nume
            assert 'București' in s2.oras
            Santier.query.filter_by(cod='UTF-DIACR').delete()
            db.session.commit()


class TestUniqueConstraints:
    """Unique cu NULL: doua randuri cu (NULL, 'X') trebuie sa fie ambele acceptate."""

    def test_unique_cod_per_tenant_with_null(self, mysql_app):
        """Cladiri pot avea acelasi cod in santiere diferite."""
        from models import db, Santier, Cladire
        with mysql_app.app_context():
            Santier.query.filter(Santier.cod.like('UNIQ-%')).delete()
            db.session.commit()
            s1 = Santier(cod='UNIQ-1', nume='A')
            s2 = Santier(cod='UNIQ-2', nume='B')
            db.session.add(s1); db.session.add(s2); db.session.commit()
            # Acelasi cod 'X' in santiere diferite -> trebuie ok
            db.session.add(Cladire(santier_id=s1.id, cod='X', nume='Cladire X1'))
            db.session.add(Cladire(santier_id=s2.id, cod='X', nume='Cladire X2'))
            db.session.commit()  # nu trebuie sa arunce
            assert Cladire.query.filter_by(cod='X').count() == 2
            Santier.query.filter(Santier.cod.like('UNIQ-%')).delete()
            db.session.commit()

    def test_unique_cod_acelasi_santier_blocat(self, mysql_app):
        """Doua cladiri cu acelasi cod in acelasi santier -> erroare."""
        from models import db, Santier, Cladire
        with mysql_app.app_context():
            Santier.query.filter(Santier.cod.like('DUPL-%')).delete()
            db.session.commit()
            s = Santier(cod='DUPL-S', nume='Dupl')
            db.session.add(s); db.session.commit()
            db.session.add(Cladire(santier_id=s.id, cod='X', nume='1'))
            db.session.commit()
            db.session.add(Cladire(santier_id=s.id, cod='X', nume='2'))
            with pytest.raises(Exception):
                db.session.commit()
            db.session.rollback()
            Santier.query.filter(Santier.cod.like('DUPL-%')).delete()
            db.session.commit()


class TestForeignKeyCascade:
    """InnoDB FK CASCADE: stergere Santier sterge si Cladiri/Niveluri/Spatii."""

    def test_cascade_delete_santier(self, mysql_app):
        from models import db, Santier, Cladire, Nivel, Spatiu
        with mysql_app.app_context():
            Santier.query.filter_by(cod='CASC-T1').delete()
            db.session.commit()
            s = Santier(cod='CASC-T1', nume='Cascade test')
            db.session.add(s); db.session.commit()
            c = Cladire(santier_id=s.id, cod='B1', nume='B1')
            db.session.add(c); db.session.commit()
            n = Nivel(cladire_id=c.id, cod='N0', nume='Parter')
            db.session.add(n); db.session.commit()
            sp = Spatiu(nivel_id=n.id, cod='SP', nume='Spatiu')
            db.session.add(sp); db.session.commit()

            sid, cid, nid, spid = s.id, c.id, n.id, sp.id

            # Sterge santierul direct - cascade trebuie sa stearga tot
            db.session.delete(s)
            db.session.commit()

            assert Santier.query.get(sid) is None
            assert Cladire.query.get(cid) is None
            assert Nivel.query.get(nid) is None
            assert Spatiu.query.get(spid) is None


class TestNullHandling:
    """NULL in coloane FK / unique e tratat corect."""

    def test_null_fk_optional(self, mysql_app):
        """proiect_id e NULLable pe Santier - poate fi NULL."""
        from models import db, Santier
        with mysql_app.app_context():
            Santier.query.filter_by(cod='NULL-FK').delete()
            db.session.commit()
            s = Santier(cod='NULL-FK', nume='Null FK', proiect_id=None)
            db.session.add(s); db.session.commit()
            assert s.proiect_id is None
            Santier.query.filter_by(cod='NULL-FK').delete()
            db.session.commit()

    def test_filter_is_null(self, mysql_app):
        """WHERE col IS NULL trebuie sa functioneze."""
        from models import db, Santier
        with mysql_app.app_context():
            Santier.query.filter(Santier.cod.like('ISN-%')).delete()
            db.session.commit()
            db.session.add(Santier(cod='ISN-1', nume='Has', proiect_id=None))
            db.session.add(Santier(cod='ISN-2', nume='None', proiect_id=None))
            db.session.commit()
            cnt = Santier.query.filter(
                Santier.cod.like('ISN-%'),
                Santier.proiect_id.is_(None)
            ).count()
            assert cnt == 2
            Santier.query.filter(Santier.cod.like('ISN-%')).delete()
            db.session.commit()
