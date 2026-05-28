"""
Service IFC Import - parseaza fisiere IFC si populeaza tabelele BIM.

Folosim ifcopenshell (pip install ifcopenshell). Daca lib nu e instalata,
functiile returneaza un dictionar cu eroare clara - nu strica aplicatia.

Mapping IFC -> BIM:
- IfcSite     -> Santier
- IfcBuilding -> Cladire
- IfcBuildingStorey -> Nivel
- IfcSpace    -> Spatiu
- IfcZone     -> Zona
- IfcWall, IfcDoor, IfcWindow, etc. -> ElementBIM (cu tip_element din map)
"""

from datetime import datetime

# Map de la tip IFC la cod nostru tip_element
IFC_TYPE_MAP = {
    'IfcWall': 'wall',
    'IfcWallStandardCase': 'wall',
    'IfcDoor': 'door',
    'IfcWindow': 'window',
    'IfcSlab': 'slab',
    'IfcBeam': 'beam',
    'IfcColumn': 'column',
    'IfcStair': 'stair',
    'IfcRailing': 'railing',
    'IfcUnitaryEquipment': 'AHU',  # CTA
    'IfcChiller': 'chiller',
    'IfcFan': 'fan',
    'IfcPump': 'pump',
    'IfcValve': 'valve',
    'IfcPipeSegment': 'pipe',
    'IfcDuctSegment': 'duct',
    'IfcCableCarrierSegment': 'cable_tray',
    'IfcLightFixture': 'light',
    'IfcOutlet': 'outlet',
    'IfcSwitchingDevice': 'switch',
    'IfcElectricDistributionBoard': 'panel',
    'IfcSensor': 'sensor',
    'IfcFireSuppressionTerminal': 'sprinkler',
    'IfcTransportElement': 'elevator',
}


def is_available():
    """Verifica daca ifcopenshell e instalat."""
    try:
        import ifcopenshell  # noqa: F401
        return True
    except ImportError:
        return False


def detection_info():
    """
    Returneaza informatii detaliate despre detectia ifcopenshell.
    Util pentru diagnostic cand instalarea pare facuta dar lib-ul nu apare.
    Mai ales pe PythonAnywhere unde app-ul ruleaza in venv si trebuie
    sa instalezi pachetul exact in acel venv, nu global.
    """
    import sys
    info = {
        'python_executable': sys.executable,
        'python_version': sys.version.split()[0],
        'sys_path_first_5': sys.path[:5],
        'site_packages_candidates': [p for p in sys.path if 'site-packages' in p][:3],
        'available': False,
        'version': None,
        'install_path': None,
        'import_error': None,
    }
    try:
        import ifcopenshell
        info['available'] = True
        info['version'] = getattr(ifcopenshell, 'version', 'unknown')
        info['install_path'] = getattr(ifcopenshell, '__file__', None)
    except ImportError as e:
        info['import_error'] = str(e)
    except Exception as e:
        info['import_error'] = f'{type(e).__name__}: {e}'
    return info


def import_ifc(file_path, santier_id=None, dry_run=False):
    """
    Parcurge un fisier IFC si creeaza Cladire/Nivel/Spatiu/ElementBIM in DB.

    Args:
        file_path: cale absoluta catre fisierul .ifc
        santier_id: ID-ul Santier-ului parinte. Daca None, IfcSite din IFC devine santier nou.
        dry_run: daca True, doar parseaza si returneaza statistici, fara a salva in DB.

    Returns:
        dict cu chei: status, mesaj, statistici, errors
    """
    if not is_available():
        return {
            'status': 'eroare',
            'mesaj': 'Biblioteca ifcopenshell nu este instalata. Ruleaza: pip install ifcopenshell',
            'statistici': {},
            'errors': ['ifcopenshell missing'],
        }

    import ifcopenshell

    # Lazy imports ca sa nu introducem dependenta circulara la import time
    from models import db, Santier, Cladire, Nivel, Zona, Spatiu, ElementBIM

    try:
        ifc = ifcopenshell.open(file_path)
    except Exception as e:
        return {
            'status': 'eroare',
            'mesaj': f'Nu am putut deschide fisierul: {e}',
            'statistici': {},
            'errors': [str(e)],
        }

    statistici = {
        'santiere_create': 0,
        'cladiri_create': 0,
        'niveluri_create': 0,
        'zone_create': 0,
        'spatii_create': 0,
        'elemente_create': 0,
        'elemente_skipped': 0,
    }
    errors = []

    # IfcSite
    sites = ifc.by_type('IfcSite')
    if not sites:
        return {
            'status': 'eroare',
            'mesaj': 'Fisierul IFC nu contine niciun IfcSite.',
            'statistici': statistici,
            'errors': ['no IfcSite'],
        }

    # Foloseste primul Site
    ifc_site = sites[0]
    if santier_id:
        santier = Santier.query.get(santier_id)
        if not santier:
            return {
                'status': 'eroare',
                'mesaj': f'Santier {santier_id} nu exista.',
                'statistici': statistici,
                'errors': [f'santier {santier_id} not found'],
            }
    else:
        cod = (ifc_site.Name or f'SITE-{ifc_site.GlobalId[:8]}').strip()[:50]
        santier = Santier.query.filter_by(extern_id=ifc_site.GlobalId).first()
        if not santier:
            santier = Santier(
                cod=cod,
                nume=ifc_site.LongName or cod,
                extern_id=ifc_site.GlobalId,
            )
            if not dry_run:
                db.session.add(santier)
                db.session.flush()
            statistici['santiere_create'] += 1

    # Harti GlobalId -> obiectul nostru (pentru legarea elementelor de structura)
    cladire_by_guid = {}
    nivel_by_guid = {}
    spatiu_by_guid = {}

    # IfcBuilding
    for ifc_building in ifc.by_type('IfcBuilding'):
        c_cod = (ifc_building.Name or f'BLD-{ifc_building.GlobalId[:8]}').strip()[:50]
        cladire = Cladire.query.filter_by(extern_id=ifc_building.GlobalId).first()
        if not cladire:
            cladire = Cladire(
                santier_id=santier.id if not dry_run else None,
                cod=c_cod,
                nume=ifc_building.LongName or c_cod,
                extern_id=ifc_building.GlobalId,
            )
            if not dry_run:
                db.session.add(cladire)
                db.session.flush()
            statistici['cladiri_create'] += 1
        elif not dry_run and cladire.santier_id is None:
            cladire.santier_id = santier.id
        cladire_by_guid[ifc_building.GlobalId] = cladire

        # IfcBuildingStorey - referinta la cladire prin IsDecomposedBy/RelatedObjects
        for rel in (ifc_building.IsDecomposedBy or []):
            for storey in (rel.RelatedObjects or []):
                if not storey.is_a('IfcBuildingStorey'):
                    continue
                n_cod = (storey.Name or f'N-{storey.GlobalId[:6]}').strip()[:50]
                nivel = Nivel.query.filter_by(extern_id=storey.GlobalId).first()
                if not nivel:
                    elev = None
                    try:
                        elev = float(storey.Elevation) if storey.Elevation is not None else None
                    except (TypeError, ValueError):
                        elev = None
                    nivel = Nivel(
                        cladire_id=cladire.id if not dry_run else None,
                        cod=n_cod,
                        nume=storey.LongName or n_cod,
                        ordine=int(elev) if elev is not None else 0,
                        elevatie_m=elev,
                        extern_id=storey.GlobalId,
                    )
                    if not dry_run:
                        db.session.add(nivel)
                        db.session.flush()
                    statistici['niveluri_create'] += 1
                nivel_by_guid[storey.GlobalId] = nivel

                # IfcSpace
                for rel2 in (storey.IsDecomposedBy or []):
                    for sp in (rel2.RelatedObjects or []):
                        if not sp.is_a('IfcSpace'):
                            continue
                        sp_cod = (sp.Name or f'SP-{sp.GlobalId[:6]}').strip()[:50]
                        spatiu = Spatiu.query.filter_by(extern_id=sp.GlobalId).first()
                        if not spatiu:
                            spatiu = Spatiu(
                                nivel_id=nivel.id if not dry_run else None,
                                cod=sp_cod,
                                nume=sp.LongName or sp_cod,
                                extern_id=sp.GlobalId,
                            )
                            if not dry_run:
                                db.session.add(spatiu)
                                db.session.flush()
                            statistici['spatii_create'] += 1
                        spatiu_by_guid[sp.GlobalId] = spatiu

    # Elemente fizice: capturam TOATE subtipurile IfcElement (nu doar maparea),
    # ca sa nu pierdem elemente structurale/MEP/proxy. tip_element din mapa daca
    # exista, altfel fallback pe numele clasei IFC (ex. IfcMember -> 'member').
    element_by_guid = {}
    seen_guids = set()
    existing_by_guid = {}
    if not dry_run:
        # Preincarcam elementele existente: la re-import le (re)legam de structura
        # (vindeca orfanii dintr-un import vechi), fara sa le recream.
        for _el in ElementBIM.query.filter(ElementBIM.ifc_global_id.isnot(None)).all():
            existing_by_guid[_el.ifc_global_id] = _el
    try:
        elemente_ifc = ifc.by_type('IfcElement')
    except Exception:
        elemente_ifc = []
    for inst in elemente_ifc:
        guid = getattr(inst, 'GlobalId', None)
        if not guid or guid in seen_guids:
            continue
        # Sarim peste goluri (IfcOpeningElement etc.) - nu-s elemente fizice reale
        if inst.is_a('IfcFeatureElement'):
            continue
        seen_guids.add(guid)
        if guid in existing_by_guid:
            # Exista deja: il luam pentru (re)legare spatiala, nu-l recream.
            element_by_guid[guid] = existing_by_guid[guid]
            statistici['elemente_skipped'] += 1
            continue
        klass = inst.is_a()
        our_type = IFC_TYPE_MAP.get(klass)
        if not our_type:
            our_type = (klass[3:] if klass.startswith('Ifc') else klass).lower()[:40]
        cod = (inst.Name or f'{our_type.upper()}-{guid[:6]}').strip()[:100]
        element = ElementBIM(
            cod=cod,
            nume=inst.Name or '',
            tip_element=our_type,
            ifc_global_id=guid,
            status='proiectat',
        )
        if not dry_run:
            db.session.add(element)
        statistici['elemente_create'] += 1
        element_by_guid[guid] = element

    # Legare elemente -> structura spatiala (IfcRelContainedInSpatialStructure).
    # Fara asta, elementele raman orfane si 4D/5D/clash (care filtreaza pe
    # cladire_id) nu le vad.
    statistici['elemente_legate'] = 0
    if not dry_run:
        db.session.flush()  # elementele primesc id-uri
        try:
            rels = ifc.by_type('IfcRelContainedInSpatialStructure')
        except Exception:
            rels = []
        for rel in rels:
            struct = getattr(rel, 'RelatingStructure', None)
            if struct is None:
                continue
            sguid = struct.GlobalId
            nivel_id = spatiu_id = cladire_id = None
            if struct.is_a('IfcBuildingStorey'):
                nv = nivel_by_guid.get(sguid)
                if nv:
                    nivel_id, cladire_id = nv.id, nv.cladire_id
            elif struct.is_a('IfcSpace'):
                sp = spatiu_by_guid.get(sguid)
                if sp:
                    spatiu_id, nivel_id = sp.id, sp.nivel_id
            elif struct.is_a('IfcBuilding'):
                cl = cladire_by_guid.get(sguid)
                if cl:
                    cladire_id = cl.id
            for el_inst in (rel.RelatedElements or []):
                elem = element_by_guid.get(getattr(el_inst, 'GlobalId', None))
                if elem is None:
                    continue
                if cladire_id is not None:
                    elem.cladire_id = cladire_id
                if nivel_id is not None:
                    elem.nivel_id = nivel_id
                if spatiu_id is not None:
                    elem.spatiu_id = spatiu_id
                statistici['elemente_legate'] += 1

    if not dry_run:
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return {
                'status': 'eroare',
                'mesaj': f'Eroare la salvare DB: {e}',
                'statistici': statistici,
                'errors': [str(e)],
            }

    total_create = sum(v for k, v in statistici.items() if k.endswith('_create'))
    return {
        'status': 'ok',
        'mesaj': f'Import finalizat. {total_create} entitati create.',
        'statistici': statistici,
        'errors': errors,
        'santier_id': santier.id if santier else None,
    }


def export_bcf(issues_query):
    """
    Genereaza un fisier BCF (BIM Collaboration Format) cu issues.

    BCF e un ZIP cu structura specifica:
      bcf.version
      <topic-guid>/
        markup.bcf  (XML cu metadata)
        viewpoint.bcfv (optional - viewpoint 3D)
        snapshot.png (optional)

    Returneaza BytesIO cu continutul ZIP.
    """
    from io import BytesIO
    from zipfile import ZipFile, ZIP_DEFLATED
    import uuid

    output = BytesIO()
    with ZipFile(output, 'w', ZIP_DEFLATED) as zf:
        # bcf.version
        zf.writestr('bcf.version', '''<?xml version="1.0" encoding="UTF-8"?>
<Version VersionId="2.1" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <DetailedVersion>2.1</DetailedVersion>
</Version>''')

        for issue in issues_query:
            topic_guid = issue.bcf_topic_guid or str(uuid.uuid4())
            data_creare = issue.data_creare or datetime.utcnow()
            markup = f'''<?xml version="1.0" encoding="UTF-8"?>
<Markup xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <Topic Guid="{topic_guid}" TopicType="{issue.tip}" TopicStatus="{issue.status}">
    <Title>{_xml_escape(issue.titlu)}</Title>
    <Priority>{issue.severitate}</Priority>
    <CreationDate>{data_creare.strftime('%Y-%m-%dT%H:%M:%S')}</CreationDate>
    <CreationAuthor>{_xml_escape(issue.raportor.email if issue.raportor else 'system')}</CreationAuthor>
    <Description>{_xml_escape(issue.descriere or '')}</Description>
  </Topic>
</Markup>'''
            zf.writestr(f'{topic_guid}/markup.bcf', markup)

    output.seek(0)
    return output


def _xml_escape(s):
    if s is None:
        return ''
    return (str(s)
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
        .replace('"', '&quot;')
        .replace("'", '&apos;'))
