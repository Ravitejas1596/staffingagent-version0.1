import { useState, useRef, useEffect, useCallback } from 'react';
import { MessageSquare, X, Send, Bot, Loader2 } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize';
import { useAuth } from '../../auth/AuthContext';
import { getToken } from '../../api/client';

const API_URL = import.meta.env.VITE_API_URL || 'https://api.staffingagent.ai';
const CHAT_URL = `${API_URL}/api/v1/chat`;
const STORAGE_KEY = 'sa-support-chat';

interface ChatMsg {
  role: 'user' | 'assistant';
  content: string;
}

// Strict allow-list for rehype-sanitize. The LLM can emit arbitrary HTML
// (including injection attempts if a page scrapes untrusted content); this
// schema drops anything not on the list — <script>, <iframe>, on* handlers,
// javascript: URLs, style attributes, etc. Replaces the old
// dangerouslySetInnerHTML path (Security Sprint Workstream 7).
const chatSanitizeSchema = {
  ...defaultSchema,
  tagNames: [
    'p', 'br', 'strong', 'em', 'code', 'pre', 'a',
    'ul', 'ol', 'li', 'blockquote', 'h1', 'h2', 'h3', 'h4', 'span',
  ],
  attributes: {
    ...defaultSchema.attributes,
    a: [
      ['className'],
      ['target', '_blank'],
      ['rel', 'noopener', 'noreferrer'],
      ['href', /^(https?:|mailto:)/],
    ],
    code: [['className']],
    span: [['className']],
  },
  // Block javascript:, data:, vbscript: on every URL attribute just in case.
  protocols: {
    href: ['http', 'https', 'mailto'],
    src: ['http', 'https'],
  },
};

function loadMessages(): ChatMsg[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch { return []; }
}

function saveMessages(msgs: ChatMsg[]) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(msgs)); } catch { /* ignore */ }
}

export default function ChatWidget() {
  const { user } = useAuth();
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMsg[]>(loadMessages);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const messagesRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => { saveMessages(messages); }, [messages]);

  useEffect(() => {
    if (isOpen && inputRef.current) inputRef.current.focus();
  }, [isOpen]);

  const scrollToBottom = useCallback(() => {
    if (messagesRef.current) messagesRef.current.scrollTop = messagesRef.current.scrollHeight;
  }, []);

  useEffect(scrollToBottom, [messages, scrollToBottom]);

  const streamResponse = useCallback(async (allMessages: ChatMsg[]) => {
    setIsStreaming(true);
    const assistantMsg: ChatMsg = { role: 'assistant', content: '' };
    setMessages(prev => [...prev, assistantMsg]);

    const abort = new AbortController();
    abortRef.current = abort;

    try {
      const token = getToken();
      const res = await fetch(CHAT_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          mode: 'support',
          messages: allMessages.filter(m => m.content),
          page_url: window.location.href,
        }),
        signal: abort.signal,
      });

      if (!res.ok) throw new Error(`Chat API error: ${res.status}`);

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let accumulated = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        accumulated += decoder.decode(value, { stream: true });
        const current = accumulated;
        setMessages(prev => {
          const updated = [...prev];
          updated[updated.length - 1] = { role: 'assistant', content: current };
          return updated;
        });
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') return;
      setMessages(prev => {
        const updated = [...prev];
        if (updated.length && updated[updated.length - 1].role === 'assistant' && !updated[updated.length - 1].content) {
          updated[updated.length - 1].content = "Sorry, I'm having trouble connecting right now. Please try again in a moment.";
        }
        return updated;
      });
    } finally {
      setIsStreaming(false);
    }
  }, []);

  const sendMessage = useCallback((text?: string) => {
    const msg = text || input.trim();
    if (!msg || isStreaming) return;

    const userMsg: ChatMsg = { role: 'user', content: msg };
    const newMessages = [...messages, userMsg];
    setMessages(newMessages);
    setInput('');
    streamResponse(newMessages);
  }, [input, isStreaming, messages, streamResponse]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  };

  const userName = user?.name?.split(' ')[0] || 'there';

  const starters = [
    'How do I send missing timesheet reminders?',
    'What do the risk categories mean?',
    'How do I manage user permissions?',
  ];

  return (
    <>
      {/* Floating bubble */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          aria-label="Open chat"
          style={{
            position: 'fixed', bottom: 24, right: 24, width: 56, height: 56,
            borderRadius: '50%', background: 'linear-gradient(135deg, #0d9488, #0f766e)',
            color: '#fff', border: 'none', cursor: 'pointer', zIndex: 99998,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: '0 4px 20px rgba(13,148,136,.45)', transition: 'transform .15s',
          }}
          onMouseEnter={e => { (e.currentTarget as HTMLElement).style.transform = 'scale(1.08)'; }}
          onMouseLeave={e => { (e.currentTarget as HTMLElement).style.transform = 'scale(1)'; }}
        >
          <MessageSquare size={26} />
        </button>
      )}

      {/* Chat panel */}
      {isOpen && (
        <div style={{
          position: 'fixed', bottom: 24, right: 24, width: 380, maxWidth: 'calc(100vw - 32px)',
          height: 540, maxHeight: 'calc(100vh - 48px)',
          background: '#0f172a', border: '1px solid rgba(255,255,255,.1)', borderRadius: 16,
          boxShadow: '0 12px 48px rgba(0,0,0,.5)', zIndex: 99999,
          display: 'flex', flexDirection: 'column', fontFamily: "'Inter', -apple-system, sans-serif",
          overflow: 'hidden',
        }}>
          {/* Header */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 10, padding: 16,
            borderBottom: '1px solid rgba(255,255,255,.08)', flexShrink: 0,
          }}>
            <div style={{
              width: 36, height: 36, borderRadius: 10,
              background: 'linear-gradient(135deg, #0d9488, #0f766e)',
              display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
            }}>
              <Bot size={20} color="#fff" />
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 14, fontWeight: 700, color: '#f1f5f9' }}>Ava</div>
              <div style={{ fontSize: 11, color: '#2dd4bf', fontWeight: 500 }}>Product Assistant</div>
            </div>
            <button
              onClick={() => setIsOpen(false)}
              aria-label="Close chat"
              style={{
                background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer',
                padding: 4, borderRadius: 6, display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}
              onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,.08)'; }}
              onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'none'; }}
            >
              <X size={20} />
            </button>
          </div>

          {/* Messages */}
          <div ref={messagesRef} style={{
            flex: 1, overflowY: 'auto', padding: 16, display: 'flex', flexDirection: 'column', gap: 12,
          }}>
            {/* Welcome message */}
            {messages.length === 0 && (
              <div style={{
                maxWidth: '85%', padding: '10px 14px', borderRadius: '12px 12px 12px 4px',
                background: 'rgba(255,255,255,.08)', color: '#e2e8f0', fontSize: 13, lineHeight: 1.5,
              }}>
                Hi {userName}! I&apos;m Ava, your product assistant. I can help with dashboard features, TimeOps, RiskOps, agents, or anything in the Command Center. What can I help you with?
              </div>
            )}

            {messages.map((m, i) => (
              <div
                key={i}
                className={m.role === 'assistant' ? 'sa-chat-msg sa-chat-msg-assistant' : 'sa-chat-msg sa-chat-msg-user'}
                style={{
                  maxWidth: '85%', padding: '10px 14px',
                  borderRadius: m.role === 'user' ? '12px 12px 4px 12px' : '12px 12px 12px 4px',
                  background: m.role === 'user' ? '#1d4ed8' : 'rgba(255,255,255,.08)',
                  color: m.role === 'user' ? '#fff' : '#e2e8f0',
                  alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
                  fontSize: 13, lineHeight: 1.5, wordBreak: 'break-word',
                }}
              >
                {m.role === 'assistant' ? (
                  <ReactMarkdown
                    rehypePlugins={[[rehypeSanitize, chatSanitizeSchema]]}
                    components={{
                      a: ({ href, children }) => (
                        <a
                          href={href}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{ color: '#2dd4bf', textDecoration: 'underline' }}
                        >
                          {children}
                        </a>
                      ),
                      code: ({ children }) => (
                        <code style={{
                          background: 'rgba(0,0,0,.15)', padding: '1px 4px',
                          borderRadius: 3, fontSize: 12,
                        }}>{children}</code>
                      ),
                    }}
                  >
                    {m.content || '...'}
                  </ReactMarkdown>
                ) : (
                  // User messages render as plain text — React escapes automatically.
                  <span style={{ whiteSpace: 'pre-wrap' }}>{m.content}</span>
                )}
              </div>
            ))}

            {isStreaming && messages.length > 0 && !messages[messages.length - 1].content && (
              <div style={{ alignSelf: 'flex-start', color: '#64748b', fontSize: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
                <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} /> Ava is thinking...
              </div>
            )}
          </div>

          {/* Starters */}
          {messages.length === 0 && (
            <div style={{ padding: '0 16px 12px', display: 'flex', flexDirection: 'column', gap: 6 }}>
              {starters.map((s, i) => (
                <button
                  key={i}
                  onClick={() => sendMessage(s)}
                  style={{
                    background: 'rgba(255,255,255,.05)', border: '1px solid rgba(255,255,255,.1)',
                    borderRadius: 10, padding: '10px 14px', color: '#94a3b8', fontSize: 12,
                    cursor: 'pointer', textAlign: 'left', fontFamily: 'inherit', transition: 'background .15s, color .15s',
                  }}
                  onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,.1)'; (e.currentTarget as HTMLElement).style.color = '#e2e8f0'; }}
                  onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,.05)'; (e.currentTarget as HTMLElement).style.color = '#94a3b8'; }}
                >
                  {s}
                </button>
              ))}
            </div>
          )}

          {/* Input */}
          <div style={{
            display: 'flex', alignItems: 'flex-end', gap: 8, padding: '12px 16px',
            borderTop: '1px solid rgba(255,255,255,.08)', flexShrink: 0,
          }}>
            <textarea
              ref={inputRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Type a message..."
              rows={1}
              style={{
                flex: 1, background: 'rgba(255,255,255,.06)',
                border: '1.5px solid rgba(255,255,255,.1)', borderRadius: 10,
                padding: '10px 12px', color: '#f1f5f9', fontSize: 13,
                fontFamily: 'inherit', resize: 'none', outline: 'none',
                maxHeight: 100, lineHeight: 1.4,
              }}
              onFocus={e => { e.currentTarget.style.borderColor = 'rgba(13,148,136,.5)'; }}
              onBlur={e => { e.currentTarget.style.borderColor = 'rgba(255,255,255,.1)'; }}
            />
            <button
              onClick={() => sendMessage()}
              disabled={!input.trim() || isStreaming}
              aria-label="Send"
              style={{
                width: 36, height: 36, borderRadius: 10, border: 'none',
                background: 'linear-gradient(135deg, #0d9488, #0f766e)', color: '#fff',
                cursor: (!input.trim() || isStreaming) ? 'not-allowed' : 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                opacity: (!input.trim() || isStreaming) ? 0.4 : 1, transition: 'opacity .15s',
              }}
            >
              <Send size={18} />
            </button>
          </div>

          {/* Footer */}
          <div style={{ textAlign: 'center', padding: 6, fontSize: 10, color: '#475569', flexShrink: 0 }}>
            Powered by StaffingAgent.ai
          </div>
        </div>
      )}
    </>
  );
}
