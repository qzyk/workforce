"""
Teste unit pentru DS faza 4 — verificari pe continut de fisiere (fara Flask):
  - service worker-ul a fost bumpat la versiune noua (v5)
  - manifestul PWA contine shortcut catre /teren
  - components.css defineste grila de KPI (.ed-stat-grid) si bottom-bar-ul mobil
    (.ed-bottombar) cu CTA central si activare doar sub 768px
  - dashboard-ul nu mai contine indigo/portocaliu hardcodat (paleta gold/navy)
  - strict aditiv: clasele vechi din components.css raman definite
"""
import json
from pathlib import Path

RADACINA = Path(__file__).resolve().parents[2]
SW = RADACINA / 'static' / 'sw.js'
MANIFEST = RADACINA / 'static' / 'manifest.webmanifest'
COMPONENTS = RADACINA / 'static' / 'css' / 'components.css'
DASHBOARD = RADACINA / 'templates' / 'dashboard.html'
BASE = RADACINA / 'templates' / 'base.html'


def test_sw_bumpat_la_v5():
    continut = SW.read_text(encoding='utf-8')
    assert "'edifico-v5'" in continut, 'sw.js trebuie bumpat la edifico-v5 (DS faza 4)'
    assert "'edifico-v4'" not in continut, 'versiunea veche edifico-v4 nu mai trebuie sa fie activa'


def test_manifest_are_shortcut_teren():
    date = json.loads(MANIFEST.read_text(encoding='utf-8'))
    urls = [s.get('url') for s in date.get('shortcuts', [])]
    assert '/teren' in urls, 'manifestul PWA trebuie sa aiba un shortcut catre /teren'
    # shortcuturile vechi raman (strict aditiv)
    assert '/bim/' in urls
    assert '/activitati' in urls


def test_components_are_stat_grid():
    continut = COMPONENTS.read_text(encoding='utf-8')
    assert '.ed-stat-grid' in continut, 'lipseste grila de KPI .ed-stat-grid'
    # grila e responsiva (auto-fit)
    bloc = continut[continut.find('.ed-stat-grid'):continut.find('.ed-stat-grid') + 250]
    assert 'auto-fit' in bloc


def test_components_are_bottombar_doar_pe_mobil():
    continut = COMPONENTS.read_text(encoding='utf-8')
    assert '.ed-bottombar' in continut, 'lipseste bottom-bar-ul mobil .ed-bottombar'
    # ascuns pe desktop: regula de baza .ed-bottombar { display: none; }
    idx = continut.find('.ed-bottombar { display: none; }')
    assert idx != -1, 'bottom-bar trebuie ascuns implicit (display:none) pe desktop'
    # vizibil doar in media query sub 768px
    mq = continut[continut.find('@media (max-width: 768px)', idx):]
    assert '.ed-bottombar {' in mq and 'display: flex' in mq, (
        'bottom-bar trebuie sa devina vizibil (flex) doar sub 768px'
    )
    # CTA central evidentiat
    assert '.ed-bottombar__item--cta' in continut


def test_components_pastreaza_clasele_vechi_ds():
    # strict aditiv: componentele din fazele anterioare raman
    continut = COMPONENTS.read_text(encoding='utf-8')
    for clasa in ('.ed-btn', '.ed-card', '.ed-stat', '.ed-table', '.ed-badge', '.ed-empty'):
        assert clasa in continut, f'clasa DS {clasa} a disparut din components.css'


def test_base_html_are_bottombar_cu_link_teren():
    continut = BASE.read_text(encoding='utf-8')
    assert 'ed-bottombar' in continut, 'base.html nu randeaza bottom-bar-ul mobil'
    assert "url_for('teren.index')" in continut, 'CTA-ul din bottom-bar trebuie sa duca la teren.index'


def test_dashboard_paleta_brand_nu_indigo():
    continut = DASHBOARD.read_text(encoding='utf-8')
    assert '#1a237e' not in continut, 'dashboard-ul mai contine indigo hardcodat (#1a237e)'
    assert '#f57c00' not in continut, 'dashboard-ul mai contine portocaliu hardcodat (#f57c00)'
    # paleta brandului (navy + gold) prezenta in scriptul de grafice
    assert '#0B1426' in continut
    assert '#C9A961' in continut


def test_dashboard_kpi_sunt_macro_stat_card():
    # KPI-urile folosesc macro-ul ed.stat_card cu url (clickabile), nu .stat-card vechi
    continut = DASHBOARD.read_text(encoding='utf-8')
    assert 'ed.stat_card' in continut
    assert continut.count('ed.stat_card') >= 4
    assert 'ed-stat-grid' in continut
    # nu mai folosim vechea grila / card indigo
    assert 'class="stat-card' not in continut


# ============================================================
# Fixuri de review DS faza 4 (verificari pe sursa de fisier)
# ============================================================

# Toate template-urile migrate in DS faza 4 (cele acuzate de review).
_TEMPLATE_MIGRATE = [
    'dashboard.html', 'dashboard_executiv.html',
    'angajati/lista.html', 'proiecte/lista.html', 'proiecte/detalii.html',
    'pontaje/lista.html', 'pontaje/aprobare.html', 'pontaje/panou.html',
]
_TEMPLATES = RADACINA / 'templates'


def test_fara_artefacte_tool_call_in_template_uri():
    """
    Finding #4: niciun template nu mai contine resturi de tool-call
    (</content>, </invoke>, </parameter>, ...).
    """
    import re
    rx = re.compile(r'</?(content|invoke|parameter|antml)\b')
    vinovati = []
    for f in _TEMPLATES.rglob('*.html'):
        if rx.search(f.read_text(encoding='utf-8')):
            vinovati.append(str(f.relative_to(RADACINA)))
    assert not vinovati, f'artefacte de tool-call ramase in: {vinovati}'


def test_dashboard_se_termina_la_endblock():
    """Finding #4: dashboard-urile se termina curat la {% endblock %}."""
    for nume in ('dashboard.html', 'dashboard_executiv.html'):
        continut = (_TEMPLATES / nume).read_text(encoding='utf-8').rstrip()
        assert continut.endswith('{% endblock %}'), (
            f'{nume} nu se termina la endblock (junk dupa bloc?)')


def test_doc_expirate_kpi_pointer_corect_in_sursa():
    """
    Finding #1 (sursa): cardul KPI Doc. Expirate foloseste documente.expirate,
    nu documente.lista cu status=expirat.
    """
    continut = DASHBOARD.read_text(encoding='utf-8')
    assert "url_for('documente.expirate')" in continut
    # nu mai exista linkul gresit (lista filtrata post-paginare) pe cardul KPI
    assert "url_for('documente.lista', status='expirat')" not in continut


def test_butoane_icon_only_au_aria_label_in_sursa():
    """
    Finding #2 (sursa): orice apel ed.btn cu title= are si aria_label= (nume
    accesibil sigur pentru screen reader), in toate template-urile migrate.
    """
    import re
    rx_btn = re.compile(r'ed\.btn\([^\n]*?title=')
    fara_aria = []
    for nume in _TEMPLATE_MIGRATE:
        continut = (_TEMPLATES / nume).read_text(encoding='utf-8')
        for linie in continut.splitlines():
            if rx_btn.search(linie) and 'aria_label=' not in linie:
                fara_aria.append(f'{nume}: {linie.strip()}')
    assert not fara_aria, (
        'butoane icon-only cu title dar fara aria_label: ' + '; '.join(fara_aria))


def test_macro_btn_suporta_aria_label():
    """Finding #2 (macro): _components.btn accepta parametrul aria_label."""
    comp = (_TEMPLATES / '_components.html').read_text(encoding='utf-8')
    assert 'aria_label' in comp, 'macro-ul btn trebuie sa expuna parametrul aria_label'
