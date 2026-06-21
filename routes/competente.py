"""
Rute pentru modulul Competente (skill matrix + matching).

Inlocuieste pe termen lung campul text liber `Angajat.specializari` cu un
nomenclator de competente structurate + atribuiri pe angajat (nivel, valabilitate).

Tot modulul e gated pe feature flag 'competente' (default OFF). Cu flag-ul OFF
toate rutele intorc 404 (zero impact, exact ca concedii / banca_preturi).

Rute:
- /competente/                          nomenclator (lista competente)
- /competente/nou, /competente/<id>/editeaza   CRUD nomenclator
- /competente/<id>/sterge               dezactiveaza (soft) competenta
- /competente/matching                  potrivire angajati pe CategorieActivitate
- /angajati/<id>/competente/...         atribuire / editare / stergere pe angajat
  (montate tot in acest blueprint, sub /angajati/<id>/competente)
"""

from datetime import date

from flask import (
    Blueprint, render_template, redirect, url_for, flash,
    request, abort
)
from flask_login import login_required, current_user

from models import (
    db, Angajat, Competenta, AngajatCompetenta, CategorieActivitate,
)
from forms.competente_forms import CompetentaForm, AtribuireCompetentaForm
from services.feature_flags import is_enabled
from services import competente as competente_srv

competente_bp = Blueprint('competente', __name__, url_prefix='/competente')


@competente_bp.before_request
def _gate():
    """Tot modulul e ascuns cat timp flag-ul 'competente' e OFF."""
    if not is_enabled('competente'):
        abort(404)


def _poate_administra() -> bool:
    """Doar managerii (admin/manager) pot edita nomenclatorul si atribuirile."""
    return current_user.is_authenticated and current_user.is_manager


# ============================================================
# NOMENCLATOR COMPETENTE - lista
# ============================================================

@competente_bp.route('/')
@login_required
def lista():
    categorie = request.args.get('categorie', '').strip()
    arata_inactive = request.args.get('inactive', '') == '1'

    query = Competenta.query
    if categorie:
        query = query.filter(Competenta.categorie == categorie)
    if not arata_inactive:
        query = query.filter(Competenta.activ.is_(True))

    competente = query.order_by(Competenta.categorie, Competenta.nume).all()

    # Categorii distincte pentru filtru
    categorii = [
        c[0] for c in db.session.query(Competenta.categorie)
        .filter(Competenta.categorie.isnot(None))
        .distinct().order_by(Competenta.categorie).all()
        if c[0]
    ]

    return render_template('competente/lista.html',
                           competente=competente,
                           categorii=categorii,
                           categorie_filtru=categorie,
                           arata_inactive=arata_inactive,
                           poate_administra=_poate_administra())


# ============================================================
# NOMENCLATOR COMPETENTE - creare
# ============================================================

@competente_bp.route('/nou', methods=['GET', 'POST'])
@login_required
def nou():
    if not _poate_administra():
        flash('Nu aveti permisiunea de a adauga competente.', 'danger')
        return redirect(url_for('competente.lista'))

    form = CompetentaForm()
    if form.validate_on_submit():
        comp = Competenta(
            nume=form.nume.data.strip(),
            categorie=form.categorie.data.strip() if form.categorie.data else None,
            descriere=form.descriere.data.strip() if form.descriere.data else None,
            necesita_certificare=bool(form.necesita_certificare.data),
            valabilitate_luni=form.valabilitate_luni.data,
            activ=bool(form.activ.data),
        )
        db.session.add(comp)
        db.session.commit()
        flash(f'Competenta "{comp.nume}" a fost adaugata.', 'success')
        return redirect(url_for('competente.lista'))

    return render_template('competente/formular.html', form=form, competenta=None)


# ============================================================
# NOMENCLATOR COMPETENTE - editare
# ============================================================

@competente_bp.route('/<int:id>/editeaza', methods=['GET', 'POST'])
@login_required
def editeaza(id):
    if not _poate_administra():
        flash('Nu aveti permisiunea de a edita competente.', 'danger')
        return redirect(url_for('competente.lista'))

    comp = Competenta.query.get_or_404(id)
    form = CompetentaForm(obj=comp)
    if form.validate_on_submit():
        comp.nume = form.nume.data.strip()
        comp.categorie = form.categorie.data.strip() if form.categorie.data else None
        comp.descriere = form.descriere.data.strip() if form.descriere.data else None
        comp.necesita_certificare = bool(form.necesita_certificare.data)
        comp.valabilitate_luni = form.valabilitate_luni.data
        comp.activ = bool(form.activ.data)
        db.session.commit()
        flash(f'Competenta "{comp.nume}" a fost actualizata.', 'success')
        return redirect(url_for('competente.lista'))

    return render_template('competente/formular.html', form=form, competenta=comp)


# ============================================================
# NOMENCLATOR COMPETENTE - dezactivare (soft delete)
# ============================================================

@competente_bp.route('/<int:id>/sterge', methods=['POST'])
@login_required
def sterge(id):
    if not _poate_administra():
        flash('Nu aveti permisiunea de a sterge competente.', 'danger')
        return redirect(url_for('competente.lista'))

    comp = Competenta.query.get_or_404(id)
    # Soft delete: pastram istoricul atribuirilor; doar dezactivam.
    comp.activ = False
    db.session.commit()
    flash(f'Competenta "{comp.nume}" a fost dezactivata. '
          'Atribuirile existente raman in istoric.', 'warning')
    return redirect(url_for('competente.lista'))


# ============================================================
# MATCHING - angajati potriviti pentru o categorie de activitate
# ============================================================

@competente_bp.route('/matching')
@login_required
def matching():
    categorie_id = request.args.get('categorie_activitate_id', 0, type=int)

    categorii = (
        CategorieActivitate.query.filter_by(activa=True)
        .order_by(CategorieActivitate.ordine, CategorieActivitate.denumire)
        .all()
    )

    categorie = None
    rezultate = []
    if categorie_id:
        categorie = CategorieActivitate.query.get(categorie_id)
        if categorie:
            rezultate = competente_srv.angajati_pentru_categorie(categorie)

    return render_template('competente/matching.html',
                           categorii=categorii,
                           categorie=categorie,
                           categorie_id=categorie_id,
                           rezultate=rezultate)


# ============================================================
# ATRIBUIRE COMPETENTA PE ANGAJAT
# ============================================================

@competente_bp.route('/angajat/<int:angajat_id>/adauga', methods=['GET', 'POST'])
@login_required
def atribuie(angajat_id):
    if not _poate_administra():
        flash('Nu aveti permisiunea de a atribui competente.', 'danger')
        return redirect(url_for('angajati.detalii', id=angajat_id))

    angajat = Angajat.query.get_or_404(angajat_id)
    form = AtribuireCompetentaForm()

    if form.validate_on_submit():
        # Index unic (angajat, competenta): daca exista deja, o actualizam.
        existent = AngajatCompetenta.query.filter_by(
            angajat_id=angajat_id, competenta_id=form.competenta_id.data
        ).first()
        if existent:
            existent.nivel = form.nivel.data
            existent.data_obtinere = form.data_obtinere.data
            existent.data_expirare = form.data_expirare.data
            existent.observatii = form.observatii.data.strip() if form.observatii.data else None
            db.session.commit()
            flash('Competenta era deja atribuita - am actualizat-o.', 'success')
        else:
            ac = AngajatCompetenta(
                angajat_id=angajat_id,
                competenta_id=form.competenta_id.data,
                nivel=form.nivel.data,
                data_obtinere=form.data_obtinere.data,
                data_expirare=form.data_expirare.data,
                observatii=form.observatii.data.strip() if form.observatii.data else None,
            )
            db.session.add(ac)
            db.session.commit()
            flash('Competenta a fost atribuita angajatului.', 'success')
        return redirect(url_for('angajati.detalii', id=angajat_id) + '#tab-competente')

    return render_template('competente/atribuire.html',
                           form=form, angajat=angajat, atribuire=None)


@competente_bp.route('/atribuire/<int:id>/editeaza', methods=['GET', 'POST'])
@login_required
def editeaza_atribuire(id):
    ac = AngajatCompetenta.query.get_or_404(id)
    if not _poate_administra():
        flash('Nu aveti permisiunea de a edita atribuiri.', 'danger')
        return redirect(url_for('angajati.detalii', id=ac.angajat_id))

    angajat = Angajat.query.get_or_404(ac.angajat_id)
    form = AtribuireCompetentaForm(obj=ac)
    if request.method == 'GET':
        form.competenta_id.data = ac.competenta_id

    if form.validate_on_submit():
        # Daca s-a schimbat competenta, evita coliziunea cu index-ul unic.
        if form.competenta_id.data != ac.competenta_id:
            coliziune = AngajatCompetenta.query.filter_by(
                angajat_id=ac.angajat_id, competenta_id=form.competenta_id.data
            ).first()
            if coliziune and coliziune.id != ac.id:
                flash('Angajatul are deja aceasta competenta atribuita.', 'warning')
                return render_template('competente/atribuire.html',
                                       form=form, angajat=angajat, atribuire=ac)
        ac.competenta_id = form.competenta_id.data
        ac.nivel = form.nivel.data
        ac.data_obtinere = form.data_obtinere.data
        ac.data_expirare = form.data_expirare.data
        ac.observatii = form.observatii.data.strip() if form.observatii.data else None
        db.session.commit()
        flash('Atribuirea a fost actualizata.', 'success')
        return redirect(url_for('angajati.detalii', id=ac.angajat_id) + '#tab-competente')

    return render_template('competente/atribuire.html',
                           form=form, angajat=angajat, atribuire=ac)


@competente_bp.route('/atribuire/<int:id>/sterge', methods=['POST'])
@login_required
def sterge_atribuire(id):
    ac = AngajatCompetenta.query.get_or_404(id)
    if not _poate_administra():
        flash('Nu aveti permisiunea de a sterge atribuiri.', 'danger')
        return redirect(url_for('angajati.detalii', id=ac.angajat_id))

    angajat_id = ac.angajat_id
    db.session.delete(ac)
    db.session.commit()
    flash('Competenta a fost retrasa de la angajat.', 'warning')
    return redirect(url_for('angajati.detalii', id=angajat_id) + '#tab-competente')
