"""
Serviciu SMTP pentru trimitere emailuri (Faza 14).

Configurare via env vars (global, conform decizie Faza 9):
  - SMTP_HOST (obligatoriu)
  - SMTP_PORT (default 587)
  - SMTP_USER (optional)
  - SMTP_PASS (optional)
  - SMTP_FROM (obligatoriu)
  - SMTP_USE_TLS (default 'true')

Graceful degradation: daca env vars lipsesc sau conexiunea esueaza,
returneaza False + logger.warning. NU arunca exceptii care sa rupa
job-ul de notificari.
"""

from __future__ import annotations

import logging
import mimetypes
import os
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional, Union


_logger = logging.getLogger(__name__)


def smtp_configured() -> bool:
    """True daca configurarea SMTP minima e prezenta."""
    return bool(os.environ.get('SMTP_HOST')) and bool(os.environ.get('SMTP_FROM'))


def trimite_email(
    destinatari: list[str],
    subiect: str,
    corp_text: str,
    corp_html: Optional[str] = None,
    reply_to: Optional[str] = None,
) -> bool:
    """
    Trimite email la o lista de destinatari.

    Returneaza True daca trimiterea a reusit la cel putin un destinatar.
    Daca SMTP nu e configurat -> log warning + return False.
    """
    if not smtp_configured():
        _logger.warning('SMTP nu e configurat (SMTP_HOST sau SMTP_FROM lipsesc). '
                        'Email-uri sarite.')
        return False

    if not destinatari:
        return False

    host = os.environ['SMTP_HOST']
    port = int(os.environ.get('SMTP_PORT', '587'))
    user = os.environ.get('SMTP_USER')
    password = os.environ.get('SMTP_PASS')
    from_addr = os.environ['SMTP_FROM']
    use_tls = os.environ.get('SMTP_USE_TLS', 'true').lower() in ('true', '1', 'yes')

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subiect
    msg['From'] = from_addr
    msg['To'] = ', '.join(destinatari)
    if reply_to:
        msg['Reply-To'] = reply_to

    msg.attach(MIMEText(corp_text, 'plain', 'utf-8'))
    if corp_html:
        msg.attach(MIMEText(corp_html, 'html', 'utf-8'))

    try:
        with smtplib.SMTP(host, port, timeout=15) as server:
            if use_tls:
                server.starttls()
            if user and password:
                server.login(user, password)
            server.sendmail(from_addr, destinatari, msg.as_string())
        _logger.info('Email trimis OK la %d destinatari (subject="%s").',
                     len(destinatari), subiect)
        return True
    except (smtplib.SMTPException, OSError, TimeoutError) as e:
        _logger.warning('Trimitere email a esuat: %s', e)
        return False


def trimite_email_termen(
    destinatari: list[str],
    termen_titlu: str,
    data_scadenta,
    zile_pana_la_scadenta: int,
    link_url: Optional[str] = None,
) -> bool:
    """Convenience wrapper pentru emailuri TermenUrmarit."""
    if zile_pana_la_scadenta < 0:
        subiect_prefix = '[DEPASIT]'
        descriere = f'Termenul a fost depasit cu {abs(zile_pana_la_scadenta)} zile.'
    elif zile_pana_la_scadenta == 0:
        subiect_prefix = '[ASTAZI]'
        descriere = 'Termenul scade astazi.'
    else:
        subiect_prefix = '[URGENT]'
        descriere = f'Mai sunt {zile_pana_la_scadenta} zile pana la scadenta.'

    subiect = f'{subiect_prefix} Termen "{termen_titlu}" scadenta {data_scadenta}'
    corp_text = (
        f'Atentie!\n\n'
        f'Termen monitorizat: {termen_titlu}\n'
        f'Data scadenta: {data_scadenta}\n'
        f'{descriere}\n\n'
    )
    if link_url:
        corp_text += f'Detalii: {link_url}\n'

    return trimite_email(destinatari, subiect, corp_text)


# ============================================================
# RAPOARTE: email cu atasament (Rapoarte Faza 1)
# ============================================================

def _ataseaza_fisier(msg: MIMEMultipart, fisier_path: str) -> Optional[str]:
    """
    Citeste `fisier_path` si il ataseaza la `msg` ca MIMEApplication cu
    Content-Disposition: attachment; filename=...

    Returneaza numele fisierului atasat (basename) sau None daca fisierul nu
    exista / nu poate fi citit. Nu arunca exceptii.
    """
    if not fisier_path or not os.path.exists(fisier_path):
        _logger.warning('Atasament inexistent: %s', fisier_path)
        return None

    filename = os.path.basename(fisier_path)
    ctype, _ = mimetypes.guess_type(filename)
    if ctype and '/' in ctype:
        maintype, subtype = ctype.split('/', 1)
    else:
        maintype, subtype = 'application', 'octet-stream'

    try:
        with open(fisier_path, 'rb') as fh:
            data = fh.read()
    except OSError as e:
        _logger.warning('Citire atasament esuata (%s): %s', fisier_path, e)
        return None

    part = MIMEApplication(data, _subtype=subtype)
    if maintype != 'application':
        # mimetypes a returnat alt maintype; pastram subtype-ul ghicit.
        part.set_type(f'{maintype}/{subtype}')
    part.add_header('Content-Disposition', 'attachment', filename=filename)
    msg.attach(part)
    return filename


def construieste_mesaj_raport(
    destinatar: Union[str, list[str]],
    subiect: str,
    corp: str,
    fisier_path: Optional[str] = None,
    corp_html: Optional[str] = None,
    from_addr: Optional[str] = None,
) -> MIMEMultipart:
    """
    Construieste mesajul MIME (multipart/mixed) pentru un raport, cu atasament
    optional. NU trimite nimic - util si pentru testare fara SMTP.

    Structura: multipart/mixed
      - multipart/alternative (text + html optional)
      - attachment (daca fisier_path exista)
    """
    if isinstance(destinatar, str):
        destinatari = [destinatar]
    else:
        destinatari = list(destinatar)

    msg = MIMEMultipart('mixed')
    msg['Subject'] = subiect
    msg['From'] = from_addr or os.environ.get('SMTP_FROM', 'noreply@edifico.space')
    msg['To'] = ', '.join(destinatari)

    corp_part = MIMEMultipart('alternative')
    corp_part.attach(MIMEText(corp, 'plain', 'utf-8'))
    if corp_html:
        corp_part.attach(MIMEText(corp_html, 'html', 'utf-8'))
    msg.attach(corp_part)

    if fisier_path:
        _ataseaza_fisier(msg, fisier_path)

    return msg


def trimite_raport_email(
    destinatar: Union[str, list[str]],
    subiect: str,
    corp: str,
    fisier_path: Optional[str] = None,
    corp_html: Optional[str] = None,
) -> bool:
    """
    Trimite un raport pe email cu atasament (best-effort).

    - Daca SMTP nu e configurat -> log warning + return False (fara crash).
    - Daca trimiterea esueaza -> log warning + return False.
    - Returneaza True doar daca SMTP a acceptat mesajul.

    Folosit din spatele flag-ului 'rapoarte-email' (default OFF). Construirea
    MIME e exportata separat (construieste_mesaj_raport) pentru testare.
    """
    if isinstance(destinatar, str):
        destinatari = [destinatar]
    else:
        destinatari = list(destinatar)

    if not destinatari:
        return False

    if not smtp_configured():
        _logger.warning('SMTP nu e configurat; raport email sarit (subject="%s").',
                        subiect)
        return False

    host = os.environ['SMTP_HOST']
    port = int(os.environ.get('SMTP_PORT', '587'))
    user = os.environ.get('SMTP_USER')
    password = os.environ.get('SMTP_PASS')
    from_addr = os.environ['SMTP_FROM']
    use_tls = os.environ.get('SMTP_USE_TLS', 'true').lower() in ('true', '1', 'yes')

    msg = construieste_mesaj_raport(
        destinatari, subiect, corp, fisier_path=fisier_path,
        corp_html=corp_html, from_addr=from_addr,
    )

    try:
        with smtplib.SMTP(host, port, timeout=15) as server:
            if use_tls:
                server.starttls()
            if user and password:
                server.login(user, password)
            server.sendmail(from_addr, destinatari, msg.as_string())
        _logger.info('Raport email trimis OK la %d destinatari (subject="%s").',
                     len(destinatari), subiect)
        return True
    except (smtplib.SMTPException, OSError, TimeoutError) as e:
        _logger.warning('Trimitere raport email a esuat: %s', e)
        return False
