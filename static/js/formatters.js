/**
 * VERLA SAS - Currency and Number Formatters
 * Formats Colombian Pesos (COP) using Intl.NumberFormat
 */
(function() {
  const copFormatter = new Intl.NumberFormat('es-CO', {
    style: 'currency',
    currency: 'COP',
    maximumFractionDigits: 0,
  });

  function parseAmount(text) {
    if (!text) return null;
    // Clean spaces, dollar signs, dots or commas depending on format
    let clean = text.replace(/[$]/g, '').trim();
    // In Django floatformat:2 it's typically "12345.67" or "12.345,67"
    // Let's normalize standard decimal representations
    if (clean.includes(',') && clean.includes('.')) {
      if (clean.indexOf('.') < clean.indexOf(',')) {
        // 1.234,56 -> Colombian style
        clean = clean.replace(/\./g, '').replace(',', '.');
      } else {
        // 1,234.56 -> US style
        clean = clean.replace(/,/g, '');
      }
    } else if (clean.includes(',')) {
      // Could be decimal comma e.g. "1234,50"
      clean = clean.replace(',', '.');
    }
    const num = parseFloat(clean);
    return isNaN(num) ? null : num;
  }

  function formatCopElements() {
    const targets = document.querySelectorAll('[data-currency="COP"], .currency-cop');
    targets.forEach(el => {
      let val = el.getAttribute('data-amount');
      if (val === null || val === '') {
        val = el.textContent;
      }
      const num = parseAmount(val);
      if (num !== null) {
        el.textContent = copFormatter.format(num);
      }
    });
  }

  window.VerlaFormatter = {
    formatCOP: function(val) {
      const num = typeof val === 'number' ? val : parseAmount(String(val));
      return num !== null ? copFormatter.format(num) : val;
    },
    formatAll: formatCopElements,
  };

  document.addEventListener('DOMContentLoaded', formatCopElements);
})();
