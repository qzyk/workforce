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

from datetime import date, datetime
from decimal import Decimal

from flask import (
    Blueprint, render_template, redirect, url_for, flash, request, abort,
)
from flask_login import login_required, current_user

from models import (
    db, Proiect, Contract, TermenContract, ProcesVerbal, Utilizator,
)
from forms.contract_forms import (
    ContractForm, TermenContractForm, ProcesVerbalForm,
    parse_participanti_text, format_participanti_text,
)
import services.audit as audit_svc
from services.feature_flags import is_enabled


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
