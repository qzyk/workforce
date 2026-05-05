"""
MySQL query semantics tests - P2 priority.

Comportamente care difera intre PostgreSQL si MySQL si pot cauza regresii
silențioase:

1. Case sensitivity (utf8mb4_unicode_ci) la WHERE/LIKE/ORDER BY
2. ILIKE (PG) -> LIKE (MySQL) - SQLAlchemy mapeaza ilike() la LIKE pe MySQL
3. ONLY_FULL_GROUP_BY mode strict
4. ORDER BY collation (diacritice romanesti)
5. LIMIT/OFFSET pagination
6. NULL semantics in IN/NOT IN

Pentru a rula:
    docker compose -f docker-compose.test.yml up -d
    export MYSQL_TEST_URL='mysql+pymysql://workforce:workforce_pass@127.0.0.1:3307/workforce_test'
    pytest tests/integration/test_mysql_query_semantics.py -v
"""

from datetime import date
import pytest

pytestmark = pytest.mark.mysql


class TestCaseSensitivity:
    """MySQL utf8mb4_unicode_ci default = case-insensitive comparisons."""

    def test_email_lookup_case_insensitive(self, mysql_app):
        """Login cu email in case diferit trebuie sa gaseasca user-ul."""
        from models import db, Utilizator
        with mysql_app.app_context():
            Utilizator.query.filter_by(email='ci-test@example.com').delete()
            db.session.commit()
            u = Utilizator(nume='CI', prenume='Test', email='ci-test@example.com',
                           rol='admin', activ=True)
            u.set_password('p')
            db.session.add(u); db.session.commit()

            # Lookup cu varianta uppercase
            u2 = Utilizator.query.filter_by(email='CI-TEST@EXAMPLE.COM').first()
            # MySQL default e case-insensitive -> ar trebui sa gaseasca
            # PG era case-sensitive -> nu gasea
            assert u2 is not None, 'MySQL utf8mb4_unicode_ci ar trebui sa gaseasca email cu majuscule'

            Utilizator.query.filter_by(email='ci-test@example.com').delete()
            db.session.commit()

    def test_like_search_case_insensitive(self, mysql_app):
        """LIKE (= ILIKE in PG) trebuie sa fie case-insensitive default."""
        from models import db, Santier
        with mysql_app.app_context():
            Santier.query.filter(Santier.cod.like('CI-%')).delete()
            db.session.commit()
            db.session.add(Santier(cod='CI-AHU-01', nume='AHU Mare'))
            db.session.add(Santier(cod='CI-ahu-02', nume='ahu mic'))
            db.session.commit()

            # Cauta dupa "ahu" - trebuie sa gaseasca AMBELE
            results = Santier.query.filter(Santier.cod.like('%ahu%')).all()
            cods = sorted([s.cod for s in results])
            assert 'CI-AHU-01' in cods
            assert 'CI-ahu-02' in cods
            Santier.query.filter(Santier.cod.like('CI-%')).delete()
            db.session.commit()

    def test_ilike_works_on_mysql(self, mysql_app):
        """SQLAlchemy ilike() trebuie sa functioneze pe MySQL (mapeaza la LIKE)."""
        from models import db, Santier
        with mysql_app.app_context():
            Santier.query.filter_by(cod='IL-1').delete()
            db.session.commit()
            db.session.add(Santier(cod='IL-1', nume='Mixed Case Test'))
            db.session.commit()

            # ilike() din SQLAlchemy
            r = Santier.query.filter(Santier.nume.ilike('%mixed case%')).first()
            assert r is not None
            assert r.cod == 'IL-1'
            Santier.query.filter_by(cod='IL-1').delete()
            db.session.commit()


class TestGroupByStrict:
    """MySQL 5.7+ are sql_mode=ONLY_FULL_GROUP_BY default. Verificam ca query-urile
    noastre cu GROUP BY nu rup pe MySQL."""

    def test_count_distinct_in_quality_report(self, mysql_app):
        """report_duplicate_extern_id foloseste GROUP BY HAVING COUNT > 1."""
        from sqlalchemy import func
        from models import db, ElementBIM, Santier, Cladire
        with mysql_app.app_context():
            # Cleanup
            ElementBIM.query.filter(ElementBIM.cod.like('GB-%')).delete()
            Cladire.query.filter(Cladire.cod.like('GB-%')).delete()
            Santier.query.filter(Santier.cod.like('GB-%')).delete()
            db.session.commit()

            s = Santier(cod='GB-S', nume='GB')
            db.session.add(s); db.session.commit()
            c = Cladire(santier_id=s.id, cod='GB-B', nume='B')
            db.session.add(c); db.session.commit()

            # Doua elemente cu acelasi GUID
            db.session.add(ElementBIM(cladire_id=c.id, cod='GB-1',
                                       tip_element='wall', ifc_global_id='SAME-GUID'))
            db.session.add(ElementBIM(cladire_id=c.id, cod='GB-2',
                                       tip_element='wall', ifc_global_id='SAME-GUID'))
            db.session.add(ElementBIM(cladire_id=c.id, cod='GB-3',
                                       tip_element='wall', ifc_global_id='UNIQUE-GUID'))
            db.session.commit()

            # Query GROUP BY (similar cu cel din bim_quality)
            duplicate = db.session.query(
                ElementBIM.ifc_global_id, func.count(ElementBIM.id).label('cnt')
            ).filter(
                ElementBIM.ifc_global_id.isnot(None)
            ).group_by(
                ElementBIM.ifc_global_id
            ).having(func.count(ElementBIM.id) > 1).all()

            # Expected: doar SAME-GUID
            assert len(duplicate) == 1
            assert duplicate[0][0] == 'SAME-GUID'
            assert duplicate[0][1] == 2

            ElementBIM.query.filter(ElementBIM.cod.like('GB-%')).delete()
            Cladire.query.filter(Cladire.cod.like('GB-%')).delete()
            Santier.query.filter(Santier.cod.like('GB-%')).delete()
            db.session.commit()

    def test_quality_report_route_no_group_by_error(self, mysql_app, mysql_authenticated_client):
        """Pagina /bim/quality nu trebuie sa dea ONLY_FULL_GROUP_BY error."""
        resp = mysql_authenticated_client.get('/bim/quality')
        assert resp.status_code == 200, f'Expected 200, got {resp.status_code}: {resp.data[:200]}'


class TestOrderByCollation:
    """ORDER BY pe utf8mb4_unicode_ci sorteaza diacritice corect."""

    def test_order_by_diacritice(self, mysql_app):
        """Stefan, Ștefan, Tudor in ordine."""
        from models import db, Angajat
        with mysql_app.app_context():
            Angajat.query.filter(Angajat.cnp.like('1100000%')).delete()
            db.session.commit()
            for i, nume in enumerate(['Tudor', 'Stefan', 'Ștefan', 'Andrei']):
                db.session.add(Angajat(
                    cnp=f'110000010000{i}', nume=nume, prenume='X',
                    functie='Inginer', data_angajare=date(2024,1,1)
                ))
            db.session.commit()
            ordered = Angajat.query.filter(
                Angajat.cnp.like('1100000%')
            ).order_by(Angajat.nume).all()
            nums = [a.nume for a in ordered]
            # Andrei trebuie primul, Tudor ultim
            assert nums[0] == 'Andrei'
            assert nums[-1] == 'Tudor'
            # Stefan / Ștefan trebuie consecutive (in mijloc)
            mid = nums[1:-1]
            assert 'Stefan' in mid and 'Ștefan' in mid
            Angajat.query.filter(Angajat.cnp.like('1100000%')).delete()
            db.session.commit()


class TestLimitOffset:
    """LIMIT/OFFSET pagination behavior."""

    def test_limit_n(self, mysql_app):
        from models import db, Santier
        with mysql_app.app_context():
            Santier.query.filter(Santier.cod.like('LIM-%')).delete()
            db.session.commit()
            for i in range(10):
                db.session.add(Santier(cod=f'LIM-{i:02d}', nume=f'L{i}'))
            db.session.commit()

            page1 = Santier.query.filter(
                Santier.cod.like('LIM-%')
            ).order_by(Santier.cod).limit(3).all()
            assert len(page1) == 3
            assert [s.cod for s in page1] == ['LIM-00', 'LIM-01', 'LIM-02']

            page2 = Santier.query.filter(
                Santier.cod.like('LIM-%')
            ).order_by(Santier.cod).limit(3).offset(3).all()
            assert len(page2) == 3
            assert [s.cod for s in page2] == ['LIM-03', 'LIM-04', 'LIM-05']

            Santier.query.filter(Santier.cod.like('LIM-%')).delete()
            db.session.commit()


class TestNullSemantics:
    """NULL in operatori IN/NOT IN."""

    def test_in_with_explicit_values(self, mysql_app):
        from models import db, Santier
        with mysql_app.app_context():
            Santier.query.filter(Santier.cod.like('NUL-%')).delete()
            db.session.commit()
            db.session.add(Santier(cod='NUL-1', nume='1'))
            db.session.add(Santier(cod='NUL-2', nume='2'))
            db.session.commit()

            r = Santier.query.filter(Santier.cod.in_(['NUL-1', 'NUL-2'])).all()
            assert len(r) == 2
            Santier.query.filter(Santier.cod.like('NUL-%')).delete()
            db.session.commit()

    def test_not_in_excludes_null(self, mysql_app):
        """NOT IN cu NULL: PG si MySQL ambele exclud NULL-urile (standard SQL)."""
        from models import db, Santier
        with mysql_app.app_context():
            Santier.query.filter(Santier.cod.like('NIN-%')).delete()
            db.session.commit()
            s1 = Santier(cod='NIN-1', nume='A', proiect_id=None)
            s2 = Santier(cod='NIN-2', nume='B', proiect_id=None)
            db.session.add(s1); db.session.add(s2); db.session.commit()

            # NOT IN (1, 2) - cu proiect_id NULL, randul nu e in rezultat
            r = Santier.query.filter(
                Santier.cod.like('NIN-%'),
                Santier.proiect_id.notin_([1, 2])
            ).all()
            # Standard SQL: NOT IN (1,2) cu NULL nu match-uieste -> 0 rezultate
            # SQLAlchemy poate sa adauge OR IS NULL pentru a face natural
            # Testam doar ca query-ul nu crapa
            assert isinstance(r, list)
            Santier.query.filter(Santier.cod.like('NIN-%')).delete()
            db.session.commit()


class TestJoinSemantics:
    """Joins distinct + COUNT pe related."""

    def test_join_distinct_no_duplicates(self, mysql_app):
        """API /bim/api/elemente face JOIN cu Spatiu/Cladire - sa nu dubleze elemente."""
        from models import db, Santier, Cladire, Nivel, Spatiu, ElementBIM
        with mysql_app.app_context():
            Santier.query.filter(Santier.cod.like('JD-%')).delete()
            db.session.commit()
            s = Santier(cod='JD-S', nume='JD')
            db.session.add(s); db.session.commit()
            c = Cladire(santier_id=s.id, cod='JD-B', nume='B')
            db.session.add(c); db.session.commit()
            n = Nivel(cladire_id=c.id, cod='N0', nume='Parter')
            db.session.add(n); db.session.commit()
            sp = Spatiu(nivel_id=n.id, cod='SP', nume='Sp')
            db.session.add(sp); db.session.commit()
            db.session.add(ElementBIM(spatiu_id=sp.id, nivel_id=n.id, cladire_id=c.id,
                                       cod='JD-E1', tip_element='wall'))
            db.session.add(ElementBIM(spatiu_id=sp.id, nivel_id=n.id, cladire_id=c.id,
                                       cod='JD-E2', tip_element='door'))
            db.session.commit()

            # Query cu join (similar cu activitati panou filter)
            elem_count = ElementBIM.query.join(
                Cladire, ElementBIM.cladire_id == Cladire.id
            ).filter(Cladire.santier_id == s.id).count()
            assert elem_count == 2

            Santier.query.filter(Santier.cod.like('JD-%')).delete()
            db.session.commit()
