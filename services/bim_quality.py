"""
BIM Data Quality Service - rapoarte de validare cross-entity.

Rapoarte oferite:
- elemente_fara_ifc_guid: elemente care ar trebui sa aiba GUID dar nu au
- elemente_orfane: elemente fara cladire/nivel/spatiu setat
- elemente_inconsistente: spatiu si nivel din locatii diferite
- activitati_link_inconsistent: activitati cu BIM links din locatii diferite
- duplicate_extern_id: acelasi extern_id folosit pe mai multe entitati ale aceluiasi tip
- mappings_orfane: ExternalMapping-uri catre entitati inexistente
- elemente_nesincronizate: elemente importate IFC dar care nu au last_synced_at

Returns:
    Lista de dict-uri cu cheile {tip, severitate, mesaj, entitate_id, link_url}
"""

from datetime import datetime, timedelta


def report_elemente_fara_guid(db, ElementBIM):
    """Elemente importate IFC fara GlobalId."""
    rezultate = []
    elemente = ElementBIM.query.filter(
        ElementBIM.source_system == 'ifc',
        ElementBIM.ifc_global_id.is_(None),
    ).all()
    for e in elemente:
        rezultate.append({
            'tip': 'element_fara_guid',
            'severitate': 'mare',
            'mesaj': f'Element {e.cod} importat din IFC dar fara GlobalId',
            'entitate_id': e.id,
            'link_url': f'/bim/element/{e.id}',
        })
    return rezultate


def report_elemente_orfane(db, ElementBIM):
    """Elemente fara cladire / nivel / spatiu (no spatial context)."""
    rezultate = []
    elemente = ElementBIM.query.filter(
        ElementBIM.cladire_id.is_(None),
        ElementBIM.nivel_id.is_(None),
        ElementBIM.spatiu_id.is_(None),
    ).all()
    for e in elemente:
        rezultate.append({
            'tip': 'element_orfan',
            'severitate': 'medie',
            'mesaj': f'Element {e.cod} ({e.tip_label}) fara context spatial',
            'entitate_id': e.id,
            'link_url': f'/bim/element/{e.id}',
        })
    return rezultate


def report_elemente_inconsistente(db, ElementBIM):
    """Elemente cu mismatch intre spatiu/nivel/cladire."""
    rezultate = []
    for e in ElementBIM.query.all():
        warnings = e.validation_warnings
        for w in warnings:
            rezultate.append({
                'tip': 'element_inconsistent',
                'severitate': 'mare',
                'mesaj': f'Element {e.cod}: {w}',
                'entitate_id': e.id,
                'link_url': f'/bim/element/{e.id}',
            })
    return rezultate


def report_activitati_link_inconsistent(db, RaportActivitate, ElementBIM, Spatiu):
    """Activitati cu element_bim si spatiu din cladiri diferite."""
    rezultate = []
    activitati = RaportActivitate.query.filter(
        RaportActivitate.element_bim_id.isnot(None),
        RaportActivitate.spatiu_id.isnot(None),
    ).all()
    for a in activitati:
        e = ElementBIM.query.get(a.element_bim_id)
        sp = Spatiu.query.get(a.spatiu_id)
        if e and sp and sp.nivel and e.cladire_id and sp.nivel.cladire_id != e.cladire_id:
            rezultate.append({
                'tip': 'activitate_link_inconsistent',
                'severitate': 'mare',
                'mesaj': f'Activitatea #{a.id} are element din cladirea {e.cladire_id} dar spatiu din cladirea {sp.nivel.cladire_id}',
                'entitate_id': a.id,
                'link_url': f'/activitati/{a.id}',
            })
    return rezultate


def report_duplicate_extern_id(db, ElementBIM):
    """Elemente cu acelasi (source_system, ifc_global_id) - posibil duplicate la import."""
    from sqlalchemy import func
    rezultate = []
    duplicate = db.session.query(
        ElementBIM.ifc_global_id, func.count(ElementBIM.id).label('cnt')
    ).filter(ElementBIM.ifc_global_id.isnot(None)).group_by(
        ElementBIM.ifc_global_id
    ).having(func.count(ElementBIM.id) > 1).all()

    for guid, cnt in duplicate:
        elemente = ElementBIM.query.filter_by(ifc_global_id=guid).all()
        codes = [e.cod for e in elemente]
        rezultate.append({
            'tip': 'duplicate_ifc_guid',
            'severitate': 'mare',
            'mesaj': f'IFC GUID {guid[:16]}... folosit de {cnt} elemente: {", ".join(codes[:3])}',
            'entitate_id': elemente[0].id,
            'link_url': f'/bim/element/{elemente[0].id}',
        })
    return rezultate


def report_mappings_orfane(db, ExternalMapping, model_classes):
    """ExternalMapping catre entitati care nu mai exista (sterse)."""
    rezultate = []
    type_to_class = {
        'santier': 'Santier', 'cladire': 'Cladire', 'nivel': 'Nivel',
        'zona': 'Zona', 'spatiu': 'Spatiu', 'element_bim': 'ElementBIM',
        'asset': 'Asset', 'issue_bim': 'IssueBIM', 'model_bim': 'ModelBIM',
    }
    for m in ExternalMapping.query.all():
        cls_name = type_to_class.get(m.entity_type)
        if not cls_name:
            continue
        cls = model_classes.get(cls_name)
        if cls and cls.query.get(m.entity_id) is None:
            rezultate.append({
                'tip': 'mapping_orfan',
                'severitate': 'medie',
                'mesaj': f'Mapping #{m.id} catre {m.entity_type}#{m.entity_id} - entitate inexistenta',
                'entitate_id': m.id,
                'link_url': '#',
            })
    return rezultate


def report_elemente_nesincronizate(db, ElementBIM, days=30):
    """Elemente importate dar nesinchronizate de mult timp."""
    rezultate = []
    cutoff = datetime.utcnow() - timedelta(days=days)
    elemente = ElementBIM.query.filter(
        ElementBIM.source_system == 'ifc',
        db.or_(
            ElementBIM.last_synced_at.is_(None),
            ElementBIM.last_synced_at < cutoff,
        ),
    ).limit(50).all()
    for e in elemente:
        last = e.last_synced_at.strftime('%Y-%m-%d') if e.last_synced_at else 'niciodata'
        rezultate.append({
            'tip': 'element_nesincronizat',
            'severitate': 'mica',
            'mesaj': f'Element {e.cod} nesincronizat din {last}',
            'entitate_id': e.id,
            'link_url': f'/bim/element/{e.id}',
        })
    return rezultate


def run_all_reports(db, RaportActivitate, ElementBIM, Spatiu, ExternalMapping,
                    Santier, Cladire, Nivel, Zona, Asset, IssueBIM, ModelBIM):
    """Ruleaza toate rapoartele si returneaza dict cu stats + lista entrii."""
    model_classes = {
        'Santier': Santier, 'Cladire': Cladire, 'Nivel': Nivel,
        'Zona': Zona, 'Spatiu': Spatiu, 'ElementBIM': ElementBIM,
        'Asset': Asset, 'IssueBIM': IssueBIM, 'ModelBIM': ModelBIM,
    }
    toate = []
    toate.extend(report_elemente_fara_guid(db, ElementBIM))
    toate.extend(report_elemente_orfane(db, ElementBIM))
    toate.extend(report_elemente_inconsistente(db, ElementBIM))
    toate.extend(report_activitati_link_inconsistent(db, RaportActivitate, ElementBIM, Spatiu))
    toate.extend(report_duplicate_extern_id(db, ElementBIM))
    toate.extend(report_mappings_orfane(db, ExternalMapping, model_classes))
    toate.extend(report_elemente_nesincronizate(db, ElementBIM))

    by_severitate = {'mare': 0, 'medie': 0, 'mica': 0}
    by_tip = {}
    for it in toate:
        by_severitate[it['severitate']] = by_severitate.get(it['severitate'], 0) + 1
        by_tip[it['tip']] = by_tip.get(it['tip'], 0) + 1

    return {
        'total': len(toate),
        'by_severitate': by_severitate,
        'by_tip': by_tip,
        'entries': toate,
    }
