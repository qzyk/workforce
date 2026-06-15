"""
Validator IDS (Information Delivery Specification) pentru BIM.

Faza 5a. Governance de livrare informationala ISO 19650 / buildingSMART IDS.
Oglindeste services/bim_rules.py (rule engine), dar in loc de model checking
geometric / de denumire, verifica CONFORMITATEA INFORMATIONALA: pe o faza de
livrare (proiectare / executie / predare), elementele relevante au Property
Sets-urile CERUTE (populate in Faza 2 in ElementBIM.proprietati_json) cu
valorile / tiparele asteptate?

Schema definitie_json a unei IDS spec (simpla, documentata):
    {
      "clase_ifc": ["wall", "door"],         # tip_element-uri vizate (gol -> toate)
      "proprietati_cerute": [
        {"pset": "Pset_WallCommon", "nume": "FireRating",
         "obligatoriu": true, "valoare": "REI 120"},
        {"pset": "Pset_WallCommon", "nume": "IsExternal", "obligatoriu": true},
        {"nume": "LoadBearing", "tipar": "^(true|false)$"}   # pset optional
      ]
    }
  - 'obligatoriu' default True.
  - 'valoare' (optional): cere egalitate exacta (string-comparat, case-insensitive).
  - 'tipar' (optional): regex care trebuie sa se potriveasca pe valoare.
  - daca 'pset' lipseste, cautam proprietatea in ORICE pset.
  - daca nici 'valoare' nici 'tipar' nu e dat -> verificam doar PREZENTA (non-empty).

ONESTITATE (lectie din fazele anterioare): un element fara proprietati_json
(model neimportat cu Faza 2, sau flag-ul 'bim-pset-extraction' OFF) NU trece
fals - genereaza o violare 'lipsa date'. Nu declaram conform ceva ce nu putem
verifica.

Engine-ul ruleaza o spec pe un scop (santier / cladire / toate elementele) si
insereaza BIMIDSViolation-uri intr-un singur run (run_id = UUID).
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime
from typing import Any, Optional

from models import db, BIMIDSSpec, BIMIDSViolation, ElementBIM
# Reutilizam helperul de parsare proprietati_json din rule engine (NU duplicam).
from services.bim_rules import _get_element_props
from services import audit as audit_svc


_logger = logging.getLogger(__name__)


# ====================================================
# UTILITARE
# ====================================================

def _select_elements(spec: BIMIDSSpec, definition: dict,
                     scope: Optional[dict] = None) -> list[ElementBIM]:
    """
    Selecteaza elementele vizate de spec: filtreaza pe clasele IFC cerute
    (tip_element) si pe scope-ul optional (santier_id / cladire_id).

    Daca 'clase_ifc' lipseste / e gol -> vizam TOATE elementele din scope.
    """
    clase = definition.get('clase_ifc') or []
    q = ElementBIM.query
    if clase:
        q = q.filter(ElementBIM.tip_element.in_(clase))

    if scope:
        if scope.get('cladire_id'):
            q = q.filter(ElementBIM.cladire_id == scope['cladire_id'])
        if scope.get('santier_id'):
            from models import Cladire
            cladiri_ids = [c.id for c in Cladire.query.filter_by(
                santier_id=scope['santier_id']).all()]
            if cladiri_ids:
                q = q.filter(ElementBIM.cladire_id.in_(cladiri_ids))
            else:
                return []  # niciun cladire pe santier -> niciun element

    return q.all()


def _gaseste_valoare(props: dict, pset: Optional[str], nume: str) -> tuple[bool, Any]:
    """
    Cauta valoarea unei proprietati in proprietati_json nested ({pset: {prop: val}}).

    Returneaza (gasit, valoare). Daca 'pset' e dat, cautam doar in acel pset;
    altfel cautam in oricare pset. 'gasit' e True chiar daca valoarea e None/''
    (proprietatea exista, dar e goala) - apelantul decide ce inseamna "non-empty".
    """
    if not isinstance(props, dict):
        return (False, None)

    if pset:
        bloc = props.get(pset)
        if isinstance(bloc, dict) and nume in bloc:
            return (True, bloc[nume])
        return (False, None)

    # Fara pset specificat: cautam proprietatea in orice pset (dict nested),
    # apoi ca fallback in cheile top-level (compat cu formatul plat eventual).
    for _pset_nume, bloc in props.items():
        if isinstance(bloc, dict) and nume in bloc:
            return (True, bloc[nume])
    if nume in props and not isinstance(props.get(nume), dict):
        return (True, props.get(nume))
    return (False, None)


def _val_goala(valoare: Any) -> bool:
    """True daca valoarea proprietatii e considerata 'goala' (lipsa efectiva)."""
    if valoare is None:
        return True
    if isinstance(valoare, str) and valoare.strip() == '':
        return True
    return False


# ====================================================
# EVALUARE PER ELEMENT
# ====================================================

def _evalueaza_element(spec: BIMIDSSpec, el: ElementBIM,
                       cerinte: list[dict], severitate: str) -> list[dict]:
    """
    Verifica un element fata de lista de proprietati cerute a unei IDS spec.

    Returneaza lista de dict-uri violare (analog cu evaluatoarele din bim_rules).
    Element fara proprietati_json -> O SINGURA violare 'lipsa date' ONESTA
    (nu il declaram conform si nu generam zgomot pe fiecare proprietate).
    """
    violations: list[dict] = []

    # ONEST: element fara Property Sets (Faza 2 neaplicata / flag OFF) -> nu putem
    # verifica nimic. Violare unica 'lipsa date', NU pass fals.
    if not el.proprietati_json:
        violations.append({
            'element_bim_id': el.id,
            'severitate': severitate,
            'mesaj': (f'{el.cod}: lipsa date - elementul nu are Property Sets '
                      f'(import fara extragere PSet / model neimportat).'),
            'detalii': {'status': 'lipsa_date', 'spec_id': spec.id,
                        'tip_element': el.tip_element},
        })
        return violations

    props = _get_element_props(el)

    for cerinta in cerinte:
        nume = cerinta.get('nume')
        if not nume:
            continue  # cerinta malformata -> ignorata defensiv
        pset = cerinta.get('pset')
        obligatoriu = cerinta.get('obligatoriu', True)
        valoare_ceruta = cerinta.get('valoare')
        tipar = cerinta.get('tipar')
        eticheta = f'{pset}.{nume}' if pset else nume

        gasit, valoare = _gaseste_valoare(props, pset, nume)

        # 1. Prezenta
        if not gasit or _val_goala(valoare):
            if obligatoriu:
                violations.append({
                    'element_bim_id': el.id,
                    'severitate': severitate,
                    'mesaj': f'{el.cod}: lipseste proprietatea ceruta {eticheta}.',
                    'detalii': {'status': 'lipsa_proprietate', 'spec_id': spec.id,
                                'pset': pset, 'proprietate': nume},
                })
            # daca nu e obligatorie si lipseste -> OK (skip restul verificarilor)
            continue

        # 2. Valoare exacta (string-comparat, case-insensitive)
        if valoare_ceruta is not None:
            if str(valoare).strip().lower() != str(valoare_ceruta).strip().lower():
                violations.append({
                    'element_bim_id': el.id,
                    'severitate': severitate,
                    'mesaj': (f'{el.cod}: {eticheta} = "{valoare}" '
                              f'difera de valoarea ceruta "{valoare_ceruta}".'),
                    'detalii': {'status': 'valoare_gresita', 'spec_id': spec.id,
                                'pset': pset, 'proprietate': nume,
                                'valoare': str(valoare),
                                'valoare_ceruta': str(valoare_ceruta)},
                })
                continue

        # 3. Tipar (regex) pe valoare
        if tipar:
            try:
                rgx = re.compile(tipar)
            except re.error as e:
                violations.append({
                    'element_bim_id': None,
                    'severitate': severitate,
                    'mesaj': f'Spec {spec.nume}: tipar invalid pentru {eticheta}: {e}',
                    'detalii': {'status': 'eroare_config', 'spec_id': spec.id,
                                'tipar': tipar},
                })
                continue
            if not rgx.match(str(valoare)):
                violations.append({
                    'element_bim_id': el.id,
                    'severitate': severitate,
                    'mesaj': (f'{el.cod}: {eticheta} = "{valoare}" '
                              f'nu respecta tiparul {tipar}.'),
                    'detalii': {'status': 'tipar_nepotrivit', 'spec_id': spec.id,
                                'pset': pset, 'proprietate': nume,
                                'valoare': str(valoare), 'tipar': tipar},
                })

    return violations


# ====================================================
# ENGINE PRINCIPAL
# ====================================================

def valideaza_spec(spec: BIMIDSSpec, scope: Optional[dict] = None,
                   user=None) -> dict:
    """
    Ruleaza o IDS spec pe un scop si insereaza BIMIDSViolation-uri in DB.

    scope (optional): {'santier_id': N} sau {'cladire_id': N} pentru a limita
    setul de elemente verificate. None -> toate elementele din clasele cerute.

    Returneaza:
        {
            'run_id': '...',
            'spec_id': spec.id,
            'total_elemente': N,
            'total_violations': M,
            'by_severitate': {'minora': ..., 'majora': ..., 'critica': ...},
            'by_status': {'lipsa_date': ..., 'lipsa_proprietate': ..., ...},
            'duration_ms': ...,
        }
    """
    run_id = str(uuid.uuid4())
    started = datetime.utcnow()

    definition = spec.get_definition()
    cerinte = definition.get('proprietati_cerute') or []
    severitate_default = definition.get('severitate', 'majora')

    elemente = _select_elements(spec, definition, scope)

    violations_data: list[dict] = []
    if cerinte:
        for el in elemente:
            violations_data.extend(
                _evalueaza_element(spec, el, cerinte, severitate_default)
            )
    else:
        # Spec fara proprietati cerute -> nimic de verificat (config gol).
        _logger.info('IDS spec %s nu are proprietati_cerute - nimic de validat.', spec.id)

    by_severitate = {'minora': 0, 'majora': 0, 'critica': 0}
    by_status: dict[str, int] = {}
    tenant_id = getattr(user, 'tenant_id', None) if user else None

    for vd in violations_data:
        sev = vd.get('severitate', severitate_default)
        violation = BIMIDSViolation(
            tenant_id=tenant_id,
            spec_id=spec.id,
            element_bim_id=vd.get('element_bim_id'),
            run_id=run_id,
            mesaj=vd['mesaj'][:500],
            severitate=sev,
            detalii_json=json.dumps(vd.get('detalii', {}), ensure_ascii=False),
            data_detectie=datetime.utcnow(),
        )
        db.session.add(violation)
        by_severitate[sev] = by_severitate.get(sev, 0) + 1
        st = (vd.get('detalii') or {}).get('status', 'altul')
        by_status[st] = by_status.get(st, 0) + 1

    db.session.commit()

    audit_svc.log(
        action='valideaza_ids',
        entity_type='bim_ids_spec',
        entity_id=spec.id,
        new_values={
            'run_id': run_id,
            'total_elemente': len(elemente),
            'total_violations': len(violations_data),
            'by_severitate': by_severitate,
            'by_status': by_status,
            'duration_ms': int((datetime.utcnow() - started).total_seconds() * 1000),
        },
        commit=True,
    )

    return {
        'run_id': run_id,
        'spec_id': spec.id,
        'total_elemente': len(elemente),
        'total_violations': len(violations_data),
        'by_severitate': by_severitate,
        'by_status': by_status,
        'duration_ms': int((datetime.utcnow() - started).total_seconds() * 1000),
    }


# ====================================================
# CRUD HELPERS
# ====================================================

def create_spec(nume: str, definition: dict, *, faza: str = 'proiectare',
                descriere: str = '', tenant_id: Optional[int] = None,
                user=None, commit: bool = True) -> BIMIDSSpec:
    """Creeaza o IDS spec noua."""
    if not nume or not nume.strip():
        raise ValueError('Numele IDS spec e obligatoriu.')
    spec = BIMIDSSpec(
        tenant_id=tenant_id,
        nume=nume.strip(),
        descriere=descriere,
        faza=faza or 'proiectare',
        definitie_json=json.dumps(definition, ensure_ascii=False),
        activ=True,
        creat_de_id=getattr(user, 'id', None) if user else None,
    )
    db.session.add(spec)
    db.session.flush()
    audit_svc.log_create('bim_ids_spec', spec.id,
                         new_values={'nume': spec.nume, 'faza': spec.faza})
    if commit:
        db.session.commit()
    return spec
