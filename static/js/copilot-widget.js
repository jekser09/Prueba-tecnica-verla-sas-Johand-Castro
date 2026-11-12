/**
 * VERLA SAS - Global Floating Copilot Widget Logic
 * Manages chat lifecycle, drawer visibility, sessionStorage tab isolation,
 * human-in-the-loop decisions, Gemini assistant interaction, and token quota metering.
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
    const quotaBadge = document.getElementById('verla-ai-quota-badge');

    if (!btn || !drawer || !form) {
      return;
    }

    const consultarUrl = drawer.getAttribute('data-consultar-url') || '/asistente/api/consultar/';
    const veredictoUrl = drawer.getAttribute('data-veredicto-url') || '/asistente/api/veredicto/';
    const estadoUrl = drawer.getAttribute('data-estado-url') || '/asistente/api/estado/';

    function getCsrfToken() {
      const csrfInput = form.querySelector('[name=csrfmiddlewaretoken]');
      return csrfInput ? csrfInput.value : '';
    }

    function updateQuotaBadge(cuota) {
      if (!quotaBadge || !cuota) return;
      const restantes = cuota.restantes_hoy !== undefined ? cuota.restantes_hoy : 50;
      const limite = cuota.limite_dia || 50;
      quotaBadge.textContent = `Disponibles: ${restantes}`;
      quotaBadge.title = `${restantes} de ${limite} consultas disponibles hoy (máximo ${cuota.limite_2min || 15} cada 2 min)`;
      if (restantes <= 5) {
        quotaBadge.style.color = 'var(--verla-status-blocked)';
        quotaBadge.style.borderColor = 'var(--verla-status-blocked)';
      } else if (restantes <= 15) {
        quotaBadge.style.color = 'var(--verla-status-inactive)';
        quotaBadge.style.borderColor = 'var(--verla-status-inactive)';
      } else {
        quotaBadge.style.color = 'var(--verla-text-primary)';
        quotaBadge.style.borderColor = 'rgba(255,255,255,0.15)';
      }
    }

    function formatMarkdown(text) {
      if (!text) return '';
      let html = text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');

      // Encabezados ###
      html = html.replace(/^### (.*$)/gim, '<h4 style="margin: 0.4rem 0 0.2rem 0; font-size: 0.95rem; color: #FFFFFF; font-weight: 600;">$1</h4>');
      // Negritas **texto**
      html = html.replace(/\*\*(.*?)\*\*/g, '<strong style="color: #FFFFFF;">$1</strong>');
      // Cursivas *texto*
      html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
      // Viñetas no ordenadas
      html = html.replace(/^\s*-\s+(.*$)/gim, '<li style="margin-left: 1.1rem; font-size: 0.85rem; line-height: 1.4;">$1</li>');
      // Viñetas ordenadas
      html = html.replace(/^\s*(\d+)\.\s+(.*$)/gim, '<li style="margin-left: 1.1rem; font-size: 0.85rem; line-height: 1.4;">$2</li>');
      // Saltos de línea
      html = html.replace(/\n\n+/g, '<br><br>');
      html = html.replace(/\n/g, '<br>');
      return html;
    }

    function loadMessages() {
      messagesContainer.innerHTML = '';
      let saved = [];
      try {
        saved = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || '[]');
      } catch (e) {
        saved = [];
      }

      // Consultar estado de sesión, rol y cuota inicial
      fetch(estadoUrl)
        .then(res => res.json())
        .then(data => {
          if (data.ok) {
            updateQuotaBadge(data.cuota);
            if (saved.length === 0) {
              appendBubble('assistant', data.mensaje_inicial);
            }
          }
        })
        .catch(() => {
          if (saved.length === 0) {
            appendBubble('assistant', '¡Hola! Soy tu Copiloto comercial de VERLA SAS. Tienes 50 consultas disponibles hoy (máximo 15 cada 2 min). ¿En qué te puedo colaborar hoy?');
          }
        });

      if (saved.length > 0) {
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
        const formattedHtml = formatMarkdown(text);
        let contentHtml = `<div class="ai-content-body">${formattedHtml}</div>`;
        if (logId) {
          contentHtml += `
            <div class="ai-actions-bar">
              <button type="button" class="ai-action-btn copy-btn" title="Copiar texto de la propuesta">📋 Copiar</button>
              <button type="button" class="ai-action-btn accept-btn" title="Aprobar borrador human-in-the-loop">✅ Aceptar</button>
              <button type="button" class="ai-action-btn reject-btn" title="Descartar borrador">✕ Descartar</button>
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
                VerlaAlert.toast('success', 'Propuesta copiada al portapapeles');
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

    window.veredictoHumano = veredictoHumano;

    btn.addEventListener('click', () => toggleDrawer(!drawer.classList.contains('is-open')));
    if (closeBtn) {
      closeBtn.addEventListener('click', () => toggleDrawer(false));
    }

    // Cierre al hacer clic fuera del drawer y del botón de activación
    document.addEventListener('click', function(e) {
      if (!drawer.classList.contains('is-open')) return;

      const target = e.target;
      const isInsideDrawer = drawer.contains(target);
      const isInsideBtn = btn.contains(target);
      const targetEl = target instanceof Element ? target : target?.parentElement;
      const isSwal = targetEl && (targetEl.closest('.swal2-container') || targetEl.closest('.swal2-popup'));
      const isAiAction = targetEl && targetEl.closest('.ai-action-btn');

      if (!isInsideDrawer && !isInsideBtn && !isSwal && !isAiAction) {
        toggleDrawer(false);
      }
    });

    if (clearBtn) {
      clearBtn.addEventListener('click', () => {
        if (window.VerlaAlert) {
          VerlaAlert.confirm('¿Reiniciar chat?', 'Se limpiará el historial de la conversación actual.', 'Limpiar')
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
      .then(res => {
        return res.json().then(data => ({ status: res.status, data }));
      })
      .then(({ status, data }) => {
        if (loadingBubble.parentNode) {
          messagesContainer.removeChild(loadingBubble);
        }
        input.disabled = false;
        input.focus();

        if (data.cuota) {
          updateQuotaBadge(data.cuota);
        }

        if (status === 200 && data.ok) {
          let textoRespuesta = '';
          const resp = data.respuesta;
          if (resp.texto_markdown) {
            textoRespuesta = resp.texto_markdown;
          } else if (resp.titulo_sugerido && resp.descripcion_comercial) {
            textoRespuesta = `### 🎁 ${resp.titulo_sugerido}\n\n**Descripción Comercial:**\n${resp.descripcion_comercial}`;
            if (resp.puntos_clave && resp.puntos_clave.length) {
              textoRespuesta += `\n\n**Condiciones Clave:**\n` + resp.puntos_clave.map(p => `- ${p}`).join('\n');
            }
          } else if (resp.diagnostico_general) {
            textoRespuesta = `**Diagnóstico:** ${resp.diagnostico_general}\n\n`;
            if (resp.alertas_criticas) {
              textoRespuesta += `**Alertas:**\n` + resp.alertas_criticas.map(a => `- ${a}`).join('\n') + `\n\n`;
            }
            if (resp.plan_de_accion) {
              textoRespuesta += `**Plan de Acción:**\n` + resp.plan_de_accion.map((p, i) => `${i+1}. ${p}`).join('\n');
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
        } else if (status === 429) {
          appendBubble('assistant', `⚠️ **Límite de Consultas:** ${data.error || 'Has superado el límite de consultas permitidas.'}`);
          if (window.VerlaAlert) {
            VerlaAlert.warning('Límite de Consultas', data.error);
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

    loadMessages();
    if (sessionStorage.getItem(STATE_KEY) === 'true') {
      toggleDrawer(true);
    }
  }

  document.addEventListener('DOMContentLoaded', initCopilot);
})();
