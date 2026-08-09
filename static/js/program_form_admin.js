// Shared behaviour for the Program create/edit fields partial
// (_program_form_fields.html), used by the create/edit modal on
// programs_list.html. Re-run initProgramFormUI(root) any time the partial's
// markup is replaced (e.g. after an AJAX re-render on validation error) so
// listeners attach to the fresh DOM.
function initProgramFormUI(root) {
  if (!root) return;

  // ── Tabs ─────────────────────────────────────────────────────────────
  const tabBtns = root.querySelectorAll('.program-tab-btn');
  tabBtns.forEach(function (btn) {
    btn.addEventListener('click', function () {
      tabBtns.forEach(function (b) {
        b.classList.remove('border-primary-600', 'text-primary-600');
        b.classList.add('border-transparent', 'text-gray-500');
      });
      btn.classList.remove('border-transparent', 'text-gray-500');
      btn.classList.add('border-primary-600', 'text-primary-600');
      const target = btn.getAttribute('data-tab-btn');
      root.querySelectorAll('[data-tab-panel]').forEach(function (panel) {
        panel.classList.toggle('hidden', panel.getAttribute('data-tab-panel') !== target);
      });
    });
  });

  // ── Department dropdown ─────────────────────────────────────────────
  // Enhanced to a searchable dropdown by the shared
  // window.enhanceSearchableSelects() (templates/includes/searchable_select.html)
  // via the .searchable-select class on this field — no page-specific init
  // needed here.

  // ── Image preview helper ────────────────────────────────────────────
  function setupImagePreview(input, previewImg, previewWrap, maxSizeMB) {
    if (!input) return;
    input.addEventListener('change', function () {
      if (!this.files || !this.files[0]) return;
      const file = this.files[0];
      if (maxSizeMB && file.size > maxSizeMB * 1024 * 1024) {
        if (window.Swal) {
          Swal.fire({ icon: 'warning', title: 'File too large', text: 'Please choose a file under ' + maxSizeMB + 'MB.' });
        } else {
          alert('Please choose a file under ' + maxSizeMB + 'MB.');
        }
        this.value = '';
        if (previewWrap) previewWrap.classList.add('hidden');
        return;
      }
      const reader = new FileReader();
      reader.onload = function (e) {
        if (previewImg) previewImg.src = e.target.result;
        if (previewWrap) previewWrap.classList.remove('hidden');
      };
      reader.readAsDataURL(file);
    });
  }

  const heroInput = root.querySelector('.program-hero-input');
  if (heroInput) {
    const wrap = root.querySelector('.program-hero-preview-wrap');
    setupImagePreview(heroInput, wrap ? wrap.querySelector('.program-hero-preview-img') : null, wrap, 5);
  }

  root.querySelectorAll('.program-gallery-input').forEach(function (input) {
    const slot = input.getAttribute('data-slot');
    const wrap = root.querySelector('.program-gallery-preview-wrap[data-slot="' + slot + '"]');
    const previewOuter = wrap ? wrap.querySelector('div') : null;
    setupImagePreview(input, wrap ? wrap.querySelector('.program-gallery-preview-img') : null, previewOuter, 3);
  });

  const videoInput = root.querySelector('.program-video-input');
  if (videoInput) {
    videoInput.addEventListener('change', function () {
      const label = root.querySelector('.program-video-filename');
      if (label) label.textContent = (this.files && this.files[0]) ? this.files[0].name : '';
    });
  }
}
