/**
 * Edifico — Premium pitch presentation generator.
 *
 * Genereaza ~20 slide-uri cu:
 * - paleta gold (#C9A961) + navy (#0B1426) + cream (#F5F1E8)
 * - font Cinzel pentru titluri, Inter pentru body
 * - icons FontAwesome rasterized via react-icons + sharp
 * - transitions intre slide-uri pentru export video
 * - slide timings auto-advance pentru video continuu
 */

const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");

// ===== ICONS =====
const Fa = require("react-icons/fa");
const Md = require("react-icons/md");
const Hi = require("react-icons/hi");
const Bi = require("react-icons/bi");

// ===== PALETTE EDIFICO =====
const C = {
  navy:        "0B1426",
  navyDeep:    "050A14",
  navyLight:   "1A2A4A",
  gold:        "C9A961",
  goldLight:   "E0BB6E",
  goldDark:    "A8893D",
  cream:       "F5F1E8",
  creamDim:    "E8E1D0",
  white:       "FFFFFF",
  textOnDark:  "F5F1E8",
  textOnLight: "0B1426",
  muted:       "8B8B8B",
  accent:      "DC9F3A",
};

const FONT_TITLE = "Cinzel";   // imperial serif latin
const FONT_BODY  = "Inter";    // modern sans
const FONT_TITLE_FALLBACK = "Georgia";
const FONT_BODY_FALLBACK = "Calibri";

// ===== HELPER: render icon to base64 PNG =====
function iconSvg(IconComp, color, size = 256) {
  return ReactDOMServer.renderToStaticMarkup(
    React.createElement(IconComp, { color, size: String(size) })
  );
}
async function iconPng(IconComp, color, size = 512) {
  const svg = iconSvg(IconComp, color, size);
  const buf = await sharp(Buffer.from(svg)).png().toBuffer();
  return "image/png;base64," + buf.toString("base64");
}

// ===== HELPER: full-bleed background =====
function addDarkBg(slide, hex = C.navy) {
  slide.background = { color: hex };
}
function addCreamBg(slide) {
  slide.background = { color: C.cream };
}

// ===== HELPER: gold accent corner ornament =====
function addCornerOrnament(slide, pos = "topRight") {
  // Subtile L-shape ornament gold
  const size = 0.45;
  const thickness = 0.04;
  let x, y, hOffset, vOffset;
  if (pos === "topRight")    { x = 9.4; y = 0.3; hOffset = -size; vOffset = size; }
  if (pos === "topLeft")     { x = 0.3; y = 0.3; hOffset = size;  vOffset = size; }
  if (pos === "bottomRight") { x = 9.4; y = 5.3; hOffset = -size; vOffset = -size; }
  if (pos === "bottomLeft")  { x = 0.3; y = 5.3; hOffset = size;  vOffset = -size; }
  slide.addShape("rect", { x: x + (hOffset < 0 ? hOffset : 0), y, w: Math.abs(hOffset), h: thickness, fill: { color: C.gold }, line: { type: "none" } });
  slide.addShape("rect", { x, y: y + (vOffset < 0 ? vOffset : 0), w: thickness, h: Math.abs(vOffset), fill: { color: C.gold }, line: { type: "none" } });
}

// ===== HELPER: footer bar (used on content slides) =====
function addFooter(slide, slideNum, total) {
  slide.addShape("rect", {
    x: 0, y: 5.45, w: 10, h: 0.175,
    fill: { color: C.gold }, line: { type: "none" },
  });
  slide.addText("EDIFICO  ·  One platform, all your sites",
    { x: 0.4, y: 5.22, w: 6, h: 0.22, fontSize: 8, color: C.gold,
      fontFace: FONT_BODY, charSpacing: 4 });
  slide.addText(`${slideNum} / ${total}`,
    { x: 8, y: 5.22, w: 1.6, h: 0.22, fontSize: 8, color: C.muted,
      fontFace: FONT_BODY, align: "right", charSpacing: 2 });
}

// ===== HELPER: section title (gold rule + uppercase tracking) =====
function addSectionTitle(slide, kicker, title, opts = {}) {
  const y = opts.y || 0.55;
  const lightBg = opts.lightBg;
  const kickerColor = lightBg ? C.goldDark : C.gold;
  const titleColor  = lightBg ? C.navy : C.cream;

  slide.addText(kicker, {
    x: 0.5, y: y, w: 9, h: 0.28, fontSize: 10, charSpacing: 7,
    fontFace: FONT_BODY, color: kickerColor, bold: true,
    valign: "top", margin: 0,
  });
  slide.addText(title, {
    x: 0.5, y: y + 0.32, w: 9, h: 0.85, fontSize: 36, charSpacing: 4,
    fontFace: FONT_TITLE_FALLBACK, color: titleColor, bold: false,
    valign: "top", margin: 0,
  });
  // gold hairline below
  slide.addShape("rect", {
    x: 0.5, y: y + 1.18, w: 1.0, h: 0.025,
    fill: { color: C.gold }, line: { type: "none" },
  });
}

// ===== MAIN =====
async function build() {
  // Pre-rasterize all icons we'll need
  const I = {
    helmet:     await iconPng(Fa.FaHardHat, "#" + C.gold),
    cubes:      await iconPng(Fa.FaCubes, "#" + C.gold),
    layers:     await iconPng(Fa.FaLayerGroup, "#" + C.gold),
    bolt:       await iconPng(Fa.FaBolt, "#" + C.gold),
    chart:      await iconPng(Fa.FaChartLine, "#" + C.gold),
    moneyBill:  await iconPng(Fa.FaMoneyBill, "#" + C.gold),
    sensor:     await iconPng(Fa.FaBroadcastTower, "#" + C.gold),
    users:      await iconPng(Fa.FaUsers, "#" + C.gold),
    kanban:     await iconPng(Fa.FaTable, "#" + C.gold),
    shield:     await iconPng(Fa.FaShieldAlt, "#" + C.gold),
    code:       await iconPng(Fa.FaCode, "#" + C.gold),
    mobile:     await iconPng(Fa.FaMobileAlt, "#" + C.gold),
    check:      await iconPng(Fa.FaCheckCircle, "#" + C.gold),
    rocket:     await iconPng(Fa.FaRocket, "#" + C.gold),
    badge:      await iconPng(Fa.FaCertificate, "#" + C.gold),
    cloud:      await iconPng(Fa.FaCloud, "#" + C.gold),
    diagram:    await iconPng(Fa.FaSitemap, "#" + C.gold),
    branch:     await iconPng(Fa.FaCodeBranch, "#" + C.gold),
    eye:        await iconPng(Fa.FaEye, "#" + C.gold),
    lock:       await iconPng(Fa.FaLock, "#" + C.gold),
    cog:        await iconPng(Fa.FaCog, "#" + C.gold),
    award:      await iconPng(Fa.FaAward, "#" + C.gold),
    play:       await iconPng(Fa.FaPlayCircle, "#" + C.gold),
    bullseye:   await iconPng(Fa.FaBullseye, "#" + C.gold),
    pen:        await iconPng(Fa.FaPenNib, "#" + C.gold),
    flask:      await iconPng(Fa.FaFlask, "#" + C.gold),
    arrowRight: await iconPng(Fa.FaArrowRight, "#" + C.gold),
    // dark-on-light versions
    helmetDark:  await iconPng(Fa.FaHardHat, "#" + C.navy),
    cubesDark:   await iconPng(Fa.FaCubes, "#" + C.navy),
    boltDark:    await iconPng(Fa.FaBolt, "#" + C.navy),
  };

  const pres = new pptxgen();
  pres.layout = "LAYOUT_16x9";
  pres.author = "Edifico";
  pres.title = "Edifico — One platform, all your sites";
  pres.subject = "Premium BIM + Digital Twin platform pitch";

  // Transition global - aplicat per-slide manual (pptxgenjs accepts in addSlide options sometimes)
  // Vom seta animation timing dupa fapt (XML inject)

  const TOTAL = 20;

  // ============================================================
  // SLIDE 1 — COVER (dark, splash)
  // ============================================================
  {
    const s = pres.addSlide();
    addDarkBg(s);

    // Decorative gold border frame
    const frameMargin = 0.35;
    s.addShape("rect", { x: frameMargin, y: frameMargin, w: 10 - 2*frameMargin, h: 0.025, fill: { color: C.gold }, line: { type: "none" } });
    s.addShape("rect", { x: frameMargin, y: 5.625 - frameMargin, w: 10 - 2*frameMargin, h: 0.025, fill: { color: C.gold }, line: { type: "none" } });
    s.addShape("rect", { x: frameMargin, y: frameMargin, w: 0.025, h: 5.625 - 2*frameMargin, fill: { color: C.gold }, line: { type: "none" } });
    s.addShape("rect", { x: 10 - frameMargin, y: frameMargin, w: 0.025, h: 5.625 - 2*frameMargin, fill: { color: C.gold }, line: { type: "none" } });

    // Inner faint frame
    const innerM = 0.5;
    s.addShape("rect", { x: innerM, y: innerM, w: 10 - 2*innerM, h: 0.012, fill: { color: C.goldDark }, line: { type: "none" } });
    s.addShape("rect", { x: innerM, y: 5.625 - innerM, w: 10 - 2*innerM, h: 0.012, fill: { color: C.goldDark }, line: { type: "none" } });

    // Large "E" mark centered
    s.addText("E", {
      x: 4.3, y: 1.2, w: 1.4, h: 1.6,
      fontSize: 130, fontFace: FONT_TITLE_FALLBACK, color: C.gold,
      align: "center", valign: "middle", margin: 0, italic: true, bold: true,
    });

    // Decorative dots under E
    s.addShape("ellipse", { x: 4.78, y: 3.0, w: 0.07, h: 0.07, fill: { color: C.gold }, line: { type: "none" } });
    s.addShape("ellipse", { x: 4.95, y: 2.97, w: 0.10, h: 0.10, fill: { color: C.goldLight }, line: { type: "none" } });
    s.addShape("ellipse", { x: 5.15, y: 3.0, w: 0.07, h: 0.07, fill: { color: C.gold }, line: { type: "none" } });

    // Wordmark
    s.addText("EDIFICO", {
      x: 1, y: 3.2, w: 8, h: 0.75, fontSize: 56, fontFace: FONT_TITLE_FALLBACK,
      color: C.cream, charSpacing: 18, align: "center", valign: "middle", margin: 0,
    });

    // Hairline below wordmark
    s.addShape("rect", { x: 3.2, y: 4.05, w: 3.6, h: 0.012, fill: { color: C.gold }, line: { type: "none" } });

    // Tagline
    s.addText("ONE PLATFORM,  ALL YOUR SITES", {
      x: 1, y: 4.18, w: 8, h: 0.35, fontSize: 13, fontFace: FONT_BODY,
      color: C.gold, charSpacing: 9, align: "center", valign: "middle", margin: 0,
    });

    // Bottom badge
    s.addText("BIM  ·  DIGITAL TWIN  ·  WORKFORCE", {
      x: 1, y: 4.85, w: 8, h: 0.25, fontSize: 9, fontFace: FONT_BODY,
      color: C.muted, charSpacing: 6, align: "center",
    });
  }

  // ============================================================
  // SLIDE 2 — THE PROBLEM
  // ============================================================
  {
    const s = pres.addSlide();
    addCreamBg(s);
    addSectionTitle(s, "01  ·  THE PROBLEM", "Construction is fragmented.", { lightBg: true });

    // Three columns: stat-driven
    const startY = 2.4;
    const colW = 2.9;
    const cols = [
      { stat: "65%", label: "din proiecte depasesc bugetul", desc: "fara o vizibilitate centralizata cost ↔ executie" },
      { stat: "30%", label: "din timpul echipei e pierdut", desc: "in coordonare manuala intre tool-uri disjuncte" },
      { stat: "0", label: "platforme accesibile pentru IMM-uri AEC", desc: "majoritatea solutiilor BIM enterprise costa €1000+/luna" },
    ];
    cols.forEach((c, i) => {
      const x = 0.5 + i * (colW + 0.15);
      s.addShape("rect", { x, y: startY, w: colW, h: 2.4, fill: { color: C.white }, line: { color: C.creamDim, width: 1 } });
      s.addShape("rect", { x, y: startY, w: 0.04, h: 2.4, fill: { color: C.gold }, line: { type: "none" } });
      s.addText(c.stat, {
        x: x + 0.25, y: startY + 0.3, w: colW - 0.5, h: 0.85,
        fontSize: 60, fontFace: FONT_TITLE_FALLBACK, color: C.gold, bold: true,
        margin: 0, valign: "top",
      });
      s.addText(c.label, {
        x: x + 0.25, y: startY + 1.2, w: colW - 0.5, h: 0.5,
        fontSize: 13, fontFace: FONT_BODY, color: C.navy, bold: true,
        margin: 0, valign: "top",
      });
      s.addText(c.desc, {
        x: x + 0.25, y: startY + 1.7, w: colW - 0.5, h: 0.6,
        fontSize: 11, fontFace: FONT_BODY, color: C.muted, margin: 0, valign: "top",
      });
    });

    addFooter(s, 2, TOTAL);
  }

  // ============================================================
  // SLIDE 3 — THE SOLUTION
  // ============================================================
  {
    const s = pres.addSlide();
    addDarkBg(s);
    addSectionTitle(s, "02  ·  THE SOLUTION", "One platform. Built for AEC.");

    // Large headline / value prop
    s.addText("Edifico unifica workforce, BIM si Digital Twin\nintr-un singur produs accesibil — gandit pentru\nIMM-urile din constructii care vor sa lucreze\nca enterprise, fara costuri enterprise.", {
      x: 0.5, y: 2.4, w: 6.5, h: 2.2, fontSize: 17, fontFace: FONT_BODY,
      color: C.cream, valign: "top", lineSpacingMultiple: 1.4, margin: 0,
    });

    // Right side: 4 key value pillars (vertical)
    const startY = 2.0;
    const pillars = [
      { t: "Self-hosted",  d: "Datele raman la tine" },
      { t: "Open standards", d: "IFC · BCF · COBie · ISO 19650" },
      { t: "Modular",       d: "8 module, activabile la nevoie" },
      { t: "Cost predictabil", d: "Fara abonament per user" },
    ];
    pillars.forEach((p, i) => {
      const x = 7.4;
      const y = startY + i * 0.7;
      s.addShape("rect", { x, y, w: 0.03, h: 0.55, fill: { color: C.gold }, line: { type: "none" } });
      s.addText(p.t, { x: x + 0.18, y, w: 2.2, h: 0.27,
        fontSize: 13, fontFace: FONT_BODY, color: C.gold, bold: true,
        valign: "top", margin: 0 });
      s.addText(p.d, { x: x + 0.18, y: y + 0.27, w: 2.2, h: 0.28,
        fontSize: 10, fontFace: FONT_BODY, color: C.cream, valign: "top", margin: 0 });
    });

    addFooter(s, 3, TOTAL);
  }

  // ============================================================
  // SLIDE 4 — PLATFORM OVERVIEW (8 modules grid)
  // ============================================================
  {
    const s = pres.addSlide();
    addCreamBg(s);
    addSectionTitle(s, "03  ·  PLATFORM", "8 module, 1 platforma.", { lightBg: true });

    const modules = [
      { icon: I.helmetDark, t: "Workforce", d: "Pontaje · Angajati · Proiecte" },
      { icon: I.cubesDark, t: "BIM Core",   d: "Santiere · Spatii · Elemente" },
      { icon: I.cubesDark, t: "3D Viewer",  d: "xeokit · APS · Federation" },
      { icon: I.boltDark,  t: "CDE Workflow", d: "ISO 19650 · Versioning" },
      { icon: I.boltDark,  t: "Rules + Clash", d: "Model checking automat" },
      { icon: I.cubesDark, t: "4D + 5D",    d: "Schedule · Cost · Gantt" },
      { icon: I.cubesDark, t: "Digital Twin", d: "Sensori · Alerte · IoT" },
      { icon: I.boltDark,  t: "Governance",  d: "RBAC · COBie · BCF · API" },
    ];

    // 4x2 grid
    const cellW = 2.18, cellH = 1.3;
    const startX = 0.5, startY = 2.3;
    const gapX = 0.12, gapY = 0.18;
    modules.forEach((m, i) => {
      const col = i % 4, row = Math.floor(i / 4);
      const x = startX + col * (cellW + gapX);
      const y = startY + row * (cellH + gapY);
      s.addShape("rect", { x, y, w: cellW, h: cellH, fill: { color: C.white }, line: { color: C.creamDim, width: 0.75 } });
      s.addShape("rect", { x, y, w: cellW, h: 0.03, fill: { color: C.gold }, line: { type: "none" } });

      // Numbered badge
      s.addText(String(i + 1).padStart(2, "0"), {
        x: x + 0.15, y: y + 0.12, w: 0.5, h: 0.28,
        fontSize: 10, fontFace: FONT_BODY, color: C.gold, bold: true, charSpacing: 2,
        valign: "top", margin: 0,
      });

      s.addText(m.t, {
        x: x + 0.15, y: y + 0.45, w: cellW - 0.3, h: 0.4,
        fontSize: 15, fontFace: FONT_BODY, color: C.navy, bold: true,
        valign: "top", margin: 0,
      });
      s.addText(m.d, {
        x: x + 0.15, y: y + 0.83, w: cellW - 0.3, h: 0.5,
        fontSize: 9.5, fontFace: FONT_BODY, color: C.muted,
        valign: "top", margin: 0,
      });
    });

    addFooter(s, 4, TOTAL);
  }

  // ============================================================
  // SLIDE 5 — MODULE: WORKFORCE
  // ============================================================
  {
    const s = pres.addSlide();
    addCreamBg(s);
    addSectionTitle(s, "04  ·  MODUL 01", "Workforce Management.", { lightBg: true });

    // Left: feature list (bullets gold + text dark)
    const features = [
      { t: "Pontaje granulare", d: "Ore normale + suplimentare 50% + 100%, validare automata weekend + sarbatori legale RO" },
      { t: "Angajati cu CV complet", d: "CNP, functie, documente cu expirare, poza, qualificari" },
      { t: "Proiecte cu echipa", d: "Asociere angajat-proiect cu tarif negociat, budget tracking" },
      { t: "Rapoarte Excel + PDF", d: "8 tipuri Excel + 3 PDF (Foaie colectiva A3, Stat plata, SSM)" },
    ];
    let yPos = 1.9;
    features.forEach((f, i) => {
      // Number badge
      s.addShape("ellipse", { x: 0.5, y: yPos + 0.05, w: 0.32, h: 0.32, fill: { color: C.gold }, line: { type: "none" } });
      s.addText(String(i + 1), {
        x: 0.5, y: yPos + 0.05, w: 0.32, h: 0.32,
        fontSize: 14, color: C.navy, bold: true, fontFace: FONT_BODY,
        align: "center", valign: "middle", margin: 0,
      });
      s.addText(f.t, {
        x: 1, y: yPos, w: 4.8, h: 0.35, fontSize: 14, fontFace: FONT_BODY,
        color: C.navy, bold: true, valign: "top", margin: 0,
      });
      s.addText(f.d, {
        x: 1, y: yPos + 0.35, w: 4.8, h: 0.55, fontSize: 10.5, fontFace: FONT_BODY,
        color: C.muted, valign: "top", margin: 0,
      });
      yPos += 0.85;
    });

    // Right side: KPI panel (dark)
    s.addShape("rect", { x: 6.2, y: 1.9, w: 3.4, h: 3.0, fill: { color: C.navy }, line: { type: "none" } });
    s.addShape("rect", { x: 6.2, y: 1.9, w: 3.4, h: 0.04, fill: { color: C.gold }, line: { type: "none" } });

    s.addText("CIFRE TIPICE", {
      x: 6.4, y: 2.05, w: 3.0, h: 0.25, fontSize: 9, fontFace: FONT_BODY,
      color: C.gold, charSpacing: 6, bold: true, valign: "top", margin: 0,
    });

    const stats = [
      { v: "200+", l: "angajati per tenant" },
      { v: "50K", l: "pontaje / an" },
      { v: "11", l: "tipuri rapoarte" },
    ];
    stats.forEach((st, i) => {
      const y = 2.5 + i * 0.85;
      s.addText(st.v, {
        x: 6.4, y, w: 3.0, h: 0.55, fontSize: 36, fontFace: FONT_TITLE_FALLBACK,
        color: C.gold, bold: true, valign: "top", margin: 0,
      });
      s.addText(st.l, {
        x: 6.4, y: y + 0.5, w: 3.0, h: 0.3, fontSize: 10, fontFace: FONT_BODY,
        color: C.cream, valign: "top", margin: 0,
      });
    });

    addFooter(s, 5, TOTAL);
  }

  // ============================================================
  // SLIDE 6 — BIM CORE
  // ============================================================
  {
    const s = pres.addSlide();
    addDarkBg(s);
    addSectionTitle(s, "05  ·  MODUL 02", "BIM Core hierarchy.");

    // Hierarchy chart visual
    const labels = ["SANTIER", "CLADIRE", "NIVEL", "ZONA", "SPATIU", "ELEMENT"];
    const startY = 2.3;
    labels.forEach((lab, i) => {
      const x = 0.5 + i * 1.55;
      // Card
      s.addShape("rect", { x, y: startY, w: 1.35, h: 1.0, fill: { color: C.navyLight }, line: { color: C.gold, width: 0.75 } });
      // Number top
      s.addText(`L${i + 1}`, {
        x, y: startY + 0.1, w: 1.35, h: 0.3,
        fontSize: 10, color: C.gold, bold: true, fontFace: FONT_BODY,
        align: "center", margin: 0, charSpacing: 2,
      });
      // Label
      s.addText(lab, {
        x, y: startY + 0.4, w: 1.35, h: 0.45,
        fontSize: 12, color: C.cream, fontFace: FONT_BODY,
        bold: true, align: "center", valign: "middle", margin: 0, charSpacing: 1,
      });

      // Arrow between
      if (i < labels.length - 1) {
        const ax = x + 1.35;
        s.addText("›", { x: ax, y: startY + 0.25, w: 0.2, h: 0.5,
          fontSize: 24, color: C.gold, align: "center", valign: "middle", margin: 0 });
      }
    });

    // Below: 3 capability boxes
    const caps = [
      { t: "IFC Import", d: "ifcopenshell native, GlobalId tracking" },
      { t: "Federation", d: "ExternalMapping: IFC + Revit + APS coexista" },
      { t: "Data quality", d: "Audit `flask validate-bim` cu 6 reports" },
    ];
    const cy = 4.0, cw = 3.0;
    caps.forEach((c, i) => {
      const x = 0.5 + i * (cw + 0.12);
      s.addShape("rect", { x, y: cy, w: cw, h: 1.1, fill: { color: C.navyDeep }, line: { color: C.goldDark, width: 0.5 } });
      s.addShape("rect", { x, y: cy, w: 0.05, h: 1.1, fill: { color: C.gold }, line: { type: "none" } });
      s.addText(c.t, { x: x + 0.2, y: cy + 0.15, w: cw - 0.4, h: 0.4,
        fontSize: 14, color: C.gold, bold: true, fontFace: FONT_BODY, margin: 0, valign: "top" });
      s.addText(c.d, { x: x + 0.2, y: cy + 0.55, w: cw - 0.4, h: 0.55,
        fontSize: 10.5, color: C.cream, fontFace: FONT_BODY, margin: 0, valign: "top" });
    });

    addFooter(s, 6, TOTAL);
  }

  // ============================================================
  // SLIDE 7 — 3D VIEWER + FEDERATION
  // ============================================================
  {
    const s = pres.addSlide();
    addCreamBg(s);
    addSectionTitle(s, "06  ·  MODUL 03", "3D Viewer + Federation.", { lightBg: true });

    // Left: bullet list of viewers in priority order
    const viewers = [
      { num: "1", name: "Autodesk APS Viewer", note: "Enterprise tier · necesita APS_CLIENT_ID" },
      { num: "2", name: "xeokit-sdk (open)", note: "Self-hosted · cea mai rapida pe modele >50MB" },
      { num: "3", name: "web-ifc-viewer (fallback)", note: "Legacy · pentru compatibilitate" },
    ];
    viewers.forEach((v, i) => {
      const y = 2.0 + i * 0.95;
      // Big rank number
      s.addText(v.num, { x: 0.5, y, w: 0.65, h: 0.85,
        fontSize: 60, color: C.gold, fontFace: FONT_TITLE_FALLBACK, bold: true,
        valign: "top", margin: 0 });
      s.addText(v.name, { x: 1.25, y: y + 0.13, w: 4.5, h: 0.4,
        fontSize: 16, color: C.navy, bold: true, fontFace: FONT_BODY, margin: 0, valign: "top" });
      s.addText(v.note, { x: 1.25, y: y + 0.5, w: 4.5, h: 0.35,
        fontSize: 11, color: C.muted, fontFace: FONT_BODY, margin: 0, valign: "top" });
    });

    // Right: Federation explainer panel
    s.addShape("rect", { x: 6.0, y: 1.9, w: 3.6, h: 3.0, fill: { color: C.navy }, line: { type: "none" } });
    s.addShape("rect", { x: 6.0, y: 1.9, w: 0.05, h: 3.0, fill: { color: C.gold }, line: { type: "none" } });

    s.addText("FEDERATION", {
      x: 6.2, y: 2.05, w: 3.3, h: 0.25, fontSize: 10, fontFace: FONT_BODY,
      color: C.gold, charSpacing: 7, bold: true, valign: "top", margin: 0,
    });
    s.addText("Multi-disciplina overlap.", {
      x: 6.2, y: 2.4, w: 3.3, h: 0.5, fontSize: 18, fontFace: FONT_TITLE_FALLBACK,
      color: C.cream, valign: "top", margin: 0,
    });

    // Discipline pills
    const disciplines = ["ARH", "STR", "MEP", "ELE", "HVAC", "SAN"];
    disciplines.forEach((d, i) => {
      const px = 6.2 + (i % 3) * 1.1;
      const py = 3.1 + Math.floor(i / 3) * 0.45;
      s.addShape("rect", { x: px, y: py, w: 1.0, h: 0.35, fill: { color: C.navyLight }, line: { color: C.gold, width: 0.5 } });
      s.addText(d, { x: px, y: py, w: 1.0, h: 0.35,
        fontSize: 11, color: C.gold, bold: true, fontFace: FONT_BODY,
        align: "center", valign: "middle", margin: 0, charSpacing: 2 });
    });

    s.addText("Viewer publicat la nivel santier.\nFiltrabil per disciplina prin pillule.", {
      x: 6.2, y: 4.1, w: 3.3, h: 0.7, fontSize: 10.5, fontFace: FONT_BODY,
      color: C.cream, valign: "top", margin: 0,
    });

    addFooter(s, 7, TOTAL);
  }

  // ============================================================
  // SLIDE 8 — CDE WORKFLOW
  // ============================================================
  {
    const s = pres.addSlide();
    addDarkBg(s);
    addSectionTitle(s, "07  ·  MODUL 04", "CDE Workflow · ISO 19650.");

    // Status flow as horizontal pills
    const statuses = [
      { t: "WIP",       c: "FFA726" },
      { t: "SHARED",    c: "42A5F5" },
      { t: "PUBLISHED", c: "66BB6A" },
      { t: "REJECTED",  c: "EF5350" },
      { t: "ARCHIVED",  c: "9E9E9E" },
    ];
    const fy = 2.3, fw = 1.62, fh = 0.6, gap = 0.18;
    statuses.forEach((st, i) => {
      const x = 0.5 + i * (fw + gap);
      s.addShape("rect", { x, y: fy, w: fw, h: fh, fill: { color: st.c }, line: { type: "none" } });
      s.addText(st.t, { x, y: fy, w: fw, h: fh,
        fontSize: 13, color: C.navy, bold: true, fontFace: FONT_BODY,
        align: "center", valign: "middle", margin: 0, charSpacing: 2 });
      if (i < statuses.length - 1) {
        s.addText("→", { x: x + fw, y: fy, w: gap, h: fh,
          fontSize: 16, color: C.gold, align: "center", valign: "middle", margin: 0 });
      }
    });

    // Below: key features
    const features = [
      { t: "Versioning explicit", d: "Fiecare model are N versiuni cu istoricul complet" },
      { t: "Permisiuni granulare", d: "Operator: WIP↔SHARED. Manager: publish/reject/archive" },
      { t: "Audit trail complet", d: "Toate tranzitiile logate cu user, timestamp, comentariu" },
      { t: "Aprobari oficiale", d: "Doar versiunile PUBLISHED apar in federation + execution" },
    ];
    features.forEach((f, i) => {
      const col = i % 2, row = Math.floor(i / 2);
      const x = 0.5 + col * 4.7;
      const y = 3.25 + row * 0.95;
      s.addShape("rect", { x, y, w: 0.03, h: 0.8, fill: { color: C.gold }, line: { type: "none" } });
      s.addText(f.t, { x: x + 0.15, y, w: 4.3, h: 0.35,
        fontSize: 13, color: C.gold, bold: true, fontFace: FONT_BODY, valign: "top", margin: 0 });
      s.addText(f.d, { x: x + 0.15, y: y + 0.35, w: 4.3, h: 0.5,
        fontSize: 11, color: C.cream, fontFace: FONT_BODY, valign: "top", margin: 0 });
    });

    addFooter(s, 8, TOTAL);
  }

  // ============================================================
  // SLIDE 9 — RULE ENGINE + CLASH
  // ============================================================
  {
    const s = pres.addSlide();
    addCreamBg(s);
    addSectionTitle(s, "08  ·  MODUL 05", "Rule Engine + Clash Detection.", { lightBg: true });

    // Left: rule example (code-like dark block)
    s.addShape("rect", { x: 0.5, y: 1.85, w: 4.5, h: 3.0, fill: { color: C.navy }, line: { type: "none" } });
    s.addText("EXEMPLU REGULA · JSON DSL", {
      x: 0.7, y: 1.95, w: 4.1, h: 0.25, fontSize: 9, color: C.gold,
      bold: true, charSpacing: 5, fontFace: FONT_BODY, valign: "top", margin: 0,
    });

    const codeLines = [
      '{',
      '  "tip": "required_properties",',
      '  "selector": {',
      '    "tip_element": "wall"',
      '  },',
      '  "constraint": {',
      '    "required_properties":',
      '      ["fire_rating", "thickness"]',
      '  }',
      '}',
    ];
    codeLines.forEach((line, i) => {
      s.addText(line, {
        x: 0.7, y: 2.3 + i * 0.22, w: 4.1, h: 0.22,
        fontSize: 11, fontFace: "Consolas", color: C.cream,
        valign: "top", margin: 0,
      });
    });

    // Right: 3 feature blocks
    const right = [
      { num: "01", t: "3 tipuri reguli", d: "required_properties · naming_convention · forbidden_in_zone" },
      { num: "02", t: "Clash auto", d: "AABB geometric + Logic (GUID duplicat, supraincarcare)" },
      { num: "03", t: "Issue promotion", d: "Violation → IssueBIM oficial cu un click manager" },
    ];
    right.forEach((r, i) => {
      const y = 1.95 + i * 1.0;
      s.addText(r.num, { x: 5.4, y, w: 0.6, h: 0.5,
        fontSize: 28, color: C.gold, bold: true, fontFace: FONT_TITLE_FALLBACK,
        valign: "top", margin: 0 });
      s.addText(r.t, { x: 6.0, y: y + 0.05, w: 3.5, h: 0.35,
        fontSize: 14, color: C.navy, bold: true, fontFace: FONT_BODY,
        valign: "top", margin: 0 });
      s.addText(r.d, { x: 6.0, y: y + 0.4, w: 3.5, h: 0.6,
        fontSize: 10.5, color: C.muted, fontFace: FONT_BODY,
        valign: "top", margin: 0 });
    });

    addFooter(s, 9, TOTAL);
  }

  // ============================================================
  // SLIDE 10 — 4D + 5D
  // ============================================================
  {
    const s = pres.addSlide();
    addDarkBg(s);
    addSectionTitle(s, "09  ·  MODUL 06", "4D Schedule + 5D Cost.");

    // Two large panels side by side
    const panelY = 2.0, panelW = 4.6, panelH = 2.9;

    // LEFT: 4D
    s.addShape("rect", { x: 0.5, y: panelY, w: panelW, h: panelH, fill: { color: C.navyLight }, line: { color: C.gold, width: 0.75 } });
    s.addShape("rect", { x: 0.5, y: panelY, w: 0.06, h: panelH, fill: { color: C.gold }, line: { type: "none" } });
    s.addText("4D · SCHEDULE", { x: 0.7, y: panelY + 0.15, w: panelW - 0.4, h: 0.3,
      fontSize: 10, color: C.gold, bold: true, charSpacing: 6, fontFace: FONT_BODY, margin: 0, valign: "top" });
    s.addText("Construction\nsequencing.", { x: 0.7, y: panelY + 0.5, w: panelW - 0.4, h: 0.9,
      fontSize: 26, color: C.cream, fontFace: FONT_TITLE_FALLBACK, valign: "top", margin: 0 });
    const f4d = [
      "9 faze tipice (excavatie → finisaje)",
      "Gantt chart cu progres %",
      "Detectie automata intarzieri",
      "API: `visible-at` pentru viewer",
    ];
    f4d.forEach((f, i) => {
      const y = panelY + 1.5 + i * 0.32;
      s.addShape("rect", { x: 0.7, y: y + 0.12, w: 0.08, h: 0.08, fill: { color: C.gold }, line: { type: "none" } });
      s.addText(f, { x: 0.9, y, w: panelW - 0.6, h: 0.3,
        fontSize: 11, color: C.cream, fontFace: FONT_BODY, valign: "top", margin: 0 });
    });

    // RIGHT: 5D
    const rx = 5.4;
    s.addShape("rect", { x: rx, y: panelY, w: panelW, h: panelH, fill: { color: C.navyLight }, line: { color: C.gold, width: 0.75 } });
    s.addShape("rect", { x: rx, y: panelY, w: 0.06, h: panelH, fill: { color: C.gold }, line: { type: "none" } });
    s.addText("5D · COST", { x: rx + 0.2, y: panelY + 0.15, w: panelW - 0.4, h: 0.3,
      fontSize: 10, color: C.gold, bold: true, charSpacing: 6, fontFace: FONT_BODY, margin: 0, valign: "top" });
    s.addText("Plan vs. real,\nin timp real.", { x: rx + 0.2, y: panelY + 0.5, w: panelW - 0.4, h: 0.9,
      fontSize: 26, color: C.cream, fontFace: FONT_TITLE_FALLBACK, valign: "top", margin: 0 });
    const f5d = [
      "6 categorii (material · manopera · ...)",
      "Tip: planificat sau real (facturat)",
      "Agregare per disciplina · cladire · tip",
      "Delta plan vs real cu %",
    ];
    f5d.forEach((f, i) => {
      const y = panelY + 1.5 + i * 0.32;
      s.addShape("rect", { x: rx + 0.2, y: y + 0.12, w: 0.08, h: 0.08, fill: { color: C.gold }, line: { type: "none" } });
      s.addText(f, { x: rx + 0.4, y, w: panelW - 0.6, h: 0.3,
        fontSize: 11, color: C.cream, fontFace: FONT_BODY, valign: "top", margin: 0 });
    });

    addFooter(s, 10, TOTAL);
  }

  // ============================================================
  // SLIDE 11 — DIGITAL TWIN / IoT
  // ============================================================
  {
    const s = pres.addSlide();
    addCreamBg(s);
    addSectionTitle(s, "10  ·  MODUL 07", "Digital Twin / IoT.", { lightBg: true });

    // Large stat callout left
    s.addText("9", {
      x: 0.5, y: 1.85, w: 1.5, h: 1.8,
      fontSize: 130, color: C.gold, fontFace: FONT_TITLE_FALLBACK, bold: true,
      valign: "top", margin: 0,
    });
    s.addText("tipuri senzori", {
      x: 0.5, y: 3.4, w: 1.8, h: 0.4,
      fontSize: 13, color: C.navy, bold: true, fontFace: FONT_BODY,
      valign: "top", margin: 0,
    });
    s.addText("temperatura · umiditate · CO₂\nenergie · vibratie · ocupare\npresiune · debit · custom", {
      x: 0.5, y: 3.8, w: 2.5, h: 1.0,
      fontSize: 10, color: C.muted, fontFace: FONT_BODY,
      valign: "top", margin: 0, lineSpacingMultiple: 1.4,
    });

    // Right side: feature blocks 2x2
    const fy = 1.85, fw = 3.3, fh = 1.4;
    const features = [
      { t: "Token-auth ingest",   d: "POST /bim/api/sensors/ingest\nHeader X-Sensor-Token" },
      { t: "Time-series indexed", d: "(senzor_id, ts) — scaleaza\nla milioane de citiri" },
      { t: "Auto-alerts",         d: "Threshold violation →\nseveritate calculata" },
      { t: "Chart.js dashboards", d: "Raw / 1h / 1d aggregare\ncu linii threshold" },
    ];
    features.forEach((f, i) => {
      const col = i % 2, row = Math.floor(i / 2);
      const x = 3.5 + col * (fw + 0.12);
      const y = fy + row * (fh + 0.12);
      s.addShape("rect", { x, y, w: fw, h: fh, fill: { color: C.white }, line: { color: C.creamDim, width: 0.75 } });
      s.addShape("rect", { x, y, w: 0.04, h: fh, fill: { color: C.gold }, line: { type: "none" } });
      s.addText(f.t, { x: x + 0.2, y: y + 0.2, w: fw - 0.4, h: 0.4,
        fontSize: 13, color: C.navy, bold: true, fontFace: FONT_BODY, margin: 0, valign: "top" });
      s.addText(f.d, { x: x + 0.2, y: y + 0.6, w: fw - 0.4, h: 0.7,
        fontSize: 10, color: C.muted, fontFace: FONT_BODY, margin: 0, valign: "top", lineSpacingMultiple: 1.4 });
    });

    addFooter(s, 11, TOTAL);
  }

  // ============================================================
  // SLIDE 12 — REAL-TIME COLLAB + KANBAN
  // ============================================================
  {
    const s = pres.addSlide();
    addDarkBg(s);
    addSectionTitle(s, "11  ·  MODUL 08", "Real-time + Kanban.");

    // Headline
    s.addText("Colaborare multi-user fara WebSockets.", {
      x: 0.5, y: 2.0, w: 9, h: 0.5,
      fontSize: 22, color: C.cream, fontFace: FONT_TITLE_FALLBACK,
      valign: "top", margin: 0,
    });
    s.addText("Server-Sent Events + reconnect automat — compatibil cu orice hosting low-cost (PythonAnywhere, etc.)", {
      x: 0.5, y: 2.6, w: 9, h: 0.4,
      fontSize: 12, color: C.muted, fontFace: FONT_BODY,
      valign: "top", margin: 0,
    });

    // 4 feature cards horizontal
    const fy = 3.3, fw = 2.2, fh = 1.6;
    const features = [
      { t: "Kanban drag-drop", d: "5 coloane status\nworkflow native" },
      { t: "Comments live", d: "Sub-threads + SSE\nbroadcast la peers" },
      { t: "Presence",      d: "Heartbeat 30s\nlista \"online acum\"" },
      { t: "Event stream",  d: "/api/events/stream\ncu reconnect auto" },
    ];
    features.forEach((f, i) => {
      const x = 0.5 + i * (fw + 0.13);
      s.addShape("rect", { x, y: fy, w: fw, h: fh, fill: { color: C.navyLight }, line: { color: C.goldDark, width: 0.5 } });
      s.addShape("rect", { x, y: fy, w: fw, h: 0.04, fill: { color: C.gold }, line: { type: "none" } });
      s.addText(f.t, { x: x + 0.2, y: fy + 0.25, w: fw - 0.4, h: 0.4,
        fontSize: 13, color: C.gold, bold: true, fontFace: FONT_BODY, margin: 0, valign: "top" });
      s.addText(f.d, { x: x + 0.2, y: fy + 0.65, w: fw - 0.4, h: 0.9,
        fontSize: 11, color: C.cream, fontFace: FONT_BODY, margin: 0, valign: "top", lineSpacingMultiple: 1.4 });
    });

    addFooter(s, 12, TOTAL);
  }

  // ============================================================
  // SLIDE 13 — GOVERNANCE (RBAC + API + COBie + BCF)
  // ============================================================
  {
    const s = pres.addSlide();
    addCreamBg(s);
    addSectionTitle(s, "12  ·  MODUL 09", "Governance enterprise.", { lightBg: true });

    // 4 columns of governance features
    const features = [
      { num: "01", t: "RBAC fin", d: "7 roluri × 5 scopes:\nglobal / proiect /\nsantier / cladire /\ndisciplina" },
      { num: "02", t: "API tokens", d: "Bearer auth · scopes\nJSON · expiration\noptional. Suport pentru\nintegrari BI." },
      { num: "03", t: "COBie 2.4", d: "Excel cu 6 sheet-uri\npentru handover\nfacility management." },
      { num: "04", t: "BCF 2.1", d: "Round-trip complet:\nexport zip + import\nUPSERT pe topic GUID." },
    ];
    const fy = 1.95, fw = 2.18, fh = 2.9;
    features.forEach((f, i) => {
      const x = 0.5 + i * (fw + 0.13);
      s.addShape("rect", { x, y: fy, w: fw, h: fh, fill: { color: C.white }, line: { color: C.creamDim, width: 0.75 } });
      s.addShape("rect", { x, y: fy, w: fw, h: 0.04, fill: { color: C.gold }, line: { type: "none" } });

      s.addText(f.num, { x: x + 0.2, y: fy + 0.2, w: fw - 0.4, h: 0.3,
        fontSize: 10, color: C.gold, bold: true, charSpacing: 3, fontFace: FONT_BODY,
        margin: 0, valign: "top" });
      s.addText(f.t, { x: x + 0.2, y: fy + 0.55, w: fw - 0.4, h: 0.45,
        fontSize: 18, color: C.navy, bold: true, fontFace: FONT_TITLE_FALLBACK,
        margin: 0, valign: "top" });
      s.addText(f.d, { x: x + 0.2, y: fy + 1.1, w: fw - 0.4, h: 1.7,
        fontSize: 11, color: C.muted, fontFace: FONT_BODY,
        margin: 0, valign: "top", lineSpacingMultiple: 1.5 });
    });

    addFooter(s, 13, TOTAL);
  }

  // ============================================================
  // SLIDE 14 — STANDARDS COMPLIANCE
  // ============================================================
  {
    const s = pres.addSlide();
    addDarkBg(s);
    addSectionTitle(s, "13  ·  STANDARDS", "Open standards. By design.");

    // 4 standard badges in row
    const badges = [
      { code: "ISO 19650", desc: "Common Data Environment workflow" },
      { code: "IFC 4",     desc: "Native parser ifcopenshell" },
      { code: "BCF 2.1",   desc: "Round-trip import + export" },
      { code: "COBie 2.4", desc: "Facility management handover" },
    ];
    badges.forEach((b, i) => {
      const x = 0.5 + i * 2.35;
      // Circle badge
      s.addShape("ellipse", { x: x + 0.5, y: 2.1, w: 1.3, h: 1.3, fill: { color: C.gold }, line: { type: "none" } });
      // Inner ring
      s.addShape("ellipse", { x: x + 0.7, y: 2.3, w: 0.9, h: 0.9, fill: { color: C.navy }, line: { type: "none" } });
      s.addText(b.code, { x, y: 2.5, w: 2.3, h: 0.5,
        fontSize: 13, color: C.gold, bold: true, fontFace: FONT_BODY,
        align: "center", valign: "middle", margin: 0, charSpacing: 2 });

      // Title under badge
      s.addText(b.code.split(" ")[0], { x, y: 3.7, w: 2.3, h: 0.4,
        fontSize: 16, color: C.cream, bold: true, fontFace: FONT_TITLE_FALLBACK,
        align: "center", margin: 0 });
      s.addText(b.desc, { x: x + 0.15, y: 4.1, w: 2.0, h: 0.7,
        fontSize: 10, color: C.muted, fontFace: FONT_BODY,
        align: "center", margin: 0, lineSpacingMultiple: 1.4 });
    });

    addFooter(s, 14, TOTAL);
  }

  // ============================================================
  // SLIDE 15 — TECH STACK
  // ============================================================
  {
    const s = pres.addSlide();
    addCreamBg(s);
    addSectionTitle(s, "14  ·  TECH STACK", "Modern. Maintainable.", { lightBg: true });

    const groups = [
      { cat: "BACKEND",    items: ["Python 3.11", "Flask 3.x", "SQLAlchemy 2.x", "Alembic", "Flask-Login", "Flask-WTF"] },
      { cat: "DATABASE",   items: ["SQLite (dev)", "MySQL (prod)", "8 migrations", "tenant-aware"] },
      { cat: "FRONTEND",   items: ["Jinja2", "Inter + Cinzel", "Chart.js 4.4", "xeokit-sdk", "Font Awesome 6"] },
      { cat: "BIM / IO",   items: ["ifcopenshell", "openpyxl (COBie)", "BCF 2.1 XML", "OpenAPI 3.0"] },
      { cat: "INFRA / PWA", items: ["HTTPS Let's Encrypt", "PWA install", "Service Worker", "Self-hosted"] },
      { cat: "QUALITY",    items: ["401 tests pytest", "Playwright E2E", "GitHub Actions CI", "Audit log"] },
    ];

    const gy = 1.85, gw = 2.95, gh = 1.45;
    groups.forEach((g, i) => {
      const col = i % 3, row = Math.floor(i / 3);
      const x = 0.5 + col * (gw + 0.13);
      const y = gy + row * (gh + 0.13);
      s.addShape("rect", { x, y, w: gw, h: gh, fill: { color: C.white }, line: { color: C.creamDim, width: 0.5 } });
      s.addShape("rect", { x, y, w: 0.04, h: gh, fill: { color: C.gold }, line: { type: "none" } });
      s.addText(g.cat, { x: x + 0.2, y: y + 0.15, w: gw - 0.4, h: 0.3,
        fontSize: 9.5, color: C.gold, bold: true, charSpacing: 5, fontFace: FONT_BODY,
        margin: 0, valign: "top" });
      // Items
      s.addText(
        g.items.map((it, idx) => ({ text: it + (idx < g.items.length - 1 ? "  ·  " : ""), options: {} })),
        { x: x + 0.2, y: y + 0.5, w: gw - 0.4, h: gh - 0.6,
          fontSize: 10, color: C.navy, fontFace: FONT_BODY,
          margin: 0, valign: "top", lineSpacingMultiple: 1.5 }
      );
    });

    addFooter(s, 15, TOTAL);
  }

  // ============================================================
  // SLIDE 16 — SECURITY
  // ============================================================
  {
    const s = pres.addSlide();
    addDarkBg(s);
    addSectionTitle(s, "15  ·  SECURITY", "Security by default.");

    const items = [
      { num: "01", t: "HTTPS Let's Encrypt", d: "Auto-renew 90 zile · Force HTTPS · TLS 1.3" },
      { num: "02", t: "Audit log complet",   d: "Cine, ce, cand · diff old/new values · context request" },
      { num: "03", t: "RBAC fin pe scope",    d: "Roluri pe disciplina · santier · cladire · proiect" },
      { num: "04", t: "Multi-tenant isolation", d: "Row-level scoping · tenant_id pe toate tabelele BIM" },
      { num: "05", t: "Password hashing",     d: "Werkzeug + bcrypt-style salt · rate-limit login 5/15min" },
      { num: "06", t: "CSRF + Security headers", d: "Flask-WTF · X-Frame-Options · CSP-ready · token IoT exempt" },
    ];
    items.forEach((it, i) => {
      const col = i % 2, row = Math.floor(i / 2);
      const x = 0.5 + col * 4.7;
      const y = 2.0 + row * 1.05;
      // Big number
      s.addText(it.num, { x, y, w: 0.7, h: 0.7,
        fontSize: 32, color: C.gold, bold: true, fontFace: FONT_TITLE_FALLBACK,
        valign: "top", margin: 0 });
      s.addText(it.t, { x: x + 0.75, y: y + 0.05, w: 4.0, h: 0.4,
        fontSize: 14, color: C.cream, bold: true, fontFace: FONT_BODY,
        valign: "top", margin: 0 });
      s.addText(it.d, { x: x + 0.75, y: y + 0.4, w: 4.0, h: 0.55,
        fontSize: 10.5, color: C.muted, fontFace: FONT_BODY,
        valign: "top", margin: 0 });
    });

    addFooter(s, 16, TOTAL);
  }

  // ============================================================
  // SLIDE 17 — MOBILE PWA
  // ============================================================
  {
    const s = pres.addSlide();
    addCreamBg(s);
    addSectionTitle(s, "16  ·  MOBILE", "Install ca app nativa.", { lightBg: true });

    // Left: stat + description
    s.addText("0", {
      x: 0.5, y: 1.85, w: 1.8, h: 1.6,
      fontSize: 140, color: C.gold, bold: true, fontFace: FONT_TITLE_FALLBACK,
      margin: 0, valign: "top",
    });
    s.addText("App Store fees", {
      x: 0.5, y: 3.45, w: 2.5, h: 0.4,
      fontSize: 14, color: C.navy, bold: true, fontFace: FONT_BODY,
      margin: 0, valign: "top",
    });
    s.addText("Edifico se instaleaza ca\nProgressive Web App direct\ndin browser — iOS Safari +\nAndroid Chrome.", {
      x: 0.5, y: 3.85, w: 3.0, h: 1.1,
      fontSize: 11, color: C.muted, fontFace: FONT_BODY,
      margin: 0, valign: "top", lineSpacingMultiple: 1.5,
    });

    // Right: 3 PWA features
    const features = [
      { t: "Native icon",   d: "Logo Edifico gold pe navy in home screen" },
      { t: "Standalone",    d: "Ruleaza fara bara browser, ca app nativa" },
      { t: "Offline mode",  d: "Service Worker cache + offline page premium" },
      { t: "Auto-update",   d: "Versiune noua → detectata + aplicata instant" },
    ];
    features.forEach((f, i) => {
      const y = 1.85 + i * 0.78;
      s.addShape("ellipse", { x: 4.0, y: y + 0.05, w: 0.45, h: 0.45, fill: { color: C.gold }, line: { type: "none" } });
      s.addText(String(i + 1), { x: 4.0, y: y + 0.05, w: 0.45, h: 0.45,
        fontSize: 16, color: C.navy, bold: true, fontFace: FONT_BODY,
        align: "center", valign: "middle", margin: 0 });
      s.addText(f.t, { x: 4.6, y: y + 0.05, w: 5.0, h: 0.35,
        fontSize: 13, color: C.navy, bold: true, fontFace: FONT_BODY,
        valign: "top", margin: 0 });
      s.addText(f.d, { x: 4.6, y: y + 0.4, w: 5.0, h: 0.3,
        fontSize: 10.5, color: C.muted, fontFace: FONT_BODY,
        valign: "top", margin: 0 });
    });

    addFooter(s, 17, TOTAL);
  }

  // ============================================================
  // SLIDE 18 — STATISTICS / BY THE NUMBERS
  // ============================================================
  {
    const s = pres.addSlide();
    addDarkBg(s);
    addSectionTitle(s, "17  ·  BY THE NUMBERS", "Built carefully.");

    const stats = [
      { v: "8", l: "module integrate",   sub: "workforce → governance" },
      { v: "8", l: "DB migrations",      sub: "Alembic incremental safe" },
      { v: "401", l: "tests verzi",      sub: "unit + integration + E2E" },
      { v: "16+", l: "servicii cross-cutting", sub: "audit · rbac · iot · realtime ..." },
      { v: "0", l: "vendor lock-in",     sub: "stack 100% open-source" },
      { v: "10", l: "minute ca sa pornesti", sub: "self-hosted, MySQL sau SQLite" },
    ];
    const sy = 2.0, sw = 3.0, sh = 1.45;
    stats.forEach((st, i) => {
      const col = i % 3, row = Math.floor(i / 3);
      const x = 0.5 + col * (sw + 0.15);
      const y = sy + row * (sh + 0.15);
      s.addShape("rect", { x, y, w: sw, h: sh, fill: { color: C.navyLight }, line: { color: C.goldDark, width: 0.5 } });
      s.addText(st.v, { x: x + 0.2, y: y + 0.15, w: sw - 0.4, h: 0.85,
        fontSize: 52, color: C.gold, bold: true, fontFace: FONT_TITLE_FALLBACK,
        margin: 0, valign: "top" });
      s.addText(st.l, { x: x + 0.2, y: y + 0.95, w: sw - 0.4, h: 0.3,
        fontSize: 12, color: C.cream, bold: true, fontFace: FONT_BODY,
        margin: 0, valign: "top" });
      s.addText(st.sub, { x: x + 0.2, y: y + 1.2, w: sw - 0.4, h: 0.25,
        fontSize: 9.5, color: C.muted, fontFace: FONT_BODY,
        margin: 0, valign: "top" });
    });

    addFooter(s, 18, TOTAL);
  }

  // ============================================================
  // SLIDE 19 — WHY EDIFICO
  // ============================================================
  {
    const s = pres.addSlide();
    addCreamBg(s);
    addSectionTitle(s, "18  ·  POSITIONING", "Why Edifico?", { lightBg: true });

    // Comparison table
    const rows = [
      ["",                "EDIFICO",         "Autodesk Construction Cloud",  "Solibri + BIM Collab"],
      ["Workforce",       "✓ Native",         "Limited",                       "—"],
      ["BIM Viewer",      "✓ Open + APS",     "✓ APS only",                    "✓"],
      ["Digital Twin / IoT", "✓ Integrat",    "Limited",                       "—"],
      ["Self-hosted",     "✓ Da",             "—",                             "—"],
      ["Pret ~",          "Self-hosted",      "€100+ / user / luna",           "€500+ / luna"],
    ];

    const tStartY = 1.85;
    const colWidths = [2.3, 2.0, 2.6, 2.6];
    const rowH = 0.45;

    rows.forEach((row, ri) => {
      let xCursor = 0.5;
      row.forEach((cell, ci) => {
        const isHeader = ri === 0;
        const isEdifico = ci === 1;
        const bg = isHeader ? C.navy : (ri % 2 === 0 ? C.white : C.creamDim);
        const fg = isHeader ? C.gold : (isEdifico ? C.gold : C.navy);
        const bold = isHeader || isEdifico;
        s.addShape("rect", { x: xCursor, y: tStartY + ri * rowH, w: colWidths[ci], h: rowH,
          fill: { color: bg }, line: { color: C.creamDim, width: 0.5 } });
        if (isEdifico && !isHeader) {
          s.addShape("rect", { x: xCursor, y: tStartY + ri * rowH, w: 0.05, h: rowH,
            fill: { color: C.gold }, line: { type: "none" } });
        }
        s.addText(cell, {
          x: xCursor + 0.2, y: tStartY + ri * rowH, w: colWidths[ci] - 0.3, h: rowH,
          fontSize: ci === 0 ? 11 : 12, color: fg, bold,
          fontFace: FONT_BODY, valign: "middle", margin: 0,
        });
        xCursor += colWidths[ci];
      });
    });

    // Bottom note
    s.addText("Edifico nu inlocuieste enterprise tools high-end. Le face accesibile pentru cei care nu si-le permit.", {
      x: 0.5, y: 4.85, w: 9, h: 0.4, fontSize: 11, italic: true,
      color: C.muted, fontFace: FONT_BODY, align: "center", margin: 0,
    });

    addFooter(s, 19, TOTAL);
  }

  // ============================================================
  // SLIDE 20 — CTA / GET STARTED
  // ============================================================
  {
    const s = pres.addSlide();
    addDarkBg(s);

    // Decorative top + bottom gold bands
    s.addShape("rect", { x: 0, y: 0, w: 10, h: 0.08, fill: { color: C.gold }, line: { type: "none" } });
    s.addShape("rect", { x: 0, y: 5.55, w: 10, h: 0.08, fill: { color: C.gold }, line: { type: "none" } });

    // Big "E" backdrop
    s.addText("E", {
      x: 7.5, y: 0.5, w: 2.5, h: 4.5,
      fontSize: 360, color: C.navyLight, fontFace: FONT_TITLE_FALLBACK,
      italic: true, bold: true, align: "center", valign: "middle", margin: 0,
    });

    // Main message
    s.addText("ONE PLATFORM ·  ALL YOUR SITES", {
      x: 0.5, y: 0.9, w: 8, h: 0.4, fontSize: 11, charSpacing: 8,
      color: C.gold, bold: true, fontFace: FONT_BODY, margin: 0, valign: "top",
    });

    s.addText("Hai sa\nincepi.", {
      x: 0.5, y: 1.4, w: 7, h: 2.4, fontSize: 92,
      color: C.cream, fontFace: FONT_TITLE_FALLBACK,
      margin: 0, valign: "top", lineSpacingMultiple: 0.95,
    });

    // Gold line divider
    s.addShape("rect", { x: 0.5, y: 4.0, w: 2.0, h: 0.025, fill: { color: C.gold }, line: { type: "none" } });

    s.addText("www.edifico.space", {
      x: 0.5, y: 4.2, w: 6, h: 0.45, fontSize: 22,
      color: C.gold, bold: true, fontFace: FONT_BODY,
      margin: 0, valign: "top", charSpacing: 1,
    });

    s.addText("Self-hosted · Open standards · 8 module integrate", {
      x: 0.5, y: 4.75, w: 8, h: 0.3, fontSize: 11,
      color: C.muted, fontFace: FONT_BODY, charSpacing: 3,
      margin: 0, valign: "top",
    });
  }

  // ===== Save =====
  await pres.writeFile({ fileName: "edifico_pitch.pptx" });
  console.log("Done: edifico_pitch.pptx");
}

build().catch((err) => {
  console.error(err);
  process.exit(1);
});
