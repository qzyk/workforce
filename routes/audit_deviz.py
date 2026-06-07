"""
Rute pentru modulul Audit Deviz.

Verifica un pachet de deviz EXTERN (F2 centralizator + N obiecte x F3 + extrase
C6/C7/C8/C9): reconciliere 3 niveluri, structura de cost, raport anomalii.

Tot modulul e gated pe feature flag 'audit-deviz' (default OFF) -> 404 daca off.
Audit: log_create / log_delete pe write-uri.
"""

import io
import json
import zipfile

from flask import (
    Blueprint, render_template, redirect, url_for, flash, request, abort,
    send_file,
)
from flask_login import login_required, current_user

from models import db, Proiect, AuditDeviz, ObiectAuditDeviz, AnomalieDeviz
from forms.audit_deviz_forms import AuditDevizForm
import services.audit as audit_svc
from services.feature_flags import is_enabled
from services.audit_deviz import analizeaza_set


audit_deviz_bp = Blueprint('audit_deviz', __name__, url_prefix='/audit-deviz')

_EXT_OK = ('.xls', '.xlsx')


@audit_deviz_bp.before_request
def _check_flag():
    """404 daca feature flag-ul nu e activ pentru tenant-ul curent."""
    if not is_enabled('audit-deviz'):
        abort(404)


def _extrage_fisiere(file_storages) -> list[tuple[str, bytes]]:
    """Din input (fisiere multiple sau un ZIP) -> [(nume, continut_bytes)]."""
    fisiere: list[tuple[str, bytes]] = []
    for fs in file_storages:
        if not fs or not fs.filename:
            continue
        data = fs.read()
        low = fs.filename.lower()
        if low.endswith('.zip'):
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as z:
                    for info in z.infolist():
                        if info.is_dir():
                            continue
                        nm = info.filename.replace('\\', '/').split('/')[-1]
                        if nm and not nm.startswith('.') \
                                and nm.lower().endswith(_EXT_OK):
                            fisiere.append((nm, z.read(info)))
            except zipfile.BadZipFile:
                continue
        elif low.endswith(_EXT_OK):
            fisiere.append((fs.filename, data))
    return fisiere


@audit_deviz_bp.route('/')
@login_required
def lista():
    audituri = (AuditDeviz.query
                .order_by(AuditDeviz.data_creare.desc())
                .limit(200).all())
    return render_template('audit_deviz/lista.html', audituri=audituri)


@audit_deviz_bp.route('/nou', methods=['GET', 'POST'])
@login_required
def nou():
    form = AuditDevizForm()
    form.seteaza_proiecte(Proiect.query.order_by(Proiect.cod_proiect).all())

    if form.validate_on_submit():
        fisiere = _extrage_fisiere(request.files.getlist('fisiere'))
        if not fisiere:
            flash('Niciun fisier .xls/.xlsx valid (incarca un ZIP cu setul sau '
                  'selecteaza fisierele).', 'error')
            return render_template('audit_deviz/formular.html', form=form)

        rez = analizeaza_set(fisiere)
        if not rez['nr_obiecte']:
            flash('Nu am putut detecta niciun obiect (F3). Verifica denumirile '
                  'fisierelor (ex: 004_01_..._F3_lista_cantitati.xls).', 'error')
            return render_template('audit_deviz/formular.html', form=form)

        pid = form.proiect_id.data or None
        a = AuditDeviz(
            nume=form.nume.data.strip(),
            nume_fisier=(fisiere[0][0] if len(fisiere) == 1 else f'{len(fisiere)} fisiere'),
            proiect_id=pid,
            total_f2=rez['total_f2'], total_f3=rez['total_f3'],
            tva=rez['tva'], total_cu_tva=rez['total_cu_tva'],
            delta_reconciliere=rez['delta_reconciliere'],
            pct_material=rez['pct_material'], pct_manopera=rez['pct_manopera'],
            pct_utilaj=rez['pct_utilaj'], pct_transport=rez['pct_transport'],
            nr_obiecte=rez['nr_obiecte'], nr_anomalii=rez['nr_anomalii'],
            rezultat_json=json.dumps(rez, ensure_ascii=False),
            creat_de_id=current_user.id,
        )
        db.session.add(a)
        db.session.flush()
        for o in rez['obiecte']:
            db.session.add(ObiectAuditDeviz(
                audit_id=a.id, numar=o['numar'], nume=o['nume'],
                val_f3=o['f3'], val_f2=o['f2'], val_c6=o['c6'], val_c7=o['c7'],
                val_c8=o['c8'], val_c9=o['c9'],
                delta_l1=o['delta_l1'], delta_l2=o['delta_l2'], status=o['status'],
            ))
        for an in rez['anomalii']:
            db.session.add(AnomalieDeviz(
                audit_id=a.id, obiect=an['obiect'], tip=an['tip'],
                severitate=an['severitate'], mesaj=an['mesaj'], valoare=an['valoare'],
            ))
        audit_svc.log_create('audit_deviz', a.id, new_values={
            'nume': a.nume, 'nr_obiecte': a.nr_obiecte, 'nr_anomalii': a.nr_anomalii,
            'total_f3': str(a.total_f3) if a.total_f3 is not None else None,
        })
        db.session.commit()
        flash(f'Audit creat: {a.nr_obiecte} obiecte, {a.nr_anomalii} anomalii. '
              f'Vezi reconcilierea si structura de cost mai jos.', 'success')
        return redirect(url_for('audit_deviz.detalii', audit_id=a.id))

    return render_template('audit_deviz/formular.html', form=form)


@audit_deviz_bp.route('/<int:audit_id>')
@login_required
def detalii(audit_id):
    a = AuditDeviz.query.get_or_404(audit_id)
    try:
        rez = json.loads(a.rezultat_json) if a.rezultat_json else {}
    except (ValueError, TypeError):
        rez = {}
    return render_template('audit_deviz/detalii.html', a=a, rez=rez)


@audit_deviz_bp.route('/<int:audit_id>/export')
@login_required
def export(audit_id):
    a = AuditDeviz.query.get_or_404(audit_id)
    rez = json.loads(a.rezultat_json) if a.rezultat_json else {}
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = 'Reconciliere'
    ws.append(['Audit deviz:', a.nume])
    ws.append([])
    ws.append(['Obiect', 'F3 fara TVA', 'F2', 'C6 mat', 'C7 man', 'C8 util',
               'C9 transp', 'delta L1', 'delta L2', 'status'])
    for o in rez.get('obiecte', []):
        ws.append([o['nume'], o['f3'], o['f2'], o['c6'], o['c7'], o['c8'],
                   o['c9'], o['delta_l1'], o['delta_l2'], o['status']])
    ws.append([])
    ws.append(['TOTAL F3', rez.get('total_f3'), 'TOTAL F2', rez.get('total_f2'),
               'TVA', rez.get('tva'), 'TOTAL cu TVA', rez.get('total_cu_tva')])
    ws.append(['Structura %', 'material', rez.get('pct_material'),
               'manopera', rez.get('pct_manopera'), 'utilaj', rez.get('pct_utilaj'),
               'transport', rez.get('pct_transport')])

    wsa = wb.create_sheet('Anomalii')
    wsa.append(['Severitate', 'Tip', 'Obiect', 'Mesaj', 'Valoare'])
    for an in rez.get('anomalii', []):
        wsa.append([an['severitate'], an['tip'], an.get('obiect') or '',
                    an['mesaj'], an.get('valoare')])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True,
                     download_name=f'audit_deviz_{a.id}.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@audit_deviz_bp.route('/<int:audit_id>/sterge', methods=['POST'])
@login_required
def sterge(audit_id):
    a = AuditDeviz.query.get_or_404(audit_id)
    nume = a.nume
    audit_svc.log_delete('audit_deviz', a.id, old_values={'nume': nume})
    db.session.delete(a)
    db.session.commit()
    flash(f'Audit "{nume}" sters.', 'success')
    return redirect(url_for('audit_deviz.lista'))
