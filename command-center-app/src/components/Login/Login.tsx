import { useState, type FormEvent } from 'react';
import { Bot, Loader2, Lock, Mail, Building2 } from 'lucide-react';
import { useAuth } from '../../auth/AuthContext';

export default function Login() {
  const { login, error: authError, isLoading } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [tenant, setTenant] = useState('default');
  const [localError, setLocalError] = useState('');
  const [showTenant, setShowTenant] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setLocalError('');
    if (!email.trim() || !password.trim()) {
      setLocalError('Email and password are required.');
      return;
    }
    try {
      await login(email.trim(), password, tenant.trim() || 'demo');
    } catch {
      /* error is set in AuthContext */
    }
  };

  const displayError = localError || authError;

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: '#080d1a',
      background: '#020617',
      backgroundImage: `
        radial-gradient(at 0% 0%, rgba(30, 58, 138, 0.15) 0px, transparent 50%),
        radial-gradient(at 100% 0%, rgba(13, 148, 136, 0.1) 0px, transparent 50%),
        radial-gradient(at 100% 100%, rgba(79, 70, 229, 0.1) 0px, transparent 50%)
      `,
      fontFamily: "'Outfit', sans-serif",
    }}>
      <div style={{ width: '100%', maxWidth: 420, padding: 20 }}>
        <div style={{
          borderRadius: 16, padding: 32, backdropFilter: 'blur(12px)',
        }}>
          <form onSubmit={handleSubmit}>
            {/* Email */}
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#94a3b8', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '.05em' }}>
                Email
              </label>
              <div style={{ position: 'relative' }}>
                <Mail size={16} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: '#475569' }} />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@company.com"
                  autoComplete="email"
                  autoFocus
                  style={{
                    width: '100%', padding: '12px 12px 12px 40px', borderRadius: 10,
                    border: '1.5px solid rgba(255,255,255,.12)', background: 'rgba(255,255,255,.06)',
                    color: '#f1f5f9', fontSize: 14, outline: 'none',
                    transition: 'border-color .15s',
                  }}
                  onFocus={(e) => { e.currentTarget.style.borderColor = 'rgba(13,148,136,.6)'; }}
                  onBlur={(e) => { e.currentTarget.style.borderColor = 'rgba(255,255,255,.12)'; }}
                />
              </div>
            </div>

            {/* Password */}
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#94a3b8', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '.05em' }}>
                Password
              </label>
              <div style={{ position: 'relative' }}>
                <Lock size={16} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: '#475569' }} />
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter your password"
                  autoComplete="current-password"
                  style={{
                    width: '100%', padding: '12px 12px 12px 40px', borderRadius: 10,
                    border: '1.5px solid rgba(255,255,255,.12)', background: 'rgba(255,255,255,.06)',
                    color: '#f1f5f9', fontSize: 14, outline: 'none',
                    transition: 'border-color .15s',
                  }}
                  onFocus={(e) => { e.currentTarget.style.borderColor = 'rgba(13,148,136,.6)'; }}
                  onBlur={(e) => { e.currentTarget.style.borderColor = 'rgba(255,255,255,.12)'; }}
                />
              </div>
            </div>

            {/* Tenant (collapsible) */}
            <div style={{ marginBottom: 20 }}>
              <button
                type="button"
                onClick={() => setShowTenant(!showTenant)}
                style={{
                  background: 'none', border: 'none', cursor: 'pointer',
                  fontSize: 11, color: '#64748b', fontWeight: 500,
                  display: 'flex', alignItems: 'center', gap: 4, padding: 0,
                }}
              >
                <Building2 size={12} />
                {showTenant ? 'Hide' : 'Show'} organization
              </button>
              {showTenant && (
                <div style={{ marginTop: 8 }}>
                  <input
                    type="text"
                    value={tenant}
                    onChange={(e) => setTenant(e.target.value)}
                    placeholder="Organization slug"
                    style={{
                      width: '100%', padding: '10px 12px', borderRadius: 10,
                      border: '1.5px solid rgba(255,255,255,.12)', background: 'rgba(255,255,255,.06)',
                      color: '#f1f5f9', fontSize: 13, outline: 'none',
                    }}
                  />
                </div>
              )}
            </div>

            {/* Error */}
            {displayError && (
              <div style={{
                padding: '10px 14px', borderRadius: 8, marginBottom: 16,
                background: 'rgba(220,38,38,.12)', border: '1px solid rgba(220,38,38,.3)',
                color: '#fca5a5', fontSize: 13, fontWeight: 500,
              }}>
                {displayError}
              </div>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={isLoading}
              style={{
                width: '100%', padding: '14px 0', borderRadius: 12, border: 'none',
                background: isLoading ? 'rgba(45, 212, 191, 0.4)' : 'linear-gradient(135deg, #2dd4bf, #14b8a6)',
                color: '#020617', fontSize: 15, fontWeight: 700, cursor: isLoading ? 'wait' : 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                boxShadow: '0 10px 20px rgba(45, 212, 191, 0.2)', transition: 'transform 0.2s',
              }}
              onMouseEnter={(e) => { if (!isLoading) e.currentTarget.style.transform = 'translateY(-2px)'; }}
              onMouseLeave={(e) => { if (!isLoading) e.currentTarget.style.transform = 'translateY(0)'; }}
            >
              {isLoading ? <Loader2 size={18} style={{ animation: 'spin 1s linear infinite' }} /> : null}
              {isLoading ? 'Processing Request...' : 'Authorize & Sign In'}
            </button>
          </form>

          {/* SSO divider */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 12, margin: '24px 0 16px',
          }}>
            <div style={{ flex: 1, height: 1, background: 'rgba(255,255,255,.1)' }} />
            <span style={{ fontSize: 11, color: '#64748b', fontWeight: 500, textTransform: 'uppercase', letterSpacing: '.05em' }}>Coming Soon</span>
            <div style={{ flex: 1, height: 1, background: 'rgba(255,255,255,.1)' }} />
          </div>

          {/* SSO placeholders */}
          <div style={{ display: 'flex', gap: 10 }}>
            <button
              disabled
              title="Microsoft SSO coming soon"
              style={{
                flex: 1, padding: '10px 0', borderRadius: 10,
                border: '1.5px solid rgba(255,255,255,.08)', background: 'rgba(255,255,255,.03)',
                color: '#475569', fontSize: 13, fontWeight: 600, cursor: 'not-allowed',
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                opacity: 0.5,
              }}
            >
              <svg width="16" height="16" viewBox="0 0 21 21" fill="none"><rect x="1" y="1" width="9" height="9" fill="#f25022"/><rect x="11" y="1" width="9" height="9" fill="#7fba00"/><rect x="1" y="11" width="9" height="9" fill="#00a4ef"/><rect x="11" y="11" width="9" height="9" fill="#ffb900"/></svg>
              Microsoft
            </button>
            <button
              disabled
              title="Google SSO coming soon"
              style={{
                flex: 1, padding: '10px 0', borderRadius: 10,
                border: '1.5px solid rgba(255,255,255,.08)', background: 'rgba(255,255,255,.03)',
                color: '#475569', fontSize: 13, fontWeight: 600, cursor: 'not-allowed',
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                opacity: 0.5,
              }}
            >
              <svg width="16" height="16" viewBox="0 0 48 48"><path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/><path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/><path fill="#FBBC05" d="M10.53 28.59a14.5 14.5 0 010-9.18l-7.98-6.19a24.003 24.003 0 000 21.56l7.98-6.19z"/><path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/></svg>
              Google
            </button>
          </div>
        </div>

        {/* Footer */}
        <p style={{ textAlign: 'center', fontSize: 11, color: '#475569', marginTop: 24 }}>
          &copy; 2026 StaffingAgent LLC &mdash; Confidential
        </p>
      </div>
    </div>
  );
}
