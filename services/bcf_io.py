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
import logging
import uuid
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from typing import Optional

from models import db, IssueBIM, BIMComment, ElementBIM
from services import audit as audit_svc


_logger = logging.getLogger(__name__)


BCF_VERSION = '2.1'


# ====================================================
# EXPORT
# ====================================================

def _make_markup_xml(issue: IssueBIM) -> str:
    """Genereaza markup.bcf XML pentru un issue (BCF 2.1)."""
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

        for issue in issues:
            guid = issue.bcf_topic_guid or str(uuid.uuid4())
            if not issue.bcf_topic_guid:
                issue.bcf_topic_guid = guid
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

    with zipfile.ZipFile(file_obj, 'r') as zf:
        names = zf.namelist()
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
