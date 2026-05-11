@echo off
echo ============================================================
echo   EDIFICO WORKFORCE - Instalare automata
echo   Sistem de Management al Fortei de Munca in Constructii
echo ============================================================
echo.

:: Verificare Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [EROARE] Python nu este instalat sau nu este in PATH!
    echo Descarcati Python de la: https://www.python.org/downloads/
    pause
    exit /b 1
)

:: Creare mediu virtual
echo [1/4] Creez mediul virtual...
if not exist "venv" (
    python -m venv venv
    echo [OK] Mediu virtual creat.
) else (
    echo [INFO] Mediul virtual exista deja.
)

:: Activare mediu virtual
echo [2/4] Activez mediul virtual...
call venv\Scripts\activate.bat

:: Instalare dependente
echo [3/4] Instalez dependentele...
pip install -r requirements.txt
if errorlevel 1 (
    echo [EROARE] Instalarea dependentelor a esuat!
    pause
    exit /b 1
)
echo [OK] Dependente instalate.

:: Initializare baza de date
echo [4/4] Initializez baza de date cu date demo...
set FLASK_APP=app.py
flask init-db
echo [OK] Baza de date initializata.

echo.
echo ============================================================
echo   INSTALARE COMPLETA!
echo.
echo   Pentru a porni aplicatia:
echo     1. Activati mediul virtual: venv\Scripts\activate.bat
echo     2. Rulati: python app.py
echo     3. Deschideti: http://localhost:5000
echo.
echo   Conturi demo:
echo     Admin:    admin@edifico.ro / admin123
echo     Manager:  manager@edifico.ro / manager123
echo     Operator: operator@edifico.ro / op123
echo ============================================================
echo.
pause
