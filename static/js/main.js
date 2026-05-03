// ─── Lucide Icons — safe init ───────────────────────────────────────────────
function initLucide() {
    if (window.lucide) {
        lucide.createIcons();
    }
}

// Run on both events to handle CDN async loading
document.addEventListener('DOMContentLoaded', initLucide);
window.addEventListener('load', initLucide);

// ─── SweetAlert2 Toast — deferred until window.load so Swal is ready ────────
let Toast;
window.addEventListener('load', function () {
    if (window.Swal) {
        Toast = Swal.mixin({
            toast: true,
            position: 'top-end',
            showConfirmButton: false,
            timer: 6000,
            timerProgressBar: true,
            didOpen: (toast) => {
                toast.addEventListener('mouseenter', Swal.stopTimer);
                toast.addEventListener('mouseleave', Swal.resumeTimer);
            },
            customClass: {
                popup: 'rounded-xl shadow-2xl border-l-4',
                title: 'text-sm font-semibold',
                timerProgressBar: 'bg-gradient-to-r from-primary-950 to-purple-700'
            },
            iconColor: '#840384',
            background: '#ffffff'
        });
    }
});

window.showToast = function (type, message) {
    if (Toast) Toast.fire({ icon: type, title: message });
};

// ─── All DOM-dependent code ──────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function () {

    // ── Mobile Menu ─────────────────────────────────────────────────────────
    const mobileMenuBtn = document.getElementById('mobileMenuBtn');
    const mobileMenu    = document.getElementById('mobileMenu');

    /**
     * closeMobileMenu
     * Hides the panel, resets aria-expanded, swaps the icon back to "menu",
     * and restores normal body scrolling.
     */
    function closeMobileMenu() {
        if (!mobileMenu) return;
        mobileMenu.classList.add('hidden');
        if (mobileMenuBtn) mobileMenuBtn.setAttribute('aria-expanded', 'false');
        const icon = document.getElementById('menuIcon');
        if (icon) {
            icon.outerHTML = '<i data-lucide="menu" class="w-6 h-6 text-primary-950" id="menuIcon"></i>';
            initLucide();
        }
        // Restore body scroll when menu closes
        document.body.style.overflow = '';
    }

    if (mobileMenuBtn && mobileMenu) {
        mobileMenuBtn.addEventListener('click', function (e) {
            e.stopPropagation();
            const isHidden = mobileMenu.classList.contains('hidden');
            if (isHidden) {
                // ── OPEN ──────────────────────────────────────────────────
                mobileMenu.classList.remove('hidden');
                mobileMenuBtn.setAttribute('aria-expanded', 'true');
                const icon = document.getElementById('menuIcon');
                if (icon) {
                    icon.outerHTML = '<i data-lucide="x" class="w-6 h-6 text-primary-950" id="menuIcon"></i>';
                    initLucide();
                }
                // NOTE: We do NOT lock body scroll here.
                // The #mobileMenu panel itself scrolls (via CSS max-height +
                // overflow-y:auto set in base.html <style>). Locking the body
                // would prevent momentum scrolling inside the panel on iOS.
            } else {
                // ── CLOSE ─────────────────────────────────────────────────
                closeMobileMenu();
            }
        });

        // Close mobile menu on outside click
        document.addEventListener('click', function (e) {
            if (!mobileMenuBtn.contains(e.target) && !mobileMenu.contains(e.target)) {
                closeMobileMenu();
            }
        });
    }

    // ── Mobile Dropdown Handlers ─────────────────────────────────────────────
    function setupMobileDropdown(btnId, menuId, chevronId) {
        const btn     = document.getElementById(btnId);
        const menu    = document.getElementById(menuId);
        const chevron = document.getElementById(chevronId);

        if (btn && menu && chevron) {
            btn.addEventListener('click', function (e) {
                e.stopPropagation();
                const isOpen = !menu.classList.contains('hidden');
                if (isOpen) {
                    menu.classList.add('hidden');
                    chevron.classList.remove('rotate-180');
                    btn.setAttribute('aria-expanded', 'false');
                } else {
                    menu.classList.remove('hidden');
                    chevron.classList.add('rotate-180');
                    btn.setAttribute('aria-expanded', 'true');
                    initLucide();
                }
            });
        }
    }

    setupMobileDropdown('mobileFacultiesBtn', 'mobileFacultiesMenu', 'facultiesChevron');
    setupMobileDropdown('mobileProgramsBtn',  'mobileProgramsMenu',  'programsChevron');
    setupMobileDropdown('mobileMoreBtn',      'mobileMoreMenu',      'moreChevron');

    // ── Desktop Dropdown Handlers ────────────────────────────────────────────
    document.querySelectorAll('.relative.group').forEach(function (dropdown) {
        const button = dropdown.querySelector('button[aria-haspopup="true"]');
        const menu   = dropdown.querySelector('[role="menu"]');

        if (button && menu) {
            button.addEventListener('click', function (e) {
                e.preventDefault();
                e.stopPropagation();

                const isVisible = menu.classList.contains('opacity-100');

                // Close all other open menus
                document.querySelectorAll('[role="menu"]').forEach(function (m) {
                    m.classList.remove('opacity-100', 'visible');
                    m.classList.add('opacity-0', 'invisible');
                });
                document.querySelectorAll('.relative.group button[aria-haspopup="true"]').forEach(function (b) {
                    b.setAttribute('aria-expanded', 'false');
                });

                if (!isVisible) {
                    menu.classList.remove('opacity-0', 'invisible');
                    menu.classList.add('opacity-100', 'visible');
                    button.setAttribute('aria-expanded', 'true');
                    initLucide();
                }
            });

            // Hover behaviour on desktop only
            if (window.matchMedia('(min-width: 1024px)').matches) {
                dropdown.addEventListener('mouseenter', function () {
                    menu.classList.remove('opacity-0', 'invisible');
                    menu.classList.add('opacity-100', 'visible');
                    button.setAttribute('aria-expanded', 'true');
                    initLucide();
                });

                dropdown.addEventListener('mouseleave', function () {
                    menu.classList.remove('opacity-100', 'visible');
                    menu.classList.add('opacity-0', 'invisible');
                    button.setAttribute('aria-expanded', 'false');
                });
            }
        }
    });

    // ── Close all dropdowns on outside click ─────────────────────────────────
    document.addEventListener('click', function (e) {
        if (!e.target.closest('.relative.group')) {
            document.querySelectorAll('[role="menu"]').forEach(function (m) {
                m.classList.remove('opacity-100', 'visible');
                m.classList.add('opacity-0', 'invisible');
            });
            document.querySelectorAll('.relative.group button[aria-haspopup="true"]').forEach(function (b) {
                b.setAttribute('aria-expanded', 'false');
            });
        }
    });

    // ── Escape key closes everything ─────────────────────────────────────────
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            document.querySelectorAll('[role="menu"]').forEach(function (m) {
                m.classList.remove('opacity-100', 'visible');
                m.classList.add('opacity-0', 'invisible');
            });
            document.querySelectorAll('.relative.group button[aria-haspopup="true"]').forEach(function (b) {
                b.setAttribute('aria-expanded', 'false');
            });
            closeMobileMenu();
        }
    });

    // ── Smooth Scroll ────────────────────────────────────────────────────────
    document.querySelectorAll('a[href^="#"]').forEach(function (anchor) {
        anchor.addEventListener('click', function (e) {
            const href = this.getAttribute('href');
            if (href !== '#' && href.length > 1) {
                e.preventDefault();
                const target = document.querySelector(href);
                if (target) {
                    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    closeMobileMenu();
                }
            }
        });
    });

    // ── Header Scroll Shadow ─────────────────────────────────────────────────
    const header = document.querySelector('header');
    if (header) {
        window.addEventListener('scroll', function () {
            header.classList.toggle('shadow-xl', window.pageYOffset > 50);
        });
    }

}); // end DOMContentLoaded