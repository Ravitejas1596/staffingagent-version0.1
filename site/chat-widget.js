(function () {
  'use strict';

  var API_URL = 'https://api.staffingagent.ai/api/v1/chat';
  var LEAD_URL = 'https://api.staffingagent.ai/api/v1/chat/lead';
  var STORAGE_KEY = 'sa-sales-chat';
  var SEEN_KEY = 'sa-chat-seen';
  var EMAIL_RE = /[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}/;

  var messages = [];
  var visitor = {};
  var isOpen = false;
  var isStreaming = false;
  var abortCtrl = null;

  function loadState() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        var s = JSON.parse(raw);
        messages = s.messages || [];
        visitor = s.visitor || {};
      }
    } catch (e) { /* ignore */ }
  }

  function saveState() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ messages: messages, visitor: visitor }));
    } catch (e) { /* ignore */ }
  }

  function simpleMarkdown(text) {
    return text
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      .replace(/`(.+?)`/g, '<code style="background:rgba(0,0,0,.1);padding:1px 4px;border-radius:3px;font-size:12px;">$1</code>')
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener" style="color:#22d3ee;text-decoration:underline;">$1</a>')
      .replace(/\n/g, '<br>');
  }

  function injectStyles() {
    var css = '\
#sa-chat-bubble{position:fixed;bottom:24px;right:24px;width:60px;height:60px;border-radius:50%;background:linear-gradient(135deg,#06b6d4,#8b5cf6);color:#fff;border:none;cursor:pointer;box-shadow:0 4px 20px rgba(6,182,212,.45);z-index:99998;display:flex;align-items:center;justify-content:center;transition:transform .15s,box-shadow .15s;}\
#sa-chat-bubble:hover{transform:scale(1.08);box-shadow:0 6px 28px rgba(6,182,212,.55);}\
#sa-chat-bubble svg{width:28px;height:28px;}\
#sa-chat-tooltip{position:fixed;bottom:92px;right:24px;background:#1e293b;color:#f1f5f9;padding:10px 16px;border-radius:10px;font-size:13px;font-weight:500;box-shadow:0 4px 16px rgba(0,0,0,.3);z-index:99997;pointer-events:none;opacity:0;transition:opacity .3s;font-family:Inter,-apple-system,BlinkMacSystemFont,sans-serif;}\
#sa-chat-tooltip.visible{opacity:1;}\
#sa-chat-tooltip::after{content:"";position:absolute;bottom:-6px;right:28px;width:12px;height:12px;background:#1e293b;transform:rotate(45deg);}\
#sa-chat-panel{position:fixed;bottom:24px;right:24px;width:380px;max-width:calc(100vw - 32px);height:560px;max-height:calc(100vh - 48px);background:#0f172a;border:1px solid rgba(255,255,255,.1);border-radius:16px;box-shadow:0 12px 48px rgba(0,0,0,.5);z-index:99999;display:none;flex-direction:column;font-family:Inter,-apple-system,BlinkMacSystemFont,sans-serif;overflow:hidden;}\
#sa-chat-panel.open{display:flex;}\
#sa-chat-header{display:flex;align-items:center;gap:10px;padding:16px;border-bottom:1px solid rgba(255,255,255,.08);flex-shrink:0;}\
#sa-chat-header-avatar{width:36px;height:36px;border-radius:10px;background:linear-gradient(135deg,#06b6d4,#8b5cf6);display:flex;align-items:center;justify-content:center;flex-shrink:0;}\
#sa-chat-header-avatar svg{width:20px;height:20px;color:#fff;}\
#sa-chat-header-info{flex:1;}\
#sa-chat-header-name{font-size:14px;font-weight:700;color:#f1f5f9;}\
#sa-chat-header-status{font-size:11px;color:#22d3ee;font-weight:500;}\
#sa-chat-close{background:none;border:none;color:#94a3b8;cursor:pointer;padding:4px;border-radius:6px;display:flex;align-items:center;justify-content:center;}\
#sa-chat-close:hover{background:rgba(255,255,255,.08);color:#f1f5f9;}\
#sa-chat-messages{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:12px;}\
#sa-chat-messages::-webkit-scrollbar{width:4px;}\
#sa-chat-messages::-webkit-scrollbar-thumb{background:rgba(255,255,255,.15);border-radius:2px;}\
.sa-msg{max-width:85%;padding:10px 14px;border-radius:12px;font-size:13px;line-height:1.5;word-wrap:break-word;}\
.sa-msg a{color:#22d3ee !important;}\
.sa-msg-user{align-self:flex-end;background:#1d4ed8;color:#fff;border-bottom-right-radius:4px;}\
.sa-msg-assistant{align-self:flex-start;background:rgba(255,255,255,.08);color:#e2e8f0;border-bottom-left-radius:4px;}\
.sa-msg-assistant code{background:rgba(0,0,0,.2);}\
#sa-chat-starters{padding:0 16px 12px;display:flex;flex-direction:column;gap:6px;}\
.sa-starter{background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.1);border-radius:10px;padding:10px 14px;color:#94a3b8;font-size:12px;cursor:pointer;text-align:left;font-family:inherit;transition:background .15s,color .15s;}\
.sa-starter:hover{background:rgba(255,255,255,.1);color:#e2e8f0;}\
#sa-chat-input-row{display:flex;align-items:flex-end;gap:8px;padding:12px 16px;border-top:1px solid rgba(255,255,255,.08);flex-shrink:0;}\
#sa-chat-input{flex:1;background:rgba(255,255,255,.06);border:1.5px solid rgba(255,255,255,.1);border-radius:10px;padding:10px 12px;color:#f1f5f9;font-size:13px;font-family:inherit;resize:none;outline:none;max-height:100px;line-height:1.4;}\
#sa-chat-input::placeholder{color:#64748b;}\
#sa-chat-input:focus{border-color:rgba(6,182,212,.5);}\
#sa-chat-send{width:36px;height:36px;border-radius:10px;border:none;background:linear-gradient(135deg,#06b6d4,#8b5cf6);color:#fff;cursor:pointer;display:flex;align-items:center;justify-content:center;flex-shrink:0;transition:opacity .15s;}\
#sa-chat-send:disabled{opacity:.4;cursor:not-allowed;}\
#sa-chat-send svg{width:18px;height:18px;}\
#sa-chat-powered{text-align:center;padding:6px;font-size:10px;color:#475569;flex-shrink:0;}\
@media(max-width:480px){#sa-chat-panel{width:100vw;height:100vh;max-height:100vh;bottom:0;right:0;border-radius:0;}#sa-chat-bubble{bottom:16px;right:16px;width:52px;height:52px;}}\
';
    var style = document.createElement('style');
    style.textContent = css;
    document.head.appendChild(style);
  }

  function createBubble() {
    var btn = document.createElement('button');
    btn.id = 'sa-chat-bubble';
    btn.setAttribute('aria-label', 'Open chat');
    btn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>';
    btn.onclick = togglePanel;
    document.body.appendChild(btn);

    var tooltip = document.createElement('div');
    tooltip.id = 'sa-chat-tooltip';
    tooltip.textContent = 'Have questions about StaffingAgent?';
    document.body.appendChild(tooltip);

    if (!localStorage.getItem(SEEN_KEY)) {
      setTimeout(function () {
        if (!isOpen) tooltip.classList.add('visible');
      }, 3000);
      setTimeout(function () {
        tooltip.classList.remove('visible');
        localStorage.setItem(SEEN_KEY, '1');
      }, 9000);
    }
  }

  function createPanel() {
    var panel = document.createElement('div');
    panel.id = 'sa-chat-panel';
    panel.innerHTML = '\
<div id="sa-chat-header">\
  <div id="sa-chat-header-avatar"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 8V4H8"/><rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4v4"/><rect x="4" y="8" width="16" height="12" rx="2"/><path d="M2 14h2"/><path d="M20 14h2"/><path d="M9 13v2"/><path d="M15 13v2"/></svg></div>\
  <div id="sa-chat-header-info"><div id="sa-chat-header-name">Ava from StaffingAgent</div><div id="sa-chat-header-status">Online</div></div>\
  <button id="sa-chat-close" aria-label="Close chat"><svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>\
</div>\
<div id="sa-chat-messages"></div>\
<div id="sa-chat-starters"></div>\
<div id="sa-chat-input-row">\
  <textarea id="sa-chat-input" placeholder="Type a message..." rows="1"></textarea>\
  <button id="sa-chat-send" aria-label="Send" disabled><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg></button>\
</div>\
<div id="sa-chat-powered">Powered by StaffingAgent.ai</div>';
    document.body.appendChild(panel);

    document.getElementById('sa-chat-close').onclick = togglePanel;

    var input = document.getElementById('sa-chat-input');
    var sendBtn = document.getElementById('sa-chat-send');

    input.oninput = function () {
      sendBtn.disabled = !input.value.trim() || isStreaming;
      input.style.height = 'auto';
      input.style.height = Math.min(input.scrollHeight, 100) + 'px';
    };
    input.onkeydown = function (e) {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
    };
    sendBtn.onclick = sendMessage;

    renderMessages();
  }

  function renderMessages() {
    var container = document.getElementById('sa-chat-messages');
    var starters = document.getElementById('sa-chat-starters');
    if (!container) return;

    container.innerHTML = '';

    if (messages.length === 0) {
      var welcome = document.createElement('div');
      welcome.className = 'sa-msg sa-msg-assistant';
      welcome.innerHTML = simpleMarkdown("Hi! I'm Ava from StaffingAgent. I can answer questions about the Command Center, our AI agents, pricing, or help you book a demo. What brings you here today?");
      container.appendChild(welcome);

      if (starters) {
        starters.style.display = 'flex';
        starters.innerHTML = '';
        var prompts = [
          'What does the Command Center do?',
          'How much does StaffingAgent cost?',
          'Can I see a demo?',
        ];
        prompts.forEach(function (p) {
          var btn = document.createElement('button');
          btn.className = 'sa-starter';
          btn.textContent = p;
          btn.onclick = function () { sendStarterMessage(p); };
          starters.appendChild(btn);
        });
      }
    } else {
      if (starters) starters.style.display = 'none';
      messages.forEach(function (m) {
        var div = document.createElement('div');
        div.className = 'sa-msg sa-msg-' + m.role;
        div.innerHTML = m.role === 'assistant' ? simpleMarkdown(m.content) : escapeHtml(m.content);
        container.appendChild(div);
      });
    }

    container.scrollTop = container.scrollHeight;
  }

  function escapeHtml(text) {
    return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\n/g, '<br>');
  }

  function sendStarterMessage(text) {
    var input = document.getElementById('sa-chat-input');
    if (input) input.value = '';
    messages.push({ role: 'user', content: text });
    saveState();
    renderMessages();
    streamResponse();
  }

  function sendMessage() {
    var input = document.getElementById('sa-chat-input');
    if (!input) return;
    var text = input.value.trim();
    if (!text || isStreaming) return;

    messages.push({ role: 'user', content: text });
    input.value = '';
    input.style.height = 'auto';
    document.getElementById('sa-chat-send').disabled = true;

    checkForEmail(text);
    saveState();
    renderMessages();
    streamResponse();
  }

  function checkForEmail(text) {
    var match = text.match(EMAIL_RE);
    if (match && !visitor.emailCaptured) {
      visitor.email = match[0];
      visitor.emailCaptured = true;
      saveState();
      captureLead();
    }
  }

  function captureLead() {
    if (!visitor.email) return;
    var payload = {
      email: visitor.email,
      name: visitor.name || '',
      company: visitor.company || '',
      source_page: window.location.href,
      messages: messages.slice(-10),
    };
    fetch(LEAD_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).catch(function () { /* silent fail */ });
  }

  function streamResponse() {
    isStreaming = true;
    document.getElementById('sa-chat-send').disabled = true;

    messages.push({ role: 'assistant', content: '' });
    renderMessages();

    var container = document.getElementById('sa-chat-messages');
    var lastMsg = container ? container.lastElementChild : null;

    abortCtrl = new AbortController();

    fetch(API_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        mode: 'sales',
        messages: messages.filter(function (m) { return m.content; }),
        page_url: window.location.href,
        visitor: visitor,
      }),
      signal: abortCtrl.signal,
    })
      .then(function (res) {
        if (!res.ok) throw new Error('Chat API error: ' + res.status);
        var reader = res.body.getReader();
        var decoder = new TextDecoder();

        function read() {
          reader.read().then(function (result) {
            if (result.done) {
              isStreaming = false;
              document.getElementById('sa-chat-send').disabled = false;
              saveState();
              return;
            }
            var chunk = decoder.decode(result.value, { stream: true });
            messages[messages.length - 1].content += chunk;
            if (lastMsg) {
              lastMsg.innerHTML = simpleMarkdown(messages[messages.length - 1].content);
              container.scrollTop = container.scrollHeight;
            }
            read();
          }).catch(handleStreamError);
        }
        read();
      })
      .catch(handleStreamError);
  }

  function handleStreamError(err) {
    if (err.name === 'AbortError') return;
    isStreaming = false;
    if (messages.length && messages[messages.length - 1].role === 'assistant' && !messages[messages.length - 1].content) {
      messages[messages.length - 1].content = "Sorry, I'm having trouble connecting right now. Please try again in a moment.";
    }
    renderMessages();
    document.getElementById('sa-chat-send').disabled = false;
    saveState();
  }

  function togglePanel() {
    isOpen = !isOpen;
    var panel = document.getElementById('sa-chat-panel');
    var bubble = document.getElementById('sa-chat-bubble');
    var tooltip = document.getElementById('sa-chat-tooltip');

    if (panel) panel.classList.toggle('open', isOpen);
    if (bubble) bubble.style.display = isOpen ? 'none' : 'flex';
    if (tooltip) tooltip.classList.remove('visible');

    if (isOpen) {
      localStorage.setItem(SEEN_KEY, '1');
      setTimeout(function () {
        var input = document.getElementById('sa-chat-input');
        if (input) input.focus();
      }, 100);
    }
  }

  function init() {
    loadState();
    injectStyles();
    createBubble();
    createPanel();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
