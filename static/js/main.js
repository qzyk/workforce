/**
 * EDIFICO WORKFORCE v2.0 - JavaScript Principal
 * Sidebar, notificari, modal stergere, clock live, toast, auto-refresh
 */

(function() {
    'use strict';

    // ============================================================
    // SIDEBAR TOGGLE (mobil)
    // ============================================================
    const sidebar = document.getElementById('sidebar');
    const sidebarToggle = document.getElementById('sidebarToggle');
    const sidebarOverlay = document.getElementById('sidebarOverlay');

    function openSidebar() {
        if (sidebar) {
            sidebar.classList.add('open');
            if (sidebarOverlay) sidebarOverlay.classList.add('show');
            document.body.style.overflow = 'hidden';
        }
    }

    function closeSidebar() {
        if (sidebar) {
            sidebar.classList.remove('open');
            if (sidebarOverlay) sidebarOverlay.classList.remove('show');
            document.body.style.overflow = '';
        }
    }

    if (sidebarToggle) {
        sidebarToggle.addEventListener('click', function(e) {
            e.stopPropagation();
            if (sidebar.classList.contains('open')) {
                closeSidebar();
            } else {
                openSidebar();
            }
        });
    }

    if (sidebarOverlay) {
        sidebarOverlay.addEventListener('click', closeSidebar);
    }

    // ============================================================
    // NOTIFICATION DROPDOWN
    // ============================================================
    const notifBtn = document.getElementById('notifBtn');
    const notifDropdown = document.getElementById('notifDropdown');

    if (notifBtn && notifDropdown) {
        notifBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            notifDropdown.classList.toggle('show');
            // Close user dropdown
            const ud = document.getElementById('userDropdown');
            if (ud) ud.classList.remove('show');
        });
    }

    // ============================================================
    // USER MENU DROPDOWN
    // ============================================================
    const userMenuBtn = document.getElementById('userMenuBtn');
    const userDropdown = document.getElementById('userDropdown');

    if (userMenuBtn && userDropdown) {
        userMenuBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            userDropdown.classList.toggle('show');
            // Close notif dropdown
            if (notifDropdown) notifDropdown.classList.remove('show');
        });
    }

    // Close dropdowns on outside click
    document.addEventListener('click', function() {
        if (notifDropdown) notifDropdown.classList.remove('show');
        if (userDropdown) userDropdown.classList.remove('show');
    });

    // ============================================================
    // LIVE CLOCK IN HEADER
    // ============================================================
    const clockEl = document.getElementById('liveClock');

    function updateClock() {
        if (clockEl) {
            const now = new Date();
            const days = ['Duminica', 'Luni', 'Marti', 'Miercuri', 'Joi', 'Vineri', 'Sambata'];
            const day = days[now.getDay()];
            const dd = String(now.getDate()).padStart(2, '0');
            const mm = String(now.getMonth() + 1).padStart(2, '0');
            const yyyy = now.getFullYear();
            const hh = String(now.getHours()).padStart(2, '0');
            const min = String(now.getMinutes()).padStart(2, '0');
            const ss = String(now.getSeconds()).padStart(2, '0');
            clockEl.textContent = day + ', ' + dd + '.' + mm + '.' + yyyy + ' ' + hh + ':' + min + ':' + ss;
        }
    }

    updateClock();
    setInterval(updateClock, 1000);

    // ============================================================
    // FLASH MESSAGES AUTO-DISMISS
    // ============================================================
    document.querySelectorAll('.flash-message').forEach(function(msg) {
        setTimeout(function() {
            msg.style.animation = 'slideOut 0.3s ease forwards';
            setTimeout(function() { msg.remove(); }, 300);
        }, 5000);
    });

    // ============================================================
    // TOAST NOTIFICATIONS
    // ============================================================
    window.showToast = function(message, type) {
        type = type || 'info';
        const container = document.getElementById('toastContainer');
        if (!container) return;

        const icons = {
            success: 'fa-circle-check',
            danger: 'fa-circle-xmark',
            warning: 'fa-triangle-exclamation',
            info: 'fa-circle-info'
        };

        const toast = document.createElement('div');
        toast.className = 'toast toast-' + type;
        toast.innerHTML =
            '<i class="fa-solid ' + (icons[type] || icons.info) + '"></i>' +
            '<span>' + message + '</span>' +
            '<button class="toast-close" onclick="this.parentElement.remove()">&times;</button>';

        container.appendChild(toast);

        // Auto-remove after 5 seconds
        setTimeout(function() {
            toast.style.animation = 'slideOut 0.3s ease forwards';
            setTimeout(function() { toast.remove(); }, 300);
        }, 5000);
    };

    // ============================================================
    // CONFIRM DELETE MODAL
    // ============================================================
    window.confirmDelete = function(url, message) {
        message = message || 'Sunteti sigur ca doriti sa stergeti acest element? Aceasta actiune este ireversibila.';
        const modal = document.getElementById('deleteModal');
        const form = document.getElementById('deleteModalForm');
        const msgEl = document.getElementById('deleteModalMessage');

        if (modal && form && msgEl) {
            msgEl.textContent = message;
            form.action = url;
            modal.classList.add('show');
        }
    };

    window.closeDeleteModal = function() {
        const modal = document.getElementById('deleteModal');
        if (modal) modal.classList.remove('show');
    };

    // Close modal on overlay click
    const deleteModal = document.getElementById('deleteModal');
    if (deleteModal) {
        deleteModal.addEventListener('click', function(e) {
            if (e.target === deleteModal) {
                closeDeleteModal();
            }
        });
    }

    // Escape key closes modal
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            closeDeleteModal();
            closeSidebar();
            if (notifDropdown) notifDropdown.classList.remove('show');
            if (userDropdown) userDropdown.classList.remove('show');
        }
    });

    // ============================================================
    // LOADING OVERLAY
    // ============================================================
    window.showLoading = function() {
        const overlay = document.getElementById('loadingOverlay');
        if (overlay) overlay.classList.add('show');
    };

    window.hideLoading = function() {
        const overlay = document.getElementById('loadingOverlay');
        if (overlay) overlay.classList.remove('show');
    };

    // ============================================================
    // AUTO-REFRESH DASHBOARD (every 5 minutes)
    // ============================================================
    if (window.location.pathname === '/' || window.location.pathname === '/dashboard') {
        setInterval(function() {
            fetch('/api/dashboard-stats')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    // Update stat values if elements exist
                    var statCards = document.querySelectorAll('.stat-value');
                    if (statCards.length >= 4) {
                        statCards[0].textContent = data.angajati_activi;
                        statCards[1].textContent = data.proiecte_active;
                        statCards[2].textContent = Math.round(data.ore_luna);
                        statCards[3].textContent = data.doc_expirate;
                    }
                })
                .catch(function() { /* silently fail */ });
        }, 5 * 60 * 1000); // 5 minutes
    }

    // ============================================================
    // TABLE ROW HIGHLIGHT ON HOVER (done via CSS, but add click)
    // ============================================================
    document.querySelectorAll('.data-table tbody tr').forEach(function(row) {
        row.addEventListener('click', function(e) {
            // Don't trigger if clicking a button, link, or form
            if (e.target.closest('a, button, form, .actions-cell')) return;
            // Find first link in the row
            var link = row.querySelector('a');
            if (link) window.location.href = link.href;
        });
        row.style.cursor = 'pointer';
    });

    // ============================================================
    // SORTABLE TABLE COLUMNS
    // ============================================================
    document.querySelectorAll('.data-table thead th.sortable').forEach(function(th) {
        th.addEventListener('click', function() {
            var table = th.closest('table');
            var tbody = table.querySelector('tbody');
            var rows = Array.from(tbody.querySelectorAll('tr'));
            var colIndex = Array.from(th.parentNode.children).indexOf(th);
            var ascending = !th.classList.contains('sort-asc');

            // Remove sort classes from all headers
            th.parentNode.querySelectorAll('th').forEach(function(h) {
                h.classList.remove('sort-asc', 'sort-desc');
            });
            th.classList.add(ascending ? 'sort-asc' : 'sort-desc');

            rows.sort(function(a, b) {
                var aVal = a.children[colIndex].textContent.trim();
                var bVal = b.children[colIndex].textContent.trim();
                // Try numeric sort
                var aNum = parseFloat(aVal.replace(/[^\d.-]/g, ''));
                var bNum = parseFloat(bVal.replace(/[^\d.-]/g, ''));
                if (!isNaN(aNum) && !isNaN(bNum)) {
                    return ascending ? aNum - bNum : bNum - aNum;
                }
                return ascending ? aVal.localeCompare(bVal, 'ro') : bVal.localeCompare(aVal, 'ro');
            });

            rows.forEach(function(row) { tbody.appendChild(row); });
        });
    });

    // ============================================================
    // FORM CONFIRMATIONS (data-confirm attribute)
    // ============================================================
    document.querySelectorAll('[data-confirm]').forEach(function(el) {
        el.addEventListener('click', function(e) {
            if (!confirm(this.getAttribute('data-confirm'))) {
                e.preventDefault();
            }
        });
    });

    document.querySelectorAll('form[data-confirm]').forEach(function(form) {
        form.addEventListener('submit', function(e) {
            if (!confirm(this.getAttribute('data-confirm'))) {
                e.preventDefault();
            }
        });
    });

    // ============================================================
    // INIT LOG
    // ============================================================
    console.log('%cEDIFICO WORKFORCE v2.0', 'color: #1a237e; font-size: 14px; font-weight: bold;');
    console.log('%cSistem de Management al Fortei de Munca in Constructii', 'color: #757575; font-size: 11px;');

})();
