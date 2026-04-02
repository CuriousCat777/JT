"""Browser bridge — generates the bookmarklet JavaScript.

The bookmarklet:
1. Fetches profile list from local server
2. Shows a picker overlay so you choose which profile to fill
3. Requests a one-time token
4. Fetches fill data using the token
5. Force-fills every matched field, bypassing:
   - autocomplete="off"
   - readonly/disabled attributes
   - Shadow DOM inputs
   - React/Angular controlled inputs (dispatches native events)
   - Dynamically loaded fields (MutationObserver retry)
"""

from __future__ import annotations


def get_bookmarklet_js(port: int = 17380) -> str:
    """Return the full bookmarklet JavaScript source."""
    return _BRIDGE_JS.replace("{{PORT}}", str(port))


# The actual bookmarklet source — self-contained, no dependencies.
_BRIDGE_JS = r"""
(function() {
  'use strict';

  var API = 'http://127.0.0.1:{{PORT}}/api/autofill';
  var OVERLAY_ID = '__guardian_autofill_overlay__';

  // Remove existing overlay if re-triggered
  var existing = document.getElementById(OVERLAY_ID);
  if (existing) { existing.remove(); }

  // ── Fetch helpers ─────────────────────────────────────────

  function apiGet(path) {
    return fetch(API + path).then(function(r) { return r.json(); });
  }

  function apiPost(path, body) {
    return fetch(API + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    }).then(function(r) { return r.json(); });
  }

  // ── Force-fill a single input ─────────────────────────────

  function forceFill(input, value) {
    if (!value) return false;

    // Remove anti-autofill attributes
    input.removeAttribute('readonly');
    input.removeAttribute('disabled');
    input.removeAttribute('autocomplete');

    // Set via native setter to bypass React/Angular
    var nativeSetter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype, 'value'
    );
    if (nativeSetter && nativeSetter.set) {
      nativeSetter.set.call(input, value);
    } else {
      input.value = value;
    }

    // Dispatch events that frameworks listen for
    ['input', 'change', 'blur', 'keyup'].forEach(function(evt) {
      input.dispatchEvent(new Event(evt, { bubbles: true }));
    });

    return true;
  }

  // ── Match a field to fill hints ───────────────────────────

  function scoreField(input, fieldDef) {
    var score = 0;
    var hints = fieldDef.hints || [];
    var ac = fieldDef.autocomplete || '';

    // Check autocomplete attribute
    var inputAC = (input.getAttribute('autocomplete') || '').toLowerCase();
    if (ac && inputAC && inputAC.indexOf(ac) !== -1) score += 10;

    // Check name, id, placeholder, aria-label
    var targets = [
      (input.name || '').toLowerCase(),
      (input.id || '').toLowerCase(),
      (input.getAttribute('placeholder') || '').toLowerCase(),
      (input.getAttribute('aria-label') || '').toLowerCase(),
      (input.getAttribute('data-label') || '').toLowerCase()
    ];

    // Check associated label
    if (input.id) {
      var label = document.querySelector('label[for="' + input.id + '"]');
      if (label) targets.push(label.textContent.toLowerCase().trim());
    }
    // Walk up to find parent label
    var parent = input.closest('label');
    if (parent) targets.push(parent.textContent.toLowerCase().trim());

    var combined = targets.join(' ');

    hints.forEach(function(hint) {
      if (combined.indexOf(hint.toLowerCase()) !== -1) score += 5;
    });

    return score;
  }

  function findBestInput(fieldDef, inputs) {
    var best = null;
    var bestScore = 0;
    inputs.forEach(function(inp) {
      var s = scoreField(inp, fieldDef);
      if (s > bestScore) {
        bestScore = s;
        best = inp;
      }
    });
    return bestScore >= 5 ? best : null;
  }

  // ── Gather all inputs (including inside iframes) ──────────

  function gatherInputs() {
    var inputs = Array.from(document.querySelectorAll(
      'input:not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="checkbox"]):not([type="radio"]), select, textarea'
    ));

    // Try to reach into same-origin iframes
    try {
      var iframes = document.querySelectorAll('iframe');
      iframes.forEach(function(iframe) {
        try {
          var iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
          var iframeInputs = iframeDoc.querySelectorAll(
            'input:not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="checkbox"]):not([type="radio"]), select, textarea'
          );
          inputs = inputs.concat(Array.from(iframeInputs));
        } catch(e) { /* cross-origin, skip */ }
      });
    } catch(e) {}

    return inputs;
  }

  // ── Execute the fill ──────────────────────────────────────

  function doFill(fillData) {
    var fields = fillData.fill.fields || [];
    var inputs = gatherInputs();
    var filled = 0;
    var matched = [];

    fields.forEach(function(fieldDef) {
      var input = findBestInput(fieldDef, inputs);
      if (input && forceFill(input, fieldDef.value)) {
        filled++;
        matched.push(input);
        // Remove from pool so we don't double-fill
        inputs = inputs.filter(function(i) { return i !== input; });
      }
    });

    return { filled: filled, total: fields.length, matched: matched };
  }

  // ── UI: Profile Picker ────────────────────────────────────

  function createOverlay(profiles) {
    var overlay = document.createElement('div');
    overlay.id = OVERLAY_ID;
    overlay.style.cssText = 'position:fixed;top:0;right:0;z-index:2147483647;' +
      'background:rgba(0,0,0,0.85);color:#fff;font-family:-apple-system,system-ui,sans-serif;' +
      'font-size:14px;padding:16px;border-radius:0 0 0 12px;max-width:340px;' +
      'max-height:80vh;overflow-y:auto;box-shadow:0 4px 24px rgba(0,0,0,0.4);';

    var title = document.createElement('div');
    title.style.cssText = 'font-size:16px;font-weight:700;margin-bottom:12px;' +
      'display:flex;align-items:center;justify-content:space-between;';
    title.innerHTML = '<span>Guardian Autofill</span>';

    var closeBtn = document.createElement('button');
    closeBtn.textContent = 'X';
    closeBtn.style.cssText = 'background:none;border:none;color:#fff;font-size:18px;cursor:pointer;padding:0 4px;';
    closeBtn.onclick = function() { overlay.remove(); };
    title.appendChild(closeBtn);
    overlay.appendChild(title);

    if (profiles.length === 0) {
      var empty = document.createElement('div');
      empty.style.cssText = 'color:#aaa;padding:8px 0;';
      empty.textContent = 'No profiles found. Add one via CLI: python main.py --autofill-add card';
      overlay.appendChild(empty);
      document.body.appendChild(overlay);
      return;
    }

    profiles.forEach(function(p) {
      var btn = document.createElement('button');
      var displayText = p.label;
      if (p.type === 'card' && p.masked_number) {
        displayText += ' (' + p.masked_number + ')';
      }
      var typeColors = { card: '#4CAF50', address: '#2196F3', identity: '#FF9800' };
      var typeLabels = { card: 'CARD', address: 'ADDR', identity: 'ID' };

      btn.innerHTML = '<span style="background:' + (typeColors[p.type] || '#666') +
        ';padding:2px 6px;border-radius:4px;font-size:11px;margin-right:8px;">' +
        (typeLabels[p.type] || p.type.toUpperCase()) + '</span>' + displayText;

      btn.style.cssText = 'display:block;width:100%;text-align:left;background:#333;' +
        'color:#fff;border:1px solid #555;border-radius:8px;padding:10px 12px;' +
        'margin-bottom:8px;cursor:pointer;font-size:13px;transition:background 0.15s;';
      btn.onmouseover = function() { btn.style.background = '#444'; };
      btn.onmouseout = function() { btn.style.background = '#333'; };

      btn.onclick = function() {
        btn.textContent = 'Filling...';
        btn.disabled = true;

        apiPost('/token', { type: p.type, profile_id: p.profile_id })
          .then(function(tokenResp) {
            if (tokenResp.error) throw new Error(tokenResp.error);
            return apiPost('/fill', { token: tokenResp.token });
          })
          .then(function(fillResp) {
            if (fillResp.error) throw new Error(fillResp.error);
            var result = doFill(fillResp);
            btn.textContent = 'Filled ' + result.filled + '/' + result.total + ' fields';
            btn.style.background = result.filled > 0 ? '#2E7D32' : '#C62828';

            // Highlight filled fields briefly
            result.matched.forEach(function(inp) {
              inp.style.outline = '2px solid #4CAF50';
              setTimeout(function() { inp.style.outline = ''; }, 2000);
            });

            setTimeout(function() { overlay.remove(); }, 2500);
          })
          .catch(function(err) {
            btn.textContent = 'Error: ' + err.message;
            btn.style.background = '#C62828';
          });
      };

      overlay.appendChild(btn);
    });

    document.body.appendChild(overlay);
  }

  // ── Main: load profiles and show picker ───────────────────

  apiGet('/profiles')
    .then(function(data) {
      createOverlay(data.profiles || []);
    })
    .catch(function(err) {
      alert('Guardian Autofill: Cannot reach local server.\n\n' +
            'Start it with: python main.py --autofill-server\n\n' +
            'Error: ' + err.message);
    });

})();
""".strip()
