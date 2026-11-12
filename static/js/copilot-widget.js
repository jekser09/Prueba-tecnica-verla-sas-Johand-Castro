/**
 * VERLA SAS - Global Floating Copilot Widget Logic
 * Manages chat lifecycle, drawer visibility, sessionStorage tab isolation,
 * human-in-the-loop decisions, and Gemini assistant interaction.
 */
(function() {
  const STORAGE_KEY = 'verla_ai_chat_session';
  const STATE_KEY = 'verla_ai_widget_open';

  function initCopilot() {
    const btn = document.getElementById('verla-ai-btn');
    const drawer = document.getElementById('verla-ai-drawer');
    const closeBtn = document.getElementById('verla-ai-close-btn');
    const clearBtn = document.getElementById('verla-ai-clear-btn');
    const form = document.getElementById('verla-ai-form');
    const input = document.getElementById('verla-ai-input');
    const messagesContainer = document.getElementById('verla-ai-messages');
    const chips = document.querySelectorAll('.ai-chip');

    if (!btn || !drawer || !form) {
      return;
    }

    const consultarUrl = drawer.getAttribute('data-consultar-url') || '/asistente/api/consultar/';
    const veredictoUrl = drawer.getAttribute('data-veredicto-url') || '/asistente/api/veredicto/';

    function getCsrfToken() {
      const csrfInput = form.querySelector('[name=csrfmiddlewaretoken]');
      return csrfInput ? csrfInput.value : '';
    }

    function loadMessages() {
      messagesContainer.innerHTML = '';
      let saved = [];
      try {
        saved = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || '[]');
      } catch (e) {
        saved = [];
      }

      if (saved.length === 0) {
        appendBubble('assistant', '¡Hola! Soy tu Copiloto comercial de VERLA SAS. ¿En qué te puedo apoyar hoy? Puedes pedirme redactar un copy de oferta o analizar el cumplimiento de metas.');
      } else {
        saved.forEach(msg => {
          renderBubble(msg.role, msg.text, msg.log_id, false);
        });
      }
      scrollBottom();
    }

    function saveMessage(role, text, log_id) {
      let saved = [];
      try {
        saved = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || '[]');
      } catch (e) {
        saved = [];
      }
      saved.push({ role, text, log_id });
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(saved));
    }

    function renderBubble(role, text, logId = null, save = true) {
      const bubble = document.createElement('div');
      bubble.className = `ai-bubble ${role}`;

      if (role === 'assistant') {
        let contentHtml = `<div>${text}</div>`;
        if (logId) {
          contentHtml += `
            <div class="ai-actions-bar">
              <button type="button" class="ai-action-btn copy-btn">📋 Copiar</button>
              <button type="button" class="ai-action-btn accept-btn">✅ Aceptar</button>
              <button type="button" class="ai-action-btn reject-btn">✕ Descartar</button>
            </div>
          `;
        }
        bubble.innerHTML = contentHtml;

        if (logId) {
          const copyBtn = bubble.querySelector('.copy-btn');
          const acceptBtn = bubble.querySelector('.accept-btn');
          const rejectBtn = bubble.querySelector('.reject-btn');

          if (copyBtn) {
            copyBtn.addEventListener('click', () => {
              navigator.clipboard.writeText(text);
              if (window.VerlaAlert) {
                VerlaAlert.toast('success', 'Texto copiado');
              }
            });
          }
          if (acceptBtn) {
            acceptBtn.addEventListener('click', () => veredictoHumano(logId, 'ACEPTADO', acceptBtn));
          }
          if (rejectBtn) {
            rejectBtn.addEventListener('click', () => veredictoHumano(logId, 'DESCARTADO', rejectBtn));
          }
        }
      } else {
        bubble.textContent = text;
      }

      messagesContainer.appendChild(bubble);
      if (save) {
        saveMessage(role, text, logId);
      }
      scrollBottom();
    }

    function appendBubble(role, text, logId = null) {
      renderBubble(role, text, logId, true);
    }

    function scrollBottom() {
      messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    function toggleDrawer(open) {
      if (open) {
        drawer.classList.add('is-open');
        drawer.setAttribute('aria-hidden', 'false');
        sessionStorage.setItem(STATE_KEY, 'true');
        input.focus();
      } else {
        drawer.classList.remove('is-open');
        drawer.setAttribute('aria-hidden', 'true');
        sessionStorage.setItem(STATE_KEY, 'false');
      }
    }

    function veredictoHumano(logId, decision, btnElement) {
      fetch(veredictoUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCsrfToken(),
        },
        body: JSON.stringify({ log_id: logId, decision: decision }),
      })
      .then(res => res.json())
      .then(data => {
        if (data.ok) {
          const bar = btnElement.closest('.ai-actions-bar');
          if (bar) {
            bar.innerHTML = `<small style="color:var(--verla-status-active); font-size:0.75rem;">Veredicto registrado: ${decision}</small>`;
          }
          if (window.VerlaAlert) {
            VerlaAlert.toast('success', `Decisión registrada: ${decision}`);
          }
        }
      })
      .catch(() => {
        if (window.VerlaAlert) {
          VerlaAlert.error('Error', 'No se pudo guardar el veredicto');
        }
      });
    }

    // Exponer globalmente para retrocompatibilidad
    window.veredictoHumano = veredictoHumano;

    // Eventos UI
    btn.addEventListener('click', () => toggleDrawer(!drawer.classList.contains('is-open')));
    if (closeBtn) {
      closeBtn.addEventListener('click', () => toggleDrawer(false));
    }

    if (clearBtn) {
      clearBtn.addEventListener('click', () => {
        if (window.VerlaAlert) {
          VerlaAlert.confirm('¿Reiniciar chat?', 'Se borrará el historial de la conversación actual.', 'Limpiar')
          .then(result => {
            if (result.isConfirmed) {
              sessionStorage.removeItem(STORAGE_KEY);
              loadMessages();
              VerlaAlert.toast('success', 'Conversación reiniciada');
            }
          });
        } else {
          sessionStorage.removeItem(STORAGE_KEY);
          loadMessages();
        }
      });
    }

    chips.forEach(chip => {
      chip.addEventListener('click', () => {
        const prompt = chip.getAttribute('data-prompt');
        input.value = prompt;
        form.dispatchEvent(new Event('submit'));
      });
    });

    form.addEventListener('submit', function(e) {
      e.preventDefault();
      const prompt = input.value.trim();
      if (!prompt) return;

      appendBubble('user', prompt);
      input.value = '';
      input.disabled = true;

      const loadingBubble = document.createElement('div');
      loadingBubble.className = 'ai-bubble assistant';
      loadingBubble.textContent = 'Pensando con Gemini...';
      messagesContainer.appendChild(loadingBubble);
      scrollBottom();

      fetch(consultarUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCsrfToken(),
        },
        body: JSON.stringify({
          mensaje: prompt,
          current_path: window.location.pathname,
        }),
      })
      .then(res => res.json())
      .then(data => {
        if (loadingBubble.parentNode) {
          messagesContainer.removeChild(loadingBubble);
        }
        input.disabled = false;
        input.focus();

        if (data.ok) {
          let textoRespuesta = '';
          const resp = data.respuesta;
          if (resp.titulo_sugerido && resp.descripcion_comercial) {
            textoRespuesta = `<strong>${resp.titulo_sugerido}</strong><br><br>${resp.descripcion_comercial}`;
            if (resp.puntos_clave && resp.puntos_clave.length) {
              textoRespuesta += `<br><br><em>Puntos Clave:</em><ul>${resp.puntos_clave.map(p => `<li>${p}</li>`).join('')}</ul>`;
            }
          } else if (resp.diagnostico_general) {
            textoRespuesta = `<strong>Diagnóstico:</strong> ${resp.diagnostico_general}<br><br>`;
            if (resp.alertas_criticas) {
              textoRespuesta += `<strong>Alertas:</strong><ul>${resp.alertas_criticas.map(a => `<li>${a}</li>`).join('')}</ul>`;
            }
            if (resp.plan_de_accion) {
              textoRespuesta += `<strong>Plan de Acción:</strong><ol>${resp.plan_de_accion.map(p => `<li>${p}</li>`).join('')}</ol>`;
            }
          } else if (resp.respuesta_asistente) {
            textoRespuesta = resp.respuesta_asistente;
          } else if (resp.texto_directo) {
            textoRespuesta = resp.texto_directo;
          } else {
            textoRespuesta = JSON.stringify(resp);
          }

          appendBubble('assistant', textoRespuesta, data.log_id);

          if (data.modo === 'FALLBACK_LOCAL' && window.VerlaAlert) {
            VerlaAlert.toast('warning', 'Modo de contingencia activo (Fallback)');
          }
        } else {
          appendBubble('assistant', `⚠️ Error: ${data.error || 'No se pudo procesar la consulta.'}`);
        }
      })
      .catch(err => {
        if (loadingBubble.parentNode) {
          messagesContainer.removeChild(loadingBubble);
        }
        input.disabled = false;
        appendBubble('assistant', '⚠️ Error de red al comunicarse con el servidor.');
      });
    });

    // Inicializar historial y visibilidad
    loadMessages();
    if (sessionStorage.getItem(STATE_KEY) === 'true') {
      toggleDrawer(true);
    }
  }

  document.addEventListener('DOMContentLoaded', initCopilot);
})();
