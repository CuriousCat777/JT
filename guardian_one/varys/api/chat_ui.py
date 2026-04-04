"""VARYS Chat UI — HTML chatbot interface for security queries."""

CHAT_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>VARYS — Security Sentinel</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
    background: #0a0a0f;
    color: #e0e0e0;
    height: 100vh;
    display: flex;
    flex-direction: column;
  }
  .header {
    background: #12121a;
    border-bottom: 1px solid #2a2a3a;
    padding: 12px 20px;
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .header .logo {
    color: #ff4444;
    font-size: 18px;
    font-weight: bold;
    letter-spacing: 2px;
  }
  .header .status {
    font-size: 12px;
    color: #66bb6a;
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .header .status::before {
    content: '';
    width: 8px;
    height: 8px;
    background: #66bb6a;
    border-radius: 50%;
    display: inline-block;
  }
  .stats-bar {
    background: #12121a;
    border-bottom: 1px solid #1a1a2a;
    padding: 8px 20px;
    display: flex;
    gap: 24px;
    font-size: 11px;
    color: #888;
  }
  .stats-bar .stat { display: flex; gap: 6px; }
  .stats-bar .stat .value { color: #e0e0e0; font-weight: bold; }
  .stats-bar .stat.critical .value { color: #ff4444; }
  .stats-bar .stat.high .value { color: #ff9800; }
  .chat-area {
    flex: 1;
    overflow-y: auto;
    padding: 20px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }
  .message {
    max-width: 80%;
    padding: 12px 16px;
    border-radius: 8px;
    font-size: 14px;
    line-height: 1.5;
    white-space: pre-wrap;
  }
  .message.user {
    align-self: flex-end;
    background: #1a3a5c;
    border: 1px solid #2a5a8c;
    color: #c0d8f0;
  }
  .message.varys {
    align-self: flex-start;
    background: #1a1a2a;
    border: 1px solid #2a2a3a;
    color: #e0e0e0;
  }
  .message.varys .sender {
    color: #ff4444;
    font-weight: bold;
    font-size: 11px;
    margin-bottom: 4px;
    letter-spacing: 1px;
  }
  .message.system {
    align-self: center;
    background: transparent;
    border: 1px solid #2a2a3a;
    color: #666;
    font-size: 12px;
    text-align: center;
  }
  .input-area {
    background: #12121a;
    border-top: 1px solid #2a2a3a;
    padding: 16px 20px;
    display: flex;
    gap: 12px;
  }
  .input-area input {
    flex: 1;
    background: #0a0a0f;
    border: 1px solid #2a2a3a;
    border-radius: 6px;
    padding: 10px 14px;
    color: #e0e0e0;
    font-family: inherit;
    font-size: 14px;
    outline: none;
  }
  .input-area input:focus { border-color: #ff4444; }
  .input-area input::placeholder { color: #555; }
  .input-area button {
    background: #ff4444;
    border: none;
    border-radius: 6px;
    padding: 10px 20px;
    color: white;
    font-family: inherit;
    font-weight: bold;
    cursor: pointer;
    letter-spacing: 1px;
  }
  .input-area button:hover { background: #cc3333; }
  .input-area button:disabled { background: #333; cursor: not-allowed; }
</style>
</head>
<body>
  <div class="header">
    <span class="logo">VARYS</span>
    <span class="status">SENTINEL ACTIVE</span>
  </div>
  <div class="stats-bar" id="statsBar">
    <div class="stat"><span>Risk:</span><span class="value" id="riskScore">--</span></div>
    <div class="stat"><span>Alerts:</span><span class="value" id="alertCount">--</span></div>
    <div class="stat"><span>Events:</span><span class="value" id="eventCount">--</span></div>
  </div>
  <div class="chat-area" id="chatArea">
    <div class="message system">VARYS Security Sentinel initialized. Ask me anything about your security posture.</div>
    <div class="message varys">
      <div class="sender">VARYS</div>
      I monitor your systems for threats, analyze security events, and recommend responses. Try asking:
- "What is the current risk level?"
- "Show me recent alerts"
- "Analyze suspicious login from 198.51.100.23"
- "What MITRE techniques should I watch for?"
    </div>
  </div>
  <div class="input-area">
    <input type="text" id="userInput" placeholder="Ask VARYS..." autofocus />
    <button id="sendBtn" onclick="sendMessage()">SEND</button>
  </div>
<script>
const chatArea = document.getElementById('chatArea');
const userInput = document.getElementById('userInput');
const sendBtn = document.getElementById('sendBtn');

userInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !sendBtn.disabled) sendMessage();
});

async function sendMessage() {
  const msg = userInput.value.trim();
  if (!msg) return;

  appendMessage(msg, 'user');
  userInput.value = '';
  sendBtn.disabled = true;

  try {
    const res = await fetch('/api/varys/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: msg}),
    });
    const data = await res.json();
    appendVarys(data.response || 'No response.');
    if (data.context) updateStats(data.context);
  } catch (e) {
    appendVarys('Connection error. VARYS API may be offline.');
  }
  sendBtn.disabled = false;
  userInput.focus();
}

function appendMessage(text, cls) {
  const div = document.createElement('div');
  div.className = 'message ' + cls;
  div.textContent = text;
  chatArea.appendChild(div);
  chatArea.scrollTop = chatArea.scrollHeight;
}

function appendVarys(text) {
  const div = document.createElement('div');
  div.className = 'message varys';
  div.innerHTML = '<div class="sender">VARYS</div>' + escapeHtml(text);
  chatArea.appendChild(div);
  chatArea.scrollTop = chatArea.scrollHeight;
}

function escapeHtml(t) {
  return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\\n/g,'<br>');
}

function updateStats(ctx) {
  const rs = ctx.risk_score;
  if (rs) document.getElementById('riskScore').textContent = rs.overall + '/100';
  if (ctx.active_alerts !== undefined) document.getElementById('alertCount').textContent = ctx.active_alerts;
  if (ctx.events_processed !== undefined) document.getElementById('eventCount').textContent = ctx.events_processed;
}

// Initial stats fetch
fetch('/api/varys/metrics/detection-stats')
  .then(r => r.json())
  .then(d => {
    document.getElementById('alertCount').textContent = d.active_alerts || 0;
    document.getElementById('eventCount').textContent = d.events_processed || 0;
  }).catch(() => {});
fetch('/api/varys/metrics/risk-score')
  .then(r => r.json())
  .then(d => {
    if (d.overall !== undefined) document.getElementById('riskScore').textContent = d.overall + '/100';
  }).catch(() => {});
</script>
</body>
</html>"""


def get_chat_html() -> str:
    """Return the VARYS chat UI HTML."""
    return CHAT_HTML
