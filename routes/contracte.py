"""
Rute pentru modulul Contract & Project Controls (Faza 10).

Acopera 3 entitati core:
  - Contract (principal + acte aditionale via parinte_contract_id)
  - TermenContract (termene contractuale per contract)
  - ProcesVerbal (predare amplasament, receptii, etc.)

Tot modulul e gated pe feature flag 'controale-contract' (default OFF).
Daca flag-ul nu e activ, toate endpoint-urile returneaza 404 - modulul
e invizibil pentru utilizatorii la care nu a fost activat.

Audit: log_create / log_update / log_delete pe toate write-urile.
"""

import os
import uuid
from datetime import date, datetime
from decimal import Decimal

from flask import (
    Blueprint, render_template, redirect, url_for, flash, request, abort,
    current_app, jsonify,
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from models import (
    db, Proiect, Contract, TermenContract, ProcesVerbal, Utilizator,
    ProgramReferinta, TaskProgram, OfertaContract, PozitieBoQ,
    CantitateExecutataLunara, SituatieLunara, RaportLucrariProiect,
    Corespondenta, Revendicare, RevendicareTermen, RevendicareTask,
    RevendicareCantitate, TermenUrmarit, TarifCategorie,
)
from forms.contract_forms import (
    ContractForm, TermenContractForm, ProcesVerbalForm,
    parse_participanti_text, format_participanti_text,
)
from forms.cantitate_forms import CantitateLunaraForm, parse_bulk_cantitati
from forms.situatie_forms import (
    SituatieLunaraForm, SchimbaStatusSituatieForm, RaportLucrariForm,
    LUNI_CHOICES,
)
from forms.corespondenta_forms import CorespondentaForm
from forms.revendicare_forms import (
    RevendicareForm, LinkRevendicareTermenForm, LinkRevendicareTaskForm,
    LinkRevendicareCantitateForm,
)
from forms.reguli_notificare_forms import (
    ReguliNotificareForm, parse_emails_text, format_emails_text,
)
import services.audit as audit_svc
from services.feature_flags import is_enabled
from services.parsers import (
    MSProjectXMLParser, EDevizeXMLParser, EDevizePDFParser,
    ExcelBoQParser, ParseError,
)
from services.situatii import (
    genereaza_situatie, export_situatie_xlsx, export_situatie_pdf, LUNI_RO,
)
from services.rapoarte_lucrari import genereaza_raport_lucrari
from services.termen_urmarit import (
    creeaza_termen_din_corespondenta, sterge_termen_din_corespondenta,
)
from services.conflict_revendicare import detecta_conflicte, numara_conflicte
from services import deviz_pricing
from services import centralizator
from forms.clasificare_forms import parse_bulk_categorii
from services.notificari_app import (
    marcheaza_citita, marcheaza_toate_citite, count_necitite, lista_notificari,
)
from services.pv_generator import genereaza_pv_docx, genereaza_pv_pdf
from models import NotificareApp, ReguliNotificareProiect


ALLOWED_EXT_MSPROJECT = {'xml'}
ALLOWED_EXT_OFERTA = {'xml', 'xlsx', 'xls', 'pdf'}
MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB hard limit per file


contracte_bp = Blueprint('contracte', __name__)


# ============================================================
# FLAG GUARD - intregul modul e invizibil daca flag OFF
# ============================================================

@contracte_bp.before_request
def _check_flag():
    """404 daca feature flag-ul nu e activ pentru tenant-ul curent."""
    if not is_enabled('controale-contract'):
        abort(404)


# ============================================================
# CONTRACT - lista, detalii, create, edit, delete
# ============================================================

@contracte_bp.route('/')
@login_required
def lista():
    """Lista cu toate contractele (filtrabila pe status / proiect / cautare)."""
    status_filtru = request.args.get('status', '').strip()
    proiect_filtru = request.args.get('proiect', type=int)
    cautare = request.args.get('cautare', '').strip()

    query = Contract.query
    if status_filtru:
        query = query.filter_by(status=status_filtru)
    if proiect_filtru:
        query = query.filter_by(proiect_id=proiect_filtru)
    if cautare:
        query = query.filter(
            db.or_(
                Contract.nr_contract.ilike(f'%{cautare}%'),
                Contract.beneficiar.ilike(f'%{cautare}%'),
                Contract.antreprenor.ilike(f'%{cautare}%'),
            )
        )
    # Doar contractele principale in lista; actele aditionale apar sub fiecare
    query = query.filter(Contract.parinte_contract_id.is_(None))
    contracte = query.order_by(Contract.data_semnare.desc()).all()

    # Statistici simple pentru sidebar de filtre
    total_activ = Contract.query.filter_by(
        status='activ', parinte_contract_id=None
    ).count()
    total_finalizat = Contract.query.filter_by(
        status='finalizat', parinte_contract_id=None
    ).count()
    total_suspendat = Contract.query.filter_by(
        status='suspendat', parinte_contract_id=None
    ).count()

    proiecte_pentru_filtru = Proiect.query.order_by(Proiect.cod_proiect).all()

    return render_template(
        'contracte/lista.html',
        contracte=contracte,
        proiecte=proiecte_pentru_filtru,
        status_filtru=status_filtru,
        proiect_filtru=proiect_filtru,
        cautare=cautare,
        total_activ=total_activ,
        total_finalizat=total_finalizat,
        total_suspendat=total_suspendat,
        statuses=Contract.STATUSES,
    )


@contracte_bp.route('/<int:id>')
@login_required
def detalii(id):
    """Detalii contract + acte aditionale + termene + PV-uri asociate."""
    c = Contract.query.get_or_404(id)
    # Acte aditionale (sortate dupa data semnare)
    acte = c.acte_aditionale.order_by(Contract.data_semnare).all()
    # Termene (sortate dupa data_scadenta)
    termene = c.termeni.order_by(TermenContract.data_scadenta).all()
    # PV-uri asociate contractului
    pv_list = ProcesVerbal.query.filter_by(contract_id=c.id).order_by(
        ProcesVerbal.data_emitere.desc()
    ).all()
    return render_template(
        'contracte/detalii.html',
        contract=c,
        acte_aditionale=acte,
        termene=termene,
        pv_list=pv_list,
        pv_tipuri=ProcesVerbal.TIPURI,
    )


@contracte_bp.route('/nou', methods=['GET', 'POST'])
@login_required
def formular_nou():
    """Creeaza un contract nou (principal sau act aditional)."""
    form = ContractForm()
    if form.validate_on_submit():
        try:
            parinte_id = form.parinte_contract_id.data or None
            if parinte_id == 0:
                parinte_id = None
            c = Contract(
                proiect_id=form.proiect_id.data,
                parinte_contract_id=parinte_id,
                nr_contract=form.nr_contract.data.strip(),
                data_semnare=form.data_semnare.data,
                data_inceput_referinta=form.data_inceput_referinta.data,
                data_inceput_executie=form.data_inceput_executie.data,
                data_finalizare_planificata=form.data_finalizare_planificata.data,
                valoare_totala=form.valoare_totala.data,
                moneda=form.moneda.data,
                beneficiar=(form.beneficiar.data or '').strip() or None,
                antreprenor=(form.antreprenor.data or '').strip() or None,
                obiect_contract=form.obiect_contract.data or None,
                observatii=form.observatii.data or None,
                status=form.status.data,
                creat_de_id=current_user.id,
            )
            db.session.add(c)
            db.session.flush()
            audit_svc.log_create('contract', c.id, new_values={
                'nr_contract': c.nr_contract,
                'proiect_id': c.proiect_id,
                'data_semnare': c.data_semnare.isoformat() if c.data_semnare else None,
                'valoare_totala': str(c.valoare_totala) if c.valoare_totala else None,
                'status': c.status,
            })
            db.session.commit()
            flash(f'Contractul "{c.nr_contract}" a fost creat.', 'success')
            return redirect(url_for('contracte.detalii', id=c.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Eroare la salvare: {e}', 'danger')
    return render_template('contracte/formular.html', form=form, contract=None)


@contracte_bp.route('/<int:id>/editeaza', methods=['GET', 'POST'])
@login_required
def formular_editeaza(id):
    """Editeaza un contract existent."""
    c = Contract.query.get_or_404(id)
    form = ContractForm(obj=c)
    if request.method == 'GET':
        form.contract_id.data = c.id
        form.parinte_contract_id.data = c.parinte_contract_id or 0
    if form.validate_on_submit():
        try:
            audit_fields = [
                'nr_contract', 'proiect_id', 'parinte_contract_id', 'data_semnare',
                'data_inceput_referinta', 'data_inceput_executie',
                'data_finalizare_planificata', 'valoare_totala', 'moneda',
                'beneficiar', 'antreprenor', 'status',
            ]
            before = audit_svc.snapshot(c, audit_fields)
            parinte_id = form.parinte_contract_id.data or None
            if parinte_id == 0:
                parinte_id = None
            # Nu permite self-FK direct (un contract nu poate fi propriul parinte)
            if parinte_id == c.id:
                flash('Un contract nu poate fi propriul sau parinte.', 'danger')
                return render_template('contracte/formular.html', form=form, contract=c)
            c.proiect_id = form.proiect_id.data
            c.parinte_contract_id = parinte_id
            c.nr_contract = form.nr_contract.data.strip()
            c.data_semnare = form.data_semnare.data
            c.data_inceput_referinta = form.data_inceput_referinta.data
            c.data_inceput_executie = form.data_inceput_executie.data
            c.data_finalizare_planificata = form.data_finalizare_planificata.data
            c.valoare_totala = form.valoare_totala.data
            c.moneda = form.moneda.data
            c.beneficiar = (form.beneficiar.data or '').strip() or None
            c.antreprenor = (form.antreprenor.data or '').strip() or None
            c.obiect_contract = form.obiect_contract.data or None
            c.observatii = form.observatii.data or None
            c.status = form.status.data
            audit_svc.log_update('contract', c.id, before,
                                 audit_svc.snapshot(c, audit_fields))
            db.session.commit()
            flash(f'Contractul "{c.nr_contract}" a fost actualizat.', 'success')
            return redirect(url_for('contracte.detalii', id=c.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Eroare la salvare: {e}', 'danger')
    return render_template('contracte/formular.html', form=form, contract=c)


@contracte_bp.route('/<int:id>/sterge', methods=['POST'])
@login_required
def sterge(id):
    """Sterge un contract. Termenele + actele aditionale raman in DB
    (nu folosim cascade automata - permitem soft-handling)."""
    c = Contract.query.get_or_404(id)
    # Refuz daca are acte aditionale active sau termene neindeplinite
    if c.acte_aditionale.count() > 0:
        flash('Nu poti sterge un contract care are acte aditionale. Sterge-le mai intai.', 'danger')
        return redirect(url_for('contracte.detalii', id=c.id))
    try:
        audit_svc.log_delete('contract', c.id, old_values={
            'nr_contract': c.nr_contract,
            'proiect_id': c.proiect_id,
            'status': c.status,
        })
        nr = c.nr_contract
        # Sterge termenele asociate explicit (fara cascade)
        TermenContract.query.filter_by(contract_id=c.id).delete()
        db.session.delete(c)
        db.session.commit()
        flash(f'Contractul "{nr}" a fost sters.', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Eroare la stergere: {e}', 'danger')
    return redirect(url_for('contracte.lista'))


# ============================================================
# TERMEN CONTRACT - create, edit, delete (in context contract)
# ============================================================

@contracte_bp.route('/<int:contract_id>/termen/nou', methods=['GET', 'POST'])
@login_required
def termen_nou(contract_id):
    c = Contract.query.get_or_404(contract_id)
    form = TermenContractForm()
    form.contract_id_hidden.data = c.id
    if form.validate_on_submit():
        try:
            resp_id = form.responsabil_id.data or None
            if resp_id == 0:
                resp_id = None
            t = TermenContract(
                contract_id=c.id,
                proiect_id=c.proiect_id,
                denumire=form.denumire.data.strip(),
                tip=form.tip.data,
                descriere=form.descriere.data or None,
                data_scadenta=form.data_scadenta.data,
                data_realizare=form.data_realizare.data,
                zile_alerta_inainte=form.zile_alerta_inainte.data or 7,
                status=form.status.data,
                responsabil_id=resp_id,
                creat_de_id=current_user.id,
            )
            db.session.add(t)
            db.session.flush()
            audit_svc.log_create('termen_contract', t.id, new_values={
                'contract_id': c.id, 'tip': t.tip,
                'data_scadenta': t.data_scadenta.isoformat(),
                'status': t.status,
            })
            db.session.commit()
            flash(f'Termenul "{t.denumire}" a fost adaugat.', 'success')
            return redirect(url_for('contracte.detalii', id=c.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Eroare la salvare: {e}', 'danger')
    return render_template('contracte/termen_formular.html',
                           form=form, contract=c, termen=None)


@contracte_bp.route('/termen/<int:termen_id>/editeaza', methods=['GET', 'POST'])
@login_required
def termen_editeaza(termen_id):
    t = TermenContract.query.get_or_404(termen_id)
    c = Contract.query.get_or_404(t.contract_id)
    form = TermenContractForm(obj=t)
    if request.method == 'GET':
        form.termen_id.data = t.id
        form.contract_id_hidden.data = c.id
        form.responsabil_id.data = t.responsabil_id or 0
    if form.validate_on_submit():
        try:
            audit_fields = ['denumire', 'tip', 'data_scadenta', 'data_realizare',
                            'zile_alerta_inainte', 'status', 'responsabil_id']
            before = audit_svc.snapshot(t, audit_fields)
            resp_id = form.responsabil_id.data or None
            if resp_id == 0:
                resp_id = None
            t.denumire = form.denumire.data.strip()
            t.tip = form.tip.data
            t.descriere = form.descriere.data or None
            t.data_scadenta = form.data_scadenta.data
            t.data_realizare = form.data_realizare.data
            t.zile_alerta_inainte = form.zile_alerta_inainte.data or 7
            t.status = form.status.data
            t.responsabil_id = resp_id
            audit_svc.log_update('termen_contract', t.id, before,
                                 audit_svc.snapshot(t, audit_fields))
            db.session.commit()
            flash(f'Termenul "{t.denumire}" a fost actualizat.', 'success')
            return redirect(url_for('contracte.detalii', id=c.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Eroare la salvare: {e}', 'danger')
    return render_template('contracte/termen_formular.html',
                           form=form, contract=c, termen=t)


@contracte_bp.route('/termen/<int:termen_id>/sterge', methods=['POST'])
@login_required
def termen_sterge(termen_id):
    t = TermenContract.query.get_or_404(termen_id)
    contract_id = t.contract_id
    try:
        audit_svc.log_delete('termen_contract', t.id, old_values={
            'contract_id': t.contract_id, 'tip': t.tip,
            'data_scadenta': t.data_scadenta.isoformat() if t.data_scadenta else None,
        })
        denumire = t.denumire
        db.session.delete(t)
        db.session.commit()
        flash(f'Termenul "{denumire}" a fost sters.', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Eroare la stergere: {e}', 'danger')
    return redirect(url_for('contracte.detalii', id=contract_id))


# ============================================================
# PROCES VERBAL - lista, detalii, create, edit, delete
# ============================================================

@contracte_bp.route('/pv')
@login_required
def pv_lista():
    """Lista cu toate PV-urile (filtrabila pe tip / proiect)."""
    tip_filtru = request.args.get('tip', '').strip()
    proiect_filtru = request.args.get('proiect', type=int)

    query = ProcesVerbal.query
    if tip_filtru:
        query = query.filter_by(tip=tip_filtru)
    if proiect_filtru:
        query = query.filter_by(proiect_id=proiect_filtru)
    pv_list = query.order_by(ProcesVerbal.data_emitere.desc()).all()

    proiecte_pentru_filtru = Proiect.query.order_by(Proiect.cod_proiect).all()
    return render_template(
        'contracte/pv_lista.html',
        pv_list=pv_list,
        proiecte=proiecte_pentru_filtru,
        tip_filtru=tip_filtru,
        proiect_filtru=proiect_filtru,
        tipuri=ProcesVerbal.TIPURI,
    )


@contracte_bp.route('/pv/nou', methods=['GET', 'POST'])
@login_required
def pv_nou():
    form = ProcesVerbalForm()
    # Pre-populare proiect_id dacă vine din URL ?proiect_id=X (creare din contextul unui contract)
    preset_proiect = request.args.get('proiect_id', type=int)
    preset_contract = request.args.get('contract_id', type=int)
    if request.method == 'GET':
        if preset_proiect:
            form.proiect_id.data = preset_proiect
        if preset_contract:
            form.contract_id.data = preset_contract
    if form.validate_on_submit():
        try:
            contract_id = form.contract_id.data or None
            if contract_id == 0:
                contract_id = None
            pv = ProcesVerbal(
                proiect_id=form.proiect_id.data,
                contract_id=contract_id,
                tip=form.tip.data,
                numar=(form.numar.data or '').strip() or None,
                data_emitere=form.data_emitere.data,
                obiect=form.obiect.data or None,
                concluzii=form.concluzii.data or None,
                semnat=bool(form.semnat.data),
                creat_de_id=current_user.id,
            )
            pv.participanti = parse_participanti_text(form.participanti_text.data or '')
            db.session.add(pv)
            db.session.flush()
            audit_svc.log_create('proces_verbal', pv.id, new_values={
                'tip': pv.tip, 'proiect_id': pv.proiect_id,
                'data_emitere': pv.data_emitere.isoformat() if pv.data_emitere else None,
            })
            db.session.commit()
            flash(f'PV "{pv.tip}" creat.', 'success')
            if contract_id:
                return redirect(url_for('contracte.detalii', id=contract_id))
            return redirect(url_for('contracte.pv_lista'))
        except Exception as e:
            db.session.rollback()
            flash(f'Eroare la salvare: {e}', 'danger')
    return render_template('contracte/pv_formular.html', form=form, pv=None)


@contracte_bp.route('/pv/<int:id>/editeaza', methods=['GET', 'POST'])
@login_required
def pv_editeaza(id):
    pv = ProcesVerbal.query.get_or_404(id)
    form = ProcesVerbalForm(obj=pv)
    if request.method == 'GET':
        form.pv_id.data = pv.id
        form.contract_id.data = pv.contract_id or 0
        form.participanti_text.data = format_participanti_text(pv.participanti)
    if form.validate_on_submit():
        try:
            audit_fields = ['tip', 'numar', 'data_emitere', 'proiect_id',
                            'contract_id', 'semnat']
            before = audit_svc.snapshot(pv, audit_fields)
            contract_id = form.contract_id.data or None
            if contract_id == 0:
                contract_id = None
            pv.proiect_id = form.proiect_id.data
            pv.contract_id = contract_id
            pv.tip = form.tip.data
            pv.numar = (form.numar.data or '').strip() or None
            pv.data_emitere = form.data_emitere.data
            pv.obiect = form.obiect.data or None
            pv.concluzii = form.concluzii.data or None
            pv.semnat = bool(form.semnat.data)
            pv.participanti = parse_participanti_text(form.participanti_text.data or '')
            audit_svc.log_update('proces_verbal', pv.id, before,
                                 audit_svc.snapshot(pv, audit_fields))
            db.session.commit()
            flash('PV actualizat.', 'success')
            if pv.contract_id:
                return redirect(url_for('contracte.detalii', id=pv.contract_id))
            return redirect(url_for('contracte.pv_lista'))
        except Exception as e:
            db.session.rollback()
            flash(f'Eroare la salvare: {e}', 'danger')
    return render_template('contracte/pv_formular.html', form=form, pv=pv)


@contracte_bp.route('/pv/<int:id>/sterge', methods=['POST'])
@login_required
def pv_sterge(id):
    pv = ProcesVerbal.query.get_or_404(id)
    redirect_contract = pv.contract_id
    try:
        audit_svc.log_delete('proces_verbal', pv.id, old_values={
            'tip': pv.tip, 'proiect_id': pv.proiect_id,
            'data_emitere': pv.data_emitere.isoformat() if pv.data_emitere else None,
        })
        db.session.delete(pv)
        db.session.commit()
        flash('PV sters.', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Eroare la stergere: {e}', 'danger')
    if redirect_contract:
        return redirect(url_for('contracte.detalii', id=redirect_contract))
    return redirect(url_for('contracte.pv_lista'))


# ============================================================
# PROGRAM REFERINTA (Faza 11) - import MS Project XML
# ============================================================

def _save_uploaded_file(file_storage, subdir: str, allowed_ext: set) -> str:
    """
    Salveaza fisierul uploadat in uploads/<subdir>/<uuid>_<safe_name>.

    Returneaza path absolut. Refuza extensii nepermise sau fisiere > MAX_UPLOAD_BYTES.
    Arunca ValueError la probleme - call-site-ul prinde si afiseaza flash.
    """
    if not file_storage or not file_storage.filename:
        raise ValueError('Niciun fisier selectat.')

    fname = secure_filename(file_storage.filename)
    if not fname or '.' not in fname:
        raise ValueError('Nume fisier invalid.')

    ext = fname.rsplit('.', 1)[1].lower()
    if ext not in allowed_ext:
        raise ValueError(
            f'Extensie "{ext}" nepermisa. Acceptate: {", ".join(sorted(allowed_ext))}.'
        )

    # Limita dimensiune (citire stream → seek 0 + tell)
    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    if size > MAX_UPLOAD_BYTES:
        raise ValueError(
            f'Fisierul are {size} bytes, limita e {MAX_UPLOAD_BYTES} ({MAX_UPLOAD_BYTES // 1024 // 1024}MB).'
        )

    upload_dir = os.path.join(
        current_app.config.get('UPLOAD_FOLDER',
                               os.path.join(current_app.root_path, 'uploads')),
        subdir,
    )
    os.makedirs(upload_dir, exist_ok=True)
    safe_unique = f'{uuid.uuid4().hex}_{fname}'
    path = os.path.join(upload_dir, safe_unique)
    file_storage.save(path)
    return path


@contracte_bp.route('/<int:contract_id>/program/import', methods=['GET', 'POST'])
@login_required
def program_import(contract_id):
    """Upload + parse MS Project XML -> creeaza ProgramReferinta + N x TaskProgram."""
    if not is_enabled('controale-contract-import-msproject'):
        flash('Importul MS Project nu e activ. Activeaza flag-ul '
              '"controale-contract-import-msproject" din setari.', 'warning')
        return redirect(url_for('contracte.detalii', id=contract_id))

    contract = Contract.query.get_or_404(contract_id)

    if request.method == 'POST':
        file_storage = request.files.get('fisier')
        try:
            file_path = _save_uploaded_file(file_storage, 'programe',
                                            ALLOWED_EXT_MSPROJECT)
        except ValueError as e:
            flash(str(e), 'danger')
            return render_template('contracte/program_import.html',
                                   contract=contract)

        parser = MSProjectXMLParser()
        try:
            result = parser.parse(file_path)
        except ParseError as e:
            flash(f'Eroare parsare XML: {e}', 'danger')
            return render_template('contracte/program_import.html',
                                   contract=contract)

        if result.has_errors:
            for err in result.errors:
                flash(f'Eroare: {err}', 'danger')
            return render_template('contracte/program_import.html',
                                   contract=contract, parse_result=result)

        if result.is_empty:
            flash('Niciun task gasit in XML.', 'warning')
            return render_template('contracte/program_import.html',
                                   contract=contract, parse_result=result)

        # Creez ProgramReferinta + taskuri in tranzactie
        try:
            # Versiune urmatoare pe proiect
            ultima_v = db.session.query(db.func.max(ProgramReferinta.versiune)) \
                .filter_by(proiect_id=contract.proiect_id).scalar() or 0
            program = ProgramReferinta(
                proiect_id=contract.proiect_id,
                contract_id=contract.id,
                versiune=ultima_v + 1,
                denumire=result.stats.get('project_name') or contract.nr_contract,
                data_emitere=date.today(),
                sursa_import=result.sursa,
                fisier_sursa_path=file_path,
                aprobat=False,
                creat_de_id=current_user.id,
            )
            db.session.add(program)
            db.session.flush()

            # Map cod_extern -> task.id pentru parinte_task_id resolve
            cod_to_id: dict[str, int] = {}
            # Prima trecere: creem taskurile (fara parinte_task_id)
            tasks_buffer = []
            for ent in result.entities:
                t = TaskProgram(
                    program_id=program.id,
                    proiect_id=contract.proiect_id,
                    cod_extern=ent['cod_extern'],
                    cod_wbs=ent.get('cod_wbs'),
                    denumire=ent['denumire'][:500],  # safeguard
                    nivel_ierarhie=ent['nivel_ierarhie'],
                    data_start_planificat=ent['data_start_planificat'],
                    data_sfarsit_planificat=ent['data_sfarsit_planificat'],
                    durata_zile=ent.get('durata_zile'),
                    procent_realizare=ent['procent_realizare'],
                    tip_task=ent['tip_task'],
                )
                t.predecesori = ent.get('predecesori', [])
                db.session.add(t)
                tasks_buffer.append((t, ent))
            db.session.flush()
            for t, ent in tasks_buffer:
                cod_to_id[ent['cod_extern']] = t.id

            # A doua trecere: parinte_task_id pe baza nivel_ierarhie + ordine WBS
            # MS Project XML nu are explicit ParentUID; deducem din WBS pattern.
            # WBS '1.2.3' are parinte '1.2'. Daca nu gasim parinte, lasam None.
            for t, ent in tasks_buffer:
                wbs = ent.get('cod_wbs')
                if not wbs or '.' not in wbs:
                    continue
                parent_wbs = wbs.rsplit('.', 1)[0]
                # Caut un alt task cu acelasi WBS prefix in batch
                for t2, ent2 in tasks_buffer:
                    if ent2.get('cod_wbs') == parent_wbs and t2.id != t.id:
                        t.parinte_task_id = t2.id
                        break

            audit_svc.log_create('program_referinta', program.id, new_values={
                'proiect_id': program.proiect_id,
                'versiune': program.versiune,
                'sursa_import': program.sursa_import,
                'taskuri_count': len(tasks_buffer),
            })
            db.session.commit()
            flash(
                f'Program v{program.versiune} importat: '
                f'{len(tasks_buffer)} taskuri din MS Project XML. '
                f'Warnings: {len(result.warnings)}.',
                'success',
            )
            return redirect(url_for('contracte.program_detalii', program_id=program.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Eroare la salvarea programului: {e}', 'danger')
            return render_template('contracte/program_import.html',
                                   contract=contract, parse_result=result)

    return render_template('contracte/program_import.html', contract=contract)


@contracte_bp.route('/program/<int:program_id>')
@login_required
def program_detalii(program_id):
    """Vezi programul + lista taskuri ierarhic."""
    program = ProgramReferinta.query.get_or_404(program_id)
    # Taskuri sortate dupa data_start_planificat (cu summary-urile sus prin
    # nivel_ierarhie ASC pe start egal)
    taskuri = TaskProgram.query.filter_by(program_id=program.id) \
        .order_by(TaskProgram.data_start_planificat,
                  TaskProgram.nivel_ierarhie,
                  TaskProgram.id).all()
    return render_template('contracte/program_detalii.html',
                           program=program, taskuri=taskuri)


# ============================================================
# OFERTA + BoQ (Faza 11) - import eDevize XML / Excel XLSX
# ============================================================

@contracte_bp.route('/<int:contract_id>/oferta/import', methods=['GET', 'POST'])
@login_required
def oferta_import(contract_id):
    """Upload + parse eDevize XML sau Excel XLSX -> OfertaContract + N x PozitieBoQ."""
    contract = Contract.query.get_or_404(contract_id)

    if request.method == 'POST':
        tip_parser = request.form.get('tip_parser', 'auto').strip()
        file_storage = request.files.get('fisier')
        try:
            file_path = _save_uploaded_file(file_storage, 'oferte',
                                            ALLOWED_EXT_OFERTA)
        except ValueError as e:
            flash(str(e), 'danger')
            return render_template('contracte/oferta_import.html',
                                   contract=contract)

        ext = file_path.rsplit('.', 1)[1].lower()
        # Auto-detect parser dupa extensie
        if tip_parser == 'auto':
            if ext == 'xml':
                tip_parser = 'edevize_xml'
            elif ext == 'pdf':
                tip_parser = 'edevize_pdf'
            else:
                tip_parser = 'excel_xlsx'

        if tip_parser == 'edevize_xml':
            parser = EDevizeXMLParser()
        elif tip_parser == 'edevize_pdf':
            parser = EDevizePDFParser()
        elif tip_parser == 'excel_xlsx':
            parser = ExcelBoQParser()
        else:
            flash(f'Tip parser necunoscut: {tip_parser}', 'danger')
            return render_template('contracte/oferta_import.html',
                                   contract=contract)

        try:
            result = parser.parse(file_path)
        except ParseError as e:
            flash(f'Eroare parsare: {e}', 'danger')
            return render_template('contracte/oferta_import.html',
                                   contract=contract)

        if result.has_errors:
            for err in result.errors:
                flash(f'Eroare: {err}', 'danger')
            return render_template('contracte/oferta_import.html',
                                   contract=contract, parse_result=result)

        if result.is_empty:
            flash('Nicio pozitie BoQ gasita in fisier.', 'warning')
            return render_template('contracte/oferta_import.html',
                                   contract=contract, parse_result=result)

        # Creare oferta + pozitii in tranzactie
        try:
            ultima_v = db.session.query(db.func.max(OfertaContract.versiune)) \
                .filter_by(contract_id=contract.id).scalar() or 0
            data_emitere_str = result.stats.get('data_emitere')
            data_emitere_parsed = date.today()
            if data_emitere_str:
                try:
                    data_emitere_parsed = datetime.strptime(
                        data_emitere_str, '%Y-%m-%d'
                    ).date()
                except ValueError:
                    pass
            valoare_totala_calc = sum(
                (Decimal(str(e['cantitate_oferta'])) * Decimal(str(e['pret_unitar'])))
                for e in result.entities
            )
            oferta = OfertaContract(
                contract_id=contract.id,
                proiect_id=contract.proiect_id,
                versiune=ultima_v + 1,
                data_emitere=data_emitere_parsed,
                valoare_totala=valoare_totala_calc,
                sursa_import=result.sursa,
                fisier_sursa_path=file_path,
                aprobata=False,
                creat_de_id=current_user.id,
            )
            db.session.add(oferta)
            db.session.flush()

            for ent in result.entities:
                pz = PozitieBoQ(
                    oferta_id=oferta.id,
                    proiect_id=contract.proiect_id,
                    cod_articol=ent['cod_articol'],
                    cod_capitol=ent.get('cod_capitol'),
                    denumire=ent['denumire'],
                    um=ent['um'],
                    cantitate_oferta=ent['cantitate_oferta'],
                    pret_unitar=ent['pret_unitar'],
                    categorie=ent['categorie'],
                    ordine=ent['ordine'],
                    valoare_materiale_unitar=ent.get('valoare_materiale_unitar'),
                    valoare_manopera_unitar=ent.get('valoare_manopera_unitar'),
                    valoare_utilaj_unitar=ent.get('valoare_utilaj_unitar'),
                    valoare_transport_unitar=ent.get('valoare_transport_unitar'),
                )
                db.session.add(pz)

            audit_svc.log_create('oferta_contract', oferta.id, new_values={
                'contract_id': oferta.contract_id,
                'versiune': oferta.versiune,
                'sursa_import': oferta.sursa_import,
                'pozitii_count': len(result.entities),
            })
            db.session.commit()
            flash(
                f'Oferta v{oferta.versiune} importata: '
                f'{len(result.entities)} pozitii BoQ. '
                f'Valoare totala: {valoare_totala_calc:.2f}. '
                f'Warnings: {len(result.warnings)}.',
                'success',
            )
            return redirect(url_for('contracte.oferta_detalii', oferta_id=oferta.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Eroare la salvarea ofertei: {e}', 'danger')
            return render_template('contracte/oferta_import.html',
                                   contract=contract, parse_result=result)

    return render_template('contracte/oferta_import.html', contract=contract)


@contracte_bp.route('/oferta/<int:oferta_id>')
@login_required
def oferta_detalii(oferta_id):
    """Vezi oferta + pozitii BoQ cu totals pe categorii."""
    oferta = OfertaContract.query.get_or_404(oferta_id)
    pozitii = PozitieBoQ.query.filter_by(oferta_id=oferta.id) \
        .order_by(PozitieBoQ.cod_capitol, PozitieBoQ.ordine).all()
    # Totals per categorie pentru un mic sumar
    totals = {'materiale': Decimal('0'), 'manopera': Decimal('0'),
              'utilaje': Decimal('0'), 'transport': Decimal('0'),
              'mixt': Decimal('0')}
    for p in pozitii:
        val = (p.cantitate_oferta or 0) * (p.pret_unitar or 0)
        totals[p.categorie] = totals.get(p.categorie, Decimal('0')) + Decimal(str(val))
    return render_template('contracte/oferta_detalii.html',
                           oferta=oferta, pozitii=pozitii, totals=totals)


# ============================================================
# FAZA 12 - CANTITATI EXECUTATE LUNARE (matrice editabila)
# ============================================================

@contracte_bp.route('/oferta/<int:oferta_id>/cantitati', methods=['GET', 'POST'])
@login_required
def oferta_cantitati(oferta_id):
    """
    Matrice editabila cantitati executate lunar pentru o oferta.

    GET cu ?an=2026&luna=3&capitol=...&q=...&page=1 - lista filtrate
    POST cu hidden fields cantitate_<pid>, note_<pid> - bulk save
    """
    oferta = OfertaContract.query.get_or_404(oferta_id)
    # Parametri filtrare / paginare
    today = date.today()
    an = request.args.get('an', type=int) or today.year
    luna = request.args.get('luna', type=int) or today.month
    capitol = (request.args.get('capitol') or '').strip()
    categorie = (request.args.get('categorie') or '').strip()
    q = (request.args.get('q') or '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 50

    if request.method == 'POST':
        # Bulk save cantitati
        bulk = parse_bulk_cantitati(request.form)
        count_created = 0
        count_updated = 0
        for entry in bulk:
            pid = entry['pozitie_boq_id']
            # Validez ca pozitia apartine ofertei (evit injectii)
            pz = PozitieBoQ.query.filter_by(id=pid, oferta_id=oferta.id).first()
            if pz is None:
                continue
            existing = CantitateExecutataLunara.query.filter_by(
                pozitie_boq_id=pid, an=an, luna=luna
            ).first()
            cant_valoare = entry['cantitate_executata']
            pret = pz.pret_unitar or Decimal('0')
            val_calc = cant_valoare * pret
            if existing is None:
                c = CantitateExecutataLunara(
                    pozitie_boq_id=pid, proiect_id=pz.proiect_id,
                    an=an, luna=luna,
                    cantitate_executata=cant_valoare,
                    valoare_calculata=val_calc,
                    note=entry.get('note'),
                    inregistrat_de_id=current_user.id,
                )
                db.session.add(c)
                db.session.flush()
                audit_svc.log_create('cantitate_executata_lunara', c.id, new_values={
                    'pozitie_boq_id': pid, 'an': an, 'luna': luna,
                    'cantitate': str(cant_valoare),
                })
                count_created += 1
            else:
                before = audit_svc.snapshot(existing, ['cantitate_executata', 'note'])
                existing.cantitate_executata = cant_valoare
                existing.valoare_calculata = val_calc
                if entry.get('note'):
                    existing.note = entry['note']
                # Reset validare daca admin schimba cantitate
                if existing.validat:
                    existing.validat = False
                    existing.validat_de_id = None
                    existing.data_validare = None
                audit_svc.log_update('cantitate_executata_lunara', existing.id,
                                     before, audit_svc.snapshot(existing, ['cantitate_executata', 'note']))
                count_updated += 1
        db.session.commit()
        flash(
            f'{count_created} cantitati noi + {count_updated} actualizate '
            f'pentru {LUNI_RO.get(luna, luna)} {an}.',
            'success',
        )
        # Redirect cu aceleasi filtre
        return redirect(url_for(
            'contracte.oferta_cantitati', oferta_id=oferta.id,
            an=an, luna=luna, capitol=capitol, categorie=categorie, q=q, page=page,
        ))

    # GET - construiesc query
    query = PozitieBoQ.query.filter_by(oferta_id=oferta.id)
    if capitol:
        query = query.filter(PozitieBoQ.cod_capitol == capitol)
    if categorie:
        query = query.filter(PozitieBoQ.categorie == categorie)
    if q:
        query = query.filter(
            db.or_(
                PozitieBoQ.cod_articol.ilike(f'%{q}%'),
                PozitieBoQ.denumire.ilike(f'%{q}%'),
            )
        )
    query = query.order_by(PozitieBoQ.cod_capitol, PozitieBoQ.ordine)
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    pozitii = pagination.items

    # Cantitati deja inregistrate pentru luna (mapate pe pozitie_boq_id)
    cantitati_existente = {}
    if pozitii:
        for c in CantitateExecutataLunara.query.filter(
            CantitateExecutataLunara.pozitie_boq_id.in_([p.id for p in pozitii]),
            CantitateExecutataLunara.an == an,
            CantitateExecutataLunara.luna == luna,
        ).all():
            cantitati_existente[c.pozitie_boq_id] = c

    # Capitole + categorii distincte pentru filtre dropdown
    capitole_distincte = [
        c[0] for c in db.session.query(PozitieBoQ.cod_capitol).filter(
            PozitieBoQ.oferta_id == oferta.id,
            PozitieBoQ.cod_capitol.isnot(None),
        ).distinct().order_by(PozitieBoQ.cod_capitol).all()
        if c[0]
    ]
    categorii = [c[0] for c, in zip(*[(['materiale', 'manopera', 'utilaje', 'transport', 'mixt'],)])]

    return render_template(
        'contracte/cantitati_matrice.html',
        oferta=oferta, pozitii=pozitii, pagination=pagination,
        cantitati_existente=cantitati_existente,
        an=an, luna=luna, capitol=capitol, categorie=categorie, q=q,
        luni_choices=LUNI_CHOICES,
        capitole=capitole_distincte,
        categorii_disponibile=['materiale', 'manopera', 'utilaje', 'transport', 'mixt'],
    )


@contracte_bp.route('/cantitate/<int:cantitate_id>/valideaza', methods=['POST'])
@login_required
def cantitate_valideaza(cantitate_id):
    """Manager valideaza o cantitate. Doar adminii / managerii."""
    if current_user.rol not in ('admin', 'manager'):
        flash('Doar managerii pot valida cantitati.', 'danger')
        return redirect(request.referrer or url_for('contracte.lista'))
    c = CantitateExecutataLunara.query.get_or_404(cantitate_id)
    if c.validat:
        flash('Cantitate deja validata.', 'info')
        return redirect(request.referrer or url_for('contracte.lista'))
    before = audit_svc.snapshot(c, ['validat', 'validat_de_id'])
    c.validat = True
    c.validat_de_id = current_user.id
    c.data_validare = datetime.utcnow()
    audit_svc.log_update('cantitate_executata_lunara', c.id, before,
                         audit_svc.snapshot(c, ['validat', 'validat_de_id']))
    db.session.commit()
    flash(f'Cantitate validata (poz {c.pozitie_boq_id}, '
          f'{LUNI_RO.get(c.luna, c.luna)} {c.an}).', 'success')
    return redirect(request.referrer or url_for('contracte.lista'))


@contracte_bp.route('/cantitate/<int:cantitate_id>/sterge', methods=['POST'])
@login_required
def cantitate_sterge(cantitate_id):
    """Sterge o cantitate (doar daca nu e legata de o situatie emisa)."""
    c = CantitateExecutataLunara.query.get_or_404(cantitate_id)
    pid = c.pozitie_boq_id
    try:
        audit_svc.log_delete('cantitate_executata_lunara', c.id, old_values={
            'pozitie_boq_id': pid, 'an': c.an, 'luna': c.luna,
            'cantitate': str(c.cantitate_executata),
        })
        db.session.delete(c)
        db.session.commit()
        flash('Cantitate stearsa.', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Eroare la stergere: {e}', 'danger')
    return redirect(request.referrer or url_for('contracte.lista'))


# ============================================================
# FAZA 12 - SITUATII LUNARE
# ============================================================

@contracte_bp.route('/<int:contract_id>/situatii')
@login_required
def situatii_lista(contract_id):
    """Lista situatii lunare pentru un contract."""
    contract = Contract.query.get_or_404(contract_id)
    situatii = SituatieLunara.query.filter_by(
        contract_id=contract.id
    ).order_by(SituatieLunara.an.desc(), SituatieLunara.luna.desc()).all()
    return render_template('contracte/situatii_lista.html',
                           contract=contract, situatii=situatii,
                           luni_ro=LUNI_RO)


@contracte_bp.route('/<int:contract_id>/situatie/nou', methods=['GET', 'POST'])
@login_required
def situatie_nou(contract_id):
    """Genereaza o situatie lunara noua din cantitati validate."""
    contract = Contract.query.get_or_404(contract_id)
    form = SituatieLunaraForm()
    if request.method == 'GET':
        # Preset luna/an din URL daca prezent
        preset_an = request.args.get('an', type=int)
        preset_luna = request.args.get('luna', type=int)
        if preset_an: form.an.data = preset_an
        if preset_luna: form.luna.data = preset_luna
        if not form.an.data:
            form.an.data = date.today().year
        if not form.luna.data:
            form.luna.data = date.today().month
        if not form.status.data:
            form.status.data = 'draft'

    if form.validate_on_submit():
        an = form.an.data
        luna = form.luna.data
        # Verifica daca exista deja o situatie pentru (proiect, an, luna)
        existing = SituatieLunara.query.filter_by(
            proiect_id=contract.proiect_id, an=an, luna=luna,
        ).first()
        try:
            situatie = genereaza_situatie(contract.id, an, luna, current_user.id)
            # Aplic numar + status (override din form)
            if form.numar_situatie.data:
                situatie.numar_situatie = form.numar_situatie.data.strip()
            if form.status.data:
                situatie.status = form.status.data
            if form.data_emitere.data:
                situatie.data_emitere = form.data_emitere.data
            audit_svc.log_create(
                'situatie_lunara', situatie.id,
                new_values={
                    'contract_id': contract.id, 'an': an, 'luna': luna,
                    'valoare_luna': str(situatie.valoare_totala_luna or 0),
                },
            )
            db.session.commit()
            action = 'actualizata' if existing else 'creata'
            flash(
                f'Situatie {action}: {LUNI_RO.get(luna, luna)} {an}, '
                f'valoare luna {situatie.valoare_totala_luna or 0:.2f} RON.',
                'success',
            )
            return redirect(url_for('contracte.situatie_detalii',
                                     situatie_id=situatie.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Eroare la generare: {e}', 'danger')

    return render_template('contracte/situatie_formular.html',
                           form=form, contract=contract, situatie=None)


@contracte_bp.route('/situatie/<int:situatie_id>')
@login_required
def situatie_detalii(situatie_id):
    """Detalii situatie cu tabel pozitii, totaluri, butoane export + status."""
    from services.situatii import _get_situatie_data
    situatie = SituatieLunara.query.get_or_404(situatie_id)
    data = _get_situatie_data(situatie)
    # Status transitions valide (workflow simplu)
    transitions = {
        'draft': ['emisa'],
        'emisa': ['aprobata_beneficiar', 'respinsa'],
        'aprobata_beneficiar': ['platita'],
        'platita': [],
        'respinsa': ['draft'],
    }
    return render_template('contracte/situatie_detalii.html',
                           situatie=situatie, data=data,
                           luna_text=data['luna_text'],
                           transitions=transitions.get(situatie.status, []),
                           statuses=SituatieLunara.STATUSES)


@contracte_bp.route('/situatie/<int:situatie_id>/status', methods=['POST'])
@login_required
def situatie_schimba_status(situatie_id):
    """Schimba statusul unei situatii (workflow draft->emisa->aprobata->platita)."""
    situatie = SituatieLunara.query.get_or_404(situatie_id)
    nou_status = (request.form.get('nou_status') or '').strip()
    valid_statuses = {s[0] for s in SituatieLunara.STATUSES}
    if nou_status not in valid_statuses:
        flash(f'Status invalid: {nou_status}', 'danger')
        return redirect(url_for('contracte.situatie_detalii', situatie_id=situatie.id))
    before = audit_svc.snapshot(situatie, ['status'])
    vechi_status = situatie.status
    situatie.status = nou_status
    if nou_status == 'aprobata_beneficiar':
        situatie.aprobat_de_id = current_user.id
        situatie.data_aprobare = datetime.utcnow()
    audit_svc.log_update('situatie_lunara', situatie.id, before,
                         audit_svc.snapshot(situatie, ['status']))
    db.session.commit()
    flash(f'Status schimbat: {vechi_status} -> {nou_status}', 'success')
    return redirect(url_for('contracte.situatie_detalii', situatie_id=situatie.id))


@contracte_bp.route('/situatie/<int:situatie_id>/retentii', methods=['POST'])
@login_required
def situatie_retentii(situatie_id):
    """
    Editeaza retentia + garantia + avansul recuperat ale unei situatii.

    Deviz Faza 3, gated pe flag 'situatii-retentii'. Cu flag OFF, 404 (sectiunea
    nu apare in UI). Recalculeaza plata neta din valoarea lunii cu procentele /
    avansul introdus si persista coloanele aditive.
    """
    from services.feature_flags import is_enabled
    if not is_enabled('situatii-retentii'):
        abort(404)
    situatie = SituatieLunara.query.get_or_404(situatie_id)
    before = audit_svc.snapshot(
        situatie, ['retentie_procent', 'retentie_suma', 'garantie_bex_suma',
                   'avans_recuperat', 'plata_neta', 'retentii_editate_manual'])

    def _dec(name):
        raw = (request.form.get(name) or '').strip().replace(',', '.')
        if raw == '':
            return Decimal('0')
        try:
            return Decimal(raw)
        except Exception:
            return Decimal('0')

    valoare_luna = Decimal(situatie.valoare_totala_luna or 0)
    retentie_procent = _dec('retentie_procent')
    garantie_procent = _dec('garantie_bex_procent')
    avans_recuperat = _dec('avans_recuperat')

    retentie_suma = (valoare_luna * retentie_procent / 100).quantize(Decimal('0.01'))
    garantie_suma = (valoare_luna * garantie_procent / 100).quantize(Decimal('0.01'))
    plata_neta = (valoare_luna - retentie_suma - garantie_suma
                  - avans_recuperat).quantize(Decimal('0.01'))

    situatie.retentie_procent = retentie_procent
    situatie.retentie_suma = retentie_suma
    situatie.garantie_bex_suma = garantie_suma
    situatie.avans_recuperat = avans_recuperat
    situatie.plata_neta = plata_neta
    # Marcaj explicit: aceste sume au fost editate manual de utilizator. La o
    # regenerare ulterioara, auto-generarea pastreaza sumele si recalculeaza doar
    # plata neta (nu le suprascrie din procent * valoare_luna).
    situatie.retentii_editate_manual = True
    audit_svc.log_update(
        'situatie_lunara', situatie.id, before,
        audit_svc.snapshot(
            situatie, ['retentie_procent', 'retentie_suma', 'garantie_bex_suma',
                       'avans_recuperat', 'plata_neta', 'retentii_editate_manual']))
    db.session.commit()
    flash(f'Retentii actualizate. Plata neta: {plata_neta:.2f} RON.', 'success')
    return redirect(url_for('contracte.situatie_detalii', situatie_id=situatie.id))


@contracte_bp.route('/situatie/<int:situatie_id>/export/xlsx')
@login_required
def situatie_export_xlsx(situatie_id):
    """Export Excel pentru situatie lunara."""
    from flask import send_file
    try:
        path = export_situatie_xlsx(situatie_id)
    except Exception as e:
        flash(f'Eroare export Excel: {e}', 'danger')
        return redirect(url_for('contracte.situatie_detalii', situatie_id=situatie_id))
    return send_file(path, as_attachment=True,
                     download_name=os.path.basename(path),
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@contracte_bp.route('/situatie/<int:situatie_id>/export/pdf')
@login_required
def situatie_export_pdf(situatie_id):
    """Export PDF pentru situatie lunara."""
    from flask import send_file
    try:
        path = export_situatie_pdf(situatie_id)
    except Exception as e:
        flash(f'Eroare export PDF: {e}', 'danger')
        return redirect(url_for('contracte.situatie_detalii', situatie_id=situatie_id))
    return send_file(path, as_attachment=True,
                     download_name=os.path.basename(path),
                     mimetype='application/pdf')


# ============================================================
# FAZA 12 - RAPOARTE LUCRARI PROIECT (aggregator)
# ============================================================

@contracte_bp.route('/proiect/<int:proiect_id>/rapoarte-lucrari')
@login_required
def rapoarte_lucrari_lista(proiect_id):
    """Lista rapoarte lunare pentru un proiect."""
    proiect = Proiect.query.get_or_404(proiect_id)
    rapoarte = RaportLucrariProiect.query.filter_by(
        proiect_id=proiect_id
    ).order_by(RaportLucrariProiect.an.desc(),
               RaportLucrariProiect.luna.desc()).all()
    return render_template('contracte/rapoarte_lucrari_lista.html',
                           proiect=proiect, rapoarte=rapoarte,
                           luni_ro=LUNI_RO)


@contracte_bp.route('/proiect/<int:proiect_id>/raport-lucrari/genereaza',
                    methods=['GET', 'POST'])
@login_required
def raport_lucrari_genereaza(proiect_id):
    """Genereaza un raport lunar agregator (Pontaj + Activitati + Taskuri)."""
    proiect = Proiect.query.get_or_404(proiect_id)
    form = RaportLucrariForm()
    if request.method == 'GET':
        form.an.data = date.today().year
        form.luna.data = date.today().month

    if form.validate_on_submit():
        try:
            raport = genereaza_raport_lucrari(
                proiect_id, form.an.data, form.luna.data, current_user.id
            )
            # Permit override descriere manual
            if form.progres_descriere.data:
                manual = form.progres_descriere.data.strip()
                auto = (raport.progres_descriere or '').strip()
                raport.progres_descriere = (
                    f'{manual}\n\n--- Auto-extras din activitati ---\n{auto}'
                    if auto else manual
                )
            audit_svc.log_create('raport_lucrari_proiect', raport.id, new_values={
                'proiect_id': proiect_id, 'an': form.an.data, 'luna': form.luna.data,
                'ore_totale_manopera': str(raport.ore_totale_manopera or 0),
            })
            db.session.commit()
            flash(
                f'Raport generat: {LUNI_RO.get(raport.luna, raport.luna)} {raport.an}, '
                f'{raport.ore_totale_manopera or 0:.1f} ore manopera, '
                f'{len(raport.taskuri_acoperite)} taskuri acoperite.',
                'success',
            )
            return redirect(url_for('contracte.raport_lucrari_detalii',
                                     raport_id=raport.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Eroare la generare raport: {e}', 'danger')

    return render_template('contracte/raport_lucrari_formular.html',
                           form=form, proiect=proiect)


@contracte_bp.route('/raport-lucrari/<int:raport_id>')
@login_required
def raport_lucrari_detalii(raport_id):
    """Detalii raport lunar."""
    raport = RaportLucrariProiect.query.get_or_404(raport_id)
    # Imbogatesc cu numele taskurilor (cautam in TaskProgram)
    taskuri_acoperite_details = []
    if raport.taskuri_acoperite:
        for cod in raport.taskuri_acoperite:
            t = TaskProgram.query.filter(
                TaskProgram.proiect_id == raport.proiect_id,
                TaskProgram.cod_extern == cod,
            ).first()
            taskuri_acoperite_details.append({
                'cod_extern': cod,
                'denumire': t.denumire if t else '(task nereperat)',
                'data_start': t.data_start_planificat if t else None,
                'data_sfarsit': t.data_sfarsit_planificat if t else None,
                'procent_realizare': t.procent_realizare if t else None,
            })
    return render_template('contracte/raport_lucrari_detalii.html',
                           raport=raport, luna_text=LUNI_RO.get(raport.luna, raport.luna),
                           taskuri_details=taskuri_acoperite_details)


# ============================================================
# FAZA 13 - CORESPONDENTA (registru per proiect)
# ============================================================

@contracte_bp.route('/corespondenta')
@login_required
def corespondenta_lista():
    """Lista corespondenta (toate proiectele, filtrabila)."""
    proiect_filtru = request.args.get('proiect', type=int)
    tip_filtru = (request.args.get('tip') or '').strip()
    subtip_filtru = (request.args.get('subtip') or '').strip()
    directie_filtru = (request.args.get('directie') or '').strip()
    cautare = (request.args.get('cautare') or '').strip()
    page = request.args.get('page', 1, type=int)

    query = Corespondenta.query
    if proiect_filtru:
        query = query.filter_by(proiect_id=proiect_filtru)
    if tip_filtru:
        query = query.filter_by(tip=tip_filtru)
    if subtip_filtru:
        query = query.filter_by(subtip=subtip_filtru)
    if directie_filtru:
        query = query.filter_by(directie=directie_filtru)
    if cautare:
        query = query.filter(
            db.or_(
                Corespondenta.numar_inregistrare.ilike(f'%{cautare}%'),
                Corespondenta.subiect.ilike(f'%{cautare}%'),
                Corespondenta.expeditor.ilike(f'%{cautare}%'),
                Corespondenta.destinatar.ilike(f'%{cautare}%'),
            )
        )
    pagination = query.order_by(Corespondenta.data_inregistrare.desc()) \
        .paginate(page=page, per_page=30, error_out=False)

    proiecte_pentru_filtru = Proiect.query.order_by(Proiect.cod_proiect).all()
    return render_template(
        'contracte/corespondenta_lista.html',
        corespondente=pagination.items, pagination=pagination,
        proiecte=proiecte_pentru_filtru,
        tipuri=Corespondenta.TIPURI, subtipuri=Corespondenta.SUBTIPURI,
        directii=Corespondenta.DIRECTII,
        proiect_filtru=proiect_filtru, tip_filtru=tip_filtru,
        subtip_filtru=subtip_filtru, directie_filtru=directie_filtru,
        cautare=cautare,
    )


@contracte_bp.route('/corespondenta/nou', methods=['GET', 'POST'])
@login_required
def corespondenta_nou():
    form = CorespondentaForm()
    preset_proiect = request.args.get('proiect_id', type=int)
    preset_contract = request.args.get('contract_id', type=int)
    if request.method == 'GET':
        if preset_proiect:
            form.proiect_id.data = preset_proiect
            form.populeaza_raspuns_la(preset_proiect)
        if preset_contract:
            form.contract_id.data = preset_contract

    if request.method == 'POST' and form.proiect_id.data:
        form.populeaza_raspuns_la(form.proiect_id.data)

    if form.validate_on_submit():
        try:
            contract_id = form.contract_id.data or None
            if contract_id == 0:
                contract_id = None
            raspuns_la_id = form.raspuns_la_id.data or None
            if raspuns_la_id == 0:
                raspuns_la_id = None
            c = Corespondenta(
                proiect_id=form.proiect_id.data,
                contract_id=contract_id,
                numar_inregistrare=form.numar_inregistrare.data.strip(),
                data_inregistrare=form.data_inregistrare.data,
                tip=form.tip.data,
                subtip=(form.subtip.data or '').strip() or None,
                directie=form.directie.data,
                expeditor=(form.expeditor.data or '').strip() or None,
                destinatar=(form.destinatar.data or '').strip() or None,
                subiect=(form.subiect.data or '').strip() or None,
                continut_text=form.continut_text.data or None,
                raspuns_la_id=raspuns_la_id,
                genereaza_termen=bool(form.genereaza_termen.data),
                creat_de_id=current_user.id,
            )
            db.session.add(c)
            db.session.flush()
            # Hook auto: creare TermenUrmarit daca genereaza_termen=True
            termen_creat = None
            if c.genereaza_termen:
                termen_creat = creeaza_termen_din_corespondenta(c, current_user.id)
            audit_svc.log_create('corespondenta', c.id, new_values={
                'proiect_id': c.proiect_id, 'tip': c.tip,
                'subtip': c.subtip, 'directie': c.directie,
                'numar_inregistrare': c.numar_inregistrare,
            })
            db.session.commit()
            msg = f'Corespondenta "{c.numar_inregistrare}" inregistrata.'
            if termen_creat:
                msg += (f' Termen 30 zile creat automat '
                        f'(scadenta {termen_creat.data_scadenta}).')
            flash(msg, 'success')
            return redirect(url_for('contracte.corespondenta_detalii', id=c.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Eroare la salvare: {e}', 'danger')

    return render_template('contracte/corespondenta_formular.html',
                           form=form, corespondenta=None)


@contracte_bp.route('/corespondenta/<int:id>')
@login_required
def corespondenta_detalii(id):
    c = Corespondenta.query.get_or_404(id)
    raspunsuri = Corespondenta.query.filter_by(raspuns_la_id=c.id).order_by(
        Corespondenta.data_inregistrare
    ).all()
    termen_asociat = TermenUrmarit.query.filter_by(
        entitate_sursa='corespondenta', id_entitate_sursa=c.id
    ).first()
    return render_template('contracte/corespondenta_detalii.html',
                           corespondenta=c, raspunsuri=raspunsuri,
                           termen_asociat=termen_asociat)


@contracte_bp.route('/corespondenta/<int:id>/editeaza', methods=['GET', 'POST'])
@login_required
def corespondenta_editeaza(id):
    c = Corespondenta.query.get_or_404(id)
    form = CorespondentaForm(obj=c)
    form.populeaza_raspuns_la(c.proiect_id)
    if request.method == 'GET':
        form.corespondenta_id.data = c.id
        form.contract_id.data = c.contract_id or 0
        form.raspuns_la_id.data = c.raspuns_la_id or 0
        form.subtip.data = c.subtip or ''

    if form.validate_on_submit():
        try:
            audit_fields = ['proiect_id', 'contract_id', 'numar_inregistrare',
                            'tip', 'subtip', 'directie', 'genereaza_termen']
            before = audit_svc.snapshot(c, audit_fields)
            had_termen = bool(c.genereaza_termen)
            contract_id = form.contract_id.data or None
            if contract_id == 0:
                contract_id = None
            raspuns_la_id = form.raspuns_la_id.data or None
            if raspuns_la_id == 0:
                raspuns_la_id = None
            c.proiect_id = form.proiect_id.data
            c.contract_id = contract_id
            c.numar_inregistrare = form.numar_inregistrare.data.strip()
            c.data_inregistrare = form.data_inregistrare.data
            c.tip = form.tip.data
            c.subtip = (form.subtip.data or '').strip() or None
            c.directie = form.directie.data
            c.expeditor = (form.expeditor.data or '').strip() or None
            c.destinatar = (form.destinatar.data or '').strip() or None
            c.subiect = (form.subiect.data or '').strip() or None
            c.continut_text = form.continut_text.data or None
            c.raspuns_la_id = raspuns_la_id
            c.genereaza_termen = bool(form.genereaza_termen.data)
            # Hook: gestionare TermenUrmarit la schimbarea genereaza_termen
            if c.genereaza_termen:
                creeaza_termen_din_corespondenta(c, current_user.id)
            elif had_termen and not c.genereaza_termen:
                sterge_termen_din_corespondenta(c)
            audit_svc.log_update('corespondenta', c.id, before,
                                 audit_svc.snapshot(c, audit_fields))
            db.session.commit()
            flash('Corespondenta actualizata.', 'success')
            return redirect(url_for('contracte.corespondenta_detalii', id=c.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Eroare la salvare: {e}', 'danger')

    return render_template('contracte/corespondenta_formular.html',
                           form=form, corespondenta=c)


@contracte_bp.route('/corespondenta/<int:id>/sterge', methods=['POST'])
@login_required
def corespondenta_sterge(id):
    c = Corespondenta.query.get_or_404(id)
    proiect_id = c.proiect_id
    try:
        audit_svc.log_delete('corespondenta', c.id, old_values={
            'numar_inregistrare': c.numar_inregistrare, 'tip': c.tip,
        })
        # Sterge TermenUrmarit asociat (daca exista)
        sterge_termen_din_corespondenta(c)
        db.session.delete(c)
        db.session.commit()
        flash('Corespondenta stearsa.', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Eroare la stergere: {e}', 'danger')
    return redirect(url_for('contracte.corespondenta_lista', proiect=proiect_id))


# ============================================================
# FAZA 13 - REVENDICARI (Claims)
# ============================================================

@contracte_bp.route('/revendicari')
@login_required
def revendicari_lista():
    """Lista revendicari toate proiectele, filtrabila."""
    proiect_filtru = request.args.get('proiect', type=int)
    status_filtru = (request.args.get('status') or '').strip()
    tip_filtru = (request.args.get('tip') or '').strip()
    cautare = (request.args.get('cautare') or '').strip()

    query = Revendicare.query
    if proiect_filtru:
        query = query.filter_by(proiect_id=proiect_filtru)
    if status_filtru:
        query = query.filter_by(status=status_filtru)
    if tip_filtru:
        query = query.filter_by(tip=tip_filtru)
    if cautare:
        query = query.filter(
            db.or_(
                Revendicare.numar_revendicare.ilike(f'%{cautare}%'),
                Revendicare.descriere.ilike(f'%{cautare}%'),
            )
        )
    revendicari = query.order_by(Revendicare.data_emitere.desc()).all()

    # Numara conflicte per revendicare (read-only, cache per request)
    conflicte_count = {r.id: numara_conflicte(r.id) for r in revendicari}

    proiecte_pentru_filtru = Proiect.query.order_by(Proiect.cod_proiect).all()
    return render_template(
        'contracte/revendicari_lista.html',
        revendicari=revendicari, conflicte_count=conflicte_count,
        proiecte=proiecte_pentru_filtru,
        tipuri=Revendicare.TIPURI, statuses=Revendicare.STATUSES,
        proiect_filtru=proiect_filtru, status_filtru=status_filtru,
        tip_filtru=tip_filtru, cautare=cautare,
    )


@contracte_bp.route('/revendicare/nou', methods=['GET', 'POST'])
@login_required
def revendicare_nou():
    form = RevendicareForm()
    preset_contract = request.args.get('contract_id', type=int)
    preset_corespondenta = request.args.get('corespondenta_id', type=int)
    if request.method == 'GET':
        if preset_contract:
            contract = Contract.query.get(preset_contract)
            if contract:
                form.contract_id.data = contract.id
                form.proiect_id.data = contract.proiect_id
                form.populeaza_corespondenta(contract.proiect_id)
        if preset_corespondenta:
            form.corespondenta_initiatoare_id.data = preset_corespondenta

    if request.method == 'POST' and form.proiect_id.data:
        form.populeaza_corespondenta(form.proiect_id.data)

    if form.validate_on_submit():
        try:
            coresp_id = form.corespondenta_initiatoare_id.data or None
            if coresp_id == 0:
                coresp_id = None
            r = Revendicare(
                proiect_id=form.proiect_id.data,
                contract_id=form.contract_id.data,
                numar_revendicare=form.numar_revendicare.data.strip(),
                data_emitere=form.data_emitere.data,
                tip=form.tip.data,
                descriere=form.descriere.data or None,
                valoare_solicitata=form.valoare_solicitata.data,
                zile_prelungire_solicitate=form.zile_prelungire_solicitate.data,
                status=form.status.data,
                data_decizie=form.data_decizie.data,
                motivare_decizie=form.motivare_decizie.data or None,
                corespondenta_initiatoare_id=coresp_id,
                creat_de_id=current_user.id,
            )
            db.session.add(r)
            db.session.flush()
            audit_svc.log_create('revendicare', r.id, new_values={
                'numar_revendicare': r.numar_revendicare,
                'tip': r.tip, 'status': r.status,
                'valoare_solicitata': str(r.valoare_solicitata or 0),
            })
            db.session.commit()
            flash(f'Revendicare "{r.numar_revendicare}" creata.', 'success')
            return redirect(url_for('contracte.revendicare_detalii', id=r.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Eroare la salvare: {e}', 'danger')

    return render_template('contracte/revendicare_formular.html',
                           form=form, revendicare=None)


@contracte_bp.route('/revendicare/<int:id>')
@login_required
def revendicare_detalii(id):
    r = Revendicare.query.get_or_404(id)
    # Conflicte detection (live)
    conflicte = detecta_conflicte(r.id)
    # Legaturi M:N
    legaturi_termeni = RevendicareTermen.query.filter_by(revendicare_id=r.id).all()
    legaturi_taskuri = RevendicareTask.query.filter_by(revendicare_id=r.id).all()
    legaturi_cantitati = RevendicareCantitate.query.filter_by(revendicare_id=r.id).all()
    return render_template(
        'contracte/revendicare_detalii.html',
        revendicare=r, conflicte=conflicte,
        legaturi_termeni=legaturi_termeni,
        legaturi_taskuri=legaturi_taskuri,
        legaturi_cantitati=legaturi_cantitati,
    )


@contracte_bp.route('/revendicare/<int:id>/editeaza', methods=['GET', 'POST'])
@login_required
def revendicare_editeaza(id):
    r = Revendicare.query.get_or_404(id)
    form = RevendicareForm(obj=r)
    form.populeaza_corespondenta(r.proiect_id)
    if request.method == 'GET':
        form.revendicare_id.data = r.id
        form.corespondenta_initiatoare_id.data = r.corespondenta_initiatoare_id or 0

    if form.validate_on_submit():
        try:
            audit_fields = ['numar_revendicare', 'tip', 'status',
                            'valoare_solicitata', 'zile_prelungire_solicitate',
                            'data_decizie']
            before = audit_svc.snapshot(r, audit_fields)
            coresp_id = form.corespondenta_initiatoare_id.data or None
            if coresp_id == 0:
                coresp_id = None
            r.proiect_id = form.proiect_id.data
            r.contract_id = form.contract_id.data
            r.numar_revendicare = form.numar_revendicare.data.strip()
            r.data_emitere = form.data_emitere.data
            r.tip = form.tip.data
            r.descriere = form.descriere.data or None
            r.valoare_solicitata = form.valoare_solicitata.data
            r.zile_prelungire_solicitate = form.zile_prelungire_solicitate.data
            r.status = form.status.data
            r.data_decizie = form.data_decizie.data
            r.motivare_decizie = form.motivare_decizie.data or None
            r.corespondenta_initiatoare_id = coresp_id
            audit_svc.log_update('revendicare', r.id, before,
                                 audit_svc.snapshot(r, audit_fields))
            db.session.commit()
            flash('Revendicare actualizata.', 'success')
            return redirect(url_for('contracte.revendicare_detalii', id=r.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Eroare la salvare: {e}', 'danger')

    return render_template('contracte/revendicare_formular.html',
                           form=form, revendicare=r)


@contracte_bp.route('/revendicare/<int:id>/sterge', methods=['POST'])
@login_required
def revendicare_sterge(id):
    r = Revendicare.query.get_or_404(id)
    try:
        audit_svc.log_delete('revendicare', r.id, old_values={
            'numar_revendicare': r.numar_revendicare, 'tip': r.tip,
        })
        # Sterge legaturile M:N explicit
        RevendicareTermen.query.filter_by(revendicare_id=r.id).delete()
        RevendicareTask.query.filter_by(revendicare_id=r.id).delete()
        RevendicareCantitate.query.filter_by(revendicare_id=r.id).delete()
        db.session.delete(r)
        db.session.commit()
        flash('Revendicare stearsa.', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Eroare la stergere: {e}', 'danger')
    return redirect(url_for('contracte.revendicari_lista'))


# ============================================================
# FAZA 13 - LEGATURI M:N (Revendicare <-> Termen/Task/Cantitate)
# ============================================================

@contracte_bp.route('/revendicare/<int:id>/link/termen', methods=['GET', 'POST'])
@login_required
def revendicare_link_termen(id):
    r = Revendicare.query.get_or_404(id)
    form = LinkRevendicareTermenForm()
    form.populeaza_termene(r.contract_id)
    if form.validate_on_submit():
        # Verific unicitate
        existing = RevendicareTermen.query.filter_by(
            revendicare_id=r.id, termen_contract_id=form.termen_contract_id.data,
        ).first()
        if existing:
            flash('Legatura cu acest termen exista deja.', 'warning')
        else:
            try:
                link = RevendicareTermen(
                    revendicare_id=r.id,
                    termen_contract_id=form.termen_contract_id.data,
                    tip_legatura=form.tip_legatura.data,
                    observatii=form.observatii.data or None,
                )
                db.session.add(link)
                db.session.commit()
                flash('Legatura cu termen adaugata.', 'success')
            except Exception as e:
                db.session.rollback()
                flash(f'Eroare: {e}', 'danger')
        return redirect(url_for('contracte.revendicare_detalii', id=r.id))
    return render_template('contracte/revendicare_link_form.html',
                           form=form, revendicare=r, tip='termen')


@contracte_bp.route('/revendicare/<int:id>/link/task', methods=['GET', 'POST'])
@login_required
def revendicare_link_task(id):
    r = Revendicare.query.get_or_404(id)
    form = LinkRevendicareTaskForm()
    form.populeaza_taskuri(r.proiect_id)
    if form.validate_on_submit():
        existing = RevendicareTask.query.filter_by(
            revendicare_id=r.id, task_program_id=form.task_program_id.data,
        ).first()
        if existing:
            flash('Legatura cu acest task exista deja.', 'warning')
        else:
            try:
                link = RevendicareTask(
                    revendicare_id=r.id,
                    task_program_id=form.task_program_id.data,
                    tip_legatura=form.tip_legatura.data,
                    observatii=form.observatii.data or None,
                )
                db.session.add(link)
                db.session.commit()
                flash('Legatura cu task adaugata.', 'success')
            except Exception as e:
                db.session.rollback()
                flash(f'Eroare: {e}', 'danger')
        return redirect(url_for('contracte.revendicare_detalii', id=r.id))
    return render_template('contracte/revendicare_link_form.html',
                           form=form, revendicare=r, tip='task')


@contracte_bp.route('/revendicare/<int:id>/link/cantitate', methods=['GET', 'POST'])
@login_required
def revendicare_link_cantitate(id):
    r = Revendicare.query.get_or_404(id)
    form = LinkRevendicareCantitateForm()
    form.populeaza_cantitati(r.proiect_id)
    if form.validate_on_submit():
        existing = RevendicareCantitate.query.filter_by(
            revendicare_id=r.id, cantitate_lunara_id=form.cantitate_lunara_id.data,
        ).first()
        if existing:
            flash('Legatura cu aceasta cantitate exista deja.', 'warning')
        else:
            try:
                link = RevendicareCantitate(
                    revendicare_id=r.id,
                    cantitate_lunara_id=form.cantitate_lunara_id.data,
                    observatii=form.observatii.data or None,
                )
                db.session.add(link)
                db.session.commit()
                flash('Legatura cu cantitate adaugata.', 'success')
            except Exception as e:
                db.session.rollback()
                flash(f'Eroare: {e}', 'danger')
        return redirect(url_for('contracte.revendicare_detalii', id=r.id))
    return render_template('contracte/revendicare_link_form.html',
                           form=form, revendicare=r, tip='cantitate')


@contracte_bp.route('/revendicare/<int:rev_id>/link/<string:tip>/<int:link_id>/sterge',
                    methods=['POST'])
@login_required
def revendicare_link_sterge(rev_id, tip, link_id):
    """Sterge o legatura M:N (tip = termen|task|cantitate)."""
    model_map = {
        'termen': RevendicareTermen,
        'task': RevendicareTask,
        'cantitate': RevendicareCantitate,
    }
    model = model_map.get(tip)
    if not model:
        flash(f'Tip legatura necunoscut: {tip}', 'danger')
        return redirect(url_for('contracte.revendicare_detalii', id=rev_id))
    link = model.query.get_or_404(link_id)
    if link.revendicare_id != rev_id:
        abort(404)
    try:
        db.session.delete(link)
        db.session.commit()
        flash('Legatura stearsa.', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Eroare: {e}', 'danger')
    return redirect(url_for('contracte.revendicare_detalii', id=rev_id))


# ============================================================
# FAZA 14 - NOTIFICARI IN-APP (inbox + mark-read)
# ============================================================

@contracte_bp.route('/notificari/inbox')
@login_required
def notificari_inbox():
    """Inbox notificari pentru utilizator curent."""
    doar_necitite = request.args.get('doar_necitite', '0') == '1'
    notificari = lista_notificari(current_user.id, doar_necitite=doar_necitite,
                                  limit=200)
    return render_template('contracte/notificari_inbox.html',
                           notificari=notificari, doar_necitite=doar_necitite,
                           count_necitite=count_necitite(current_user.id))


@contracte_bp.route('/notificari/<int:id>/mark-read', methods=['POST'])
@login_required
def notificare_mark_read(id):
    """Marcheaza o notificare ca citita."""
    ok = marcheaza_citita(id, current_user.id)
    next_url = request.referrer or url_for('contracte.notificari_inbox')
    if ok:
        flash('Notificare marcata ca citita.', 'success')
    return redirect(next_url)


@contracte_bp.route('/notificari/mark-all-read', methods=['POST'])
@login_required
def notificari_mark_all_read():
    """Bulk mark-as-read pentru utilizator."""
    count = marcheaza_toate_citite(current_user.id)
    flash(f'{count} notificari marcate ca citite.', 'info')
    return redirect(url_for('contracte.notificari_inbox'))


@contracte_bp.route('/notificari/count')
@login_required
def notificari_count():
    """JSON cu count notificari necitite (pentru bell badge)."""
    from flask import jsonify
    return jsonify({'count': count_necitite(current_user.id)})


# ============================================================
# FAZA 14 - PV EXPORT DOCX / PDF
# ============================================================

@contracte_bp.route('/pv/<int:id>/export/docx')
@login_required
def pv_export_docx(id):
    """Export DOCX pentru un ProcesVerbal."""
    from flask import send_file
    try:
        path = genereaza_pv_docx(id)
    except Exception as e:
        flash(f'Eroare generare DOCX: {e}', 'danger')
        return redirect(url_for('contracte.pv_lista'))
    return send_file(
        path, as_attachment=True,
        download_name=os.path.basename(path),
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    )


@contracte_bp.route('/pv/<int:id>/export/pdf')
@login_required
def pv_export_pdf(id):
    """Export PDF pentru un ProcesVerbal."""
    from flask import send_file
    try:
        path = genereaza_pv_pdf(id)
    except Exception as e:
        flash(f'Eroare generare PDF: {e}', 'danger')
        return redirect(url_for('contracte.pv_lista'))
    return send_file(path, as_attachment=True,
                     download_name=os.path.basename(path),
                     mimetype='application/pdf')


# ============================================================
# FAZA 14 - REGULI NOTIFICARE PROIECT (CRUD config)
# ============================================================

@contracte_bp.route('/proiect/<int:proiect_id>/reguli-notificare')
@login_required
def reguli_notificare_lista(proiect_id):
    """Lista reguli notificare configurate pentru un proiect."""
    proiect = Proiect.query.get_or_404(proiect_id)
    reguli = ReguliNotificareProiect.query.filter_by(
        proiect_id=proiect_id
    ).order_by(ReguliNotificareProiect.tip_eveniment).all()
    return render_template('contracte/reguli_notificare_lista.html',
                           proiect=proiect, reguli=reguli)


@contracte_bp.route('/proiect/<int:proiect_id>/reguli-notificare/nou',
                    methods=['GET', 'POST'])
@login_required
def regula_notificare_nou(proiect_id):
    proiect = Proiect.query.get_or_404(proiect_id)
    form = ReguliNotificareForm()
    if form.validate_on_submit():
        # Verific unicitate (proiect_id, tip_eveniment)
        existing = ReguliNotificareProiect.query.filter_by(
            proiect_id=proiect_id, tip_eveniment=form.tip_eveniment.data
        ).first()
        if existing:
            flash(f'Exista deja o regula pentru "{form.tip_eveniment.data}" '
                  'pe acest proiect. Editeaz-o in loc.', 'warning')
            return redirect(url_for('contracte.regula_notificare_editeaza',
                                     id=existing.id))
        try:
            r = ReguliNotificareProiect(
                proiect_id=proiect_id,
                tip_eveniment=form.tip_eveniment.data,
                zile_anticipare=form.zile_anticipare.data,
                in_app_activ=bool(form.in_app_activ.data),
                email_activ=bool(form.email_activ.data),
                creat_de_id=current_user.id,
            )
            r.email_destinatari = parse_emails_text(
                form.email_destinatari_text.data or ''
            )
            db.session.add(r)
            db.session.flush()
            audit_svc.log_create('reguli_notificare_proiect', r.id, new_values={
                'proiect_id': proiect_id, 'tip_eveniment': r.tip_eveniment,
                'in_app': r.in_app_activ, 'email': r.email_activ,
            })
            db.session.commit()
            flash(f'Regula creata pentru evenimentul "{r.tip_eveniment}".',
                  'success')
            return redirect(url_for('contracte.reguli_notificare_lista',
                                     proiect_id=proiect_id))
        except Exception as e:
            db.session.rollback()
            flash(f'Eroare salvare: {e}', 'danger')
    return render_template('contracte/reguli_notificare_formular.html',
                           form=form, proiect=proiect, regula=None)


@contracte_bp.route('/regula-notificare/<int:id>/editeaza',
                    methods=['GET', 'POST'])
@login_required
def regula_notificare_editeaza(id):
    r = ReguliNotificareProiect.query.get_or_404(id)
    form = ReguliNotificareForm(obj=r)
    if request.method == 'GET':
        form.regula_id.data = r.id
        form.email_destinatari_text.data = format_emails_text(r.email_destinatari)

    if form.validate_on_submit():
        try:
            audit_fields = ['tip_eveniment', 'zile_anticipare', 'in_app_activ',
                            'email_activ']
            before = audit_svc.snapshot(r, audit_fields)
            r.tip_eveniment = form.tip_eveniment.data
            r.zile_anticipare = form.zile_anticipare.data
            r.in_app_activ = bool(form.in_app_activ.data)
            r.email_activ = bool(form.email_activ.data)
            r.email_destinatari = parse_emails_text(
                form.email_destinatari_text.data or ''
            )
            audit_svc.log_update('reguli_notificare_proiect', r.id, before,
                                 audit_svc.snapshot(r, audit_fields))
            db.session.commit()
            flash('Regula actualizata.', 'success')
            return redirect(url_for('contracte.reguli_notificare_lista',
                                     proiect_id=r.proiect_id))
        except Exception as e:
            db.session.rollback()
            flash(f'Eroare salvare: {e}', 'danger')
    return render_template('contracte/reguli_notificare_formular.html',
                           form=form, proiect=r.proiect, regula=r)


@contracte_bp.route('/regula-notificare/<int:id>/sterge', methods=['POST'])
@login_required
def regula_notificare_sterge(id):
    r = ReguliNotificareProiect.query.get_or_404(id)
    proiect_id = r.proiect_id
    try:
        audit_svc.log_delete('reguli_notificare_proiect', r.id, old_values={
            'proiect_id': proiect_id, 'tip_eveniment': r.tip_eveniment,
        })
        db.session.delete(r)
        db.session.commit()
        flash('Regula stearsa.', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Eroare: {e}', 'danger')
    return redirect(url_for('contracte.reguli_notificare_lista',
                             proiect_id=proiect_id))


# ============================================================
# AUTO-PRICING DEVIZE (distribuire total global pe pozitii BoQ)
# ============================================================

@contracte_bp.route('/oferta/<int:oferta_id>/pricing/preview')
@login_required
def oferta_pricing_preview(oferta_id):
    """JSON dry-run clasificare (distributie categorii + Diverse) - fara persist."""
    oferta = OfertaContract.query.get_or_404(oferta_id)
    rez = deviz_pricing.dry_run_clasificare(oferta)
    return jsonify(rez)


@contracte_bp.route('/oferta/<int:oferta_id>/pricing', methods=['GET', 'POST'])
@login_required
def oferta_pricing(oferta_id):
    """
    Wizard auto-pricing: clasifica pozitiile + distribuie un total global
    fara TVA, ponderat (cantitate x tarif x factor). Σ pozitii == total.
    """
    oferta = OfertaContract.query.get_or_404(oferta_id)
    contract = oferta.contract
    # Asigur tarife default seed-uite
    if TarifCategorie.query.filter_by(proiect_id=None).count() == 0:
        deviz_pricing.seed_tarife_default()

    if request.method == 'POST':
        try:
            total_global = Decimal(str(request.form.get('total_global', '0')).replace(',', '.'))
            procent_material = Decimal(str(request.form.get('procent_material', '65')).replace(',', '.')) / 100
            seed = request.form.get('seed', type=int) or 42
            if total_global <= 0:
                flash('Totalul global trebuie sa fie pozitiv.', 'danger')
                return redirect(url_for('contracte.oferta_pricing', oferta_id=oferta.id))

            tarife = deviz_pricing.get_tarife_efective(oferta.proiect_id)
            stats = deviz_pricing.aplica_pricing(
                oferta, total_global, tarife=tarife,
                procent_material=procent_material, seed=seed,
            )
            audit_svc.log_update('oferta_contract', oferta.id,
                                 {'pricing': 'before'},
                                 {'pricing': 'applied', 'total': str(total_global),
                                  'pozitii': stats.get('pozitii_pretuite', 0)})
            db.session.commit()
            flash(
                f'Pricing aplicat: {stats["pozitii_pretuite"]} pozitii pretuite, '
                f'total {total_global:,.2f} RON fara TVA '
                f'(diferenta reconciliere: {stats["diferenta"]:.2f}).',
                'success',
            )
            return redirect(url_for('contracte.oferta_detalii', oferta_id=oferta.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Eroare la pricing: {e}', 'danger')

    # GET: dry-run + total sugerat
    dry = deviz_pricing.dry_run_clasificare(oferta)
    tarife = deviz_pricing.get_tarife_efective(oferta.proiect_id)
    total_sug = deviz_pricing.total_sugerat(oferta, tarife)
    return render_template(
        'contracte/oferta_pricing.html',
        oferta=oferta, contract=contract, dry=dry,
        total_sugerat=total_sug,
    )


@contracte_bp.route('/proiect/<int:proiect_id>/tarife')
@login_required
def tarife_lista(proiect_id):
    """Matrice editabila tarife per disciplina (global default + override proiect)."""
    proiect = Proiect.query.get_or_404(proiect_id)
    if TarifCategorie.query.filter_by(proiect_id=None).count() == 0:
        deviz_pricing.seed_tarife_default()
    # Tarife efective: global default + override proiect, grupate pe disciplina
    tarife = TarifCategorie.query.filter(
        db.or_(TarifCategorie.proiect_id.is_(None),
               TarifCategorie.proiect_id == proiect_id)
    ).order_by(TarifCategorie.disciplina, TarifCategorie.categorie_lucrare).all()
    # Override-urile proiectului (set de chei (disc, cat))
    overrides = {
        (t.disciplina, t.categorie_lucrare)
        for t in tarife if t.proiect_id == proiect_id
    }
    # Construiesc lista efectiva: override are prioritate
    efective = {}
    for t in tarife:
        key = (t.disciplina, t.categorie_lucrare)
        if t.proiect_id == proiect_id:
            efective[key] = t  # override
        elif key not in efective:
            efective[key] = t  # global (doar daca nu exista override)
    # Grupez pe disciplina
    grupat = {}
    for (disc, cat), t in sorted(efective.items()):
        grupat.setdefault(disc, []).append({
            'categorie': cat, 'tarif': t.tarif_baza,
            'este_override': (disc, cat) in overrides,
        })
    return render_template('contracte/tarife_lista.html',
                           proiect=proiect, grupat=grupat,
                           discipline=dict(TarifCategorie.DISCIPLINE))


@contracte_bp.route('/proiect/<int:proiect_id>/tarife/salveaza', methods=['POST'])
@login_required
def tarife_salveaza(proiect_id):
    """Bulk save tarife override per proiect (chei: tarif_<disc>__<cat>)."""
    proiect = Proiect.query.get_or_404(proiect_id)
    count = 0
    for key, raw in request.form.items():
        if not key.startswith('tarif_'):
            continue
        if not raw or not str(raw).strip():
            continue
        try:
            disc_cat = key[len('tarif_'):]
            disc, cat = disc_cat.split('__', 1)
            val = Decimal(str(raw).strip().replace(',', '.'))
        except (ValueError, TypeError):
            continue
        if val < 0:
            continue
        # Upsert override pe proiect
        t = TarifCategorie.query.filter_by(
            proiect_id=proiect_id, disciplina=disc, categorie_lucrare=cat
        ).first()
        if t is None:
            t = TarifCategorie(proiect_id=proiect_id, disciplina=disc,
                               categorie_lucrare=cat, tarif_baza=val,
                               creat_de_id=current_user.id)
            db.session.add(t)
        else:
            t.tarif_baza = val
        count += 1
    db.session.commit()
    flash(f'{count} tarife salvate pentru acest proiect.', 'success')
    return redirect(url_for('contracte.tarife_lista', proiect_id=proiect_id))


# ============================================================
# CLASIFICARE PROIECT + CENTRALIZATOR + DEVIZ GENERAL
# ============================================================

@contracte_bp.route('/proiect/<int:proiect_id>/clasifica-oferte', methods=['POST'])
@login_required
def clasifica_oferte_proiect(proiect_id):
    """Clasifica toate ofertele proiectului (bulk). Protejeaza editarile manuale."""
    proiect = Proiect.query.get_or_404(proiect_id)
    # doar_neclasificate din form (default True - nu suprascrie manualul)
    forteaza = request.form.get('forteaza') == '1'
    try:
        raport = centralizator.clasifica_proiect(
            proiect.id, doar_neclasificate=not forteaza)
        audit_svc.log('classify', 'proiect', proiect.id, new_values={
            'oferte': raport['oferte'], 'pozitii': raport['pozitii'],
            'forteaza': forteaza,
        }, commit=True)
        flash(
            f'Clasificare completa: {raport["oferte"]} oferte, '
            f'{raport["pozitii"]} pozitii. '
            f'{len(raport["distributie"])} categorii distincte.',
            'success',
        )
    except Exception as e:
        db.session.rollback()
        flash(f'Eroare la clasificare: {e}', 'danger')
    return redirect(url_for('contracte.centralizator_proiect', proiect_id=proiect.id))


@contracte_bp.route('/oferta/<int:oferta_id>/clasificare-manuala', methods=['GET', 'POST'])
@login_required
def clasificare_manuala(oferta_id):
    """Matrice editabila categorie_lucrare per pozitie (override manual)."""
    oferta = OfertaContract.query.get_or_404(oferta_id)
    doar_diverse = request.args.get('doar_diverse') == '1'

    if request.method == 'POST':
        categorii = parse_bulk_categorii(request.form)
        modificate = 0
        for pid, cat in categorii.items():
            pz = PozitieBoQ.query.filter_by(id=pid, oferta_id=oferta.id).first()
            if pz is None:
                continue
            if (pz.categorie_lucrare or '') != cat:
                pz.categorie_lucrare = cat
                modificate += 1
        if modificate:
            db.session.commit()
        flash(f'{modificate} pozitii reclasificate manual.', 'success')
        return redirect(url_for('contracte.clasificare_manuala',
                                oferta_id=oferta.id, doar_diverse=request.args.get('doar_diverse', '')))

    query = PozitieBoQ.query.filter_by(oferta_id=oferta.id)
    if doar_diverse:
        query = query.filter(
            db.or_(
                PozitieBoQ.categorie_lucrare.is_(None),
                PozitieBoQ.categorie_lucrare.like('diverse%'),
                PozitieBoQ.categorie_lucrare == 'neclasificat',
            )
        )
    pozitii = query.order_by(PozitieBoQ.ordine).all()
    return render_template(
        'contracte/clasificare_manuala.html',
        oferta=oferta, pozitii=pozitii, doar_diverse=doar_diverse,
        categorii_disponibile=deviz_pricing.toate_categoriile_flat(),
    )


@contracte_bp.route('/proiect/<int:proiect_id>/centralizator')
@login_required
def centralizator_proiect(proiect_id):
    """Centralizator: agregare toate ofertele pe disciplina -> categorie."""
    proiect = Proiect.query.get_or_404(proiect_id)
    data = centralizator.genereaza_centralizator(proiect.id)
    dry = centralizator.dry_run_proiect(proiect.id)
    return render_template(
        'contracte/centralizator.html',
        proiect=proiect, data=data, dry=dry,
    )


@contracte_bp.route('/proiect/<int:proiect_id>/centralizator/export')
@login_required
def centralizator_export(proiect_id):
    from flask import send_file
    try:
        path = centralizator.export_centralizator_xlsx(proiect_id)
    except Exception as e:
        flash(f'Eroare export: {e}', 'danger')
        return redirect(url_for('contracte.centralizator_proiect', proiect_id=proiect_id))
    return send_file(path, as_attachment=True, download_name=os.path.basename(path),
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@contracte_bp.route('/proiect/<int:proiect_id>/deviz-general')
@login_required
def deviz_general_proiect(proiect_id):
    """Deviz General: consolidare pe capitole HG907/2016 + TVA."""
    proiect = Proiect.query.get_or_404(proiect_id)
    cota = request.args.get('cota_tva', type=float) or 21
    data = centralizator.genereaza_deviz_general(proiect.id, cota_tva=cota)
    return render_template(
        'contracte/deviz_general.html',
        proiect=proiect, data=data, cota_tva=cota,
    )


@contracte_bp.route('/proiect/<int:proiect_id>/deviz-general/export')
@login_required
def deviz_general_export(proiect_id):
    from flask import send_file
    cota = request.args.get('cota_tva', type=float) or 21
    try:
        path = centralizator.export_deviz_general_xlsx(proiect_id, cota_tva=cota)
    except Exception as e:
        flash(f'Eroare export: {e}', 'danger')
        return redirect(url_for('contracte.deviz_general_proiect', proiect_id=proiect_id))
    return send_file(path, as_attachment=True, download_name=os.path.basename(path),
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
