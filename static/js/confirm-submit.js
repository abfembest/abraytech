// Shared SweetAlert2 confirmation for delete/destructive form submissions
// across the admin portal — replaces native confirm(), which blocks the
// whole page (and breaks any automated testing/extensions) until manually
// dismissed. Two call shapes:
//
//   <form onsubmit="return swalConfirmSubmit(this, {title: 'Delete X?'})">
//   <button onclick="return swalConfirmSubmit(this, {title: 'Clear X?'})" name="save" value="clear_x">
//
// Pass `this` either way. When called from a button, `this.form` resolves
// the parent form AND the button is re-submitted via requestSubmit(button)
// so its name/value (e.g. name="save" value="clear_x") still lands in the
// POST body — a plain form.submit() would silently drop that, breaking any
// view that branches on request.POST.get('save').
//
// Named swalConfirmSubmit (not confirmSubmit) deliberately — several pages
// already define their own page-specific confirmSubmit() for bulk-action
// forms; a same-named global here would silently shadow (or be shadowed
// by) those.
//
// Falls back to native confirm() if SweetAlert2 didn't load for any reason,
// so the form never becomes impossible to submit.
function swalConfirmSubmit(el, options) {
  options = options || {};
  var isButton = !!el.form;
  var form = isButton ? el.form : el;

  if (!window.Swal) {
    return confirm(options.text || options.title || 'Are you sure?');
  }
  Swal.fire({
    title: options.title || 'Are you sure?',
    html: options.html || options.text || 'This action cannot be undone.',
    icon: options.icon || 'warning',
    showCancelButton: true,
    confirmButtonColor: options.confirmButtonColor || '#ef4444',
    cancelButtonColor: '#6b7280',
    confirmButtonText: options.confirmButtonText || 'Yes, delete',
    cancelButtonText: options.cancelButtonText || 'Cancel',
    reverseButtons: true,
  }).then(function (result) {
    if (!result.isConfirmed) return;
    if (isButton && form.requestSubmit) form.requestSubmit(el);
    else form.submit();
  });
  return false;
}
