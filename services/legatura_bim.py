"""
Puntea BIM (IFC) <-> deviz (F3) <-> resurse (C).

Legatura nu se face pe cod comun (BIM si devizul nu impart un cod), ci pe
CATEGORIA DE LUCRARE + cantitate. Modelul 3D e sursa cantitatilor (QTO),
devizul F3 e cantitatile pretuite, iar resursele C se ataseaza prin F3.

  legatura_bim(proiect_id) -> {
    are_model, are_plan,
    categorii: [ {categorie, model_cant, model_um, model_nr, f3_cant, f3_um,
                  f3_valoare, diff_pct, status, resurse: [{tip, cod, denumire, valoare}]} ]
  }

Maparea tip element BIM -> categorie de lucrare (F2) e un default rezonabil,
editabil pe viitor. status: ok/atentie/critic (acelasi UM), info (UM diferit),
doar_model / doar_deviz.
"""
from __future__ import annotations

# tip element BIM -> categorie de lucrare (deviz / F2)
TIP_F2 = {
    'slab': 'beton', 'beam': 'beton', 'column': 'beton', 'footing': 'beton',
    'foundation': 'beton', 'stair': 'beton', 'pile': 'beton', 'ramp': 'beton',
    'rebar': 'armatura', 'mesh': 'armatura',
    'wall': 'zidarie', 'curtain_wall': 'placaje', 'covering': 'termosistem',
    'roof': 'invelitori', 'door': 'tamplarie', 'window': 'tamplarie',
    'railing': 'confectii_metalice', 'member': 'confectii_metalice',
    'plate': 'confectii_metalice', 'fastener': 'confectii_metalice',
    'pipe': 'conducte_sanitare', 'duct': 'ventilatie', 'valve': 'armaturi_sanitare',
    'pump': 'echipamente_sanitare', 'sprinkler': 'echipamente_sanitare',
    'AHU': 'echipamente_termice', 'chiller': 'echipamente_termice', 'fan': 'ventilatie',
    'panel': 'tablouri', 'sensor': 'instrumente', 'light': 'corpuri_iluminat',
    'outlet': 'accesorii_electrice', 'switch': 'accesorii_electrice',
    'cable_tray': 'cabluri', 'elevator': 'echipamente_cs',
}


def _elemente_proiect(proiect_id):
    """Elementele BIM ale proiectului (prin santierele legate)."""
    from models import ElementBIM, Cladire, Proiect
    p = Proiect.query.get(proiect_id)
    if not p:
        return []
    sids = [ls.santier_id for ls in p.legaturi_santiere if ls.santier_id]
    if not sids:
        return []
    return (ElementBIM.query.join(Cladire, ElementBIM.cladire_id == Cladire.id)
            .filter(Cladire.santier_id.in_(sids)).all())


def legatura_bim(proiect_id: int) -> dict:
    from models import GanttPlan, ExtrasResursa
    from services.ifc_qto import qto_din_elemente
    from services.deviz_extras import cod_resursa, _rezultat_plan

    elemente = _elemente_proiect(proiect_id)
    # 1. QTO model -> grupat pe categorie F2
    model = {}   # categorie -> {cant, um, nr}
    for row in qto_din_elemente(elemente):
        cat = TIP_F2.get(row['tip'])
        if not cat:
            continue
        m = model.setdefault(cat, {'cant': 0.0, 'um': row['um'], 'nr': 0})
        m['cant'] += float(row['cantitate'] or 0)
        m['nr'] += int(row['nr'] or 0)
        if row['um'] and row['um'] != 'buc':
            m['um'] = row['um']

    # 2. F3 (plan) -> grupat pe categorie_lucrare + codurile de resursa pe categorie
    f3 = {}      # categorie -> {cant, um, valoare, coduri:set}
    plan = (GanttPlan.query.filter_by(proiect_id=proiect_id)
            .order_by(GanttPlan.data_creare.desc()).first())
    if plan:
        try:
            rez, _ = _rezultat_plan(plan)
            for a in rez.activitati:
                cat = a.categorie_lucrare
                if not cat:
                    continue
                g = f3.setdefault(cat, {'cant': 0.0, 'um': a.um, 'valoare': 0.0, 'coduri': set()})
                g['cant'] += float(a.cantitate or 0)
                g['valoare'] += float(a.valoare or 0)
                if a.um and not g['um']:
                    g['um'] = a.um
                c = cod_resursa(a.nume)
                if c:
                    g['coduri'].add(c)
        except Exception:
            plan = None

    # 3. resurse C (pe cod) -> atasate categoriei via codurile articolelor F3
    extrase = {e.cod: e for e in ExtrasResursa.query.filter_by(proiect_id=proiect_id).all()
               if e.cod}

    cats = sorted(set(model) | set(f3))
    out = []
    for cat in cats:
        m = model.get(cat)
        f = f3.get(cat)
        mc = round(m['cant'], 2) if m else 0.0
        fc = round(f['cant'], 2) if f else 0.0
        mum = (m['um'] if m else '') or ''
        fum = (f['um'] if f else '') or ''
        if not f:
            status = 'doar_model'
        elif not m:
            status = 'doar_deviz'
        elif mum and fum and mum != fum:
            status = 'info'           # UM diferit -> nu comparam cantitativ
        else:
            baza = max(mc, fc)
            diff = (abs(mc - fc) / baza * 100.0) if baza else 0.0
            status = 'ok' if diff <= 5 else ('atentie' if diff <= 25 else 'critic')
        resurse = []
        if f:
            for c in sorted(f['coduri']):
                e = extrase.get(c)
                if e:
                    resurse.append({'tip': e.tip, 'cod': e.cod,
                                    'denumire': e.denumire[:50],
                                    'valoare': round(float(e.valoare or 0), 0)})
        out.append({
            'categorie': cat, 'model_cant': mc, 'model_um': mum,
            'model_nr': (m['nr'] if m else 0),
            'f3_cant': fc, 'f3_um': fum,
            'f3_valoare': round(f['valoare'], 0) if f else 0.0,
            'diff_pct': round((abs(mc - fc) / max(mc, fc) * 100.0), 1) if (m and f and max(mc, fc)) else 0.0,
            'status': status, 'resurse': resurse,
        })
    return {'are_model': bool(elemente), 'are_plan': bool(plan),
            'nr_elemente': len(elemente), 'categorii': out}
