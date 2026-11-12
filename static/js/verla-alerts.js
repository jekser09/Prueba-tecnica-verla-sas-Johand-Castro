/**
 * VERLA SAS - Centralized SweetAlert2 Bridge
 * Integrated with VERLA Dark Theme design tokens.
 */
window.VerlaAlert = {
  toast: function(icon, title) {
    if (typeof Swal === 'undefined') return;
    return Swal.fire({
      toast: true,
      position: 'top-end',
      icon: icon,
      title: title,
      showConfirmButton: false,
      timer: 3500,
      timerProgressBar: true,
      background: '#11102E',
      color: '#F4F4FB',
    });
  },

  success: function(title, text) {
    if (typeof Swal === 'undefined') return;
    return Swal.fire({
      icon: 'success',
      title: title,
      text: text,
      confirmButtonColor: '#3B33BC',
      background: '#11102E',
      color: '#F4F4FB',
    });
  },

  error: function(title, text) {
    if (typeof Swal === 'undefined') return;
    return Swal.fire({
      icon: 'error',
      title: title,
      text: text,
      confirmButtonColor: '#3B33BC',
      background: '#11102E',
      color: '#F4F4FB',
    });
  },

  warning: function(title, text) {
    if (typeof Swal === 'undefined') return;
    return Swal.fire({
      icon: 'warning',
      title: title,
      text: text,
      confirmButtonColor: '#3B33BC',
      background: '#11102E',
      color: '#F4F4FB',
    });
  },

  confirm: function(title, text, confirmButtonText = 'Confirmar', isDanger = false) {
    if (typeof Swal === 'undefined') {
      return Promise.resolve({ isConfirmed: window.confirm(text || title) });
    }
    return Swal.fire({
      icon: isDanger ? 'warning' : 'question',
      title: title,
      text: text,
      showCancelButton: true,
      confirmButtonColor: isDanger ? '#EF4444' : '#3B33BC',
      cancelButtonColor: '#2A2768',
      confirmButtonText: confirmButtonText,
      cancelButtonText: 'Cancelar',
      background: '#11102E',
      color: '#F4F4FB',
    });
  },

  conflict: function(mensaje) {
    if (typeof Swal === 'undefined') return;
    return Swal.fire({
      icon: 'warning',
      title: 'Conflicto de Concurrencia (409)',
      html: `<p>${mensaje || 'El registro fue modificado por otro usuario en paralelo.'}</p><small style="color:#A09EC7">Para evitar sobreescribir datos ajenos, recargue la página.</small>`,
      confirmButtonColor: '#3B33BC',
      confirmButtonText: 'Recargar página',
      showCancelButton: true,
      cancelButtonText: 'Cerrar',
      background: '#11102E',
      color: '#F4F4FB',
    }).then((result) => {
      if (result.isConfirmed) {
        window.location.reload();
      }
    });
  }
};
