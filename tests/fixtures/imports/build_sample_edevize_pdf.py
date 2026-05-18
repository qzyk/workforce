"""
Construieste un PDF eDevize sintetic pentru testarea parser-ului F3.

Foloseste reportlab (deja in requirements.txt) ca sa generam un PDF cu
structura identica cu cea produsa de eDevize.ro (testat pe DEVIZ SAPUNARI.pdf):

  Pagina 1: CENTRALIZATORUL (skipped by parser)
  Pagina 2: Formular F3 cu 3 articole + sub-rânduri (parsed)
  Pagina 3: Continuare F3 cu 2 articole (test pentru multi-page F3)

NOTA: PDF-ul reportlab e identic ca structura cu eDevize doar in aspectele
relevante pentru parser - mark-erii F3 si pattern-urile de articole.
Nu e replica 1:1 stilistica.

Folosire:
    from tests.fixtures.imports.build_sample_edevize_pdf import build_sample_pdf
    pdf_path = build_sample_pdf('/tmp/sample.pdf')
"""

from __future__ import annotations

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def build_sample_pdf(output_path: str) -> str:
    """Construieste PDF-ul si returneaza path-ul."""
    c = canvas.Canvas(output_path, pagesize=A4)
    width, height = A4

    # ---- Page 1: Centralizator (skipped by parser) ----
    c.setFont('Helvetica-Bold', 14)
    c.drawString(100, height - 80, 'CENTRALIZATORUL')
    c.drawString(100, height - 100, 'cheltuielilor pe obiectiv')
    c.setFont('Helvetica', 10)
    c.drawString(100, height - 140, 'Beneficiar: Test Beneficiar SRL')
    c.drawString(100, height - 160, 'Obiectivul: Sample Project')
    c.drawString(100, height - 200, '1.2  Amenajarea terenului            50,000.00')
    c.drawString(100, height - 220, '4.1  Constructii si instalatii      450,000.00')
    c.drawString(100, height - 240, 'TOTAL (fara TVA)                    500,000.00')
    c.drawString(100, height - 260, 'Formular generat cu programul')
    c.drawString(100, height - 280, '(www.eDevize.ro)')
    c.showPage()

    # ---- Page 2: Formular F3 ----
    c.setFont('Helvetica-Bold', 12)
    c.drawString(100, height - 60, 'Formular F3')
    c.drawString(100, height - 80, 'Lista cu cantitati de lucrari pe categorii de lucrari')
    c.setFont('Helvetica', 10)
    c.drawString(100, height - 110, 'Stadiul fizic: 1 REZISTENTA')
    c.drawString(100, height - 140, 'SECTIUNEA TEHNICA SECTIUNEA FINANCIARA')
    c.drawString(100, height - 160, 'Nr. Capitol de lucrari U.M. Cantitatea Pretul unitar TOTALUL')

    # Articol 1 (one-liner - denumire scurta)
    y = height - 200
    lines_art1 = [
        '1 SLVI03B5 - Sapatura mc 2,260.000 13.97 31,582.88',
        'material: 0.00 0.00',
        'manopera: 0.00 0.00',
        'utilaj: 13.97 31,582.88',
        'transport: 0.00 0.00',
    ]
    for line in lines_art1:
        c.drawString(100, y, line)
        y -= 16

    # Articol 2 (one-liner cu sufix special %)
    y -= 8
    lines_art2 = [
        '2 CR06A% - Perna de loess mc 900.000 39.97 35,976.02',
        'material: 19.27 17,346.02',
        'manopera: 20.70 18,630.00',
        'utilaj: 0.00 0.00',
        'transport: 0.00 0.00',
    ]
    for line in lines_art2:
        c.drawString(100, y, line)
        y -= 16

    # Articol 3 (multi-line: denumire pe 2 randuri inainte de UM)
    y -= 8
    lines_art3_multi = [
        '3 CK03B02^ - Plafon casetat 60x60, cu placi metalice,',
        'inclusiv structura de sustinere',
        'mp 1,537.000 76.25 117,203.60',
        'material: 55.25 84,926.60',
        'manopera: 21.00 32,277.00',
        'utilaj: 0.00 0.00',
        'transport: 0.00 0.00',
    ]
    for line in lines_art3_multi:
        c.drawString(100, y, line)
        y -= 16

    c.drawString(100, y - 16, 'TOTAL Terasamente   184,762.50')
    c.showPage()

    # ---- Page 3: Continuare F3 cu Stadiul fizic schimbat ----
    c.setFont('Helvetica-Bold', 12)
    c.drawString(100, height - 60, 'Formular F3')
    c.drawString(100, height - 80, 'Lista cu cantitati de lucrari pe categorii de lucrari')
    c.setFont('Helvetica', 10)
    c.drawString(100, height - 110, 'Stadiul fizic: 2 ARHITECTURA')
    c.drawString(100, height - 140, 'SECTIUNEA TEHNICA SECTIUNEA FINANCIARA')

    # Articol 4
    y = height - 180
    lines_art4 = [
        '1 RMA02A# - Beton C25/30 mc 363.000 627.38 227,739.05',
        'material: 556.42 201,981.54',
        'manopera: 60.00 21,780.00',
        'utilaj: 10.96 3,977.51',
        'transport: 0.00 0.00',
    ]
    for line in lines_art4:
        c.drawString(100, y, line)
        y -= 16

    # Articol 5 (cu cod containing dash)
    y -= 8
    lines_art5 = [
        '2 W2A08XC - Profil antiderapant pentru scari ml 36.000 50.47 1,816.87',
        'material: 38.47 1,384.87',
        'manopera: 12.00 432.00',
        'utilaj: 0.00 0.00',
        'transport: 0.00 0.00',
    ]
    for line in lines_art5:
        c.drawString(100, y, line)
        y -= 16

    c.drawString(100, y - 16, 'TOTAL Arhitectura   229,555.92')
    c.showPage()

    c.save()
    return output_path


if __name__ == '__main__':
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else '/tmp/sample_edevize.pdf'
    print(build_sample_pdf(out))
