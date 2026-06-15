"""
BCF 2.1 export + import (Faza 8).

BCF (BIM Collaboration Format) = standard buildingSMART pentru schimb de
issues intre tool-uri BIM. Format: zip cu structura:

    bcf.version
    project.bcfp (optional)
    <topic_guid>/
        markup.bcf       — XML cu issue
        viewpoint.bcfv   — XML cu camera + visibility (opt)
        snapshot.png     — screenshot (opt)
"""

from __future__ import annotations

import io
import json
import logging
import math
import uuid
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from typing import Optional

from models import db, IssueBIM, BIMComment, ElementBIM
from services import audit as audit_svc
from services import feature_flags as ff_svc


_logger = logging.getLogger(__name__)


BCF_VERSION = '2.1'

# Namespace custom Edifico pentru a pastra exact 'look' (distanta) la round-trip.
# CameraDirection standard BCF e doar directia normalizata -> daca reconstruim
# look = eye + dir am pierde distanta. Pastram look explicit intr-un element
# custom; alte tool-uri BCF ignora elementele necunoscute (interop pastrat).
_EDIFICO_LOOKAT_TAG = 'EdificoCameraLookAt'


# ====================================================
# EXPORT
# ====================================================

def _make_markup_xml(issue: IssueBIM, viewpoint_file: Optional[str] = None,
                     viewpoint_guid: Optional[str] = None) -> str:
    """
    Genereaza markup.bcf XML pentru un issue (BCF 2.1).

    Daca viewpoint_file e dat (ex 'viewpoint.bcfv') adauga si un element
    Viewpoints/ViewPoint care refera fisierul .bcfv (BCF 2.1).
    """
    root = ET.Element('Markup')

    topic = ET.SubElement(root, 'Topic', attrib={
        'Guid': issue.bcf_topic_guid or str(uuid.uuid4()),
        'TopicType': (issue.tip or 'Issue').capitalize(),
        'TopicStatus': _map_status(issue.status),
    })
    ET.SubElement(topic, 'Title').text = issue.titlu
    ET.SubElement(topic, 'Priority').text = _map_severity(issue.severitate)
    ET.SubElement(topic, 'CreationDate').text = (
        issue.data_creare.isoformat() if issue.data_creare else datetime.utcnow().isoformat()
    )
    if issue.raportor:
        ET.SubElement(topic, 'CreationAuthor').text = issue.raportor.email
    ET.SubElement(topic, 'ModifiedDate').text = (
        issue.data_modificare.isoformat() if hasattr(issue, 'data_modificare') and issue.data_modificare
        else datetime.utcnow().isoformat()
    )
    if issue.asignat:
        ET.SubElement(topic, 'AssignedTo').text = issue.asignat.email
    if issue.descriere:
        ET.SubElement(topic, 'Description').text = issue.descriere

    # Comentariile asociate
    for c in BIMComment.query.filter_by(issue_id=issue.id, sters=False).order_by(BIMComment.data_creare).all():
        comment_el = ET.SubElement(root, 'Comment', attrib={'Guid': str(uuid.uuid4())})
        ET.SubElement(comment_el, 'Date').text = c.data_creare.isoformat() if c.data_creare else ''
        if c.autor:
            ET.SubElement(comment_el, 'Author').text = c.autor.email
        ET.SubElement(comment_el, 'Comment').text = c.text

    # Faza 4: referinta la viewpoint.bcfv (BCF 2.1 ViewPoints/ViewPoint)
    if viewpoint_file:
        vps = ET.SubElement(root, 'Viewpoints', attrib={
            'Guid': viewpoint_guid or str(uuid.uuid4()),
        })
        ET.SubElement(vps, 'Viewpoint').text = viewpoint_file
        # Snapshot PNG: best-effort, sarit (nu generam PNG din backend) - nu il
        # referim daca nu exista, ca sa nu lasam o referinta moarta in markup.

    tree = ET.ElementTree(root)
    buffer = io.BytesIO()
    tree.write(buffer, encoding='utf-8', xml_declaration=True)
    return buffer.getvalue().decode('utf-8')


def _map_status(status: str) -> str:
    """workforce status -> BCF TopicStatus."""
    mapping = {
        'deschis': 'Open',
        'in_lucru': 'InProgress',
        'rezolvat': 'Resolved',
        'verificat': 'Resolved',
        'inchis': 'Closed',
        'anulat': 'Closed',
    }
    return mapping.get(status, 'Open')


def _reverse_status(bcf_status: str) -> str:
    """BCF status -> workforce status."""
    mapping = {
        'open': 'deschis',
        'inprogress': 'in_lucru',
        'resolved': 'rezolvat',
        'closed': 'inchis',
    }
    return mapping.get((bcf_status or '').lower().replace(' ', ''), 'deschis')


def _map_severity(sev: str) -> str:
    """workforce severitate -> BCF Priority."""
    mapping = {
        'mica': 'Low', 'medie': 'Normal',
        'mare': 'High', 'critica': 'Critical',
    }
    return mapping.get(sev, 'Normal')


def _reverse_severity(bcf_pri: str) -> str:
    mapping = {
        'low': 'mica', 'normal': 'medie',
        'high': 'mare', 'critical': 'critica',
    }
    return mapping.get((bcf_pri or '').lower(), 'medie')


# ====================================================
# VIEWPOINT (BCF 2.1 VisualizationInfo) - Faza 4
# ====================================================

def _vec3(parent: ET.Element, tag: str, vec) -> None:
    """Adauga un element vector 3D (X/Y/Z) sub parent (componenta BCF camera)."""
    el = ET.SubElement(parent, tag)
    ET.SubElement(el, 'X').text = repr(float(vec[0]))
    ET.SubElement(el, 'Y').text = repr(float(vec[1]))
    ET.SubElement(el, 'Z').text = repr(float(vec[2]))


def _read_vec3(parent: Optional[ET.Element]) -> Optional[list]:
    """Citeste un element vector 3D (X/Y/Z). Returneaza [x,y,z] sau None."""
    if parent is None:
        return None
    try:
        x = float(parent.findtext('X'))
        y = float(parent.findtext('Y'))
        z = float(parent.findtext('Z'))
        return [x, y, z]
    except (TypeError, ValueError):
        return None


def _normalize(vec) -> list:
    """Normalizeaza un vector 3D. Vector nul -> directie implicita [0,0,-1]."""
    n = math.sqrt(vec[0] ** 2 + vec[1] ** 2 + vec[2] ** 2)
    if n < 1e-12:
        return [0.0, 0.0, -1.0]
    return [vec[0] / n, vec[1] / n, vec[2] / n]


def _make_viewpoint_xml(viewpoint: dict) -> Optional[str]:
    """
    Genereaza viewpoint.bcfv (VisualizationInfo BCF 2.1) dintr-un dict viewpoint.

    Mapare: eye -> CameraViewPoint, normalize(look-eye) -> CameraDirection,
    up -> CameraUpVector, fov -> FieldOfView. Pastram 'look' exact intr-un
    element custom (vezi _EDIFICO_LOOKAT_TAG) pentru round-trip fara pierdere de
    distanta. Optional: Components (vizibilitate) + ClippingPlanes.

    Returneaza XML string sau None daca nu exista camera valida.
    """
    cam = (viewpoint or {}).get('camera') or {}
    eye = cam.get('eye')
    look = cam.get('look')
    up = cam.get('up') or [0, 0, 1]
    if not (eye and look and len(eye) == 3 and len(look) == 3):
        return None

    direction = _normalize([look[0] - eye[0], look[1] - eye[1], look[2] - eye[2]])

    root = ET.Element('VisualizationInfo', attrib={'Guid': str(uuid.uuid4())})

    # Components (vizibilitate optionala): visible_guids -> Selection
    visible_guids = (viewpoint or {}).get('visible_guids') or []
    if visible_guids:
        components = ET.SubElement(root, 'Components')
        selection = ET.SubElement(components, 'Selection')
        for g in visible_guids:
            ET.SubElement(selection, 'Component', attrib={'IfcGuid': str(g)})

    # PerspectiveCamera
    cam_el = ET.SubElement(root, 'PerspectiveCamera')
    _vec3(cam_el, 'CameraViewPoint', eye)
    _vec3(cam_el, 'CameraDirection', direction)
    _vec3(cam_el, 'CameraUpVector', up)
    ET.SubElement(cam_el, 'FieldOfView').text = repr(float(cam.get('fov', 60)))
    # Look exact pastrat (custom Edifico, ignorat de alte tool-uri)
    _vec3(cam_el, _EDIFICO_LOOKAT_TAG, look)

    # ClippingPlanes (optional)
    clipping = (viewpoint or {}).get('clipping') or []
    if clipping:
        planes = ET.SubElement(root, 'ClippingPlanes')
        for cp in clipping:
            pos = cp.get('pos')
            direction_cp = cp.get('dir')
            if not (pos and direction_cp):
                continue
            plane = ET.SubElement(planes, 'ClippingPlane')
            _vec3(plane, 'Location', pos)
            _vec3(plane, 'Direction', direction_cp)

    tree = ET.ElementTree(root)
    buffer = io.BytesIO()
    tree.write(buffer, encoding='utf-8', xml_declaration=True)
    return buffer.getvalue().decode('utf-8')


def _parse_viewpoint_xml(xml_data: str) -> Optional[dict]:
    """
    Parseaza viewpoint.bcfv (VisualizationInfo) -> dict viewpoint_json.

    Reconstruieste camera: eye=CameraViewPoint, up=CameraUpVector, fov=FieldOfView.
    Pentru 'look': foloseste elementul custom EdificoCameraLookAt daca exista
    (round-trip exact); altfel fallback la look = eye + CameraDirection (distanta
    pierduta, dar directia pastrata). Citeste si visibility + clipping daca exista.
    """
    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError:
        return None

    cam_el = root.find('PerspectiveCamera')
    if cam_el is None:
        cam_el = root.find('OrthogonalCamera')
    if cam_el is None:
        return None

    eye = _read_vec3(cam_el.find('CameraViewPoint'))
    up = _read_vec3(cam_el.find('CameraUpVector')) or [0, 0, 1]
    direction = _read_vec3(cam_el.find('CameraDirection'))
    if eye is None:
        return None

    look = _read_vec3(cam_el.find(_EDIFICO_LOOKAT_TAG))
    if look is None and direction is not None:
        # Fallback: distanta unitara (look = eye + dir normalizat)
        look = [eye[0] + direction[0], eye[1] + direction[1], eye[2] + direction[2]]
    if look is None:
        return None

    fov_txt = cam_el.findtext('FieldOfView')
    try:
        fov = float(fov_txt) if fov_txt is not None else 60.0
    except ValueError:
        fov = 60.0

    viewpoint = {'camera': {'eye': eye, 'look': look, 'up': up, 'fov': fov}}

    # Vizibilitate (Selection)
    visible = []
    for comp in root.findall('.//Components/Selection/Component'):
        g = comp.attrib.get('IfcGuid')
        if g:
            visible.append(g)
    if visible:
        viewpoint['visible_guids'] = visible

    # ClippingPlanes
    clipping = []
    for plane in root.findall('.//ClippingPlanes/ClippingPlane'):
        pos = _read_vec3(plane.find('Location'))
        direction_cp = _read_vec3(plane.find('Direction'))
        if pos and direction_cp:
            clipping.append({'pos': pos, 'dir': direction_cp})
    if clipping:
        viewpoint['clipping'] = clipping

    return viewpoint


def export_bcfzip(issue_ids: Optional[list[int]] = None) -> io.BytesIO:
    """
    Exporta unul sau mai multe issues ca .bcfzip BCF 2.1.

    Daca issue_ids = None -> exporta toate issues (atentie la marime).
    Returneaza BytesIO cu zip-ul.
    """
    q = IssueBIM.query
    if issue_ids:
        q = q.filter(IssueBIM.id.in_(issue_ids))
    issues = q.all()
    if not issues:
        raise ValueError('Nicio issue de exportat')

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        # bcf.version
        version_xml = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            f'<Version VersionId="{BCF_VERSION}" DetailedVersion="{BCF_VERSION}" />\n'
        )
        zf.writestr('bcf.version', version_xml)

        # Comportament viewpoint gateat pe flag. Cu OFF -> identic cu azi
        # (doar markup.bcf, byte-compatibil) - regresie.
        bcf_full = ff_svc.is_enabled('bim-bcf-full')

        for issue in issues:
            guid = issue.bcf_topic_guid or str(uuid.uuid4())
            if not issue.bcf_topic_guid:
                issue.bcf_topic_guid = guid

            viewpoint_xml = None
            if bcf_full and issue.viewpoint_json:
                try:
                    vp = json.loads(issue.viewpoint_json)
                    viewpoint_xml = _make_viewpoint_xml(vp)
                except (ValueError, TypeError) as e:
                    _logger.warning('viewpoint invalid pe issue %s: %s', issue.id, e)

            if viewpoint_xml:
                markup_xml = _make_markup_xml(issue, viewpoint_file='viewpoint.bcfv')
                zf.writestr(f'{guid}/markup.bcf', markup_xml)
                zf.writestr(f'{guid}/viewpoint.bcfv', viewpoint_xml)
            else:
                markup_xml = _make_markup_xml(issue)
                zf.writestr(f'{guid}/markup.bcf', markup_xml)

        try:
            db.session.commit()  # salvam guid-urile generate
        except Exception:
            db.session.rollback()

    buf.seek(0)
    return buf


# ====================================================
# IMPORT
# ====================================================

def import_bcfzip(file_obj, *, user, tenant_id: Optional[int] = None,
                  commit: bool = True) -> dict:
    """
    Importa un .bcfzip. Pentru fiecare topic creeaza/updateaza IssueBIM.
    Match pe bcf_topic_guid (upsert).

    Returneaza:
        {'created': N, 'updated': M, 'skipped': K, 'errors': [...]}
    """
    stats = {'created': 0, 'updated': 0, 'skipped': 0, 'errors': []}

    # Viewpoint import gateat pe flag (cu OFF, comportament ca azi).
    bcf_full = ff_svc.is_enabled('bim-bcf-full')

    with zipfile.ZipFile(file_obj, 'r') as zf:
        names = zf.namelist()
        names_set = set(names)
        # Toate fisierele markup.bcf (in folder per topic)
        markup_files = [n for n in names if n.endswith('markup.bcf')]
        for markup_path in markup_files:
            try:
                xml_data = zf.read(markup_path).decode('utf-8')
                root = ET.fromstring(xml_data)
                topic = root.find('Topic')
                if topic is None:
                    stats['skipped'] += 1
                    continue
                guid = topic.attrib.get('Guid')
                if not guid:
                    stats['skipped'] += 1
                    continue

                titlu_el = topic.find('Title')
                titlu = titlu_el.text.strip() if titlu_el is not None and titlu_el.text else f'BCF {guid[:8]}'
                desc_el = topic.find('Description')
                descriere = desc_el.text.strip() if desc_el is not None and desc_el.text else None
                status_el = topic.find('TopicStatus')
                bcf_status = status_el.text if status_el is not None else None
                # Fallback la atributul TopicStatus
                if not bcf_status:
                    bcf_status = topic.attrib.get('TopicStatus')
                priority_el = topic.find('Priority')
                bcf_priority = priority_el.text if priority_el is not None else None
                tip_el = topic.attrib.get('TopicType', 'Issue')

                existing = IssueBIM.query.filter_by(bcf_topic_guid=guid).first()
                if existing:
                    existing.titlu = titlu[:300]
                    existing.descriere = descriere
                    existing.status = _reverse_status(bcf_status)
                    existing.severitate = _reverse_severity(bcf_priority)
                    stats['updated'] += 1
                    iss = existing
                else:
                    iss = IssueBIM(
                        tenant_id=tenant_id,
                        bcf_topic_guid=guid,
                        titlu=titlu[:300],
                        descriere=descriere,
                        tip='neconformitate',
                        severitate=_reverse_severity(bcf_priority),
                        status=_reverse_status(bcf_status),
                        raportat_de_id=getattr(user, 'id', None),
                    )
                    db.session.add(iss)
                    db.session.flush()
                    stats['created'] += 1

                # Faza 4: viewpoint.bcfv din acelasi folder de topic (daca exista)
                if bcf_full:
                    folder = markup_path[:-len('markup.bcf')]
                    vp_path = folder + 'viewpoint.bcfv'
                    if vp_path in names_set:
                        try:
                            vp_xml = zf.read(vp_path).decode('utf-8')
                            vp = _parse_viewpoint_xml(vp_xml)
                            if vp:
                                iss.viewpoint_json = json.dumps(vp)
                        except Exception as e:
                            stats['errors'].append(f'{vp_path}: {e}')

                # Comments
                for comment_el in root.findall('Comment'):
                    text_el = comment_el.find('Comment')
                    text = text_el.text.strip() if text_el is not None and text_el.text else ''
                    if not text:
                        continue
                    # Check if exact comment already exists (simplificare: skip duplicate
                    # daca exista deja un comment cu text identic pe issue)
                    existing_c = BIMComment.query.filter_by(
                        issue_id=iss.id, text=text).first()
                    if existing_c:
                        continue
                    bc = BIMComment(
                        tenant_id=tenant_id,
                        issue_id=iss.id,
                        autor_id=getattr(user, 'id', None),
                        text=text,
                    )
                    db.session.add(bc)
            except Exception as e:
                stats['errors'].append(f'{markup_path}: {e}')

    if commit:
        try:
            db.session.commit()
            audit_svc.log('import_bcf', 'bim_issue_bulk', None,
                          new_values=stats, commit=True)
        except Exception as e:
            db.session.rollback()
            stats['errors'].append(f'commit: {e}')
    return stats
