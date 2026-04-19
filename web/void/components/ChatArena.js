(() => {
    const { useState, useEffect, useRef, useMemo } = React;
    const html = htm.bind(React.createElement);

    // ── Persona accent color palette ──────────────────────────────────────────
    // Warm, distinctive colors — amber, terracotta, sage, dusty rose, warm blue, bronze, olive, mauve
    const PERSONA_COLORS = [
        { border: 'border-amber-400',   text: 'text-amber-400',   bg: 'bg-amber-900/40',   ring: 'border-amber-400'   },
        { border: 'border-red-400',     text: 'text-red-400',     bg: 'bg-red-900/40',     ring: 'border-red-400'     },
        { border: 'border-lime-600',    text: 'text-lime-600',    bg: 'bg-lime-900/40',    ring: 'border-lime-600'    },
        { border: 'border-rose-300',    text: 'text-rose-300',    bg: 'bg-rose-900/40',    ring: 'border-rose-300'    },
        { border: 'border-sky-400',     text: 'text-sky-400',     bg: 'bg-sky-900/40',     ring: 'border-sky-400'     },
        { border: 'border-yellow-600',  text: 'text-yellow-600',  bg: 'bg-yellow-900/40',  ring: 'border-yellow-600'  },
        { border: 'border-green-600',   text: 'text-green-600',   bg: 'bg-green-900/40',   ring: 'border-green-600'   },
        { border: 'border-fuchsia-300', text: 'text-fuchsia-300', bg: 'bg-fuchsia-900/40', ring: 'border-fuchsia-300' },
    ];

    // ── Language detection ────────────────────────────────────────────────────
    const detectLang = (text) => {
        const ch = (text || '').trim()[0] || '';
        if (/[\u3040-\u30ff]/.test(ch)) return 'Japanese';
        if (/[\uac00-\ud7af]/.test(ch)) return 'Korean';
        if (/[\u4e00-\u9fff]/.test(ch)) return 'Chinese';
        return 'English';
    };

    // ── Main component ────────────────────────────────────────────────────────
    const ChatArena = ({
        context,
        selectedPersonas,
        setView,
        userAvatar,
        user,
        initialMessages = [],
        parentSessionId = "",
    }) => {
        // ── State ─────────────────────────────────────────────────────────────
        const [history, setHistory]             = useState(initialMessages);
        const [options, setOptions]             = useState([]);
        const [isDebating, setIsDebating]       = useState(false);
        const [sessionId, setSessionId]         = useState(parentSessionId || '');
        const [inputValue, setInputValue]       = useState('');
        const [credits, setCredits]             = useState(null);
        const [showPaywall, setShowPaywall]     = useState(false);
        const [showVerify, setShowVerify]       = useState(false);
        const [verifyError, setVerifyError]     = useState('');
        const [redeemCode, setRedeemCode]       = useState('');
        const [followUpMode, setFollowUpMode]   = useState(false);
        const [webSearchMode, setWebSearchMode] = useState(false);
        const [maxSpeakers, setMaxSpeakers]     = useState(0);
        const [language, setLanguage]           = useState(() => localStorage.getItem('lifee_lang') || '');
        const [extractStatus, setExtractStatus] = useState(''); // '' | 'extracting' | 'done'
        const [summaryData, setSummaryData]     = useState({});
        const [summaryLoading, setSummaryLoading] = useState(false);
        const [showSummaryPanel, setShowSummaryPanel] = useState(false);
        const [showMoreMenu, setShowMoreMenu]   = useState(false);

        // ── Refs ──────────────────────────────────────────────────────────────
        const scrollRef        = useRef(null);
        const inputFieldRef    = useRef(null);
        const verifyRef        = useRef(null);
        const verifyWidgetRef  = useRef(null);
        const sessionIdRef     = useRef(sessionId);
        const extractTimerRef  = useRef(null);
        const summaryAtCountRef = useRef(0);
        const autoStartedRef   = useRef(false);
        const moreMenuRef      = useRef(null);
        const optionsCacheRef  = useRef({});  // sessionId → options[]

        useEffect(() => { sessionIdRef.current = sessionId; }, [sessionId]);

        // Persist options per-session as they change
        useEffect(() => {
            if (sessionId) optionsCacheRef.current[sessionId] = options;
        }, [options, sessionId]);

        // Sync with parent state changes (New Session / restore / navigate away)
        useEffect(() => {
            setSessionId(parentSessionId || '');
            setHistory(initialMessages || []);
            setOptions(optionsCacheRef.current[parentSessionId] || []);
            setSummaryData({});
            autoStartedRef.current = false;  // allow auto-start again for new context
        }, [parentSessionId]);

        // ── Close more menu on outside click ─────────────────────────────────
        useEffect(() => {
            if (!showMoreMenu) return;
            const handler = (e) => {
                if (moreMenuRef.current && !moreMenuRef.current.contains(e.target)) {
                    setShowMoreMenu(false);
                }
            };
            document.addEventListener('mousedown', handler);
            return () => document.removeEventListener('mousedown', handler);
        }, [showMoreMenu]);

        // ── Persona color mapping (stable by first-seen order) ────────────────
        const personaColorMap = useMemo(() => {
            const map = {};
            (selectedPersonas || []).forEach((p, idx) => {
                map[p.id] = PERSONA_COLORS[idx % PERSONA_COLORS.length];
            });
            return map;
        }, [selectedPersonas]);

        const getColor = (personaId) =>
            personaColorMap[personaId] || PERSONA_COLORS[0];

        // ── Auto-scroll ───────────────────────────────────────────────────────
        useEffect(() => {
            if (scrollRef.current) {
                scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
            }
        }, [history]);

        // ── Credits ───────────────────────────────────────────────────────────
        useEffect(() => {
            const url = user?.id ? `/credits?userId=${user.id}` : '/credits';
            fetch(url, { credentials: 'include' })
                .then(r => r.json())
                .then(d => { if (typeof d.balance === 'number') setCredits(d.balance); })
                .catch(() => {});
        }, [user]);

        // ── Profile auto-extract ──────────────────────────────────────────────
        const fireExtractMemory = (sid) => {
            if (!user?.id || !sid) return;
            supabaseClient
                .from('profiles')
                .select('user_memory')
                .eq('id', user.id)
                .maybeSingle()
                .then(({ data }) => {
                    window.fetch('/extract-memory', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        credentials: 'include',
                        body: JSON.stringify({
                            sessionId: sid,
                            userId: user.id,
                            currentMemory: data?.user_memory || '',
                        }),
                    })
                        .then(r => r.json())
                        .then(res => {
                            if (res?.updated) {
                                setExtractStatus('done');
                                clearTimeout(extractTimerRef.current);
                                extractTimerRef.current = setTimeout(
                                    () => setExtractStatus(''),
                                    3000
                                );
                            }
                        })
                        .catch(() => {});
                })
                .catch(() => {});
        };

        // ── Core round runner ─────────────────────────────────────────────────
        const runRound = async (userInput = null) => {
            setIsDebating(true);
            const cleanInput = (userInput ?? inputValue ?? '').toString().trim();

            if (cleanInput) {
                setHistory(prev => [...prev, { personaId: 'user', text: cleanInput }]);
                setInputValue('');
                // Reset textarea height
                if (inputFieldRef.current) {
                    inputFieldRef.current.style.height = 'auto';
                }
            }

            try {
                const situation = (context?.situation || '').trim();

                // Language detection: use cached, else detect and persist
                let lang = language;
                if (!lang) {
                    lang = detectLang(
                        cleanInput ||
                        situation ||
                        (history.findLast
                            ? history.findLast(m => m.personaId === 'user')?.text
                            : [...history].reverse().find(m => m.personaId === 'user')?.text) ||
                        ''
                    );
                    setLanguage(lang);
                    localStorage.setItem('lifee_lang', lang);
                }

                const payload = {
                    situation: situation || (history.length > 0 ? '' : 'Start the internal debate.'),
                    userInput: cleanInput,
                    personas: (selectedPersonas || []).map(p => ({ id: p.id, name: p.name })),
                    sessionId: sessionId,
                    userId: user?.id || '',
                    language: lang,
                    moderator: followUpMode,
                    webSearch: webSearchMode,
                    maxSpeakers: maxSpeakers,
                };

                if (!payload.personas.length) {
                    setOptions([]);
                    return;
                }

                const handlers = {
                    onMessage: async (msg) => {
                        setHistory(prev => [...prev, msg]);
                    },
                    onMessageUpdate: async (msg) => {
                        setHistory(prev => {
                            const updated = [...prev];
                            if (
                                updated.length > 0 &&
                                updated[updated.length - 1].personaId === msg.personaId
                            ) {
                                updated[updated.length - 1] = { ...msg };
                            }
                            return updated;
                        });
                    },
                    onOptions: (opts) => {
                        setOptions(Array.isArray(opts) ? opts : []);
                    },
                };

                if (credits !== null && credits <= 0) {
                    setShowPaywall(true);
                    setIsDebating(false);
                    return;
                }

                try {
                    await fetchLifeeDecisionStream(payload, handlers);
                    if (window.__lifeeNeedsVerification) {
                        window.__lifeeNeedsVerification = false;
                        setVerifyError('');
                        setShowVerify(true);
                        return;
                    }
                    if (window.__lifeeNeedsPayment) {
                        window.__lifeeNeedsPayment = false;
                        setCredits(window.__lifeeBalance || 0);
                        setShowPaywall(true);
                        return;
                    }
                    if (window.__lifeeSessionId) setSessionId(window.__lifeeSessionId);
                    if (typeof window.__lifeeBalance === 'number') setCredits(window.__lifeeBalance);
                } catch (streamErr) {
                    console.warn('[ChatArena] stream failed; fallback', streamErr);
                    const data = await fetchLifeeDecision(payload);
                    if (data?.needsVerification) { setVerifyError(''); setShowVerify(true); return; }
                    if (data?.needsPayment) { setCredits(data.balance || 0); setShowPaywall(true); return; }
                    if (Array.isArray(data?.messages)) {
                        for (const m of data.messages) await handlers.onMessage(m);
                    }
                    if (Array.isArray(data?.options)) handlers.onOptions(data.options);
                    if (data?.sessionId) setSessionId(data.sessionId);
                    if (typeof data?.balance === 'number') setCredits(data.balance);
                }
            } catch (e) {
                console.error('[ChatArena]', e);
                setHistory(prev => [
                    ...prev,
                    { personaId: 'system', text: `(${e?.message || 'Request failed'})` },
                ]);
                setOptions([]);
            } finally {
                setIsDebating(false);
                fireExtractMemory(sessionIdRef.current);
            }
        };

        // ── Auto-start on mount ───────────────────────────────────────────────
        useEffect(() => {
            if (autoStartedRef.current) return;
            if (!(selectedPersonas?.length)) return;
            const initial = (context?.situation || '').trim();
            if (!initial) return;
            autoStartedRef.current = true;
            runRound(initial);
        }, [selectedPersonas?.length]);

        // ── Summary ───────────────────────────────────────────────────────────
        const handleSummary = async () => {
            if (history.length < 2 || summaryLoading) return;

            // Return cached if nothing new
            if (
                summaryAtCountRef.current === history.length &&
                Object.keys(summaryData).length > 0 &&
                !summaryData._error
            ) {
                setShowSummaryPanel(true);
                return;
            }

            const payload = sessionId
                ? JSON.stringify({ sessionId, language: language || 'Chinese' })
                : JSON.stringify({
                    messages: history
                        .filter(
                            m =>
                                m.personaId !== 'user' &&
                                m.personaId !== 'system' &&
                                m.personaId !== 'lifee-followup'
                        )
                        .slice(-4)
                        .map(m => ({
                            personaId: m.personaId,
                            text: (m.text || '').slice(0, 150),
                        })),
                    language: language || 'Chinese',
                });

            setSummaryLoading(true);
            setSummaryData({});
            try {
                const r = await window.fetch('/summarize', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: payload,
                });
                const res = await r.json();
                if (res?.error) {
                    setSummaryData({ _error: res.error });
                } else if (res?.summaries && Object.keys(res.summaries).length > 0) {
                    setSummaryData(res.summaries);
                    summaryAtCountRef.current = history.length;
                    setShowSummaryPanel(true);
                } else {
                    setSummaryData({ _error: 'No summary returned' });
                }
            } catch (e) {
                setSummaryData({ _error: e.message || 'Network error' });
            } finally {
                setSummaryLoading(false);
            }
        };

        // ── Clipboard ─────────────────────────────────────────────────────────
        const copyText = (text) => { copyToClipboard(text); };

        const quoteText = (text, name) => {
            const quote = `"${text}" — ${name}\n\n`;
            setInputValue(prev => quote + prev);
            inputFieldRef.current?.focus();
        };

        // ── Render helpers ────────────────────────────────────────────────────
        const renderMessage = (m, idx) => {
            const isUser     = m.personaId === 'user';
            const isSystem   = m.personaId === 'system';
            const isFollowUp = m.personaId === 'lifee-followup';

            if (isSystem) {
                return html`
                    <div key=${idx} class="flex justify-center my-2">
                        <span class="text-[10px] text-on-surface-variant/50 bg-surface-container/60 px-4 py-1.5 rounded-full tracking-wide">
                            ${m.text}
                        </span>
                    </div>
                `;
            }

            if (isUser) {
                const ava = userAvatar || '🙂';
                return html`
                    <div key=${idx} class="flex items-start gap-4 max-w-[85%] md:max-w-[70%] ml-auto flex-row-reverse animate-in">
                        <!-- Avatar -->
                        <div class="w-10 h-10 rounded-full border-2 border-on-surface-variant/30 bg-surface-container-high flex items-center justify-center text-on-surface font-bold text-sm shrink-0 overflow-hidden">
                            ${typeof ava === 'string' && ava.length <= 2
                                ? html`<span class="text-lg">${ava}</span>`
                                : html`<img src=${ava} class="w-full h-full object-cover" />`
                            }
                        </div>
                        <!-- Bubble -->
                        <div class="space-y-1.5 items-end flex flex-col">
                            <p class="text-[10px] font-bold uppercase tracking-widest text-on-surface-variant/60 mr-1">You</p>
                            <div class="bg-surface-container/80 backdrop-blur-md px-5 py-4 rounded-xl rounded-tr-sm text-on-surface shadow-sm leading-relaxed border-r-2 border-on-surface-variant/20 text-sm whitespace-pre-wrap break-words">
                                ${m.text}
                            </div>
                            <div class="flex gap-3 px-1 flex-row-reverse">
                                <button
                                    onClick=${() => copyText(m.text)}
                                    class="flex items-center gap-1 text-[10px] font-bold text-on-surface-variant/40 hover:text-on-surface-variant transition-colors uppercase tracking-widest"
                                >Copy</button>
                            </div>
                        </div>
                    </div>
                `;
            }

            // Persona or follow-up message
            const persona = isFollowUp
                ? { name: 'LIFEE', avatar: '💬', id: 'lifee-followup' }
                : (
                    (selectedPersonas || []).find(x => x.id === m.personaId) ||
                    (window.INITIAL_PERSONAS || []).find(x => x.id === m.personaId) ||
                    { name: m.personaId || 'Voice', avatar: '☁️', id: m.personaId }
                );

            const color = isFollowUp
                ? { border: 'border-on-surface-variant/30', text: 'text-on-surface-variant/60', bg: 'bg-surface-container/50', ring: 'border-on-surface-variant/30' }
                : getColor(m.personaId);

            const ava = persona.avatar || '☁️';

            return html`
                <div key=${idx} class="flex items-start gap-4 max-w-[85%] md:max-w-[70%] animate-in">
                    <!-- Avatar -->
                    <div class=${'w-10 h-10 rounded-full border-2 flex items-center justify-center text-lg shrink-0 overflow-hidden ' + color.ring + ' ' + color.bg}>
                        ${typeof ava === 'string' && ava.length <= 2
                            ? html`<span>${ava}</span>`
                            : html`<img src=${ava} class="w-full h-full object-cover" />`
                        }
                    </div>
                    <!-- Bubble -->
                    <div class="space-y-1.5">
                        <p class=${'text-[10px] font-bold uppercase tracking-widest ml-1 ' + color.text}>
                            ${persona.name}
                        </p>
                        <div class=${'bg-surface-container/80 backdrop-blur-md px-5 py-4 rounded-xl rounded-tl-sm text-on-surface shadow-sm leading-relaxed border-t-2 text-sm whitespace-pre-wrap break-words ' + color.border}>
                            ${m.text}
                        </div>
                        <div class="flex gap-3 px-1">
                            <button
                                onClick=${() => copyText(m.text)}
                                class="flex items-center gap-1 text-[10px] font-bold text-on-surface-variant/40 hover:text-on-surface-variant transition-colors uppercase tracking-widest"
                            >Copy</button>
                            <button
                                onClick=${() => quoteText(m.text, persona.name)}
                                class="flex items-center gap-1 text-[10px] font-bold text-on-surface-variant/40 hover:text-on-surface-variant transition-colors uppercase tracking-widest"
                            >Quote</button>
                        </div>
                    </div>
                </div>
            `;
        };

        // ── Summary panel modal ───────────────────────────────────────────────
        const SummaryPanel = () => {
            if (!showSummaryPanel) return null;
            return html`
                <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
                    <div class="bg-surface-container border border-white/10 rounded-2xl max-w-lg w-full max-h-[80vh] overflow-y-auto shadow-2xl">
                        <div class="px-6 py-4 border-b border-white/10 flex items-center justify-between">
                            <span class="text-[10px] font-black uppercase tracking-[0.3em] text-on-surface-variant">Summary</span>
                            <button
                                onClick=${() => setShowSummaryPanel(false)}
                                class="text-on-surface-variant/50 hover:text-on-surface transition-colors text-lg leading-none"
                            >✕</button>
                        </div>
                        <div class="p-6 space-y-5">
                            ${Object.entries(summaryData)
                                .filter(([k]) => k !== '_error')
                                .map(([personaId, text]) => {
                                    const persona =
                                        (selectedPersonas || []).find(x => x.id === personaId) ||
                                        { name: personaId, avatar: '☁️' };
                                    const color = getColor(personaId);
                                    return html`
                                        <div key=${personaId} class=${'border-l-2 pl-4 py-1 ' + color.border}>
                                            <p class=${'text-[10px] font-bold uppercase tracking-widest mb-2 ' + color.text}>
                                                ${persona.name}
                                            </p>
                                            <p class="text-sm text-on-surface/80 leading-relaxed">${text}</p>
                                        </div>
                                    `;
                                })
                            }
                        </div>
                    </div>
                </div>
            `;
        };

        // ── More menu dropdown ────────────────────────────────────────────────
        const MoreMenu = () => {
            if (!showMoreMenu) return null;
            return html`
                <div
                    ref=${moreMenuRef}
                    class="absolute right-0 top-full mt-2 w-64 bg-surface-container/95 backdrop-blur-xl border border-white/10 rounded-2xl shadow-2xl z-50 overflow-hidden"
                >
                    <!-- Follow-up toggle -->
                    <div class="px-4 py-3 border-b border-white/5 flex items-center justify-between">
                        <span class="text-xs text-on-surface font-semibold">Follow-up Questions</span>
                        <button
                            onClick=${() => setFollowUpMode(v => !v)}
                            class=${'relative w-10 h-5 rounded-full transition-all duration-200 ' + (followUpMode ? 'bg-primary' : 'bg-surface-container-highest')}
                        >
                            <span class=${'absolute top-0.5 w-4 h-4 rounded-full bg-on-primary shadow transition-all duration-200 ' + (followUpMode ? 'left-5' : 'left-0.5')}></span>
                        </button>
                    </div>
                    <!-- Web search toggle -->
                    <div class="px-4 py-3 border-b border-white/5 flex items-center justify-between">
                        <span class="text-xs text-on-surface font-semibold">Web Search</span>
                        <button
                            onClick=${() => setWebSearchMode(v => !v)}
                            class=${'relative w-10 h-5 rounded-full transition-all duration-200 ' + (webSearchMode ? 'bg-secondary' : 'bg-surface-container-highest')}
                        >
                            <span class=${'absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-all duration-200 ' + (webSearchMode ? 'left-5' : 'left-0.5')}></span>
                        </button>
                    </div>
                    <!-- Max speakers select -->
                    ${(selectedPersonas || []).length > 1 ? html`
                        <div class="px-4 py-3 border-b border-white/5 flex items-center justify-between gap-3">
                            <span class="text-xs text-on-surface font-semibold">Max Speakers</span>
                            <select
                                value=${maxSpeakers}
                                onChange=${(e) => setMaxSpeakers(Number(e.target.value))}
                                class="text-xs text-on-surface bg-surface-container-high border border-white/10 rounded-lg px-2 py-1"
                            >
                                <option value=${0}>All</option>
                                ${Array.from({ length: (selectedPersonas || []).length - 1 }, (_, i) =>
                                    html`<option key=${i + 1} value=${i + 1}>${i + 1}</option>`
                                )}
                            </select>
                        </div>
                    ` : null}
                    <!-- Language select -->
                    <div class="px-4 py-3 flex items-center justify-between gap-3">
                        <span class="text-xs text-on-surface font-semibold">Language</span>
                        <select
                            value=${language}
                            onChange=${(e) => { setLanguage(e.target.value); localStorage.setItem('lifee_lang', e.target.value); }}
                            class="text-xs text-on-surface bg-surface-container-high border border-white/10 rounded-lg px-2 py-1"
                        >
                            <option value="">Auto</option>
                            <option value="Chinese">中文</option>
                            <option value="English">English</option>
                            <optgroup label="Other">
                                <option value="Japanese">日本語</option>
                                <option value="Korean">한국어</option>
                                <option value="French">Français</option>
                                <option value="German">Deutsch</option>
                                <option value="Spanish">Español</option>
                                <option value="Portuguese">Português</option>
                                <option value="Russian">Русский</option>
                                <option value="Arabic">العربية</option>
                                <option value="Italian">Italiano</option>
                                <option value="Dutch">Nederlands</option>
                                <option value="Polish">Polski</option>
                                <option value="Turkish">Türkçe</option>
                                <option value="Thai">ไทย</option>
                                <option value="Vietnamese">Tiếng Việt</option>
                                <option value="Indonesian">Bahasa Indonesia</option>
                                <option value="Hindi">हिन्दी</option>
                            </optgroup>
                        </select>
                    </div>
                </div>
            `;
        };

        // ── Main render ───────────────────────────────────────────────────────
        return html`
            <div class="h-full flex flex-col overflow-hidden bg-surface text-on-surface">

                <!-- ── Header ── -->
                <header class="flex justify-between items-center w-full px-8 h-20 bg-surface-dim/30 backdrop-blur-lg border-b border-white/5 z-10 shrink-0">
                    <div class="flex items-center gap-6">
                        <div>
                            <h2 class="text-xl md:text-2xl font-headline font-bold tracking-tight text-on-surface">Void Chat</h2>
                            <p class="text-[10px] uppercase tracking-[0.2em] text-primary/80 leading-none mt-0.5">Internal Debate Ecosystem</p>
                        </div>
                        <!-- Member Avatars cluster — max 4 shown, then +N -->
                        <div class="hidden lg:flex -space-x-3 ml-4">
                            ${(selectedPersonas || []).slice(0, 4).map((p, idx) => {
                                const color = PERSONA_COLORS[idx % PERSONA_COLORS.length];
                                const ava = p.avatar || '☁️';
                                return html`
                                    <div
                                        key=${p.id}
                                        class=${'w-8 h-8 rounded-full border-2 overflow-hidden shadow-sm flex items-center justify-center text-sm ' + color.ring + ' ' + color.bg}
                                        title=${p.name}
                                    >
                                        ${typeof ava === 'string' && ava.length <= 2
                                            ? html`<span>${ava}</span>`
                                            : html`<img src=${ava} class="w-full h-full object-cover" />`
                                        }
                                    </div>
                                `;
                            })}
                            ${(selectedPersonas || []).length > 4 ? html`
                                <div class="w-8 h-8 rounded-full bg-surface-variant flex items-center justify-center text-[10px] font-bold text-on-surface-variant border-2 border-surface-container-high">
                                    +${(selectedPersonas || []).length - 4}
                                </div>
                            ` : null}
                        </div>
                    </div>

                    <!-- Right action buttons -->
                    <div class="flex items-center gap-5">
                        <!-- Credits badge -->
                        ${credits !== null ? html`
                            <span class="hidden sm:inline text-[10px] font-bold text-on-surface-variant border border-white/10 rounded-full px-3 py-1">
                                ${credits} cr
                            </span>
                        ` : null}

                        <div class="flex items-center gap-4 text-on-surface-variant/60">
                            <!-- Summary -->
                            <span
                                class=${'material-symbols-outlined cursor-pointer transition-colors ' + (history.length < 2 || summaryLoading ? 'opacity-30 pointer-events-none' : 'hover:text-primary')}
                                title="Summary"
                                onClick=${handleSummary}
                            >${summaryLoading ? 'hourglass_empty' : 'summarize'}</span>

                            <!-- Stop & Decide -->
                            <span
                                class="material-symbols-outlined cursor-pointer hover:text-primary transition-colors"
                                title="Stop & Decide"
                                onClick=${() => setView('summary')}
                            >stop_circle</span>

                            <!-- More menu -->
                            <div class="relative">
                                <span
                                    class=${'material-symbols-outlined cursor-pointer transition-colors ' + (showMoreMenu ? 'text-primary' : 'hover:text-primary')}
                                    title="More options"
                                    onClick=${() => setShowMoreMenu(v => !v)}
                                >more_vert</span>
                                <${MoreMenu} />
                            </div>
                        </div>
                    </div>
                </header>

                <!-- ── Messages scroll area ── -->
                <div
                    ref=${scrollRef}
                    class="flex-1 overflow-y-auto no-scrollbar"
                    style=${{ scrollbarWidth: 'none' }}
                >
                  <div class="max-w-3xl mx-auto w-full px-6 py-8 space-y-8">
                    ${history.length === 0 && !isDebating ? html`
                        <div class="flex flex-col items-center justify-center h-full text-center space-y-4 opacity-30 select-none">
                            <div class="text-4xl">✦</div>
                            <p class="text-[11px] uppercase tracking-[0.35em] text-on-surface-variant/60">
                                The void awaits your transmission
                            </p>
                        </div>
                    ` : null}

                    ${history.map((m, idx) => renderMessage(m, idx))}

                    <!-- Typing indicator — smooth ease-out dots instead of bounce -->
                    ${isDebating ? html`
                        <div class="flex items-start gap-4">
                            <div class="w-10 h-10 rounded-full bg-surface-container border border-white/10 shrink-0"></div>
                            <div class="flex items-center gap-1.5 bg-surface-container/80 px-5 py-4 rounded-xl rounded-tl-sm border-t-2 border-on-surface-variant/20 h-[54px]">
                                <span class="typing-dot w-1.5 h-1.5 rounded-full bg-primary/50" style=${{ animationDelay: '0ms' }}></span>
                                <span class="typing-dot w-1.5 h-1.5 rounded-full bg-primary/50" style=${{ animationDelay: '200ms' }}></span>
                                <span class="typing-dot w-1.5 h-1.5 rounded-full bg-primary/50" style=${{ animationDelay: '400ms' }}></span>
                            </div>
                        </div>
                    ` : null}
                  </div>
                </div>

                <!-- ── Footer input area ── -->
                <footer class="p-6 bg-surface-dim/40 backdrop-blur-2xl border-t border-white/5 shrink-0">
                    <div class="max-w-3xl mx-auto space-y-3">

                        <!-- Options pills -->
                        ${options.length > 0 && !isDebating ? html`
                            <div class="flex flex-wrap gap-2 animate-in justify-center">
                                ${options.map((opt, i) => html`
                                    <button
                                        key=${i}
                                        onClick=${() => runRound(opt)}
                                        class="px-4 py-2 text-xs font-semibold rounded-full border border-primary/30 text-primary/80 bg-primary/10 hover:bg-primary/20 hover:border-primary/50 transition-all"
                                    >${opt}</button>
                                `)}
                            </div>
                        ` : null}

                        <!-- Main input row -->
                        <div class="input-warm-focus flex items-center bg-surface-container-lowest border border-white/5 rounded-2xl p-2 transition-all duration-300">
                            <!-- Add attachment -->
                            <button class="p-2 text-on-surface-variant/40 hover:text-primary transition-colors shrink-0">
                                <span class="material-symbols-outlined">add_circle</span>
                            </button>

                            <!-- Textarea -->
                            <textarea
                                ref=${inputFieldRef}
                                maxLength=${1000}
                                rows=${1}
                                placeholder="Type a transmission..."
                                disabled=${isDebating}
                                class="flex-1 bg-transparent text-sm text-on-surface placeholder-on-surface-variant/30 resize-none focus:outline-none focus:ring-0 border-none min-h-[36px] max-h-[140px] px-4 py-3 font-body leading-relaxed overflow-y-auto"
                                style=${{ scrollbarWidth: 'none' }}
                                value=${inputValue}
                                onChange=${(e) => {
                                    setInputValue(e.target.value);
                                    e.target.style.height = 'auto';
                                    e.target.style.height = Math.min(e.target.scrollHeight, 140) + 'px';
                                }}
                                onKeyDown=${(e) => {
                                    if (e.key === 'Enter' && !e.shiftKey && inputValue.trim()) {
                                        e.preventDefault();
                                        runRound();
                                    }
                                }}
                            />

                            <!-- Char count -->
                            ${inputValue.length > 400 ? html`
                                <span class="text-[10px] text-on-surface-variant/30 self-center shrink-0 mr-1">${inputValue.length}/1000</span>
                            ` : null}

                            <div class="flex items-center gap-2 pr-2 shrink-0">
                                <!-- Emoji -->
                                <button class="p-2 text-on-surface-variant/40 hover:text-secondary transition-colors">
                                    <span class="material-symbols-outlined">sentiment_satisfied</span>
                                </button>

                                <!-- Send button -->
                                <button
                                    disabled=${isDebating || !inputValue.trim()}
                                    onClick=${() => runRound()}
                                    class="w-12 h-12 flex items-center justify-center rounded-xl btn-gradient shadow-lg shadow-primary/20 hover:scale-105 active:scale-95 transition-transform disabled:opacity-30 disabled:pointer-events-none"
                                >
                                    <span class="material-symbols-outlined" style=${{ fontVariationSettings: "'FILL' 1" }}>send</span>
                                </button>
                            </div>
                        </div>

                        <!-- Stay Silent link + profile extract status -->
                        <div class="flex items-center justify-between px-1">
                            <button
                                disabled=${isDebating}
                                onClick=${() => runRound(null)}
                                class="text-[10px] font-black uppercase tracking-widest text-on-surface-variant/30 hover:text-on-surface-variant/60 transition-colors disabled:opacity-30"
                            >Stay Silent</button>

                            ${extractStatus === 'done' ? html`
                                <div class="flex items-center gap-1.5 text-[10px] text-on-surface-variant/50 animate-in">
                                    <span class="material-symbols-outlined text-sm" style=${{ fontSize: '14px' }}>auto_stories</span>
                                    Profile updated
                                </div>
                            ` : html`<span></span>`}
                        </div>
                    </div>
                </footer>

                <!-- ── Summary panel modal ── -->
                <${SummaryPanel} />

                <!-- ── Summary error toast ── -->
                ${summaryData._error ? html`
                    <div class="fixed top-24 right-4 z-50 text-xs text-rose-300 bg-rose-900/80 border border-rose-500/30 px-4 py-3 rounded-2xl shadow-lg backdrop-blur-md">
                        ${summaryData._error}
                        <button onClick=${() => setSummaryData({})} class="ml-2 opacity-50 hover:opacity-100">✕</button>
                    </div>
                ` : null}

                <!-- ── Human verification modal ── -->
                ${showVerify ? html`
                    <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
                        <div class="bg-surface-container border border-white/10 rounded-2xl p-8 max-w-sm mx-4 shadow-2xl text-center">
                            <div class="text-4xl mb-4">🛡️</div>
                            <h3 class="text-lg font-bold mb-2 text-on-surface">Please verify you're human</h3>
                            <div ref=${verifyRef} class="flex justify-center mb-4"></div>
                            ${(() => {
                                setTimeout(() => {
                                    if (verifyRef.current && window.turnstile && !verifyWidgetRef.current) {
                                        verifyWidgetRef.current = window.turnstile.render(verifyRef.current, {
                                            sitekey: typeof TURNSTILE_SITEKEY !== 'undefined' ? TURNSTILE_SITEKEY : '',
                                            callback: async (token) => {
                                                const result = await verifyHumanTokenWithServer(token);
                                                if (result.ok) {
                                                    setVerifyError('');
                                                    setShowVerify(false);
                                                    verifyWidgetRef.current = null;
                                                } else {
                                                    setVerifyError(result.message || 'Verification failed. Please retry.');
                                                }
                                            },
                                            theme: 'dark',
                                        });
                                    }
                                }, 100);
                                return null;
                            })()}
                            ${verifyError ? html`
                                <div class="text-xs text-rose-300 bg-rose-900/50 border border-rose-500/30 px-4 py-3 rounded-xl mb-4">
                                    ${verifyError}
                                </div>
                            ` : null}
                            <button
                                onClick=${() => setShowVerify(false)}
                                class="text-sm text-on-surface-variant/50 hover:text-on-surface-variant transition-colors"
                            >Cancel</button>
                        </div>
                    </div>
                ` : null}

                <!-- ── Paywall modal ── -->
                ${showPaywall ? html`
                    <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
                        <div class="bg-surface-container border border-white/10 rounded-2xl p-8 max-w-sm mx-4 shadow-2xl text-center">
                            <div class="text-4xl mb-4">🔒</div>
                            <h3 class="text-lg font-bold mb-2 text-on-surface">Credits Used Up</h3>
                            <p class="text-sm text-on-surface-variant/60 mb-6">Enter a redeem code to continue the conversation.</p>
                            <input
                                type="text"
                                placeholder="Enter redeem code"
                                value=${redeemCode}
                                onChange=${(e) => setRedeemCode(e.target.value)}
                                class="w-full px-4 py-3 bg-surface-container-high border border-white/10 rounded-xl mb-4 text-center text-lg tracking-widest uppercase text-on-surface focus:outline-none focus:border-primary/40"
                            />
                            <button
                                onClick=${async () => {
                                    const res = await fetch('/credits/redeem', {
                                        method: 'POST',
                                        headers: { 'Content-Type': 'application/json' },
                                        credentials: 'include',
                                        body: JSON.stringify({ code: redeemCode, userId: user?.id || '' }),
                                    }).then(r => r.json());
                                    if (res.ok) {
                                        setCredits(res.balance);
                                        setShowPaywall(false);
                                        setRedeemCode('');
                                    } else {
                                        alert(res.message || 'Invalid code');
                                    }
                                }}
                                class="w-full py-3 btn-gradient rounded-xl font-bold"
                            >Redeem</button>
                            <button
                                onClick=${() => setShowPaywall(false)}
                                class="mt-3 text-sm text-on-surface-variant/50 hover:text-on-surface-variant transition-colors"
                            >Cancel</button>
                        </div>
                    </div>
                ` : null}

                <style>${`
                    @keyframes spin { to { transform: rotate(360deg); } }
                    .animate-in { animation: fadeSlideIn 0.2s ease-out both; }
                    @keyframes fadeSlideIn {
                        from { opacity: 0; transform: translateY(6px); }
                        to   { opacity: 1; transform: translateY(0); }
                    }
                    .no-scrollbar::-webkit-scrollbar { display: none; }

                    /* Warm amber focus glow on input */
                    .input-warm-focus:focus-within {
                        box-shadow: 0 0 0 2px rgba(232, 168, 76, 0.2), 0 0 20px rgba(232, 168, 76, 0.08);
                        border-color: rgba(232, 168, 76, 0.25) !important;
                    }

                    /* Smooth typing indicator — ease-out pulse instead of bounce */
                    @keyframes typingPulse {
                        0%, 100% { opacity: 0.3; transform: scale(0.85); }
                        50%       { opacity: 1;   transform: scale(1);    }
                    }
                    .typing-dot {
                        animation: typingPulse 1.2s ease-in-out infinite;
                    }
                `}</style>
            </div>
        `;
    };

    // ── Register in VOID_VIEWS ────────────────────────────────────────────────
    window.VOID_VIEWS = window.VOID_VIEWS || {};
    window.VOID_VIEWS.debate = (props) => html`<${ChatArena} ...${props} />`;

})();
