#!/bin/bash
echo "============================================================"
echo "  EDIFICO WORKFORCE - Instalare automata"
echo "  Sistem de Management al Fortei de Munca in Constructii"
echo "============================================================"
echo ""

# Verificare Python
if ! command -v python3 &> /dev/null; then
    echo "[EROARE] Python3 nu este instalat!"
    echo "Instalati Python3: sudo apt install python3 python3-venv python3-pip"
    exit 1
fi

# Creare mediu virtual
echo "[1/4] Creez mediul virtual..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "[OK] Mediu virtual creat."
else
    echo "[INFO] Mediul virtual exista deja."
fi

# Activare mediu virtual
echo "[2/4] Activez mediul virtual..."
source venv/bin/activate

# Instalare dependente
echo "[3/4] Instalez dependentele..."
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "[EROARE] Instalarea dependentelor a esuat!"
    exit 1
fi
echo "[OK] Dependente instalate."

# Initializare baza de date
echo "[4/4] Initializez baza de date cu date demo..."
export FLASK_APP=app.py
flask init-db
echo "[OK] Baza de date initializata."

echo ""
echo "============================================================"
echo "  INSTALARE COMPLETA!"
echo ""
echo "  Pentru a porni aplicatia:"
echo "    1. Activati mediul virtual: source venv/bin/activate"
echo "    2. Rulati: python app.py"
echo "    3. Deschideti: http://localhost:5000"
echo ""
echo "  Conturi demo:"
echo "    Admin:    admin@edifico.ro / admin123"
echo "    Manager:  manager@edifico.ro / manager123"
echo "    Operator: operator@edifico.ro / op123"
echo "============================================================"
echo ""
