(() => {
    const { useState, useEffect, useRef } = React;

    // -------------------------------------------------------------------------
    // Shared Void input / button class strings
    // -------------------------------------------------------------------------
    const CLS_INPUT =
        'w-full bg-surface-container-lowest border border-white/5 rounded-xl px-4 py-3 ' +
        'text-on-surface placeholder-on-surface-variant/30 focus:outline-none focus:ring-2 ' +
        'focus:ring-primary/25 font-body transition-all';

    const CLS_BTN_PRIMARY =
        'w-full py-3 btn-gradient ' +
        'font-bold rounded-xl disabled:opacity-40 transition-all hover:opacity-90';

    const CLS_BTN_GHOST =
        'w-full py-3 text-primary/80 hover:text-primary hover:bg-primary/5 rounded-xl transition-all text-sm font-medium';

    const CLS_BTN_DANGER =
        'text-red-400 hover:bg-red-500/10 rounded-xl px-4 py-2 text-sm transition-all';

    // Modal shell
    const ModalShell = ({ onClose, maxWidth = 'max-w-lg', children }) =>
        React.createElement(
            'div',
            { className: 'fixed inset-0 z-50 flex items-center justify-center' },
            // backdrop
            React.createElement('div', {
                className: 'absolute inset-0 bg-black/60 backdrop-blur-sm',
                onClick: onClose,
            }),
            // panel
            React.createElement(
                'div',
                {
                    className: `relative w-full ${maxWidth} mx-4 bg-surface-container/95 backdrop-blur-2xl ` +
                               'rounded-2xl border border-white/10 p-8 shadow-2xl',
                },
                children
            )
        );

    // Small helper: close icon button
    const CloseBtn = ({ onClose }) =>
        React.createElement(
            'button',
            {
                onClick: onClose,
                className: 'text-on-surface/40 hover:text-on-surface/80 transition-colors',
                'aria-label': 'Close',
            },
            React.createElement(window.VoidIcon, { name: 'close', size: 20 })
        );

    // -------------------------------------------------------------------------
    // AuthModal
    // -------------------------------------------------------------------------
    const AuthModal = ({ isOpen, onClose, onAuthed, onGuest }) => {
        const [mode, setMode]               = useState('login');
        const [email, setEmail]             = useState('');
        const [password, setPassword]       = useState('');
        const [loading, setLoading]         = useState(false);
        const [message, setMessage]         = useState('');
        const [otpSent, setOtpSent]         = useState(false);
        const [otpCode, setOtpCode]         = useState('');
        const [humanVerified, setHumanVerified] = useState(false);

        const turnstileRef = useRef(null);
        const widgetIdRef  = useRef(null);

        // 每次打开 modal 先重置到登录视图。否则登出再开会停在上次的 OTP 步。
        useEffect(() => {
            if (isOpen) {
                setMode('login');
                setOtpSent(false);
                setOtpCode('');
                setPassword('');
                setMessage('');
                setLoading(false);
            }
        }, [isOpen]);

        // Render Turnstile widget
        useEffect(() => {
            if (!isOpen || humanVerified) return;

            const renderWidget = () => {
                if (turnstileRef.current && window.turnstile && widgetIdRef.current === null) {
                    widgetIdRef.current = window.turnstile.render(turnstileRef.current, {
                        sitekey: window.TURNSTILE_SITEKEY,
                        theme: 'dark',
                        callback: async (token) => {
                            const result = await window.verifyHumanTokenWithServer(token);
                            if (result.ok) {
                                setHumanVerified(true);
                                if (result.bypassed) {
                                    setMessage('Local preview mode: server verify skipped.');
                                }
                            } else {
                                setMessage(result.message || 'Human verification failed. Please retry.');
                            }
                        },
                    });
                }
            };

            if (window.turnstile) {
                renderWidget();
            } else {
                const timer = setInterval(() => {
                    if (window.turnstile) { clearInterval(timer); renderWidget(); }
                }, 200);
                return () => clearInterval(timer);
            }

            return () => {
                if (widgetIdRef.current !== null && window.turnstile) {
                    window.turnstile.remove(widgetIdRef.current);
                    widgetIdRef.current = null;
                }
            };
        }, [isOpen, humanVerified]);

        if (!isOpen) return null;

        const handleAuth = async () => {
            setLoading(true);
            setMessage('');
            try {
                if (mode === 'login') {
                    const { data, error } = await window.supabaseClient.auth.signInWithPassword({ email, password });
                    if (error) throw error;
                    if (data?.user) onAuthed(data.user);
                } else if (otpSent) {
                    const { data, error } = await window.supabaseClient.auth.verifyOtp({
                        email, token: otpCode, type: 'signup',
                    });
                    if (error) throw error;
                    if (data?.user) onAuthed(data.user);
                } else {
                    const { data, error } = await window.supabaseClient.auth.signUp({ email, password });
                    if (error) throw error;
                    setOtpSent(true);
                    setMessage('Verification code sent to your email.');
                }
            } catch (err) {
                setMessage(err?.message || 'Operation failed. Please try again.');
            } finally {
                setLoading(false);
            }
        };

        const MessageBox = ({ text }) => {
            if (!text) return null;
            const isSuccess = text.includes('sent') || text.includes('skipped');
            return React.createElement(
                'div',
                {
                    className: isSuccess
                        ? 'text-xs px-4 py-3 rounded-xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                        : 'text-xs px-4 py-3 rounded-xl bg-red-500/10 text-red-400 border border-red-500/20',
                },
                text
            );
        };

        const OtpView = () =>
            React.createElement(
                'div',
                { className: 'space-y-4' },
                React.createElement(
                    'p',
                    { className: 'text-sm text-center text-on-surface/50' },
                    'Enter the 6-digit code sent to ',
                    React.createElement('strong', { className: 'text-on-surface/80' }, email)
                ),
                React.createElement('input', {
                    type: 'text',
                    placeholder: '000000',
                    maxLength: 6,
                    className: CLS_INPUT + ' text-center text-2xl tracking-[0.5em] font-mono',
                    value: otpCode,
                    onChange: (e) => setOtpCode(e.target.value.replace(/\D/g, '')),
                    autoFocus: true,
                }),
                React.createElement(MessageBox, { text: message }),
                React.createElement(
                    'button',
                    {
                        onClick: handleAuth,
                        disabled: loading || otpCode.length !== 6,
                        className: CLS_BTN_PRIMARY,
                    },
                    loading ? 'Verifying...' : 'Verify'
                ),
                React.createElement(
                    'button',
                    {
                        onClick: () => { setOtpSent(false); setOtpCode(''); setMessage(''); },
                        className: CLS_BTN_GHOST,
                    },
                    'Back'
                )
            );

        const LoginSignupView = () =>
            React.createElement(
                'div',
                { className: 'space-y-4' },
                React.createElement('input', {
                    type: 'email',
                    placeholder: 'Email',
                    className: CLS_INPUT,
                    value: email,
                    onChange: (e) => setEmail(e.target.value),
                    autoFocus: true,
                }),
                React.createElement('input', {
                    type: 'password',
                    placeholder: 'Password',
                    className: CLS_INPUT,
                    value: password,
                    onChange: (e) => setPassword(e.target.value),
                    onKeyDown: (e) => { if (e.key === 'Enter' && email && password) handleAuth(); },
                }),
                React.createElement(MessageBox, { text: message }),
                React.createElement(
                    'button',
                    {
                        onClick: handleAuth,
                        disabled: loading || !email || !password,
                        className: CLS_BTN_PRIMARY,
                    },
                    loading ? 'Working...' : (mode === 'login' ? 'Sign in' : 'Sign up')
                ),
                React.createElement(
                    'button',
                    {
                        onClick: () => { setMode(mode === 'login' ? 'signup' : 'login'); setMessage(''); },
                        className: CLS_BTN_GHOST,
                    },
                    mode === 'login'
                        ? "Don't have an account? Sign up"
                        : 'Already have an account? Sign in'
                ),
                // Divider
                React.createElement(
                    'div',
                    { className: 'flex items-center gap-3 my-2' },
                    React.createElement('div', { className: 'flex-1 h-px bg-white/10' }),
                    React.createElement('span', { className: 'text-[10px] uppercase tracking-widest text-on-surface/30' }, 'or'),
                    React.createElement('div', { className: 'flex-1 h-px bg-white/10' })
                ),
                React.createElement(
                    'button',
                    {
                        onClick: () => onGuest?.(),
                        className: CLS_BTN_GHOST + ' border border-white/10',
                    },
                    'Continue as Guest'
                )
            );

        const TurnstileView = () =>
            React.createElement(
                'div',
                { className: 'flex flex-col items-center gap-4 py-6' },
                React.createElement(
                    'p',
                    { className: 'text-sm text-on-surface/50' },
                    "Please verify you're human"
                ),
                React.createElement('div', { ref: turnstileRef }),
                React.createElement(MessageBox, { text: message })
            );

        return React.createElement(
            ModalShell,
            { onClose },
            // Header
            React.createElement(
                'div',
                { className: 'flex items-center justify-between mb-8' },
                React.createElement(
                    'h2',
                    { className: 'text-xl font-display text-on-surface' },
                    mode === 'login' ? 'Sign in' : 'Sign up'
                ),
                React.createElement(CloseBtn, { onClose })
            ),
            // Body
            !humanVerified
                ? React.createElement(TurnstileView)
                : otpSent
                    ? React.createElement(OtpView)
                    : React.createElement(LoginSignupView)
        );
    };

    // -------------------------------------------------------------------------
    // PaywallModal
    // -------------------------------------------------------------------------
    const PaywallModal = ({ isOpen, onClose, balance = 0 }) => {
        const [code, setCode]       = useState('');
        const [loading, setLoading] = useState(false);
        const [message, setMessage] = useState('');
        const [success, setSuccess] = useState(false);

        if (!isOpen) return null;

        const handleRedeem = async () => {
            if (!code.trim()) return;
            setLoading(true);
            setMessage('');
            try {
                const res = await fetch('/credits/redeem', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include',
                    body: JSON.stringify({ code: code.trim() }),
                });
                const data = await res.json().catch(() => ({}));
                if (res.ok && data?.ok !== false) {
                    setSuccess(true);
                    setMessage(data?.message || 'Credits redeemed successfully!');
                } else {
                    setMessage(data?.message || 'Invalid or expired code. Please try again.');
                }
            } catch (err) {
                setMessage('Network error. Please try again.');
            } finally {
                setLoading(false);
            }
        };

        return React.createElement(
            ModalShell,
            { onClose },
            // Header
            React.createElement(
                'div',
                { className: 'flex items-center justify-between mb-6' },
                React.createElement(
                    'div',
                    { className: 'flex items-center gap-2 text-on-surface' },
                    React.createElement(window.VoidIcon, { name: 'toll', size: 22, className: 'text-primary' }),
                    React.createElement('h2', { className: 'text-xl font-display' }, 'Credits depleted')
                ),
                React.createElement(CloseBtn, { onClose })
            ),
            // Balance badge
            React.createElement(
                'div',
                { className: 'flex items-center justify-center mb-8' },
                React.createElement(
                    'div',
                    {
                        className: 'flex flex-col items-center gap-1 px-8 py-5 rounded-2xl ' +
                                   'bg-surface-container-lowest border border-white/5',
                    },
                    React.createElement('span', { className: 'text-4xl font-bold text-on-surface' }, balance),
                    React.createElement('span', { className: 'text-xs text-on-surface/40 uppercase tracking-wider' }, 'credits remaining')
                )
            ),
            // Redeem section
            React.createElement(
                'div',
                { className: 'space-y-4' },
                React.createElement(
                    'p',
                    { className: 'text-sm text-on-surface/50 text-center' },
                    'Redeem a code to continue'
                ),
                React.createElement('input', {
                    type: 'text',
                    placeholder: 'Enter redeem code',
                    className: CLS_INPUT,
                    value: code,
                    onChange: (e) => setCode(e.target.value),
                    onKeyDown: (e) => { if (e.key === 'Enter') handleRedeem(); },
                    disabled: success,
                }),
                message && React.createElement(
                    'div',
                    {
                        className: success
                            ? 'text-xs px-4 py-3 rounded-xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                            : 'text-xs px-4 py-3 rounded-xl bg-red-500/10 text-red-400 border border-red-500/20',
                    },
                    message
                ),
                React.createElement(
                    'button',
                    {
                        onClick: handleRedeem,
                        disabled: loading || !code.trim() || success,
                        className: CLS_BTN_PRIMARY,
                    },
                    loading ? 'Redeeming...' : success ? 'Redeemed!' : 'Redeem'
                ),
                React.createElement(
                    'button',
                    { onClick: onClose, className: CLS_BTN_GHOST },
                    'Close'
                )
            )
        );
    };

    // -------------------------------------------------------------------------
    // VerifyModal — Turnstile human verification gate
    // -------------------------------------------------------------------------
    const VerifyModal = ({ isOpen, onClose, onVerified }) => {
        const [message, setMessage] = useState('');
        const turnstileRef = useRef(null);
        const widgetIdRef  = useRef(null);

        useEffect(() => {
            if (!isOpen) return;

            const renderWidget = () => {
                if (turnstileRef.current && window.turnstile && widgetIdRef.current === null) {
                    widgetIdRef.current = window.turnstile.render(turnstileRef.current, {
                        sitekey: window.TURNSTILE_SITEKEY,
                        theme: 'dark',
                        callback: async (token) => {
                            const result = await window.verifyHumanTokenWithServer(token);
                            if (result.ok) {
                                onVerified?.();
                                onClose?.();
                            } else {
                                setMessage(result.message || 'Verification failed. Please retry.');
                                // Reset widget so user can try again
                                if (widgetIdRef.current !== null && window.turnstile) {
                                    window.turnstile.reset(widgetIdRef.current);
                                }
                            }
                        },
                    });
                }
            };

            if (window.turnstile) {
                renderWidget();
            } else {
                const timer = setInterval(() => {
                    if (window.turnstile) { clearInterval(timer); renderWidget(); }
                }, 200);
                return () => clearInterval(timer);
            }

            return () => {
                if (widgetIdRef.current !== null && window.turnstile) {
                    window.turnstile.remove(widgetIdRef.current);
                    widgetIdRef.current = null;
                }
            };
        }, [isOpen]);

        if (!isOpen) return null;

        return React.createElement(
            ModalShell,
            { onClose, maxWidth: 'max-w-sm' },
            React.createElement(
                'div',
                { className: 'flex items-center justify-between mb-6' },
                React.createElement(
                    'div',
                    { className: 'flex items-center gap-2 text-on-surface' },
                    React.createElement(window.VoidIcon, { name: 'verified_user', size: 20, className: 'text-primary' }),
                    React.createElement('h2', { className: 'text-lg font-display' }, 'Verify you\'re human')
                ),
                React.createElement(CloseBtn, { onClose })
            ),
            React.createElement(
                'div',
                { className: 'flex flex-col items-center gap-5 py-4' },
                React.createElement(
                    'p',
                    { className: 'text-sm text-on-surface/50 text-center' },
                    'Complete the verification below to continue.'
                ),
                React.createElement('div', { ref: turnstileRef }),
                message && React.createElement(
                    'div',
                    { className: 'text-xs px-4 py-3 rounded-xl bg-red-500/10 text-red-400 border border-red-500/20 w-full text-center' },
                    message
                )
            )
        );
    };

    // -------------------------------------------------------------------------
    // SummaryModal — per-persona summary display
    // -------------------------------------------------------------------------
    // summaries: Array<{ personaId: string, name: string, color?: string, summary: string }>
    const SummaryModal = ({ isOpen, onClose, summaries = [] }) => {
        if (!isOpen) return null;

        const ACCENT_FALLBACK = '#e8a84c'; // warm amber as default

        const cards = summaries.map((item) =>
            React.createElement(
                'div',
                {
                    key: item.personaId || item.name,
                    className: 'rounded-2xl bg-surface-container-lowest border border-white/5 p-5 space-y-2',
                    style: {
                        borderTop: `2px solid ${item.color || ACCENT_FALLBACK}`,
                    },
                },
                // Persona name
                React.createElement(
                    'div',
                    { className: 'flex items-center gap-2' },
                    React.createElement('div', {
                        className: 'w-2 h-2 rounded-full flex-shrink-0',
                        style: { background: item.color || ACCENT_FALLBACK },
                    }),
                    React.createElement(
                        'span',
                        { className: 'text-xs font-bold uppercase tracking-wider text-on-surface/60' },
                        item.name || item.personaId
                    )
                ),
                // Summary text
                React.createElement(
                    'p',
                    { className: 'text-sm text-on-surface/80 leading-relaxed whitespace-pre-line' },
                    item.summary || 'No summary available.'
                )
            )
        );

        return React.createElement(
            ModalShell,
            { onClose, maxWidth: 'max-w-2xl' },
            // Header
            React.createElement(
                'div',
                { className: 'flex items-center justify-between mb-6' },
                React.createElement(
                    'div',
                    { className: 'flex items-center gap-2 text-on-surface' },
                    React.createElement(window.VoidIcon, { name: 'summarize', size: 20, className: 'text-primary' }),
                    React.createElement('h2', { className: 'text-xl font-display' }, 'Session Summary')
                ),
                React.createElement(CloseBtn, { onClose })
            ),
            // Cards grid — scrollable if many personas
            summaries.length === 0
                ? React.createElement(
                      'p',
                      { className: 'text-center text-sm text-on-surface/40 py-8' },
                      'No summaries to display.'
                  )
                : React.createElement(
                      'div',
                      {
                          className: 'grid grid-cols-1 sm:grid-cols-2 gap-4 max-h-[60vh] overflow-y-auto pr-1 ' +
                                     'scrollbar-thin scrollbar-thumb-white/10',
                      },
                      ...cards
                  ),
            // Close button
            React.createElement(
                'div',
                { className: 'mt-6' },
                React.createElement(
                    'button',
                    { onClick: onClose, className: CLS_BTN_GHOST + ' border border-white/10' },
                    'Close'
                )
            )
        );
    };

    // -------------------------------------------------------------------------
    // Register to global scope
    // -------------------------------------------------------------------------
    window.VoidAuthModal    = AuthModal;
    window.VoidPaywallModal = PaywallModal;
    window.VoidVerifyModal  = VerifyModal;
    window.VoidSummaryModal = SummaryModal;
})();
