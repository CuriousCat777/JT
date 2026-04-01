// TelePrompter PWA — Guardian One
// Telehospitalist communication coach + script prompter

(function () {
  'use strict';

  // ---- Config ----
  const API_BASE = window.location.origin;
  let API_TOKEN = localStorage.getItem('tp_token') || '';

  // ---- State ----
  let scripts = [];
  let sessions = [];
  let stats = {};
  let currentScript = null;
  let scrollInterval = null;
  let scrollSpeed = 3; // 1-5
  let isScrolling = false;
  let practiceSessionId = null;
  let practiceStartTime = null;
  let selfRating = 0;

  // ---- API helpers ----
  async function api(method, path, body) {
    const opts = {
      method,
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${API_TOKEN}`,
      },
    };
    if (body) opts.body = JSON.stringify(body);
    try {
      const res = await fetch(`${API_BASE}${path}`, opts);
      if (res.status === 401 || res.status === 403) {
        showTokenPrompt();
        return null;
      }
      return await res.json();
    } catch (e) {
      console.error('API error:', e);
      return null;
    }
  }

  function showTokenPrompt() {
    const token = prompt('Enter your API token (from Guardian One server):');
    if (token) {
      API_TOKEN = token.trim();
      localStorage.setItem('tp_token', API_TOKEN);
      loadData();
    }
  }

  // ---- Navigation ----
  function switchView(viewId) {
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    document.getElementById(viewId).classList.add('active');
    const btn = document.querySelector(`[data-view="${viewId}"]`);
    if (btn) btn.classList.add('active');

    // Hide bottom nav in prompter view
    const nav = document.getElementById('main-nav');
    nav.style.display = viewId === 'prompter-view' ? 'none' : 'flex';

    if (viewId === 'practice-view') loadStats();
    if (viewId === 'advisory-view') loadTips();
  }

  // ---- Script rendering ----
  function formatScriptHTML(text) {
    return text
      .replace(/\[PAUSE[^\]]*\]/g, '<span class="pause-marker">--- PAUSE ---</span>')
      .replace(/^(SITUATION|BACKGROUND|ASSESSMENT|RECOMMENDATION|SETTING UP|PERCEPTION|INVITATION|KNOWLEDGE|EMOTION|STRATEGY & SUMMARY|MEDICATIONS|FOLLOW-UP|WHEN TO COME BACK|ACTIVITY & DIET|OPENING|AGENDA|CLINICAL|DECISION|CLOSING):?/gm,
        '<span class="section-header">$1</span>')
      .replace(/\[([^\]]+)\]/g, '<span class="highlight">[$1]</span>')
      .replace(/\n/g, '<br>');
  }

  // ---- Scripts view ----
  function renderScripts() {
    const container = document.getElementById('scripts-list');
    if (!scripts.length) {
      container.innerHTML = '<div class="empty"><div class="empty-icon">📋</div>No scripts yet.<br>Generate one or connect to Guardian One.</div>';
      return;
    }
    container.innerHTML = scripts.map(s => `
      <div class="card" onclick="window.app.openScript('${s.script_id}')">
        <div>
          <span class="card-badge">${s.category}</span>
          ${s.ai_generated ? '<span class="card-badge green">AI</span>' : ''}
        </div>
        <div class="card-title">${esc(s.title)}</div>
        <div class="card-meta">${esc(s.scenario || 'No description')}</div>
      </div>
    `).join('');
  }

  // ---- Prompter ----
  function openScript(scriptId) {
    currentScript = scripts.find(s => s.script_id === scriptId);
    if (!currentScript) return;

    document.getElementById('prompter-script-title').textContent = currentScript.title;
    document.getElementById('prompter-text').innerHTML = formatScriptHTML(currentScript.content);
    document.getElementById('prompter-text').scrollTop = 0;

    scrollSpeed = currentScript.scroll_speed || 3;
    document.getElementById('speed-slider').value = scrollSpeed;
    document.getElementById('speed-display').textContent = `${scrollSpeed}x`;

    stopScrolling();
    switchView('prompter-view');

    // Start practice session
    startPractice(scriptId);
  }

  function toggleScrolling() {
    if (isScrolling) {
      stopScrolling();
    } else {
      startScrolling();
    }
  }

  function startScrolling() {
    isScrolling = true;
    const el = document.getElementById('prompter-text');
    const playBtn = document.getElementById('play-btn');
    playBtn.textContent = '⏸';

    const pixelsPerFrame = scrollSpeed * 0.5;
    scrollInterval = setInterval(() => {
      el.scrollTop += pixelsPerFrame;
      // Auto-stop at bottom
      if (el.scrollTop + el.clientHeight >= el.scrollHeight - 10) {
        stopScrolling();
      }
    }, 16); // ~60fps
  }

  function stopScrolling() {
    isScrolling = false;
    if (scrollInterval) {
      clearInterval(scrollInterval);
      scrollInterval = null;
    }
    const playBtn = document.getElementById('play-btn');
    if (playBtn) playBtn.textContent = '▶';
  }

  function updateSpeed(val) {
    scrollSpeed = parseInt(val);
    document.getElementById('speed-display').textContent = `${scrollSpeed}x`;
    if (isScrolling) {
      stopScrolling();
      startScrolling();
    }
  }

  function exitPrompter() {
    stopScrolling();
    if (practiceSessionId) {
      showCompleteModal();
    } else {
      switchView('scripts-view');
    }
  }

  // ---- Practice ----
  async function startPractice(scriptId) {
    practiceStartTime = Date.now();
    selfRating = 0;
    const result = await api('POST', '/api/sessions/start', { script_id: scriptId });
    if (result) {
      practiceSessionId = result.session_id;
    }
  }

  function showCompleteModal() {
    selfRating = 0;
    document.querySelectorAll('#rating-stars button').forEach(b => b.classList.remove('active'));
    document.getElementById('practice-notes').value = '';
    document.getElementById('complete-modal').classList.add('active');
  }

  function setRating(r) {
    selfRating = r;
    document.querySelectorAll('#rating-stars button').forEach((b, i) => {
      b.classList.toggle('active', i < r);
    });
  }

  async function submitPractice() {
    if (!practiceSessionId || selfRating === 0) return;

    const duration = Math.round((Date.now() - practiceStartTime) / 1000);
    const notes = document.getElementById('practice-notes').value;

    const result = await api('POST', '/api/sessions/complete', {
      session_id: practiceSessionId,
      duration_seconds: duration,
      self_rating: selfRating,
      notes: notes,
    });

    practiceSessionId = null;
    document.getElementById('complete-modal').classList.remove('active');

    if (result && result.ai_feedback) {
      alert(`AI Feedback:\n\n${result.ai_feedback}`);
    }

    switchView('scripts-view');
    loadData();
  }

  function cancelComplete() {
    practiceSessionId = null;
    document.getElementById('complete-modal').classList.remove('active');
    switchView('scripts-view');
  }

  // ---- Generate ----
  async function generateScript() {
    const scenario = document.getElementById('gen-scenario').value.trim();
    const category = document.getElementById('gen-category').value;
    const complaint = document.getElementById('gen-complaint').value.trim();
    const age = document.getElementById('gen-age').value.trim();
    const setting = document.getElementById('gen-setting').value.trim();

    if (!scenario && !complaint) {
      alert('Enter a scenario or chief complaint.');
      return;
    }

    const btn = document.getElementById('gen-btn');
    btn.disabled = true;
    btn.textContent = 'Generating...';

    const result = await api('POST', '/api/generate-script', {
      scenario,
      category,
      chief_complaint: complaint,
      patient_profile: { age },
      setting: setting || category,
    });

    btn.disabled = false;
    btn.textContent = 'Generate Script';

    if (result && result.script_id) {
      await loadData();
      openScript(result.script_id);
    } else {
      alert('Generation failed. Check your connection to Guardian One.');
    }
  }

  // ---- Advisory ----
  let tips = [];
  async function loadTips() {
    tips = await api('GET', '/api/tips?limit=10') || [];
    renderTips();
  }

  function renderTips() {
    const container = document.getElementById('tips-list');
    if (!tips.length) {
      container.innerHTML = '<div class="empty"><div class="empty-icon">💡</div>No tips yet.<br>Ask for advisory coaching below.</div>';
      return;
    }
    container.innerHTML = tips.map(t => `
      <div class="advisory-bubble">
        <div style="font-size:12px;color:var(--accent);margin-bottom:6px;">${esc(t.scenario || t.category)}</div>
        ${esc(t.content).replace(/\n/g, '<br>')}
      </div>
    `).join('');
  }

  async function askAdvisory() {
    const input = document.getElementById('advisory-input');
    const scenario = input.value.trim();
    if (!scenario) return;

    const btn = document.getElementById('advisory-btn');
    btn.disabled = true;
    btn.textContent = 'Thinking...';

    const result = await api('POST', '/api/advisory', { scenario });

    btn.disabled = false;
    btn.textContent = 'Get Advice';
    input.value = '';

    if (result) {
      await loadTips();
    }
  }

  // ---- Stats ----
  async function loadStats() {
    stats = await api('GET', '/api/stats') || {};
    renderStats();
    const sessionsData = await api('GET', '/api/sessions?limit=20') || [];
    sessions = sessionsData;
    renderSessions();
  }

  function renderStats() {
    document.getElementById('stat-sessions').textContent = stats.total_sessions || 0;
    document.getElementById('stat-rating').textContent =
      stats.average_rating ? stats.average_rating.toFixed(1) : '--';
    document.getElementById('stat-minutes').textContent =
      stats.total_practice_minutes ? Math.round(stats.total_practice_minutes) : 0;
    document.getElementById('stat-week').textContent = stats.sessions_this_week || 0;
  }

  function renderSessions() {
    const container = document.getElementById('sessions-list');
    if (!sessions.length) {
      container.innerHTML = '<div class="empty">No practice sessions yet.</div>';
      return;
    }
    container.innerHTML = sessions.map(s => {
      const date = new Date(s.started_at).toLocaleDateString();
      const stars = '★'.repeat(s.self_rating) + '☆'.repeat(5 - s.self_rating);
      const mins = Math.round(s.duration_seconds / 60);
      return `
        <div class="session-item">
          <div>
            <div style="font-weight:600;font-size:14px;">${esc(s.script_title)}</div>
            <div class="session-date">${date} · ${mins}m</div>
          </div>
          <div class="session-rating" style="color:var(--orange);">${stars}</div>
        </div>
      `;
    }).join('');
  }

  // ---- Data loading ----
  async function loadData() {
    if (!API_TOKEN) {
      showTokenPrompt();
      return;
    }
    scripts = await api('GET', '/api/scripts') || [];
    renderScripts();
  }

  // ---- Utils ----
  function esc(str) {
    if (!str) return '';
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
  }

  // ---- Init ----
  function init() {
    // Register service worker
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('/sw.js').catch(() => {});
    }

    // Nav buttons
    document.querySelectorAll('.nav-btn').forEach(btn => {
      btn.addEventListener('click', () => switchView(btn.dataset.view));
    });

    // Load data
    loadData();

    // Expose to HTML onclick handlers
    window.app = {
      openScript,
      toggleScrolling,
      updateSpeed,
      exitPrompter,
      setRating,
      submitPractice,
      cancelComplete,
      generateScript,
      askAdvisory,
      switchView,
    };
  }

  document.addEventListener('DOMContentLoaded', init);
})();
