// TelePrompter PWA — Guardian One
// Professional-grade teleprompter matching PromptSmart/Teleprompter Premium/BIGVU
(function () {
  'use strict';

  // ---- Config ----
  const API_BASE = window.location.origin;
  let API_TOKEN = localStorage.getItem('tp_token') || '';

  // ---- Persistent settings ----
  const DEFAULTS = {
    fontSize: 28,
    lineHeight: 1.7,
    margins: 24,
    scrollWPM: 160,
    theme: 'dark',       // dark, light, highContrast
    mirrorMode: false,
    showFocusLine: true,
    showTimer: true,
    showProgress: true,
    autoPauseOnCue: true,
    narrowMargins: false,
  };
  let settings = { ...DEFAULTS, ...JSON.parse(localStorage.getItem('tp_settings') || '{}') };
  function saveSettings() { localStorage.setItem('tp_settings', JSON.stringify(settings)); }

  // ---- State ----
  let scripts = [];
  let sessions = [];
  let stats = {};
  let tips = [];
  let currentScript = null;
  let scrollAnimId = null;
  let isScrolling = false;
  let practiceSessionId = null;
  let practiceStartTime = null;
  let selfRating = 0;
  let filterCategory = 'all';
  let searchQuery = '';
  let elapsedInterval = null;
  let elapsedSeconds = 0;

  // ---- Themes ----
  const THEMES = {
    dark:         { bg: '#0a0a0a', text: '#f5f5f7' },
    light:        { bg: '#ffffff', text: '#1c1c1e' },
    highContrast: { bg: '#000000', text: '#ffff00' },
  };

  // ---- Category config ----
  const CATEGORIES = {
    all:              { label: 'All',              icon: '📋' },
    admission:        { label: 'Admission',        icon: '🏥' },
    discharge:        { label: 'Discharge',        icon: '🏠' },
    consult:          { label: 'Consult',          icon: '📞' },
    handoff:          { label: 'Handoff',          icon: '🔄' },
    bad_news:         { label: 'Difficult News',   icon: '💬' },
    family:           { label: 'Family',           icon: '👥' },
    informed_consent: { label: 'Consent',          icon: '📝' },
    code:             { label: 'Code/RRT',         icon: '🚨' },
    cross_cover:      { label: 'Cross-Cover',      icon: '🌙' },
    general:          { label: 'General',          icon: '📄' },
  };

  // ---- API ----
  async function api(method, path, body) {
    const opts = {
      method,
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${API_TOKEN}` },
    };
    if (body) opts.body = JSON.stringify(body);
    try {
      const res = await fetch(`${API_BASE}${path}`, opts);
      if (res.status === 401 || res.status === 403) { showTokenPrompt(); return null; }
      return await res.json();
    } catch (e) {
      console.error('API error:', e);
      return null;
    }
  }

  function showTokenPrompt() {
    const token = prompt('Enter your Guardian One API token:');
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
    const nav = document.getElementById('main-nav');
    nav.style.display = viewId === 'prompter-view' ? 'none' : 'flex';
    if (viewId === 'practice-view') loadStats();
    if (viewId === 'advisory-view') loadTips();
  }

  // ---- Text utilities ----
  function esc(str) {
    if (!str) return '';
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
  }

  function wordCount(text) {
    return text.trim().split(/\s+/).filter(Boolean).length;
  }

  function estimateReadTime(text, wpm = 160) {
    const words = wordCount(text);
    const mins = Math.ceil(words / wpm);
    return mins < 1 ? '< 1 min' : `${mins} min`;
  }

  function formatTime(seconds) {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  }

  // ---- Script rendering (professional teleprompter format) ----
  function formatScriptHTML(text) {
    let html = esc(text);

    // Section headers (SBAR, SPIKES, etc.)
    html = html.replace(
      /^(SITUATION|BACKGROUND|ASSESSMENT|RECOMMENDATION|SETTING UP|PERCEPTION|INVITATION|KNOWLEDGE|EMOTION|STRATEGY &amp; SUMMARY|MEDICATIONS|FOLLOW-UP|WHEN TO COME BACK|ACTIVITY &amp; DIET|OPENING|AGENDA SETTING|AGENDA|CLINICAL EXPLANATION|CLINICAL|DECISION POINTS|DECISION|ANTICIPATED QUESTIONS|DIFFICULT SCENARIOS|CLOSING):?$/gm,
      '<div class="section-header">$1</div>'
    );

    // Pause markers — auto-pause capable
    html = html.replace(
      /\[PAUSE[^\]]*\]/g,
      '<div class="pause-marker" data-pause="true">PAUSE</div>'
    );

    // Stage directions [LOOK AT CAMERA], [GESTURE], etc.
    html = html.replace(
      /\[(LOOK[^\]]*|GESTURE[^\]]*|TONE[^\]]*|SLOW DOWN[^\]]*|SPEED UP[^\]]*|EMPHASIZE[^\]]*|WARNING SHOT[^\]]*|SUMMARIZE[^\]]*)\]/gi,
      '<span class="stage-direction">[$1]</span>'
    );

    // Placeholders [Patient Name], [diagnosis], etc. Exclude known
    // pause/stage-direction markers so they keep their dedicated styling.
    html = html.replace(
      /\[(?!(?:PAUSE|LOOK|GESTURE|TONE|SLOW DOWN|SPEED UP|EMPHASIZE|WARNING SHOT|SUMMARIZE)\b)([^\]]+)\]/gi,
      '<span class="highlight">[$1]</span>'
    );

    // Bold text **text**
    html = html.replace(/\*\*([^*]+)\*\*/g, '<span class="emphasis">$1</span>');

    // Numbered lists
    html = html.replace(/^(\d+\.\s)/gm, '<br>$1');

    // Paragraphs
    html = html.replace(/\n\n/g, '</p><p>');
    html = html.replace(/\n/g, '<br>');
    html = '<p>' + html + '</p>';

    return html;
  }

  // ---- Scripts view ----
  function renderScripts() {
    const container = document.getElementById('scripts-list');
    let filtered = scripts;

    if (filterCategory !== 'all') {
      filtered = filtered.filter(s => s.category === filterCategory);
    }
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      filtered = filtered.filter(s =>
        s.title.toLowerCase().includes(q) ||
        (s.scenario || '').toLowerCase().includes(q) ||
        (s.tags || []).some(t => t.toLowerCase().includes(q))
      );
    }

    if (!filtered.length) {
      container.innerHTML = `<div class="empty"><div class="empty-icon">📋</div>${scripts.length ? 'No matching scripts' : 'No scripts yet'}</div>`;
      return;
    }

    container.innerHTML = filtered.map(s => {
      const cat = CATEGORIES[s.category] || CATEGORIES.general;
      const words = wordCount(s.content || '');
      const time = estimateReadTime(s.content || '');
      return `
        <div class="card" onclick="app.openScript('${s.script_id}')">
          <div class="card-row">
            <div class="card-icon" style="background:${s.ai_generated ? 'var(--accent-dim)' : 'var(--surface2)'}">${cat.icon}</div>
            <div class="card-body">
              <div class="card-badges">
                <span class="badge badge-blue">${esc(cat.label)}</span>
                ${s.ai_generated ? '<span class="badge badge-green">AI</span>' : ''}
              </div>
              <div class="card-title">${esc(s.title)}</div>
              <div class="card-meta">
                <span>${words} words</span>
                <span>${time}</span>
              </div>
            </div>
            <span class="card-chevron">›</span>
          </div>
        </div>`;
    }).join('');
  }

  function setFilter(cat) {
    filterCategory = cat;
    document.querySelectorAll('.filter-pill').forEach(p => {
      p.classList.toggle('active', p.dataset.cat === cat);
    });
    renderScripts();
  }

  function onSearch(e) {
    searchQuery = e.target.value;
    renderScripts();
  }

  // ---- Prompter ----
  function openScript(scriptId) {
    currentScript = scripts.find(s => s.script_id === scriptId);
    if (!currentScript) return;

    applyTheme();
    document.getElementById('prompter-topbar-title').textContent = currentScript.title;
    const el = document.getElementById('prompter-text');
    el.innerHTML = formatScriptHTML(currentScript.content);
    el.scrollTop = 0;
    el.classList.toggle('mirrored', settings.mirrorMode);

    // Focus line
    document.getElementById('prompter-focus-line').style.display =
      settings.showFocusLine ? 'block' : 'none';

    // Reset state
    stopScrolling();
    elapsedSeconds = 0;
    updateTimerDisplay();
    updateProgress();

    // Word/time info
    const words = wordCount(currentScript.content || '');
    const estTime = Math.ceil(words / settings.scrollWPM * 60);
    document.getElementById('info-words').textContent = words;
    document.getElementById('info-eta').textContent = formatTime(estTime);
    document.getElementById('info-wpm').textContent = settings.scrollWPM;

    switchView('prompter-view');
    startPractice(scriptId);
  }

  function applyTheme() {
    const theme = THEMES[settings.theme] || THEMES.dark;
    const root = document.documentElement;
    root.style.setProperty('--prompter-bg', theme.bg);
    root.style.setProperty('--prompter-text-color', theme.text);
    root.style.setProperty('--prompter-font', settings.fontSize + 'px');
    root.style.setProperty('--prompter-line-height', settings.lineHeight);
    root.style.setProperty('--prompter-margin', (settings.narrowMargins ? 12 : settings.margins) + 'px');
  }

  function toggleScrolling() {
    if (isScrolling) stopScrolling();
    else startScrolling();
  }

  function startScrolling() {
    isScrolling = true;
    const el = document.getElementById('prompter-text');
    const playBtn = document.getElementById('play-btn');
    playBtn.textContent = '⏸';
    playBtn.classList.add('playing');

    // Start elapsed timer
    if (!elapsedInterval) {
      elapsedInterval = setInterval(() => {
        elapsedSeconds++;
        updateTimerDisplay();
      }, 1000);
    }

    // WPM-calibrated scroll: calculate pixels/frame from WPM
    // Average word = ~5 chars, at font-size px with line-height, roughly:
    // words_per_line ~= container_width / (fontSize * 0.5)
    // lines_per_minute = WPM / words_per_line
    // pixels_per_minute = lines_per_minute * (fontSize * lineHeight)
    const containerWidth = el.clientWidth - (settings.narrowMargins ? 24 : settings.margins * 2);
    const charsPerLine = Math.max(1, containerWidth / (settings.fontSize * 0.55));
    const wordsPerLine = charsPerLine / 5;
    const linesPerMinute = settings.scrollWPM / wordsPerLine;
    const pixelsPerMinute = linesPerMinute * (settings.fontSize * settings.lineHeight);
    const pixelsPerFrame = pixelsPerMinute / 3600; // 60fps

    function scrollFrame() {
      if (!isScrolling) return;
      el.scrollTop += pixelsPerFrame;

      // Auto-pause on cue markers
      if (settings.autoPauseOnCue) {
        const pauseEls = el.querySelectorAll('.pause-marker[data-pause="true"]');
        const viewCenter = el.scrollTop + el.clientHeight * 0.4;
        for (const p of pauseEls) {
          const pTop = p.offsetTop;
          if (Math.abs(pTop - viewCenter) < 10) {
            p.dataset.pause = 'fired';
            stopScrolling();
            showToast('Auto-paused at cue');
            return;
          }
        }
      }

      updateProgress();

      // Auto-stop at end
      if (el.scrollTop + el.clientHeight >= el.scrollHeight - 20) {
        stopScrolling();
        showToast('End of script');
        return;
      }
      scrollAnimId = requestAnimationFrame(scrollFrame);
    }
    scrollAnimId = requestAnimationFrame(scrollFrame);
  }

  function stopScrolling() {
    isScrolling = false;
    if (scrollAnimId) { cancelAnimationFrame(scrollAnimId); scrollAnimId = null; }
    if (elapsedInterval) { clearInterval(elapsedInterval); elapsedInterval = null; }
    const playBtn = document.getElementById('play-btn');
    if (playBtn) { playBtn.textContent = '▶'; playBtn.classList.remove('playing'); }
  }

  function updateSpeed(val) {
    settings.scrollWPM = parseInt(val);
    document.getElementById('speed-value').textContent = `${settings.scrollWPM} WPM`;
    document.getElementById('info-wpm').textContent = settings.scrollWPM;

    // Update ETA
    if (currentScript) {
      const words = wordCount(currentScript.content || '');
      const wordsLeft = Math.max(0, words - Math.round(words * getProgress()));
      const secsLeft = Math.ceil(wordsLeft / settings.scrollWPM * 60);
      document.getElementById('info-eta').textContent = formatTime(secsLeft);
    }

    if (isScrolling) {
      stopScrolling();
      // Restart timer
      elapsedInterval = setInterval(() => { elapsedSeconds++; updateTimerDisplay(); }, 1000);
      startScrolling();
    }
    saveSettings();
  }

  function adjustFontSize(delta) {
    settings.fontSize = Math.max(16, Math.min(72, settings.fontSize + delta));
    applyTheme();
    saveSettings();
    showToast(`Font: ${settings.fontSize}px`);
  }

  function toggleMirror() {
    settings.mirrorMode = !settings.mirrorMode;
    document.getElementById('prompter-text').classList.toggle('mirrored', settings.mirrorMode);
    document.getElementById('mirror-btn').classList.toggle('active', settings.mirrorMode);
    saveSettings();
    showToast(settings.mirrorMode ? 'Mirror ON' : 'Mirror OFF');
  }

  function scrollJump(direction) {
    const el = document.getElementById('prompter-text');
    const jump = el.clientHeight * 0.6;
    el.scrollTop += direction * jump;
    updateProgress();
  }

  function resetScroll() {
    const el = document.getElementById('prompter-text');
    el.scrollTop = 0;
    updateProgress();
    // Reset pause markers
    el.querySelectorAll('.pause-marker').forEach(p => p.dataset.pause = 'true');
  }

  function getProgress() {
    const el = document.getElementById('prompter-text');
    if (!el) return 0;
    const max = el.scrollHeight - el.clientHeight;
    return max > 0 ? el.scrollTop / max : 0;
  }

  function updateProgress() {
    const pct = Math.min(100, getProgress() * 100);
    document.getElementById('progress-fill').style.width = pct + '%';
  }

  function updateTimerDisplay() {
    document.getElementById('info-elapsed').textContent = formatTime(elapsedSeconds);
  }

  function exitPrompter() {
    stopScrolling();
    if (practiceSessionId) showCompleteModal();
    else switchView('scripts-view');
  }

  // ---- Touch gestures ----
  let touchStartY = 0;
  let touchStartX = 0;
  function onTouchStart(e) {
    touchStartY = e.touches[0].clientY;
    touchStartX = e.touches[0].clientX;
  }
  function onTouchEnd(e) {
    // Tap to toggle play/pause (center area only)
    const el = document.getElementById('prompter-text');
    const rect = el.getBoundingClientRect();
    const touchEndY = e.changedTouches[0].clientY;
    const touchEndX = e.changedTouches[0].clientX;
    const dy = Math.abs(touchEndY - touchStartY);
    const dx = Math.abs(touchEndX - touchStartX);
    if (dy < 10 && dx < 10) {
      // It's a tap, not a scroll
      const relY = (touchEndY - rect.top) / rect.height;
      if (relY > 0.2 && relY < 0.8) {
        toggleScrolling();
      }
    }
  }

  // ---- Settings panel ----
  function openSettings() {
    document.getElementById('settings-panel').classList.add('active');
    renderSettingsValues();
  }
  function closeSettings() {
    document.getElementById('settings-panel').classList.remove('active');
  }
  function renderSettingsValues() {
    document.getElementById('set-font-val').textContent = settings.fontSize + 'px';
    document.getElementById('set-font').value = settings.fontSize;
    document.getElementById('set-line-val').textContent = settings.lineHeight.toFixed(1);
    document.getElementById('set-line').value = settings.lineHeight * 10;
    document.getElementById('set-margin-val').textContent = settings.margins + 'px';
    document.getElementById('set-margin').value = settings.margins;

    // Toggles
    setToggle('set-mirror', settings.mirrorMode);
    setToggle('set-focus', settings.showFocusLine);
    setToggle('set-autopause', settings.autoPauseOnCue);
    setToggle('set-narrow', settings.narrowMargins);

    // Theme swatches
    document.querySelectorAll('.theme-swatch').forEach(s => {
      s.classList.toggle('active', s.dataset.theme === settings.theme);
    });
  }
  function setToggle(id, val) {
    document.getElementById(id).classList.toggle('on', val);
  }
  function toggleSetting(key) {
    settings[key] = !settings[key];
    saveSettings();
    renderSettingsValues();
    if (key === 'mirrorMode') {
      document.getElementById('prompter-text').classList.toggle('mirrored', settings.mirrorMode);
      document.getElementById('mirror-btn').classList.toggle('active', settings.mirrorMode);
    }
    if (key === 'showFocusLine') {
      document.getElementById('prompter-focus-line').style.display =
        settings.showFocusLine ? 'block' : 'none';
    }
    if (key === 'narrowMargins') applyTheme();
  }
  function updateSetting(key, val) {
    if (key === 'fontSize') settings.fontSize = parseInt(val);
    if (key === 'lineHeight') settings.lineHeight = parseInt(val) / 10;
    if (key === 'margins') settings.margins = parseInt(val);
    saveSettings();
    applyTheme();
    renderSettingsValues();
  }
  function setTheme(theme) {
    settings.theme = theme;
    saveSettings();
    applyTheme();
    renderSettingsValues();
  }

  // ---- Script editor ----
  let editingScript = null;
  function openEditor(scriptId) {
    if (scriptId) {
      editingScript = scripts.find(s => s.script_id === scriptId);
      document.getElementById('editor-title').value = editingScript?.title || '';
      document.getElementById('editor-content').value = editingScript?.content || '';
    } else {
      editingScript = null;
      document.getElementById('editor-title').value = '';
      document.getElementById('editor-content').value = '';
    }
    updateEditorMeta();
    document.getElementById('editor-view').classList.add('active');
  }
  function closeEditor() {
    document.getElementById('editor-view').classList.remove('active');
  }
  function updateEditorMeta() {
    const text = document.getElementById('editor-content').value;
    const words = wordCount(text);
    const chars = text.length;
    const time = estimateReadTime(text, settings.scrollWPM);
    document.getElementById('editor-words').textContent = `${words} words`;
    document.getElementById('editor-chars').textContent = `${chars} chars`;
    document.getElementById('editor-time').textContent = time;
  }
  async function saveEditor() {
    const title = document.getElementById('editor-title').value.trim();
    const content = document.getElementById('editor-content').value.trim();
    if (!title || !content) { showToast('Title and content required'); return; }

    if (editingScript) {
      await api('PUT', `/api/scripts/${editingScript.script_id}`, { title, content });
    } else {
      await api('POST', '/api/scripts', { title, content, category: 'general', scenario: '' });
    }
    closeEditor();
    await loadData();
    showToast(editingScript ? 'Script updated' : 'Script created');
  }

  // ---- Practice ----
  async function startPractice(scriptId) {
    practiceStartTime = Date.now();
    selfRating = 0;
    const result = await api('POST', '/api/sessions/start', { script_id: scriptId });
    if (result) practiceSessionId = result.session_id;
  }

  function showCompleteModal() {
    selfRating = 0;
    document.querySelectorAll('#rating-stars button').forEach(b => b.classList.remove('active'));
    document.getElementById('practice-notes').value = '';
    document.getElementById('practice-duration').textContent = formatTime(elapsedSeconds);
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
    document.querySelector('#complete-modal .btn').disabled = true;
    document.querySelector('#complete-modal .btn').textContent = 'Submitting...';

    const result = await api('POST', '/api/sessions/complete', {
      session_id: practiceSessionId,
      duration_seconds: duration,
      self_rating: selfRating,
      notes,
    });
    practiceSessionId = null;
    document.getElementById('complete-modal').classList.remove('active');
    document.querySelector('#complete-modal .btn').disabled = false;
    document.querySelector('#complete-modal .btn').textContent = 'Submit & Get AI Feedback';

    if (result && result.ai_feedback) {
      // Show feedback in a nice toast instead of alert
      showToast('AI feedback received');
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
    if (!scenario && !complaint) { showToast('Enter a scenario or chief complaint'); return; }

    const btn = document.getElementById('gen-btn');
    btn.disabled = true;
    btn.textContent = 'Generating...';

    const result = await api('POST', '/api/generate-script', {
      scenario, category, chief_complaint: complaint,
      patient_profile: { age }, setting: setting || category,
    });
    btn.disabled = false;
    btn.textContent = 'Generate Script';

    if (result && result.script_id) {
      await loadData();
      openScript(result.script_id);
    } else {
      showToast('Generation failed');
    }
  }

  // ---- Advisory ----
  async function loadTips() {
    tips = await api('GET', '/api/tips?limit=10') || [];
    renderTips();
  }
  function renderTips() {
    const container = document.getElementById('tips-list');
    if (!tips.length) {
      container.innerHTML = '<div class="empty"><div class="empty-icon">💡</div>No tips yet</div>';
      return;
    }
    container.innerHTML = tips.map(t => `
      <div class="advisory-bubble">
        <div class="advisory-label">${esc(t.scenario || t.category)}</div>
        ${esc(t.content).replace(/\n/g, '<br>')}
      </div>`).join('');
  }
  async function askAdvisory() {
    const input = document.getElementById('advisory-input');
    const scenario = input.value.trim();
    if (!scenario) return;
    const btn = document.getElementById('advisory-btn');
    btn.disabled = true;
    btn.textContent = 'Thinking...';
    await api('POST', '/api/advisory', { scenario });
    btn.disabled = false;
    btn.textContent = 'Get Advice';
    input.value = '';
    await loadTips();
  }

  // ---- Stats ----
  async function loadStats() {
    stats = await api('GET', '/api/stats') || {};
    renderStats();
    sessions = await api('GET', '/api/sessions?limit=20') || [];
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
      container.innerHTML = '<div class="empty">No sessions yet</div>';
      return;
    }
    container.innerHTML = sessions.map(s => {
      const date = new Date(s.started_at).toLocaleDateString();
      const stars = '★'.repeat(s.self_rating) + '☆'.repeat(5 - s.self_rating);
      const mins = Math.round(s.duration_seconds / 60);
      return `
        <div class="session-item">
          <div class="session-info">
            <div class="session-title">${esc(s.script_title)}</div>
            <div class="session-date">${date} · ${mins}m</div>
          </div>
          <div class="session-rating">${stars}</div>
        </div>`;
    }).join('');
  }

  // ---- Toast ----
  function showToast(msg) {
    const el = document.getElementById('toast');
    el.textContent = msg;
    el.classList.add('show');
    setTimeout(() => el.classList.remove('show'), 2200);
  }

  // ---- Delete script ----
  async function deleteScript(scriptId) {
    if (!confirm('Delete this script?')) return;
    await api('DELETE', `/api/scripts/${scriptId}`);
    await loadData();
    showToast('Script deleted');
  }

  // ---- Data loading ----
  async function loadData() {
    if (!API_TOKEN) { showTokenPrompt(); return; }
    scripts = await api('GET', '/api/scripts') || [];
    renderScripts();
  }

  // ---- Init ----
  function init() {
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('/sw.js').catch(() => {});
    }

    // Nav
    document.querySelectorAll('.nav-btn').forEach(btn => {
      btn.addEventListener('click', () => switchView(btn.dataset.view));
    });

    // Touch gestures on prompter
    const prompterText = document.getElementById('prompter-text');
    if (prompterText) {
      prompterText.addEventListener('touchstart', onTouchStart, { passive: true });
      prompterText.addEventListener('touchend', onTouchEnd, { passive: true });
      prompterText.addEventListener('scroll', updateProgress, { passive: true });
    }

    // Search
    const searchInput = document.getElementById('search-input');
    if (searchInput) searchInput.addEventListener('input', onSearch);

    // Editor textarea
    const editorContent = document.getElementById('editor-content');
    if (editorContent) editorContent.addEventListener('input', updateEditorMeta);

    loadData();

    // Expose API
    window.app = {
      openScript, toggleScrolling, updateSpeed, exitPrompter,
      setRating, submitPractice, cancelComplete, generateScript,
      askAdvisory, switchView, setFilter, adjustFontSize, toggleMirror,
      scrollJump, resetScroll, openSettings, closeSettings,
      toggleSetting, updateSetting, setTheme,
      openEditor, closeEditor, saveEditor, deleteScript,
    };
  }

  document.addEventListener('DOMContentLoaded', init);
})();
