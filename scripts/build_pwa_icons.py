"""
Build PWA icons din SVG-ul existent.

Genereaza PNG-uri in static/img/pwa/ in dimensiunile necesare pentru
instalare ca app native pe iOS/Android.

Foloseste Pillow + font Didot/Times de pe macOS (fallback la default).

Usage:
    python3 scripts/build_pwa_icons.py
"""

import os
import sys
from PIL import Image, ImageDraw, ImageFont


# Configurare brand Edifico
COLOR_NAVY = (11, 20, 38)         # #0B1426 obsidian
COLOR_GOLD = (201, 169, 97)       # #C9A961 champagne gold
COLOR_GOLD_LIGHT = (224, 187, 110)  # #E0BB6E highlight
COLOR_CREAM = (245, 241, 232)     # #F5F1E8

# Dimensiuni icons cerute de iOS + Android PWA
ICON_SIZES = [
    # (size, filename, with_padding=False)
    (192, 'icon-192.png', False),       # Android standard
    (512, 'icon-512.png', False),       # Android splash + general
    (180, 'apple-touch-icon.png', False), # iOS Safari home screen
    (144, 'icon-144.png', False),       # Windows tile / Android legacy
    (192, 'icon-192-maskable.png', True),  # Android adaptive (cu padding safe area)
    (512, 'icon-512-maskable.png', True),  # Android adaptive splash
]

# Fonturi de incercat in ordine de preferinta (cel mai elegant primul)
FONT_CANDIDATES = [
    '/System/Library/Fonts/Supplemental/Didot.ttc',
    '/System/Library/Fonts/Supplemental/Baskerville.ttc',
    '/System/Library/Fonts/Supplemental/Hoefler Text.ttc',
    '/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf',
    '/System/Library/Fonts/Times.ttc',
    # Linux fallback
    '/usr/share/fonts/truetype/dejavu/DejaVu-Serif-Bold.ttf',
    '/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf',
]


def find_font():
    """Gaseste primul font disponibil din lista."""
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            return path
    return None


def make_icon(size: int, filename: str, with_padding: bool):
    """
    Genereaza un icon PWA Edifico:
    - Fundal navy obsidian
    - Border decorativ aur (subtle bezel)
    - Litera "E" aurita centrata, font Didot
    """
    img = Image.new('RGB', (size, size), COLOR_NAVY)
    draw = ImageDraw.Draw(img)

    # Padding pentru maskable (safe area = 80% din canvas in centru)
    if with_padding:
        # Outer area umbla pentru adaptive icon (safe = 80% center)
        pad = int(size * 0.10)
    else:
        pad = int(size * 0.06)

    # Border outer (bezel auriu) - doar pentru non-maskable
    if not with_padding:
        border_thickness = max(2, size // 64)
        for i in range(border_thickness):
            draw.rectangle(
                [pad + i, pad + i, size - pad - 1 - i, size - pad - 1 - i],
                outline=COLOR_GOLD,
            )

        # Inner accent line (decorative)
        inner_pad = pad + border_thickness + max(2, size // 32)
        draw.rectangle(
            [inner_pad, inner_pad, size - inner_pad - 1, size - inner_pad - 1],
            outline=(COLOR_GOLD[0] // 2 + 32, COLOR_GOLD[1] // 2 + 24, COLOR_GOLD[2] // 2 + 8),
        )

    # Litera "E"
    font_path = find_font()
    if font_path is None:
        print('[WARN] Niciun font serif gasit. Folosesc default Pillow font.')
        font = ImageFont.load_default()
        font_size = size // 2
    else:
        # Marime font: ~75% din size pentru non-maskable, 60% pentru maskable
        font_size_ratio = 0.62 if with_padding else 0.78
        font_size = int(size * font_size_ratio)
        try:
            # Didot.ttc are mai multe variante - aleg "Bold" daca posibil
            font = ImageFont.truetype(font_path, font_size, index=1)
        except (OSError, IOError):
            try:
                font = ImageFont.truetype(font_path, font_size)
            except (OSError, IOError):
                font = ImageFont.load_default()

    # Calcul pozitie centru pentru text
    text = 'E'
    try:
        # Pillow >= 8: getbbox
        bbox = font.getbbox(text)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        text_x = (size - text_w) // 2 - bbox[0]
        text_y = (size - text_h) // 2 - bbox[1] - int(size * 0.02)  # mic lift optic
    except AttributeError:
        # Pillow vechi: textbbox / textsize
        text_w, text_h = font.getsize(text) if hasattr(font, 'getsize') else (font_size, font_size)
        text_x = (size - text_w) // 2
        text_y = (size - text_h) // 2

    # Desenez "E" cu un mic gradient simulat (umbra in jos)
    # 1) Shadow subtil
    shadow_offset = max(1, size // 256)
    draw.text((text_x + shadow_offset, text_y + shadow_offset), text,
              fill=(0, 0, 0, 128), font=font)
    # 2) E principal aurit
    draw.text((text_x, text_y), text, fill=COLOR_GOLD_LIGHT, font=font)

    return img


def main():
    out_dir = os.path.join(os.path.dirname(__file__), '..', 'static', 'img', 'pwa')
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    print(f'Generez PWA icons in: {out_dir}')
    font_path = find_font()
    print(f'Font folosit: {font_path or "(default Pillow)"}')

    for size, filename, with_padding in ICON_SIZES:
        img = make_icon(size, filename, with_padding)
        out_path = os.path.join(out_dir, filename)
        img.save(out_path, 'PNG', optimize=True)
        kb = os.path.getsize(out_path) / 1024
        suffix = ' (maskable)' if with_padding else ''
        print(f'  [OK] {filename}: {size}x{size}{suffix} = {kb:.1f} KB')

    print('\nDone. Fisiere salvate. Adauga in manifest.webmanifest si base.html.')


if __name__ == '__main__':
    main()
