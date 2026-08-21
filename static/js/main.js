// ─── Lucide Icons — safe init ───────────────────────────────────────────────
function initLucide() {
    if (window.lucide) {
        lucide.createIcons();
    }
}

// Run on both events to handle CDN async loading
document.addEventListener('DOMContentLoaded', initLucide);
window.addEventListener('load', initLucide);

// ─── Password show/hide toggle — site-wide delegated handler ───────────────
// Markup: an <i class="password-toggle" data-target="inputId" data-lucide="eye">
// sitting next to the password <input id="inputId">. Delegated on document
// (not wired per-page) so it works on every password field across the site,
// including ones added to the DOM later (e.g. an HTMX/modal swap), without
// each template needing its own copy of this listener.
document.addEventListener('click', function (e) {
    const toggle = e.target.classList && e.target.classList.contains('password-toggle')
        ? e.target
        : e.target.closest && e.target.closest('.password-toggle');
    if (!toggle) return;
    e.preventDefault();
    e.stopPropagation();

    const input = document.getElementById(toggle.dataset.target);
    if (!input) return;
    const isPassword = input.type === 'password';
    input.type = isPassword ? 'text' : 'password';
    toggle.setAttribute('data-lucide', isPassword ? 'eye-off' : 'eye');
    initLucide();
});

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
                timerProgressBar: 'bg-gradient-to-r from-primary-950 to-primary-700'
            },
            iconColor: '#06b6d4',
            background: '#ffffff'
        });
    }
});

window.showToast = function (type, message) {
    if (Toast) Toast.fire({ icon: type, title: message });
};

// ─── Public-site chrome (header dropdowns, mobile drawer, scroll reveal,
//     counters, cookie consent) — ported from the main.html redesign
//     template, same behavior on the compiled pipeline. ──────────────────────
document.addEventListener('DOMContentLoaded', function () {

    // ---- Desktop dropdown menus (click-toggle, main.html pattern) ----
    const dropdowns = [
        ['servicesBtn', 'servicesPanel'],
        ['solutionsBtn', 'solutionsPanel'],
        ['industriesBtn', 'industriesPanel'],
        ['trainingBtn', 'trainingPanel'],
        ['resourcesBtn', 'resourcesPanel'],
    ];

    function closeAllDropdowns(except) {
        dropdowns.forEach(([btnId, panelId]) => {
            if (panelId === except) return;
            const btn = document.getElementById(btnId);
            const panel = document.getElementById(panelId);
            if (panel) panel.classList.remove('open');
            if (btn) btn.setAttribute('aria-expanded', 'false');
        });
    }

    dropdowns.forEach(([btnId, panelId]) => {
        const btn = document.getElementById(btnId);
        const panel = document.getElementById(panelId);
        if (!btn || !panel) return;
        btn.addEventListener('click', function (e) {
            e.stopPropagation();
            const isOpen = panel.classList.contains('open');
            closeAllDropdowns(isOpen ? null : panelId);
            panel.classList.toggle('open', !isOpen);
            btn.setAttribute('aria-expanded', String(!isOpen));
            if (!isOpen) initLucide();
        });
    });

    document.addEventListener('click', function (e) {
        if (!e.target.closest('nav')) closeAllDropdowns(null);
    });
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') closeAllDropdowns(null);
    });

    // ---- Mobile drawer ----
    const mobileMenuBtn = document.getElementById('mobileMenuBtn');
    const mobileCloseBtn = document.getElementById('mobileCloseBtn');
    const mobileDrawer = document.getElementById('mobileDrawer');
    const mobileOverlay = document.getElementById('mobileOverlay');

    function openDrawer() {
        if (!mobileDrawer || !mobileOverlay) return;
        mobileDrawer.classList.add('open');
        mobileOverlay.classList.add('open');
        if (mobileMenuBtn) mobileMenuBtn.setAttribute('aria-expanded', 'true');
        document.body.style.overflow = 'hidden';
    }
    function closeDrawer() {
        if (!mobileDrawer || !mobileOverlay) return;
        mobileDrawer.classList.remove('open');
        mobileOverlay.classList.remove('open');
        if (mobileMenuBtn) mobileMenuBtn.setAttribute('aria-expanded', 'false');
        document.body.style.overflow = '';
    }
    mobileMenuBtn && mobileMenuBtn.addEventListener('click', openDrawer);
    mobileCloseBtn && mobileCloseBtn.addEventListener('click', closeDrawer);
    mobileOverlay && mobileOverlay.addEventListener('click', closeDrawer);
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') closeDrawer();
    });

    // ---- Cart drawer (same open/close mechanics as the mobile nav drawer
    // above; its content is loaded/refreshed by HTMX, see cart_drawer.html) ----
    const cartToggleBtn = document.getElementById('cartToggleBtn');
    const cartCloseBtn = document.getElementById('cartCloseBtn');
    const cartDrawer = document.getElementById('cartDrawer');
    const cartOverlay = document.getElementById('cartDrawerOverlay');

    function openCartDrawer() {
        if (!cartDrawer || !cartOverlay) return;
        cartDrawer.classList.add('open');
        cartOverlay.classList.add('open');
        if (cartToggleBtn) cartToggleBtn.setAttribute('aria-expanded', 'true');
        document.body.style.overflow = 'hidden';
    }
    function closeCartDrawer() {
        if (!cartDrawer || !cartOverlay) return;
        cartDrawer.classList.remove('open');
        cartOverlay.classList.remove('open');
        if (cartToggleBtn) cartToggleBtn.setAttribute('aria-expanded', 'false');
        document.body.style.overflow = '';
    }
    cartToggleBtn && cartToggleBtn.addEventListener('click', openCartDrawer);
    cartCloseBtn && cartCloseBtn.addEventListener('click', closeCartDrawer);
    cartOverlay && cartOverlay.addEventListener('click', closeCartDrawer);
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') closeCartDrawer();
    });
    // Re-render Lucide icons every time HTMX swaps in fresh drawer content
    // (quantity update/remove re-fetch the fragment) — new <i data-lucide>
    // tags from a swap aren't converted to SVG automatically.
    document.body.addEventListener('htmx:afterSwap', function (e) {
        if (e.target && e.target.id === 'cartDrawerContent') initLucide();
    });

    // ---- Smooth scroll for on-page anchors ----
    document.querySelectorAll('a[href^="#"]').forEach(function (anchor) {
        anchor.addEventListener('click', function (e) {
            const href = this.getAttribute('href');
            if (href !== '#' && href.length > 1) {
                const target = document.querySelector(href);
                if (target) {
                    e.preventDefault();
                    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    closeDrawer();
                }
            }
        });
    });

    // ---- Header scroll shadow + back-to-top visibility ----
    const header = document.getElementById('siteHeader');
    const backToTop = document.getElementById('backToTop');
    window.addEventListener('scroll', function () {
        if (header) header.classList.toggle('scrolled', window.scrollY > 8);
        if (backToTop) {
            const showTop = window.scrollY > 500;
            backToTop.classList.toggle('opacity-0', !showTop);
            backToTop.classList.toggle('pointer-events-none', !showTop);
        }
    }, { passive: true });
    backToTop && backToTop.addEventListener('click', function () {
        window.scrollTo({ top: 0, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
    });

    // ---- Scroll reveal (.reveal -> .in-view) ----
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const revealEls = document.querySelectorAll('.reveal');
    if ('IntersectionObserver' in window && !reduceMotion) {
        const io = new IntersectionObserver((entries) => {
            entries.forEach((entry) => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('in-view');
                    io.unobserve(entry.target);
                }
            });
        }, { threshold: 0.12 });
        revealEls.forEach((el) => io.observe(el));
    } else {
        revealEls.forEach((el) => el.classList.add('in-view'));
    }

    // ---- Animated stat counters (.counter[data-target]) ----
    const counters = document.querySelectorAll('.counter');
    function animateCounter(el) {
        const target = parseInt(el.getAttribute('data-target'), 10) || 0;
        if (reduceMotion) { el.textContent = target; return; }
        const duration = 1200;
        const startTime = performance.now();
        function tick(now) {
            const progress = Math.min((now - startTime) / duration, 1);
            el.textContent = Math.floor(progress * target);
            if (progress < 1) requestAnimationFrame(tick);
            else el.textContent = target;
        }
        requestAnimationFrame(tick);
    }
    if ('IntersectionObserver' in window) {
        const cio = new IntersectionObserver((entries) => {
            entries.forEach((entry) => {
                if (entry.isIntersecting) {
                    animateCounter(entry.target);
                    cio.unobserve(entry.target);
                }
            });
        }, { threshold: 0.5 });
        counters.forEach((el) => cio.observe(el));
    }

    // ---- Cookie consent ----
    const cookieConsent = document.getElementById('cookieConsent');
    const cookieAccept = document.getElementById('cookieAccept');
    const cookieDecline = document.getElementById('cookieDecline');
    if (cookieConsent) {
        try {
            if (!localStorage.getItem('abraytech_cookie_choice')) {
                cookieConsent.classList.remove('hidden');
            }
        } catch (e) { /* storage unavailable */ }
        function setCookieChoice(choice) {
            try { localStorage.setItem('abraytech_cookie_choice', choice); } catch (e) {}
            cookieConsent.classList.add('hidden');
        }
        cookieAccept && cookieAccept.addEventListener('click', () => setCookieChoice('accepted'));
        cookieDecline && cookieDecline.addEventListener('click', () => setCookieChoice('declined'));
    }
});
