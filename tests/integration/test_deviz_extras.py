"""Test parser „deviz F3 cu extrase" (capitole + sub-articole + material:/manopera:/utilaj:)."""

CSV = (
    "Nr;Capitol de lucrari;U.M.;Cantitatea;;Pretul unitar;TOTALUL\n"
    "0;1;2;3;;4;5 = 3 x 4\n"
    "1;CODA - Capitol cu copii;mp;100;;200;20000\n"
    ";;;material:;;150;15000\n"
    ";;;manopera:;;50;5000\n"
    "1.1;Vata material X;mp;100;;150;15000\n"
    "1.2;Zugrav munca;ora;200;;30;6000\n"
    "2;CODB - Capitol fara copii;mp;10;;100;1000\n"
    ";;;material:;;60;600\n"
    ";;;manopera:;;40;400\n"
).encode("utf-8")


def test_import_deviz_cu_extrase(app):
    from services.gantt import import_engine
    from services.gantt.pipeline import MotorPlanificare
    with app.app_context():
        arts, _ = import_engine.importa(CSV, '.csv', MotorPlanificare().setari)
    cods = {a.cod_articol: a for a in arts}
    # capitolul 1 are sub-articole -> NU e activitate; 1.1 si 1.2 sunt activitati
    assert '1.1' in cods and '1.2' in cods and '1' not in cods
    assert cods['1.1'].tronson.startswith('CODA')          # grupate sub capitol
    # UM 'ora' -> manopera; altfel material
    assert cods['1.2'].pret_manopera == 30 and cods['1.1'].pret_material == 150
    # capitolul 2 fara copii -> emis ca activitate, cu M/m din sub-randuri
    assert '2' in cods
    assert cods['2'].pret_material == 60 and cods['2'].pret_manopera == 40


def test_format_plat_neschimbat(app):
    """Fara sub-randuri material:/manopera:, comportamentul ramane flat (toate randurile)."""
    from services.gantt import import_engine
    from services.gantt.pipeline import MotorPlanificare
    csv = (b"cod_articol;denumire;um;cantitate;pret unitar\n"
           b"A1;Sapatura;mc;100;35\n"
           b"A2;Pozare conducta;m;200;50\n")
    with app.app_context():
        arts, _ = import_engine.importa(csv, '.csv', MotorPlanificare().setari)
    cods = {a.cod_articol for a in arts}
    assert 'A1' in cods and 'A2' in cods and len(arts) == 2   # ambele = activitati
