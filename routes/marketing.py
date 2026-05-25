"""
EDIFICO - Pagina de prezentare publica (marketing) la /home.

Surface-ul "dark editorial" din design system (Questrial + Noto Serif),
pagina standalone (NU extinde base.html, are propriul navbar/footer + CSS).
Publica - fara login. Asset-urile traiesc in static/marketing/.
"""

from flask import Blueprint, render_template

marketing_bp = Blueprint('marketing', __name__)


@marketing_bp.route('/home')
def home():
    """Landing page publica Edifico."""
    return render_template('marketing/home.html')
