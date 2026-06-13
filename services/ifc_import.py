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

import json
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)

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
    # structurale (beton armat + metal) - frecvente in modelele reale
    'IfcReinforcingBar': 'rebar',
    'IfcReinforcingMesh': 'mesh',
    'IfcFooting': 'footing',
    'IfcPlate': 'plate',
    'IfcMember': 'member',
    'IfcFastener': 'fastener',
    'IfcMechanicalFastener': 'fastener',
    'IfcBuildingElementProxy': 'proxy',
    'IfcCovering': 'covering',
    'IfcCurtainWall': 'curtain_wall',
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


# Plafon de elemente procesate geometric (bbox) per import - acelasi prag ca la
# QTO (services.ifc_qto.qto_din_ifc max_geom=3000), ca sa nu incetinim importul
# pe modele uriase. Peste plafon, elementele nu primesc bbox (raman fara bbox_json).
MAX_GEOM_BBOX = 3000


def _valoare_serializabila(v):
    """Coboara o valoare IFC la ceva serializabil JSON (str pentru rest).

    NominalValue.wrappedValue poate fi bool/int/float/str. Tipurile simple le
    pastram ca atare; orice altceva (tuple, entitati, obiecte) devine str().
    """
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    try:
        return str(v)
    except Exception:
        return None


def extrage_psets(inst):
    """Extrage Property Sets + Element Quantities ale unui element IFC.

    Functie PURA si testabila fara ifcopenshell real: accepta orice obiect
    element-like cu atributul .IsDefinedBy (lista de relatii duck-typed).
    Parcurge inst.IsDefinedBy -> IfcRelDefinesByProperties -> RelatingPropertyDefinition:
      - IfcPropertySet     -> HasProperties (IfcPropertySingleValue: .Name + .NominalValue.wrappedValue)
      - IfcElementQuantity -> Quantities (IfcQuantityLength/Area/Volume/Count/Weight)

    Returneaza {nume_pset: {nume_prop: valoare}}. Robust la None / atribute
    lipsa (try/except per proprietate) - nu arunca niciodata, doar sare peste
    ce nu poate citi. Dict gol daca elementul nu are nicio proprietate.
    """
    rezultat = {}
    relatii = getattr(inst, 'IsDefinedBy', None) or []
    for rel in relatii:
        try:
            if not rel.is_a('IfcRelDefinesByProperties'):
                continue
            pd = getattr(rel, 'RelatingPropertyDefinition', None)
            if pd is None:
                continue

            if pd.is_a('IfcPropertySet'):
                nume_pset = getattr(pd, 'Name', None) or 'Pset'
                props = rezultat.setdefault(nume_pset, {})
                for prop in (getattr(pd, 'HasProperties', None) or []):
                    try:
                        if not prop.is_a('IfcPropertySingleValue'):
                            continue
                        nume = getattr(prop, 'Name', None)
                        if not nume:
                            continue
                        nv = getattr(prop, 'NominalValue', None)
                        val = getattr(nv, 'wrappedValue', None) if nv is not None else None
                        props[nume] = _valoare_serializabila(val)
                    except Exception:
                        continue

            elif pd.is_a('IfcElementQuantity'):
                nume_qto = getattr(pd, 'Name', None) or 'Quantities'
                qtos = rezultat.setdefault(nume_qto, {})
                # (tip IFC quantity, atribut cu valoarea)
                _attr_qty = [
                    ('IfcQuantityLength', 'LengthValue'),
                    ('IfcQuantityArea', 'AreaValue'),
                    ('IfcQuantityVolume', 'VolumeValue'),
                    ('IfcQuantityCount', 'CountValue'),
                    ('IfcQuantityWeight', 'WeightValue'),
                ]
                for q in (getattr(pd, 'Quantities', None) or []):
                    try:
                        nume = getattr(q, 'Name', None)
                        if not nume:
                            continue
                        for ifc_qty, attr in _attr_qty:
                            if q.is_a(ifc_qty):
                                val = getattr(q, attr, None)
                                qtos[nume] = _valoare_serializabila(val)
                                break
                    except Exception:
                        continue
        except Exception:
            continue

    # Elimina pset-urile ramase goale (ex. set fara proprietati citibile)
    return {k: v for k, v in rezultat.items() if v}


def extrage_bbox(inst, geom, settings, ushape=None):
    """Bounding box (axis-aligned) din geometria tesalata a elementului.

    Reutilizeaza motorul geometric din services.ifc_qto (_motor_geom): geom e
    ifcopenshell.geom, settings = geom.settings(). ushape e acceptat pentru
    simetrie cu QTO dar nu e folosit aici (citim direct verticele).

    Returneaza {"min":[x,y,z], "max":[x,y,z]} in coordonate model (de regula
    metri dupa unit-scaling ifcopenshell), sau None la esec / geometrie absenta.
    """
    if geom is None or settings is None:
        return None
    try:
        sh = geom.create_shape(settings, inst)
        verts = sh.geometry.verts  # lista plata [x0,y0,z0, x1,y1,z1, ...]
        if not verts or len(verts) < 3:
            return None
        min_x = min_y = min_z = None
        max_x = max_y = max_z = None
        n = len(verts) - (len(verts) % 3)
        for i in range(0, n, 3):
            x, y, z = verts[i], verts[i + 1], verts[i + 2]
            if min_x is None:
                min_x = max_x = x
                min_y = max_y = y
                min_z = max_z = z
            else:
                if x < min_x:
                    min_x = x
                elif x > max_x:
                    max_x = x
                if y < min_y:
                    min_y = y
                elif y > max_y:
                    max_y = y
                if z < min_z:
                    min_z = z
                elif z > max_z:
                    max_z = z
        if min_x is None:
            return None
        return {
            'min': [float(min_x), float(min_y), float(min_z)],
            'max': [float(max_x), float(max_y), float(max_z)],
        }
    except Exception:
        return None


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

    # Extragere Psets + bbox: doar cand flag-ul 'bim-pset-extraction' e ON.
    # Cand OFF, comportamentul ramane IDENTIC cu cel istoric (import rapid, fara
    # parcurgere de proprietati / geometrie). Evaluam flag-ul O(1), inainte de bucla.
    extrage_proprietati = False
    try:
        from services.feature_flags import is_enabled
        extrage_proprietati = is_enabled('bim-pset-extraction')
    except Exception:
        extrage_proprietati = False

    # Motor geometric pentru bbox (lazy, doar daca extragem proprietati). Plafonat
    # global la MAX_GEOM_BBOX ca sa nu incetinim importul modelelor mari.
    geom = settings_geom = ushape = None
    if extrage_proprietati:
        try:
            from services.ifc_qto import _motor_geom
            geom, settings_geom, ushape = _motor_geom()
        except Exception:
            geom = settings_geom = ushape = None
    geom_facute = 0   # buget global de elemente procesate geometric (bbox)

    # Elemente fizice (parcurgem direct, nu via spatial structure).
    # Preincarc GlobalId-urile existente o singura data (1 query) -> evit un SELECT
    # per element la modele mari (era O(N) query-uri de dedup; acum O(1) + set lookup).
    existing_ids = {gid for (gid,) in db.session.query(ElementBIM.ifc_global_id)
                    .filter(ElementBIM.ifc_global_id.isnot(None)).all()}
    for ifc_type, our_type in IFC_TYPE_MAP.items():
        try:
            instances = ifc.by_type(ifc_type)
        except Exception:
            continue
        for inst in instances:
            if inst.GlobalId in existing_ids:
                statistici['elemente_skipped'] += 1
                continue
            existing_ids.add(inst.GlobalId)   # evita dubluri in acelasi import

            cod = (inst.Name or f'{our_type.upper()}-{inst.GlobalId[:6]}').strip()[:100]
            element = ElementBIM(
                cod=cod,
                nume=inst.Name or '',
                tip_element=our_type,
                ifc_global_id=inst.GlobalId,
                status='proiectat',
            )

            # Best-effort: extragere Psets + bbox. Orice exceptie pe un element
            # e prinsa si logata - importul continua (NU stricam importul).
            if extrage_proprietati:
                try:
                    psets = extrage_psets(inst)
                    if psets:
                        element.proprietati_json = json.dumps(psets, ensure_ascii=False)
                except Exception as e:
                    _logger.warning('extrage_psets a esuat pe %s: %s', inst.GlobalId, e)
                if geom is not None and geom_facute < MAX_GEOM_BBOX:
                    try:
                        bbox = extrage_bbox(inst, geom, settings_geom, ushape)
                        geom_facute += 1
                        if bbox:
                            element.bbox_json = json.dumps(bbox)
                            element.bbox_sursa = 'ifc_geom'
                    except Exception as e:
                        _logger.warning('extrage_bbox a esuat pe %s: %s', inst.GlobalId, e)

            if not dry_run:
                db.session.add(element)
            statistici['elemente_create'] += 1

    # Leg elementele de nivelul (storey) lor via containment IFC: nivel_id + cladire_id.
    # Necesar pentru 4D (auto-secventiere pe nivel) si pentru afisarea pe niveluri.
    if not dry_run:
        db.session.flush()
        niv_map = {n.extern_id: n for n in Nivel.query.filter(Nivel.extern_id.isnot(None)).all()}
        el_map = {e.ifc_global_id: e for e in ElementBIM.query.filter(
            ElementBIM.ifc_global_id.isnot(None), ElementBIM.nivel_id.is_(None)).all()}
        for ifc_type in IFC_TYPE_MAP:
            try:
                instances = ifc.by_type(ifc_type)
            except Exception:
                continue
            for inst in instances:
                el = el_map.get(inst.GlobalId)
                if el is None:
                    continue
                for rel in (getattr(inst, 'ContainedInStructure', None) or []):
                    rs = getattr(rel, 'RelatingStructure', None)
                    if rs is not None and rs.is_a('IfcBuildingStorey'):
                        niv = niv_map.get(rs.GlobalId)
                        if niv is not None:
                            el.nivel_id = niv.id
                            el.cladire_id = niv.cladire_id
                        break

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
