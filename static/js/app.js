/**
 * EDIFICO WORKFORCE - JavaScript principal
 * Sistem de Management al Fortei de Munca in Constructii
 */

document.addEventListener('DOMContentLoaded', function() {

    // ============================================================
    // Auto-dismiss alerts dupa 5 secunde
    // ============================================================
    const alerts = document.querySelectorAll('.alert:not(.alert-permanent)');
    alerts.forEach(function(alert) {
        setTimeout(function() {
            const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
            if (bsAlert) {
                bsAlert.close();
            }
        }, 5000);
    });

    // ============================================================
    // Confirmare stergere
    // ============================================================
    document.querySelectorAll('[data-confirm]').forEach(function(el) {
        el.addEventListener('click', function(e) {
            const message = this.getAttribute('data-confirm') || 'Sunteti sigur?';
            if (!confirm(message)) {
                e.preventDefault();
                return false;
            }
        });
    });

    // Confirmare submit form
    document.querySelectorAll('form[data-confirm]').forEach(function(form) {
        form.addEventListener('submit', function(e) {
            const message = this.getAttribute('data-confirm') || 'Sunteti sigur?';
            if (!confirm(message)) {
                e.preventDefault();
                return false;
            }
        });
    });

    // ============================================================
    // Calcul automat ore pontaj
    // ============================================================
    const oraStart = document.getElementById('ora_start');
    const oraSfarsit = document.getElementById('ora_sfarsit');
    const oreLucrateDisplay = document.getElementById('ore_calculate');

    function calculeazaOre() {
        if (oraStart && oraSfarsit && oreLucrateDisplay) {
            const start = oraStart.value;
            const sfarsit = oraSfarsit.value;
            if (start && sfarsit) {
                const [h1, m1] = start.split(':').map(Number);
                const [h2, m2] = sfarsit.split(':').map(Number);
                let totalMin = (h2 * 60 + m2) - (h1 * 60 + m1);
                if (totalMin < 0) totalMin += 24 * 60;
                const ore = (totalMin / 60).toFixed(2);
                oreLucrateDisplay.textContent = ore + ' ore';

                const oreNormale = Math.min(8, ore);
                const oreSupl = Math.max(0, ore - 8);
                const displayNorm = document.getElementById('ore_normale_display');
                const displaySupl = document.getElementById('ore_supl_display');
                if (displayNorm) displayNorm.textContent = oreNormale.toFixed(2) + 'h';
                if (displaySupl) displaySupl.textContent = oreSupl.toFixed(2) + 'h';
            }
        }
    }

    if (oraStart) oraStart.addEventListener('change', calculeazaOre);
    if (oraSfarsit) oraSfarsit.addEventListener('change', calculeazaOre);

    // ============================================================
    // Validare CNP (13 cifre)
    // ============================================================
    const cnpInput = document.getElementById('cnp');
    if (cnpInput) {
        cnpInput.addEventListener('input', function() {
            this.value = this.value.replace(/\D/g, '').substring(0, 13);
            if (this.value.length === 13) {
                this.classList.remove('is-invalid');
                this.classList.add('is-valid');
            } else if (this.value.length > 0) {
                this.classList.remove('is-valid');
                this.classList.add('is-invalid');
            } else {
                this.classList.remove('is-valid', 'is-invalid');
            }
        });
    }

    // ============================================================
    // Validare telefon
    // ============================================================
    const telInput = document.getElementById('telefon');
    if (telInput) {
        telInput.addEventListener('input', function() {
            this.value = this.value.replace(/[^\d+\-\s]/g, '').substring(0, 15);
        });
    }

    // ============================================================
    // Formatare salariu
    // ============================================================
    const salariuInput = document.getElementById('salariu_baza');
    if (salariuInput) {
        salariuInput.addEventListener('blur', function() {
            const val = parseFloat(this.value);
            if (!isNaN(val) && val > 0) {
                const tarifOrar = (val / 168).toFixed(2);
                const tarifDisplay = document.getElementById('tarif_orar_display');
                if (tarifDisplay) {
                    tarifDisplay.textContent = tarifOrar + ' RON/ora';
                }
            }
        });
        // Trigger pe load
        salariuInput.dispatchEvent(new Event('blur'));
    }

    // ============================================================
    // Toggle vizibilitate parola
    // ============================================================
    document.querySelectorAll('.toggle-password').forEach(function(btn) {
        btn.addEventListener('click', function() {
            const input = document.querySelector(this.getAttribute('data-target'));
            if (input) {
                if (input.type === 'password') {
                    input.type = 'text';
                    this.innerHTML = '<i class="bi bi-eye-slash"></i>';
                } else {
                    input.type = 'password';
                    this.innerHTML = '<i class="bi bi-eye"></i>';
                }
            }
        });
    });

    // ============================================================
    // Cautare cu debounce in tabele
    // ============================================================
    const searchInputs = document.querySelectorAll('[data-search-table]');
    searchInputs.forEach(function(input) {
        let timeout;
        input.addEventListener('input', function() {
            clearTimeout(timeout);
            timeout = setTimeout(function() {
                const tableId = input.getAttribute('data-search-table');
                const table = document.getElementById(tableId);
                if (!table) return;

                const filter = input.value.toLowerCase();
                const rows = table.querySelectorAll('tbody tr');
                rows.forEach(function(row) {
                    const text = row.textContent.toLowerCase();
                    row.style.display = text.includes(filter) ? '' : 'none';
                });
            }, 300);
        });
    });

    // ============================================================
    // Scroll to top button
    // ============================================================
    const scrollBtn = document.createElement('div');
    scrollBtn.className = 'scroll-to-top';
    scrollBtn.innerHTML = '<i class="bi bi-arrow-up"></i>';
    document.body.appendChild(scrollBtn);

    window.addEventListener('scroll', function() {
        scrollBtn.style.display = window.scrollY > 300 ? 'flex' : 'none';
    });

    scrollBtn.addEventListener('click', function() {
        window.scrollTo({ top: 0, behavior: 'smooth' });
    });

    // ============================================================
    // Tooltips Bootstrap
    // ============================================================
    const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    tooltipTriggerList.forEach(function(el) {
        new bootstrap.Tooltip(el);
    });

    // ============================================================
    // Data curenta autocompletare
    // ============================================================
    const dataInputs = document.querySelectorAll('input[type="date"][data-today]');
    dataInputs.forEach(function(input) {
        if (!input.value) {
            const today = new Date().toISOString().split('T')[0];
            input.value = today;
        }
    });

    // ============================================================
    // Print page
    // ============================================================
    document.querySelectorAll('[data-print]').forEach(function(btn) {
        btn.addEventListener('click', function() {
            window.print();
        });
    });

    console.log('EDIFICO WORKFORCE - Aplicatie incarcata cu succes.');
});
