// Shared "AJAX partial-swap modal" factory for the management (admin)
// portal — generalized from the working departments_list.html pattern.
//
// Handles: open-for-create (reset form, re-run searchable-select
// enhancers), open-for-edit (fetch the fields partial for the given pk,
// swap it in, re-run enhancers), and submit (POST the form; on redirect
// follow it, on a re-rendered fields-partial swap it in place so server
// validation errors show inline without a page reload).
//
// Usage:
//   var deptModal = createAjaxModal({
//     modalId: 'departmentModal',
//     bodyId: 'departmentModalBody',
//     formId: 'departmentModalForm',
//     titleId: 'departmentModalTitle',
//     submitBtnId: 'departmentModalSubmitBtn',
//     submitLabelId: 'departmentModalSubmitLabel',
//     fieldsPartialId: 'departmentFormFieldsPartial',
//     createUrl: '{% url "management:department_create" %}',
//     editUrlTemplate: '{% url "management:department_edit" 0 %}', // '0' is replaced with the pk
//     createTitle: 'Add Department',
//     createLabel: 'Create Department',
//     editTitle: 'Edit Department',
//     editLabel: 'Save Changes',
//     onEnhance: function (root) { /* optional: re-run any page-specific
//       field behavior (tabs, image previews, ...) after create-reset,
//       edit-prefill, or a validation-error partial swap */ },
//   });
//   deptModal.openForCreate();
//   deptModal.openForEdit(pk);
//
// Any element with [data-modal-close] inside the modal closes it; clicking
// the backdrop (the modal root itself) also closes it.
function createAjaxModal(opts) {
  var modal = document.getElementById(opts.modalId);
  if (!modal) return null;

  var modalBody = document.getElementById(opts.bodyId);
  var modalForm = document.getElementById(opts.formId);
  var modalTitle = opts.titleId ? document.getElementById(opts.titleId) : null;
  var submitBtn = document.getElementById(opts.submitBtnId);
  var submitLabel = document.getElementById(opts.submitLabelId);

  function enhance(root) {
    window.enhanceSearchableSelects && window.enhanceSearchableSelects(root);
    opts.onEnhance && opts.onEnhance(root);
  }

  function openModal() {
    modal.classList.remove('hidden');
    modal.classList.add('flex');
    document.body.classList.add('overflow-hidden');
  }
  function closeModal() {
    modal.classList.add('hidden');
    modal.classList.remove('flex');
    document.body.classList.remove('overflow-hidden');
  }

  function swapFields(html) {
    var doc = new DOMParser().parseFromString(html, 'text/html');
    var newFields = doc.getElementById(opts.fieldsPartialId);
    var oldFields = modalBody.querySelector('#' + opts.fieldsPartialId);
    if (newFields && oldFields) {
      oldFields.replaceWith(newFields);
      enhance(modalBody);
      return true;
    }
    return false;
  }

  // The fields partial as originally server-rendered for "create" (blank
  // form) at page load — captured once, before any edit-fetch can replace
  // it with an instance's values. form.reset() alone isn't enough to get
  // back to this state: it only reverts inputs to whatever is currently
  // baked into the DOM as their "default" value, and an edit-fetch
  // permanently rewrites that DOM to the edited record's values. Without
  // restoring this snapshot, re-opening "create" after having viewed an
  // edit would keep showing the previously-edited record's data.
  var initialFieldsHTML = null;
  var initialFieldsEl = modalBody.querySelector('#' + opts.fieldsPartialId);
  if (initialFieldsEl) initialFieldsHTML = initialFieldsEl.outerHTML;

  function openForCreate() {
    if (modalTitle) modalTitle.textContent = opts.createTitle;
    if (submitLabel) submitLabel.textContent = opts.createLabel;
    modalForm.action = opts.createUrl;
    if (initialFieldsHTML) {
      swapFields(initialFieldsHTML);
    } else {
      modalForm.reset();
      enhance(modalBody);
    }
    openModal();
  }

  function openForEdit(pk) {
    var editUrl = opts.editUrlTemplate.replace('0', pk);
    if (modalTitle) modalTitle.textContent = opts.editTitle;
    if (submitLabel) submitLabel.textContent = opts.editLabel;
    modalForm.action = editUrl;
    fetch(editUrl)
      .then(function (resp) { return resp.text(); })
      .then(function (html) {
        swapFields(html);
        openModal();
      })
      .catch(function () {
        if (window.Swal) {
          Swal.fire({ icon: 'error', title: 'Could not load record', text: 'Please try again.' });
        }
      });
  }

  modal.querySelectorAll('[data-modal-close]').forEach(function (btn) {
    btn.addEventListener('click', closeModal);
  });
  modal.addEventListener('click', function (e) {
    if (e.target === modal) closeModal();
  });

  modalForm.addEventListener('submit', async function (e) {
    e.preventDefault();
    if (submitBtn.disabled) return;
    submitBtn.disabled = true;
    var originalLabel = submitLabel ? submitLabel.textContent : '';
    if (submitLabel) submitLabel.textContent = 'Saving…';
    try {
      var resp = await fetch(modalForm.action, { method: 'POST', body: new FormData(modalForm) });
      if (resp.redirected) {
        window.location.href = resp.url;
        return;
      }
      var html = await resp.text();
      if (swapFields(html)) {
        modalBody.scrollTop = 0;
        if (window.Swal) {
          Swal.fire({
            toast: true,
            position: 'top-end',
            icon: 'error',
            title: 'Please fix the highlighted errors and try again.',
            showConfirmButton: false,
            timer: 5000,
            timerProgressBar: true,
            didOpen: function (toast) {
              toast.addEventListener('mouseenter', Swal.stopTimer);
              toast.addEventListener('mouseleave', Swal.resumeTimer);
            },
            customClass: { popup: 'colored-toast' },
          });
        }
      } else {
        window.location.href = modalForm.action;
      }
    } catch (err) {
      if (window.Swal) {
        Swal.fire({ icon: 'error', title: 'Something went wrong', text: 'Please try again.' });
      }
    } finally {
      submitBtn.disabled = false;
      if (submitLabel) submitLabel.textContent = originalLabel;
    }
  });

  return { openForCreate: openForCreate, openForEdit: openForEdit, close: closeModal };
}

// Shared SweetAlert2 delete-confirmation helper, generalized from the
// confirmDelete() pattern duplicated across faculties/departments/programs.
// Submits the hidden #deleteForm (method=post) to the given url on confirm.
function confirmAdminDelete(opts) {
  if (!window.Swal) {
    if (window.confirm(opts.confirmText || 'Are you sure?')) {
      var form = document.getElementById(opts.formId || 'deleteForm');
      form.action = opts.url;
      form.submit();
    }
    return;
  }
  Swal.fire({
    title: opts.title || 'Delete?',
    html: opts.html || (opts.confirmText || 'Are you sure you want to delete this item?'),
    icon: 'warning',
    showCancelButton: true,
    confirmButtonColor: '#ef4444',
    cancelButtonColor: '#6b7280',
    confirmButtonText: opts.confirmButtonText || 'Yes, Delete',
  }).then(function (result) {
    if (result.isConfirmed) {
      var form = document.getElementById(opts.formId || 'deleteForm');
      form.action = opts.url;
      form.submit();
    }
  });
}
