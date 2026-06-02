"""
Overlay de configurare pentru motorul Gantt: DB suprascrie JSON.

Principiu (zero regresie):
- daca exista randuri active in DB (pe tenant sau global) -> se folosesc;
- daca tabelul e gol, lipseste, sau nu suntem in context de aplicatie -> se cade
  pe config/gantt/*.json (config_loader). Orice eroare de DB -> fallback la JSON.

Astfel codul poate fi deployat INAINTE de rularea migratiei 0012 fara sa crape
(tabelele inca inexistente -> exceptie prinsa -> JSON).
"""
from __future__ import annotations

from typing import Optional

from . import config_loader as cfg
from .normalizare import normalizeaza


# ---------------------------------------------------------------------------
# Acces DB defensiv (fallback la None daca nu e disponibil).
# ---------------------------------------------------------------------------
def _randuri_active(model, tenant_id: Optional[int]):
    """Randuri active pentru tenant_id + globale (tenant_id NULL). None la orice esec."""
    try:
        from flask import has_app_context
        if not has_app_context():
            return None
        from sqlalchemy import or_
        q = model.query.filter_by(activ=True)
        if tenant_id is not None:
            q = q.filter(or_(model.tenant_id == tenant_id, model.tenant_id.is_(None)))
        else:
            q = q.filter(model.tenant_id.is_(None))
        return q.all()
    except Exception:
        return None  # tabel inexistent / fara context / orice eroare -> JSON


# ---------------------------------------------------------------------------
# Domenii de configurare (fiecare: DB daca exista, altfel JSON).
# ---------------------------------------------------------------------------
def coloane(tenant_id: Optional[int] = None) -> dict:
    """{camp_logic: [sinonime]} pentru maparea coloanelor de antet.
    Fuziune pe camp: campurile cu randuri in DB suprascriu JSON; restul raman pe JSON."""
    from models import GanttSinonimColoana
    base = dict(cfg.incarca('setari', cfg.SETARI_IMPLICITE).get(
        'coloane', cfg.SETARI_IMPLICITE['coloane']))
    rows = _randuri_active(GanttSinonimColoana, tenant_id)
    if rows:
        db_map: dict = {}
        for r in rows:
            db_map.setdefault(r.camp, []).append(r.sinonim)
        base.update(db_map)
    return base


def clasificare(tenant_id: Optional[int] = None) -> dict:
    """{CATEGORIE: [cuvinte-cheie]} pentru clasificare (doar regulile 'cuvant').
    Fuziune pe categorie: categoriile din DB suprascriu JSON; restul raman pe JSON."""
    from models import GanttClasificareRegula
    base = dict(cfg.incarca('clasificare', cfg.CLASIFICARE_IMPLICITA))
    rows = _randuri_active(GanttClasificareRegula, tenant_id)
    cuvinte = [r for r in rows if r.tip_regula == 'cuvant'] if rows else None
    if cuvinte:
        db_map: dict = {}
        for r in sorted(cuvinte, key=lambda x: (x.prioritate, x.id)):
            db_map.setdefault(r.categorie, []).append(r.valoare)
        base.update(db_map)
    return base


def reguli_prefix_cod(tenant_id: Optional[int] = None) -> list:
    """[(prefix, CATEGORIE, prioritate)] pentru clasificare pe prefix de cod (indicativ).
    Fuziune: prefixe.json ca baza, randurile 'prefix_cod' din DB suprascriu/adauga."""
    prefixe = cfg.incarca('prefixe', {}) or {}
    base = {str(k): v for k, v in prefixe.items() if not str(k).startswith('_')}
    from models import GanttClasificareRegula
    rows = _randuri_active(GanttClasificareRegula, tenant_id)
    if rows:
        for r in rows:
            if r.tip_regula == 'prefix_cod' and r.valoare:
                base[r.valoare] = r.categorie
    return [(p, c, 100) for p, c in base.items()]


def mapare_tip_element(tenant_id: Optional[int] = None) -> dict:
    """{tip_element_BIM: CATEGORIE_gantt} pentru 4D - mapare_bim.json suprascris de DB
    (gantt_clasificare_regula cu tip_regula='tip_element')."""
    base = {str(k): v for k, v in (cfg.incarca('mapare_bim', {}) or {}).items()
            if not str(k).startswith('_')}
    from models import GanttClasificareRegula
    rows = _randuri_active(GanttClasificareRegula, tenant_id)
    if rows:
        for r in rows:
            if r.tip_regula == 'tip_element' and r.valoare:
                base[r.valoare] = r.categorie
    return base


def dependinte(tenant_id: Optional[int] = None) -> dict:
    """{'ordine_categorii', 'intra_categorie', 'relatii'} pentru dependente."""
    from models import GanttRelatieTemplate
    rows = _randuri_active(GanttRelatieTemplate, tenant_id)
    json_dep = cfg.incarca('dependinte', cfg.DEPENDINTE_IMPLICITE)
    if not rows:
        return json_dep

    relatii = [{'from': r.categorie_din, 'to': r.categorie_in,
                'tip': r.tip, 'decalaj': r.decalaj} for r in rows]
    # reconstruieste ordine_categorii: rangul lui 'din' intai, apoi 'in' = rang_din + 1
    rang: dict = {}
    for r in rows:
        if r.rang_din is not None:
            rang.setdefault(r.categorie_din, r.rang_din)
    for r in rows:
        baza = rang.get(r.categorie_din, r.rang_din if r.rang_din is not None else 0)
        rang.setdefault(r.categorie_in, baza + 1)
    ordine = sorted(rang, key=lambda c: (rang[c], c))
    return {
        'ordine_categorii': ordine,
        'intra_categorie': json_dep.get('intra_categorie', 'secvential'),
        'relatii': relatii,
    }


def setari(tenant_id: Optional[int] = None) -> dict:
    """setari.json cu `coloane` si `randamente` suprascrise din DB (daca exista)."""
    base = dict(cfg.incarca('setari', cfg.SETARI_IMPLICITE))
    base['coloane'] = coloane(tenant_id)
    base['randamente'] = randamente_gantt(tenant_id)
    return base


# ---------------------------------------------------------------------------
# Profiluri de mapare (invatate din wizard) - amprenta antetului.
# ---------------------------------------------------------------------------
def semnatura_antet(rand_antet) -> str:
    """Amprenta stabila a unui rand de antet (celule normalizate, sortate, unite cu '|')."""
    celule = sorted({normalizeaza(c) for c in (rand_antet or []) if c is not None
                     and str(c).strip()})
    return '|'.join(celule)[:255]


def gaseste_profil(semnatura: str, tenant_id: Optional[int] = None):
    """Profilul de mapare activ pentru o semnatura de antet (sau None)."""
    if not semnatura:
        return None
    try:
        from flask import has_app_context
        if not has_app_context():
            return None
        from sqlalchemy import or_
        from models import GanttProfilMapare
        q = GanttProfilMapare.query.filter_by(activ=True, semnatura=semnatura)
        if tenant_id is not None:
            q = q.filter(or_(GanttProfilMapare.tenant_id == tenant_id,
                             GanttProfilMapare.tenant_id.is_(None)))
        else:
            q = q.filter(GanttProfilMapare.tenant_id.is_(None))
        return q.order_by(GanttProfilMapare.nr_utilizari.desc()).first()
    except Exception:
        return None


def profil_mapare(profil) -> tuple:
    """Despacheteaza un profil -> ({camp: index_coloana}, rand_antet:int|None)."""
    import json
    try:
        d = json.loads(profil.mapare_json) if (profil and profil.mapare_json) else {}
        col = {k: int(v) for k, v in (d.get('coloane') or {}).items()}
        ra = d.get('rand_antet')
        return col, (int(ra) if ra is not None else None)
    except Exception:
        return {}, None


def salveaza_profil(nume: str, semnatura: str, coloane_map: dict,
                    rand_antet: Optional[int] = None, sursa: str = 'wizard',
                    tenant_id: Optional[int] = None, user_id: Optional[int] = None):
    """Upsert profil de mapare pe (tenant_id, semnatura). Audit-logat. None la esec."""
    if not semnatura:
        return None
    try:
        from flask import has_app_context
        if not has_app_context():
            return None
        import json
        from datetime import datetime
        from models import db, GanttProfilMapare
        from services import audit

        payload = json.dumps({
            'coloane': {k: int(v) for k, v in (coloane_map or {}).items()},
            'rand_antet': (int(rand_antet) if rand_antet is not None else None),
        })
        prof = GanttProfilMapare.query.filter_by(semnatura=semnatura,
                                                 tenant_id=tenant_id).first()
        nou = prof is None
        if nou:
            prof = GanttProfilMapare(
                nume=(nume or f'Profil {semnatura[:12]}'), semnatura=semnatura,
                mapare_json=payload, sursa=sursa, tenant_id=tenant_id, creat_de_id=user_id)
            db.session.add(prof)
        else:
            prof.mapare_json = payload
            prof.sursa = sursa
            prof.activ = True
            if nume:
                prof.nume = nume
            prof.data_actualizare = datetime.utcnow()
        db.session.flush()
        audit.log('create' if nou else 'update', 'gantt_profil_mapare', prof.id,
                  new_values={'nume': prof.nume, 'semnatura': semnatura, 'sursa': sursa})
        db.session.commit()
        return prof
    except Exception:
        try:
            from models import db
            db.session.rollback()
        except Exception:
            pass
        return None


def marcheaza_utilizare(profil) -> None:
    """Incrementeaza nr_utilizari pe un profil aplicat (best-effort)."""
    try:
        from flask import has_app_context
        if not has_app_context() or profil is None:
            return
        from models import db
        profil.nr_utilizari = (profil.nr_utilizari or 0) + 1
        db.session.commit()
    except Exception:
        try:
            from models import db
            db.session.rollback()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Administrare (CRUD pentru pagina /gantt/config). Audit-logat.
# Returneaza ALL randurile (active + inactive) - spre deosebire de overlay-ul
# de mai sus, care filtreaza doar activ=True.
# ---------------------------------------------------------------------------
def _model_admin(entitate: str):
    from models import (GanttSinonimColoana, GanttClasificareRegula, GanttProfilMapare)
    return {'sinonim': GanttSinonimColoana, 'regula': GanttClasificareRegula,
            'profil': GanttProfilMapare}.get(entitate)


def _scope(q, model, tenant_id):
    from sqlalchemy import or_
    if tenant_id is not None:
        return q.filter(or_(model.tenant_id == tenant_id, model.tenant_id.is_(None)))
    return q.filter(model.tenant_id.is_(None))


def _audit(action: str, entity_type: str, entity_id, values: dict) -> None:
    try:
        from services import audit
        audit.log(action, entity_type, entity_id, new_values=values, commit=True)
    except Exception:
        pass


def lista_sinonime(tenant_id: Optional[int] = None) -> list:
    from models import GanttSinonimColoana as M
    return _scope(M.query, M, tenant_id).order_by(M.camp, M.sinonim).all()


def lista_reguli(tenant_id: Optional[int] = None) -> list:
    from models import GanttClasificareRegula as M
    return _scope(M.query, M, tenant_id).order_by(
        M.categorie, M.tip_regula, M.prioritate, M.valoare).all()


def lista_profiluri(tenant_id: Optional[int] = None) -> list:
    from models import GanttProfilMapare as M
    return _scope(M.query, M, tenant_id).order_by(M.nr_utilizari.desc(), M.nume).all()


def adauga_sinonim(camp: str, sinonim: str, tenant_id=None, user_id=None):
    """(row, eroare). Reactiveaza daca exista dezactivat; refuza duplicat activ."""
    from models import db, GanttSinonimColoana as M
    camp = (camp or '').strip()
    sinonim = (sinonim or '').strip()
    if not camp or not sinonim:
        return None, 'Camp si sinonim sunt obligatorii.'
    ex = M.query.filter_by(tenant_id=tenant_id, camp=camp, sinonim=sinonim).first()
    if ex:
        if not ex.activ:
            ex.activ = True
            db.session.commit()
            _audit('update', 'gantt_sinonim_coloana', ex.id, {'reactivat': True})
            return ex, None
        return ex, 'Sinonimul exista deja.'
    row = M(camp=camp, sinonim=sinonim, activ=True, tenant_id=tenant_id, creat_de_id=user_id)
    db.session.add(row)
    db.session.commit()
    _audit('create', 'gantt_sinonim_coloana', row.id, {'camp': camp, 'sinonim': sinonim})
    return row, None


def adauga_regula(categorie: str, tip_regula: str, valoare: str, prioritate: int = 100,
                  tenant_id=None, user_id=None):
    """(row, eroare). Reactiveaza daca exista dezactivat; refuza duplicat activ."""
    from models import db, GanttClasificareRegula as M
    categorie = (categorie or '').strip().upper()
    tip_regula = (tip_regula or 'cuvant').strip()
    valoare = (valoare or '').strip()
    if tip_regula not in ('cuvant', 'prefix_cod'):
        tip_regula = 'cuvant'
    if not categorie or not valoare:
        return None, 'Categorie si valoare sunt obligatorii.'
    try:
        prioritate = int(prioritate)
    except (TypeError, ValueError):
        prioritate = 100
    ex = M.query.filter_by(tenant_id=tenant_id, categorie=categorie,
                           tip_regula=tip_regula, valoare=valoare).first()
    if ex:
        if not ex.activ:
            ex.activ = True
            ex.prioritate = prioritate
            db.session.commit()
            _audit('update', 'gantt_clasificare_regula', ex.id, {'reactivat': True})
            return ex, None
        return ex, 'Regula exista deja.'
    row = M(categorie=categorie, tip_regula=tip_regula, valoare=valoare,
            prioritate=prioritate, activ=True, tenant_id=tenant_id, creat_de_id=user_id)
    db.session.add(row)
    db.session.commit()
    _audit('create', 'gantt_clasificare_regula', row.id,
           {'categorie': categorie, 'tip_regula': tip_regula, 'valoare': valoare})
    return row, None


def comuta_activ(entitate: str, id_: int, tenant_id=None):
    """Comuta flag-ul activ (soft-enable/disable). Intoarce randul sau None."""
    from models import db
    M = _model_admin(entitate)
    if M is None:
        return None
    row = db.session.get(M, id_)
    if not row or not hasattr(row, 'activ'):
        return None
    if getattr(row, 'tenant_id', None) not in (None, tenant_id):
        return None
    row.activ = not row.activ
    db.session.commit()
    _audit('update', M.__tablename__, id_, {'activ': row.activ})
    return row


def sterge_rand(entitate: str, id_: int, tenant_id=None) -> bool:
    """Sterge definitiv un rand (sinonim/regula/profil). Intoarce True la succes."""
    from models import db
    M = _model_admin(entitate)
    row = db.session.get(M, id_) if M else None
    if not row:
        return False
    if getattr(row, 'tenant_id', None) not in (None, tenant_id):
        return False
    tn = M.__tablename__
    db.session.delete(row)
    db.session.commit()
    _audit('delete', tn, id_, {})
    return True


def redenumeste_profil(id_: int, nume: str, tenant_id=None) -> bool:
    from models import db, GanttProfilMapare as M
    row = db.session.get(M, id_)
    if not row or getattr(row, 'tenant_id', None) not in (None, tenant_id):
        return False
    row.nume = (nume or row.nume).strip()[:120]
    db.session.commit()
    _audit('update', 'gantt_profil_mapare', id_, {'nume': row.nume})
    return True


def sync_din_json(tenant_id: Optional[int] = None, user_id: Optional[int] = None) -> dict:
    """Adauga in DB regulile din config/gantt/*.json care LIPSESC (idempotent, doar ADAUGA;
    nu sterge si nu modifica editarile existente). Necesar dupa update de dictionar pe prod,
    fiindca overlay-ul foloseste DB-ul cand exista randuri. Intoarce {sinonime, reguli, prefixe}."""
    from flask import has_app_context
    if not has_app_context():
        return {}
    from models import db, GanttSinonimColoana, GanttClasificareRegula
    adaugate = {'sinonime': 0, 'reguli': 0, 'prefixe': 0, 'tarife': 0,
                'randamente': 0, 'mapare_bim': 0}

    ex_sin = {(s.camp, s.sinonim)
              for s in GanttSinonimColoana.query.filter_by(tenant_id=tenant_id).all()}
    for camp, syns in cfg.incarca('setari', cfg.SETARI_IMPLICITE).get('coloane', {}).items():
        for s in syns:
            if (camp, s) not in ex_sin:
                db.session.add(GanttSinonimColoana(camp=camp, sinonim=s, activ=True,
                               tenant_id=tenant_id, creat_de_id=user_id))
                ex_sin.add((camp, s)); adaugate['sinonime'] += 1

    ex_cl = {(r.categorie, r.tip_regula, r.valoare)
             for r in GanttClasificareRegula.query.filter_by(tenant_id=tenant_id).all()}
    for cat, words in cfg.incarca('clasificare', cfg.CLASIFICARE_IMPLICITA).items():
        for w in words:
            if (cat, 'cuvant', w) not in ex_cl:
                db.session.add(GanttClasificareRegula(categorie=cat, tip_regula='cuvant',
                               valoare=w, prioritate=100, activ=True,
                               tenant_id=tenant_id, creat_de_id=user_id))
                ex_cl.add((cat, 'cuvant', w)); adaugate['reguli'] += 1

    for prefix, cat in (cfg.incarca('prefixe', {}) or {}).items():
        if str(prefix).startswith('_'):
            continue
        if (cat, 'prefix_cod', prefix) not in ex_cl:
            db.session.add(GanttClasificareRegula(categorie=cat, tip_regula='prefix_cod',
                           valoare=prefix, prioritate=100, activ=True,
                           tenant_id=tenant_id, creat_de_id=user_id))
            ex_cl.add((cat, 'prefix_cod', prefix)); adaugate['prefixe'] += 1

    # mapare tip_element BIM -> categorie (pentru 4D)
    for tip, cat in (cfg.incarca('mapare_bim', {}) or {}).items():
        if str(tip).startswith('_'):
            continue
        if (cat, 'tip_element', tip) not in ex_cl:
            db.session.add(GanttClasificareRegula(categorie=cat, tip_regula='tip_element',
                           valoare=tip, prioritate=100, activ=True,
                           tenant_id=tenant_id, creat_de_id=user_id))
            ex_cl.add((cat, 'tip_element', tip)); adaugate['mapare_bim'] += 1

    # tarife pe categorie -> tarife_categorie (disciplina='gantt', global)
    from models import TarifCategorie
    ex_tarif = {r.categorie_lucrare for r in TarifCategorie.query.filter_by(
        disciplina=_DISC_GANTT, proiect_id=None).all()
        if r.tenant_id in (None, tenant_id)}
    for cat, v in (cfg.incarca('tarife', {}) or {}).items():
        if str(cat).startswith('_') or cat in ex_tarif:
            continue
        db.session.add(TarifCategorie(
            disciplina=_DISC_GANTT, categorie_lucrare=cat,
            tarif_baza=float(v.get('tarif', 0) or 0), um_referinta=(v.get('um') or None),
            proiect_id=None, tenant_id=tenant_id, creat_de_id=user_id))
        ex_tarif.add(cat); adaugate['tarife'] += 1

    # randamente UM/zi -> tarife_categorie (disciplina='gantt-randament')
    ex_rand = {r.categorie_lucrare for r in TarifCategorie.query.filter_by(
        disciplina=_DISC_RAND, proiect_id=None).all() if r.tenant_id in (None, tenant_id)}
    for cat, v in (cfg.incarca('setari', cfg.SETARI_IMPLICITE).get('randamente', {}) or {}).items():
        if cat in ex_rand:
            continue
        db.session.add(TarifCategorie(
            disciplina=_DISC_RAND, categorie_lucrare=cat,
            tarif_baza=float((v or {}).get('randament_zi', 0) or 0),
            um_referinta=((v or {}).get('um') or None),
            proiect_id=None, tenant_id=tenant_id, creat_de_id=user_id))
        ex_rand.add(cat); adaugate['randamente'] += 1

    db.session.commit()
    return adaugate


# ---------------------------------------------------------------------------
# Tarife pe categorie tehnologica (5D) - stocate in tarife_categorie cu
# disciplina='gantt'. Overlay: tarife.json ca baza, DB suprascrie tariful.
# ---------------------------------------------------------------------------
_DISC_GANTT = 'gantt'          # tarif lei/UM
_DISC_RAND = 'gantt-randament'  # randament UM/zi (reutilizam tabelul de tarife)


def randamente_gantt(tenant_id: Optional[int] = None) -> dict:
    """{categorie: {'randament_zi': N, 'um': ref}} - setari.json suprascris de DB."""
    base: dict = {}
    for cat, v in (cfg.incarca('setari', cfg.SETARI_IMPLICITE).get('randamente', {}) or {}).items():
        base[cat] = dict(v or {})
    try:
        from flask import has_app_context
        if has_app_context():
            from sqlalchemy import or_
            from models import TarifCategorie
            q = TarifCategorie.query.filter_by(disciplina=_DISC_RAND, proiect_id=None)
            if tenant_id is not None:
                q = q.filter(or_(TarifCategorie.tenant_id == tenant_id,
                                 TarifCategorie.tenant_id.is_(None)))
            else:
                q = q.filter(TarifCategorie.tenant_id.is_(None))
            for r in q.all():
                d = base.setdefault(r.categorie_lucrare, {})
                d['randament_zi'] = float(r.tarif_baza or 0)
                if r.um_referinta:
                    d['um'] = r.um_referinta
    except Exception:
        pass
    return base


def tarife_gantt(tenant_id: Optional[int] = None) -> dict:
    """{categorie: {'tarif': lei/UM, 'um': ref, 'material': pondere, 'utilaj': pondere}}
    - JSON suprascris de DB. Ponderea 'utilaj' (implicit 0) decupleaza utilajul din manopera."""
    base: dict = {}
    for cat, v in (cfg.incarca('tarife', {}) or {}).items():
        if str(cat).startswith('_'):
            continue
        base[cat] = {'tarif': float((v or {}).get('tarif', 0) or 0),
                     'um': (v or {}).get('um', ''),
                     'material': float((v or {}).get('material', 0.65) or 0.65),
                     'utilaj': float((v or {}).get('utilaj', 0.0) or 0.0)}
    try:
        from flask import has_app_context
        if has_app_context():
            from sqlalchemy import or_
            from models import TarifCategorie
            q = TarifCategorie.query.filter_by(disciplina=_DISC_GANTT, proiect_id=None)
            if tenant_id is not None:
                q = q.filter(or_(TarifCategorie.tenant_id == tenant_id,
                                 TarifCategorie.tenant_id.is_(None)))
            else:
                q = q.filter(TarifCategorie.tenant_id.is_(None))
            for r in q.all():
                d = base.setdefault(r.categorie_lucrare,
                                    {'tarif': 0, 'um': '', 'material': 0.65, 'utilaj': 0.0})
                d['tarif'] = float(r.tarif_baza or 0)
                if r.um_referinta:
                    d['um'] = r.um_referinta
    except Exception:
        pass
    return base


def lista_tarife(tenant_id: Optional[int] = None) -> list:
    """Lista pentru admin: [{categorie, tarif, um, material, din_db}] ordonata."""
    din_db = set()
    try:
        from flask import has_app_context
        if has_app_context():
            from models import TarifCategorie
            for r in TarifCategorie.query.filter_by(disciplina=_DISC_GANTT, proiect_id=None).all():
                if r.tenant_id in (None, tenant_id):
                    din_db.add(r.categorie_lucrare)
    except Exception:
        pass
    eff = tarife_gantt(tenant_id)
    rand = randamente_gantt(tenant_id)
    return [{'categorie': c, 'tarif': eff[c]['tarif'], 'um': eff[c].get('um', ''),
             'material': eff[c].get('material', 0.65), 'din_db': c in din_db,
             'randament': (rand.get(c, {}) or {}).get('randament_zi', 0)}
            for c in sorted(eff)]


def seteaza_tarif(categorie: str, tarif, um: Optional[str] = None,
                  tenant_id=None, user_id=None):
    """Upsert tarif pe categorie (TarifCategorie disciplina='gantt'). (row, eroare)."""
    categorie = (categorie or '').strip().upper()
    if not categorie:
        return None, 'Categorie obligatorie.'
    try:
        tarif = float(str(tarif).replace(',', '.'))
    except (TypeError, ValueError):
        return None, 'Tarif invalid.'
    if tarif < 0:
        return None, 'Tarif invalid.'
    try:
        from flask import has_app_context
        if not has_app_context():
            return None, 'Fara context aplicatie.'
        from models import db, TarifCategorie
        row = TarifCategorie.query.filter_by(
            disciplina=_DISC_GANTT, categorie_lucrare=categorie,
            proiect_id=None, tenant_id=tenant_id).first()
        nou = row is None
        if nou:
            row = TarifCategorie(disciplina=_DISC_GANTT, categorie_lucrare=categorie,
                                 tarif_baza=tarif, um_referinta=(um or None),
                                 proiect_id=None, tenant_id=tenant_id, creat_de_id=user_id)
            db.session.add(row)
        else:
            row.tarif_baza = tarif
            if um:
                row.um_referinta = um
        db.session.flush()
        _audit('create' if nou else 'update', 'tarife_categorie', row.id,
               {'categorie': categorie, 'tarif': tarif, 'disciplina': _DISC_GANTT})
        db.session.commit()
        return row, None
    except Exception:
        try:
            from models import db
            db.session.rollback()
        except Exception:
            pass
        return None, 'Eroare la salvare.'


def seteaza_randament(categorie: str, randament, um: Optional[str] = None,
                      tenant_id=None, user_id=None):
    """Upsert randament UM/zi pe categorie (TarifCategorie disciplina='gantt-randament')."""
    categorie = (categorie or '').strip().upper()
    if not categorie:
        return None, 'Categorie obligatorie.'
    try:
        randament = float(str(randament).replace(',', '.'))
    except (TypeError, ValueError):
        return None, 'Randament invalid.'
    if randament < 0:
        return None, 'Randament invalid.'
    try:
        from flask import has_app_context
        if not has_app_context():
            return None, 'Fara context aplicatie.'
        from models import db, TarifCategorie
        row = TarifCategorie.query.filter_by(
            disciplina=_DISC_RAND, categorie_lucrare=categorie,
            proiect_id=None, tenant_id=tenant_id).first()
        nou = row is None
        if nou:
            row = TarifCategorie(disciplina=_DISC_RAND, categorie_lucrare=categorie,
                                 tarif_baza=randament, um_referinta=(um or None),
                                 proiect_id=None, tenant_id=tenant_id, creat_de_id=user_id)
            db.session.add(row)
        else:
            row.tarif_baza = randament
            if um:
                row.um_referinta = um
        db.session.flush()
        _audit('create' if nou else 'update', 'tarife_categorie', row.id,
               {'categorie': categorie, 'randament': randament, 'disciplina': _DISC_RAND})
        db.session.commit()
        return row, None
    except Exception:
        try:
            from models import db
            db.session.rollback()
        except Exception:
            pass
        return None, 'Eroare la salvare.'
