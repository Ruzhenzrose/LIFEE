(() => {
    const { useState, useEffect, useLayoutEffect, useRef, useMemo } = React;
    const html = htm.bind(React.createElement);

    // i18n shims — the real t / useLocale are installed on window by
    // index.html's inline script AFTER this file's IIFE runs, so we defer to
    // window at call-time (not at IIFE-parse time).
    const t = (key) => (typeof window !== 'undefined' && typeof window.t === 'function' ? window.t(key) : key);
    const useLocale = () => (typeof window !== 'undefined' && typeof window.useLocale === 'function' ? window.useLocale() : 'en');

    // ── ShinyLines: split text into per-visual-line spans using Pretext (loaded via ES
    // module in index.html and exposed on window.Pretext). Each line renders as its own
    // <span> so the warm-shine band aligns with the line the cursor is actually on.
    //
    // Props:
    //   fontStr       — CSS font shorthand passed to Pretext for measurement.
    //                   Must match the rendered font. Defaults to chat bubble text.
    //   lineHeightPx  — px value matching CSS line-height of the rendered text.
    //   maxLines      — if set, only render the first N lines (replaces CSS line-clamp).
    //
    // Width: we use node.offsetWidth (unscaled) rather than getBoundingClientRect
    // (which returns transform-scaled width). This keeps line breaks correct when the
    // ShinyLines sits inside a CSS transform scale (e.g. the voice-map canvas).
    const PRETEXT_FONT = '14px "Manrope", sans-serif';
    const PRETEXT_LINE_HEIGHT = 22; // text-sm × leading-relaxed ≈ 14 × 1.625 ≈ 22

    const ShinyLines = ({ text, fontStr, lineHeightPx, maxLines }) => {
        const ref = useRef(null);
        const [lines, setLines] = useState(null);
        const font = fontStr || PRETEXT_FONT;
        const lh = lineHeightPx || PRETEXT_LINE_HEIGHT;

        useLayoutEffect(() => {
            const node = ref.current;
            if (!node) return;
            let cancelled = false;

            const layout = () => {
                if (cancelled) return;
                const P = window.Pretext;
                if (!P || !P.prepareWithSegments) return false;
                const width = node.offsetWidth || node.getBoundingClientRect().width;
                if (!width || width < 10) return false;
                try {
                    const prepared = P.prepareWithSegments(text, font, { whiteSpace: 'pre-wrap' });
                    const out = P.layoutWithLines(prepared, width, lh);
                    setLines((out.lines || []).map(l => l.text));
                    return true;
                } catch (e) {
                    console.warn('[ShinyLines] layout failed', e);
                    return false;
                }
            };

            const run = () => {
                if (!layout()) {
                    const onReady = () => { window.removeEventListener('pretext-ready', onReady); layout(); };
                    window.addEventListener('pretext-ready', onReady);
                }
            };
            run();

            const obs = new ResizeObserver(() => layout());
            obs.observe(node);
            return () => { cancelled = true; obs.disconnect(); };
        }, [text, font, lh]);

        const shown = lines === null
            ? null
            : (typeof maxLines === 'number' && maxLines > 0 ? lines.slice(0, maxLines) : lines);
        const wasClamped = lines && shown && shown.length < lines.length;

        return html`
            <div ref=${ref} class="w-full">
                ${shown === null
                    ? html`<span class="whitespace-pre-wrap break-words">${text}</span>`
                    : shown.flatMap((line, i) => {
                        const isLast = i === shown.length - 1;
                        const suffix = (isLast && wasClamped) ? '…' : '';
                        return i === 0
                            ? [html`<span key=${'s' + i}>${line}${suffix}</span>`]
                            : [html`<br key=${'br' + i} />`, html`<span key=${'s' + i}>${line}${suffix}</span>`];
                    })
                }
            </div>
        `;
    };

    // ── Persona accent color generator ────────────────────────────────────────
    // 12 base hues on the colour wheel, ordered to jump across hue space so
    // neighbouring indexes always look different. Past index 11 we wrap and
    // shift lightness / saturation in tandem with a small hue rotation so
    // every further index produces a colour that is visually distinct from
    // the ones before it — effectively unlimited uniqueness.
    //
    // Shape mirrors the prior PERSONA_COLORS entries so every call site keeps
    // { border, text, bg, ring } — but the values are CSS colour strings now,
    // consumed via inline `style` instead of Tailwind classes.
    const BASE_HUES = [35, 200, 340, 160, 270, 20, 185, 300, 80, 245, 5, 175];
    // Per-wrap lightness/saturation variants. Each row is a different "tier"
    // so the palette never repeats exactly — lightness pulls the colour toward
    // pastel or deep, saturation varies the mood.
    const TIER_VARIANTS = [
        { dL:   0, dS:   0, dH:  0 },   // base
        { dL:  12, dS:  -8, dH:  8 },   // pastel-shifted
        { dL: -12, dS:   0, dH: -6 },   // deeper-shifted
        { dL:   6, dS: -20, dH: 14 },   // muted-bright
        { dL: -18, dS:  10, dH:  4 },   // rich-deep
        { dL:  16, dS:  -4, dH: -10 },  // pale-cool
    ];
    const getPersonaColorByIndex = (index) => {
        const i = ((index | 0) % 1000 + 1000) % 1000; // normalise to non-negative
        const hue = BASE_HUES[i % BASE_HUES.length];
        const tier = TIER_VARIANTS[Math.floor(i / BASE_HUES.length) % TIER_VARIANTS.length];
        const h = (hue + tier.dH + 360) % 360;
        const s = Math.max(42, Math.min(92, 72 + tier.dS));
        const l = Math.max(45, Math.min(82, 65 + tier.dL));
        const text   = `hsl(${h} ${s}% ${l}%)`;
        const border = text;
        const bg     = `hsla(${h} ${Math.max(35, s - 15)}% 22% / 0.4)`;
        return { border, text, bg, ring: border };
    };

    // Back-compat: some existing code reads PERSONA_COLORS[idx % length]. We keep
    // it as a thin proxy so those sites keep working without change.
    const PERSONA_COLORS = new Proxy([], {
        get(_, key) {
            if (key === 'length') return 1000;
            const n = Number(key);
            if (Number.isFinite(n)) return getPersonaColorByIndex(n);
            return undefined;
        },
    });

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
        allPersonas = [],
        setSelectedIds,
        setView,
        userAvatar,
        user,
        initialMessages = [],
        initialOptions = [],
        parentSessionId = "",
        onSessionCreated,
        onOpenShare,
    }) => {
        // ── State ─────────────────────────────────────────────────────────────
        const [history, setHistory]             = useState(initialMessages);
        const [options, setOptions]             = useState(initialOptions || []);
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
        // Persist summaries per session so they survive refresh. Shape:
        //   { [sessionId]: { summaries: {personaId: text}, atCount: number } }
        const loadSummaryStore = () => {
            try { return JSON.parse(window.localStorage.getItem('lifee_summary_store') || '{}') || {}; }
            catch (_) { return {}; }
        };
        const saveSummaryEntry = (sid, summaries, atCount) => {
            if (!sid) return;
            try {
                const store = loadSummaryStore();
                store[sid] = { summaries, atCount };
                window.localStorage.setItem('lifee_summary_store', JSON.stringify(store));
            } catch (_) {}
        };
        const [summaryLoading, setSummaryLoading] = useState(false);
        const [showMoreMenu, setShowMoreMenu]   = useState(false);
        const [showToolsMenu, setShowToolsMenu] = useState(false);
        const [showVoiceMap, setShowVoiceMap]   = useState(false);
        const [showMembersPanel, setShowMembersPanel] = useState(false);
        // Keep ~120px of chat visible so the user can always see there's a chat
        // on the left (and grab the resize handle to pull the map back).
        const mapMaxWidth = () => Math.max(320, (typeof window !== 'undefined' ? window.innerWidth : 1280) - 120);
        const [mapWidth, setMapWidth]           = useState(() => {
            try {
                const n = Number(window.localStorage.getItem('lifee_voice_map_width'));
                const max = mapMaxWidth();
                if (Number.isFinite(n) && n >= 320) return Math.min(n, max);
                return Math.min(560, max);
            } catch (_) { return 560; }
        });
        useEffect(() => {
            try { window.localStorage.setItem('lifee_voice_map_width', String(mapWidth)); } catch (_) {}
        }, [mapWidth]);
        // Re-clamp on window resize so buttons never get pushed off-screen.
        useEffect(() => {
            const onResize = () => setMapWidth(w => Math.min(w, mapMaxWidth()));
            window.addEventListener('resize', onResize);
            return () => window.removeEventListener('resize', onResize);
        }, []);

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
        const toolsMenuRef     = useRef(null);
        const optionsCacheRef  = useRef({});  // sessionId → options[]
        // Round guard: increments on every runRound and on session-switch. Stream
        // callbacks capture the value at start-of-round; if it changed, they drop
        // their updates (prevents old-session chunks polluting a new session's view).
        const roundIdRef       = useRef(0);
        // Latched when user clicks Stop: Supabase Realtime updates for this session
        // are ignored until the next round starts. (The in-flight SSE handlers are
        // already invalidated via roundIdRef, but Realtime events bypass that gate.)
        const stoppedRef       = useRef(false);

        // ── Unified gate + commit ───────────────────────────────────────────────
        // Three update sources funnel through here:
        //   - 'sse': the active POST stream in runRound (also observer-stream), round-scoped
        //   - 'realtime': Supabase postgres_changes fallback, no round concept
        // canApply() is the one place that blocks after Stop / on superseded rounds.
        // commitMessage() handles append-or-update with seq + last-item dedup + anti-regress.
        const canApply = (origin, myRound) => {
            if (stoppedRef.current) return false;
            if (origin === 'sse' && myRound !== undefined && myRound !== roundIdRef.current) return false;
            if (origin === 'realtime' && isDebatingRef.current) return false;
            return true;
        };
        const commitMessage = (incoming, origin, myRound) => {
            if (!canApply(origin, myRound)) return;
            const msg = {
                personaId: incoming.personaId || incoming.persona_id || incoming.role,
                text: incoming.text || incoming.content || '',
                seq: incoming.seq,
            };
            if (!msg.personaId) return;
            setHistory(prev => {
                // Locate existing row: by seq if provided, else by last-item matching personaId.
                let idx = -1;
                if (msg.seq != null) idx = prev.findIndex(m => m.seq === msg.seq);
                if (idx < 0 && prev.length > 0 && prev[prev.length - 1].personaId === msg.personaId) {
                    idx = prev.length - 1;
                }
                if (idx >= 0) {
                    // Anti-regress: don't let a late, shorter update shrink what's shown.
                    const existingLen = (prev[idx].text || '').length;
                    if (msg.text.length < existingLen) return prev;
                    const next = [...prev];
                    next[idx] = { ...prev[idx], ...msg };
                    return next;
                }
                const next = [...prev, msg];
                if (msg.seq != null) next.sort((a, b) => (a.seq ?? 1e9) - (b.seq ?? 1e9));
                return next;
            });
        };
        const commitOptions = (opts, origin, myRound) => {
            if (!canApply(origin, myRound)) return;
            setOptions(Array.isArray(opts) ? opts : []);
        };
        const commitSession = (sid, origin, myRound) => {
            if (!canApply(origin, myRound)) return;
            setSessionId(sid);
            try { onSessionCreated?.(sid); } catch (_) {}
        };
        const makeSseHandlers = (myRound) => ({
            onSession:       (sid) => commitSession(sid, 'sse', myRound),
            onMessage:       (msg) => commitMessage(msg, 'sse', myRound),
            onMessageUpdate: (msg) => commitMessage(msg, 'sse', myRound),
            onOptions:       (opts) => commitOptions(opts, 'sse', myRound),
        });

        useEffect(() => {
            sessionIdRef.current = sessionId;
            // Rehydrate persisted summary for this session (survives refresh).
            if (sessionId) {
                try {
                    const store = loadSummaryStore();
                    const entry = store[sessionId];
                    if (entry?.summaries && Object.keys(entry.summaries).length > 0) {
                        setSummaryData(entry.summaries);
                        summaryAtCountRef.current = entry.atCount || 0;
                    } else {
                        setSummaryData({});
                        summaryAtCountRef.current = 0;
                    }
                } catch (_) {}
            } else {
                // New/empty session — clear any stale summary.
                setSummaryData({});
                summaryAtCountRef.current = 0;
            }
        }, [sessionId]);

        // Persist options per-session as they change
        useEffect(() => {
            if (sessionId) optionsCacheRef.current[sessionId] = options;
        }, [options, sessionId]);

        // Sync with parent state changes (New Session / restore / navigate away)
        useEffect(() => {
            // Only reset when the SWITCH is external (user picked another session /
            // hit New Session). If the parent is just catching up with the id we
            // already set locally (via onSessionCreated during our own stream),
            // leave state alone — otherwise we'd kill our own in-flight round.
            if ((parentSessionId || '') === (sessionIdRef.current || '')) return;

            roundIdRef.current += 1;
            setSessionId(parentSessionId || '');
            setHistory(initialMessages || []);
            const cached = optionsCacheRef.current[parentSessionId];
            setOptions((cached && cached.length) ? cached : (initialOptions || []));
            setSummaryData({});
            setIsDebating(false);
            autoStartedRef.current = false;
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

        // ── Observer SSE: resume an in-flight generation after returning ─────
        // When ChatArena shows a session with backend generation still running
        // (detached task), attach to it with a fresh SSE. Feels identical to
        // the original stream: token-by-token, loading indicator, same handlers.
        useEffect(() => {
            if (!sessionId) return;
            // If this tab is already the streamer, don't double-subscribe
            if (isDebating) return;
            const myRound = ++roundIdRef.current;
            stoppedRef.current = false;  // fresh attach — reopen the gate
            let cancelled = false;
            (async () => {
                try {
                    setIsDebating(true);
                    await fetchLifeeObserveStream(sessionId, makeSseHandlers(myRound));
                } catch (e) {
                    if (!e?.notActive) console.warn('[observe]', e);
                } finally {
                    if (!cancelled && roundIdRef.current === myRound) setIsDebating(false);
                }
            })();
            return () => { cancelled = true; };
        }, [sessionId]);

        // ── Supabase Realtime: live-sync DB changes into history ─────────────
        // Only replaces local history when DB strictly has MORE content (by row
        // count, or same count with a longer last message). Prevents the race
        // where DB lags behind local SSE state and overwrites it.
        const isDebatingRef = useRef(false);
        useEffect(() => { isDebatingRef.current = isDebating; }, [isDebating]);
        useEffect(() => {
            if (!sessionId || !window.supabaseClient) return;
            const channel = window.supabaseClient
                .channel(`session-${sessionId}`)
                .on('postgres_changes', {
                    event: '*',
                    schema: 'public',
                    table: 'chat_messages',
                    filter: `session_id=eq.${sessionId}`,
                }, (payload) => commitMessage(payload.new || {}, 'realtime'))
                .subscribe();
            return () => {
                try { window.supabaseClient.removeChannel(channel); } catch (_) {}
            };
        }, [sessionId]);

        // ── Close tools menu on outside click ────────────────────────────────
        useEffect(() => {
            if (!showToolsMenu) return;
            const handler = (e) => {
                if (toolsMenuRef.current && !toolsMenuRef.current.contains(e.target)) {
                    setShowToolsMenu(false);
                }
            };
            document.addEventListener('mousedown', handler);
            return () => document.removeEventListener('mousedown', handler);
        }, [showToolsMenu]);

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

        // ── Auto-scroll (respects manual scroll-up during streaming) ──────────
        const stickyBottomRef = useRef(true);  // whether we should follow new content
        useEffect(() => {
            const el = scrollRef.current;
            if (!el) return;
            const onScroll = () => {
                const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
                stickyBottomRef.current = nearBottom;
            };
            el.addEventListener('scroll', onScroll, { passive: true });
            return () => el.removeEventListener('scroll', onScroll);
        }, []);
        useEffect(() => {
            const el = scrollRef.current;
            if (!el) return;
            if (stickyBottomRef.current) {
                el.scrollTop = el.scrollHeight;
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

        // ── Stop the in-flight generation (stop-and-keep: whatever is already
        // streamed stays visible + persisted; backend cancels the detached task). ─
        const handleStop = async () => {
            roundIdRef.current += 1;  // invalidate any handlers still in flight
            stoppedRef.current = true; // block late Realtime updates too
            setIsDebating(false);
            const sid = sessionIdRef.current || window.__lifeeSessionId;
            if (!sid) return;
            try {
                await fetch(`/sessions/${encodeURIComponent(sid)}/cancel`, {
                    method: 'POST',
                    credentials: 'include',
                });
            } catch (_) {}
        };

        // ── Core round runner ─────────────────────────────────────────────────
        const runRound = async (userInput = null) => {
            const myRound = ++roundIdRef.current;  // claim this round
            stoppedRef.current = false;            // reopen Realtime gate for the new round
            const isActive = () => roundIdRef.current === myRound;
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

                const handlers = makeSseHandlers(myRound);

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
                        window.dispatchEvent(new CustomEvent('lifee:balance', { detail: window.__lifeeBalance || 0 }));
                        setShowPaywall(true);
                        return;
                    }
                    if (isActive() && window.__lifeeSessionId) setSessionId(window.__lifeeSessionId);
                    if (typeof window.__lifeeBalance === 'number') {
                        setCredits(window.__lifeeBalance);
                        window.dispatchEvent(new CustomEvent('lifee:balance', { detail: window.__lifeeBalance }));
                    }
                } catch (streamErr) {
                    console.warn('[ChatArena] stream failed', streamErr);
                    // If the backend already accepted this request and assigned a sessionId,
                    // the generation is running detached (server-side task). Do NOT re-POST
                    // via the non-stream fallback — that would spawn a duplicate session.
                    // The Realtime subscription will catch up when DB updates land.
                    if (window.__lifeeSessionId) {
                        setSessionId(window.__lifeeSessionId);
                        return;
                    }
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
                if (isActive()) {
                    setHistory(prev => [
                        ...prev,
                        { personaId: 'system', text: `(${e?.message || 'Request failed'})` },
                    ]);
                    setOptions([]);
                }
            } finally {
                if (isActive()) setIsDebating(false);
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
                setShowVoiceMap(true);
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
                    saveSummaryEntry(sessionIdRef.current || sessionId, res.summaries, history.length);
                    setShowVoiceMap(true);
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
                const ava = userAvatar || user?.user_metadata?.avatar_url || '🙂';
                return html`
                    <div key=${idx} class="flex items-start gap-4 max-w-[85%] md:max-w-[70%] ml-auto flex-row-reverse animate-in">
                        <!-- Avatar -->
                        <div class="w-10 h-10 rounded-full border-2 border-on-surface-variant/30 bg-surface-container-high flex items-center justify-center text-on-surface font-bold text-sm shrink-0 overflow-hidden">
                            ${!(typeof ava === 'string' && /^(https?:|\/|data:)/.test(ava))
                                ? html`<span class="text-lg">${ava}</span>`
                                : html`<img src=${ava} class="w-full h-full object-cover" />`
                            }
                        </div>
                        <!-- Bubble -->
                        <div class="space-y-1.5 items-end flex flex-col flex-1 min-w-0">
                            <p class="text-[10px] font-bold uppercase tracking-widest text-on-surface-variant/60 mr-1">You</p>
                            <div class="bg-surface-container/80 backdrop-blur-md px-5 py-4 rounded-xl rounded-tr-sm text-on-surface shadow-sm leading-relaxed border-r-2 border-on-surface-variant/20 text-sm">
                                <${ShinyLines} text=${m.text || ''} />
                            </div>
                            <div class="flex gap-3 px-1 flex-row-reverse">
                                <button
                                    onClick=${() => copyText(m.text)}
                                    class="flex items-center gap-1 text-[10px] font-bold text-on-surface-variant/40 hover:text-primary transition-colors uppercase tracking-widest"
                                >${t('chat.copy')}</button>
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
                ? { border: 'rgba(175,171,159,0.35)', text: 'rgba(175,171,159,0.7)', bg: 'rgba(175,171,159,0.1)', ring: 'rgba(175,171,159,0.35)' }
                : getColor(m.personaId);

            const ava = persona.avatar || '☁️';

            return html`
                <div key=${idx} class="flex items-start gap-4 w-full pr-14 animate-in">
                    <!-- Avatar -->
                    <div
                        class="w-10 h-10 rounded-full border-2 flex items-center justify-center text-lg shrink-0 overflow-hidden"
                        style=${{ borderColor: color.ring, backgroundColor: color.bg }}
                    >
                        ${!(typeof ava === 'string' && /^(https?:|\/|data:)/.test(ava))
                            ? html`<span>${ava}</span>`
                            : html`<img src=${ava} class="w-full h-full object-cover" />`
                        }
                    </div>
                    <!-- Bubble -->
                    <div class="space-y-1.5 flex-1 min-w-0">
                        <p class="text-[10px] font-bold uppercase tracking-widest ml-1" style=${{ color: color.text }}>
                            ${persona.name}
                        </p>
                        <div
                            class="bg-surface-container/80 backdrop-blur-md px-5 py-4 rounded-tl-none rounded-tr-xl rounded-br-xl rounded-bl-[2.5rem] text-on-surface shadow-sm leading-relaxed border-l-2 text-sm"
                            style=${{ borderLeftColor: color.border }}
                        >
                            <${ShinyLines} text=${m.text || ''} />
                        </div>
                        <div class="flex gap-3 px-1">
                            <button
                                onClick=${() => copyText(m.text)}
                                class="flex items-center gap-1 text-[10px] font-bold text-on-surface-variant/40 hover:text-primary transition-colors uppercase tracking-widest"
                            >${t('chat.copy')}</button>
                            <button
                                onClick=${() => quoteText(m.text, persona.name)}
                                class="flex items-center gap-1 text-[10px] font-bold text-on-surface-variant/40 hover:text-primary transition-colors uppercase tracking-widest"
                            >${t('chat.quote')}</button>
                        </div>
                    </div>
                </div>
            `;
        };

        // ── Members panel modal ──────────────────────────────────────────────
        const MembersPanel = () => {
            if (!showMembersPanel) return null;

            const selectedIdSet = new Set((selectedPersonas || []).map(p => p.id));
            const members = (selectedPersonas || []);
            const available = (allPersonas || []).filter(p => !selectedIdSet.has(p.id));

            const removeMember = (id) => {
                if (!setSelectedIds) return;
                if (members.length <= 1) {
                    if (!confirm(t('members.confirmLast'))) return;
                }
                setSelectedIds(prev => prev.filter(x => x !== id));
            };
            const addMember = (id) => {
                if (!setSelectedIds) return;
                setSelectedIds(prev => prev.includes(id) ? prev : [...prev, id]);
            };

            // Give every persona a distinct color based on their index in the
            // FULL persona list — this way we use unique slots first (no two
            // rows share a color until we exceed the palette size). Same
            // assignment regardless of in-council / available.
            const colorIndex = {};
            (allPersonas || []).forEach((p, i) => { colorIndex[p.id] = i % PERSONA_COLORS.length; });
            const colorFor = (p) => PERSONA_COLORS[colorIndex[p.id] ?? 0];

            const renderPersonaRow = (p, inCouncil) => {
                const color = colorFor(p);
                const ava = p.avatar || '☁️';
                return html`
                    <div key=${p.id} class="flex items-center gap-3 px-3 py-2.5 rounded-xl hover:bg-surface-container/60 transition-colors">
                        <div
                            class="w-9 h-9 rounded-full border flex items-center justify-center text-base shrink-0 overflow-hidden"
                            style=${{ borderColor: color.ring, backgroundColor: color.bg }}
                        >
                            ${!(typeof ava === 'string' && /^(https?:|\/|data:)/.test(ava))
                                ? html`<span>${ava}</span>`
                                : html`<img src=${ava} class="w-full h-full object-cover" />`
                            }
                        </div>
                        <div class="flex-1 min-w-0">
                            <p class="text-xs font-bold uppercase tracking-wider truncate" style=${{ color: color.text }}>${p.name}</p>
                            <p class="text-[10px] text-on-surface-variant/50 uppercase tracking-wide truncate">${p.role || ''}</p>
                        </div>
                        ${inCouncil ? html`
                            <button
                                onClick=${() => removeMember(p.id)}
                                class="no-shine w-7 h-7 rounded-full btn-ghost flex items-center justify-center shrink-0"
                                title=${t('members.remove')}
                            ><span class="material-symbols-outlined" style=${{ fontSize: '14px' }}>remove</span></button>
                        ` : html`
                            <button
                                onClick=${() => addMember(p.id)}
                                class="no-shine w-7 h-7 rounded-full btn-ghost flex items-center justify-center shrink-0 text-primary"
                                title=${t('members.addToCouncil')}
                            ><span class="material-symbols-outlined" style=${{ fontSize: '14px' }}>add</span></button>
                        `}
                    </div>
                `;
            };

            return html`
                <div class="fixed inset-0 z-50 flex items-center justify-center">
                    <div class="absolute inset-0 bg-black/70 backdrop-blur-md" onClick=${() => setShowMembersPanel(false)}></div>
                    <div class="relative w-full max-w-md mx-4 glass-card rounded-3xl animate-in iridescent-border flex flex-col" style=${{ maxHeight: '80vh' }}>
                        <!-- Header -->
                        <div class="flex items-center justify-between px-6 py-4 border-b border-white/5 shrink-0">
                            <div>
                                <h2 class="font-headline text-lg font-bold text-on-surface">${t('members.title')}</h2>
                                <p class="text-[10px] text-on-surface-variant/60 uppercase tracking-[0.2em] mt-0.5">${members.length} ${t('members.inSession')} · ${available.length} ${t('members.available')}</p>
                            </div>
                            <button onClick=${() => setShowMembersPanel(false)} class="w-8 h-8 rounded-full btn-ghost flex items-center justify-center">
                                <span class="material-symbols-outlined" style=${{ fontSize: '14px' }}>close</span>
                            </button>
                        </div>

                        <!-- Scrollable body -->
                        <div class="overflow-y-auto px-3 py-3 space-y-5 flex-1">
                            <div>
                                <p class="text-[10px] font-black uppercase tracking-[0.25em] text-primary/70 px-3 mb-1">${t('members.inCouncil')}</p>
                                ${members.length === 0
                                    ? html`<p class="text-xs text-on-surface-variant/40 italic px-3 py-2">${t('members.noMembers')}</p>`
                                    : members.map(p => renderPersonaRow(p, true))
                                }
                            </div>
                            ${available.length > 0 ? html`
                                <div>
                                    <p class="text-[10px] font-black uppercase tracking-[0.25em] text-on-surface-variant/50 px-3 mb-1">${t('members.availSection')}</p>
                                    ${available.map(p => renderPersonaRow(p, false))}
                                </div>
                            ` : null}
                        </div>
                    </div>
                </div>
            `;
        };

        // ── Voice Map sidebar ─────────────────────────────────────────────────
        // Pre-laid positions (2-column grid). Row gap tuned for void cards
        // (taller than old UI because messages wrap more). Subtle ±1° tilt.
        const CANVAS_CARD_POSITIONS = [
            { x: 18,  y: 28,  rotate: -1   },  // A1
            { x: 288, y: 18,  rotate: 0.8  },  // B1
            { x: 18,  y: 318, rotate: 0.7  },  // A2
            { x: 288, y: 308, rotate: -0.9 },  // B2
            { x: 18,  y: 608, rotate: -0.8 },  // A3
            { x: 288, y: 598, rotate: 1    },  // B3
            { x: 18,  y: 898, rotate: 0.6  },  // A4
            { x: 288, y: 888, rotate: -0.7 },  // B4
        ];

        const VoiceMapSidebar = () => {
            if (!showVoiceMap) return null;

            // Per-persona: collect all messages + count
            const perPersona = {};
            (history || []).forEach(m => {
                if (!m || !m.personaId || m.personaId === 'user' || m.personaId === 'system' || m.personaId === 'lifee-followup') return;
                if (!perPersona[m.personaId]) perPersona[m.personaId] = { count: 0, messages: [] };
                perPersona[m.personaId].count += 1;
                if (m.text) perPersona[m.personaId].messages.push(m.text);
            });

            const voices = (selectedPersonas || []).map(p => ({
                ...p,
                count: perPersona[p.id]?.count || 0,
                messages: perPersona[p.id]?.messages || [],
            }));

            const userMessages = (history || []).filter(m => m?.personaId === 'user').map(m => m.text).filter(Boolean);
            const userCount = userMessages.length;
            const userLast = userMessages[userMessages.length - 1] || '';

            // Load persisted view (pan/scale/cardPos) — merge defaults for any
            // personas that don't have saved positions yet.
            const loadSaved = () => {
                try { return JSON.parse(window.localStorage.getItem('lifee_voice_map_view') || '{}') || {}; }
                catch (_) { return {}; }
            };
            const saved = loadSaved();
            const [pan, setPan] = useState(() => saved.pan && typeof saved.pan.x === 'number' ? saved.pan : { x: 0, y: 0 });
            const [scale, setScale] = useState(() => typeof saved.scale === 'number' ? saved.scale : 1.0);
            const [cardPos, setCardPos] = useState(() => {
                const out = { ...(saved.cardPos || {}) };
                voices.forEach((v, i) => {
                    if (!out[v.id]) {
                        const s = CANVAS_CARD_POSITIONS[i % CANVAS_CARD_POSITIONS.length];
                        out[v.id] = { x: s.x, y: s.y, rotate: s.rotate };
                    }
                });
                if (!out['__user']) {
                    const userSlot = CANVAS_CARD_POSITIONS[voices.length % CANVAS_CARD_POSITIONS.length];
                    out['__user'] = { x: userSlot.x, y: userSlot.y, rotate: userSlot.rotate };
                }
                return out;
            });
            // Persist view changes (debounced naturally by React batching)
            useEffect(() => {
                try {
                    window.localStorage.setItem('lifee_voice_map_view', JSON.stringify({ pan, scale, cardPos }));
                } catch (_) {}
            }, [pan, scale, cardPos]);

            const canvasRef = useRef(null);
            const panRef = useRef({ dragging: false, startX: 0, startY: 0, origX: 0, origY: 0 });
            const cardRef = useRef({ id: null, startX: 0, startY: 0, origX: 0, origY: 0 });

            const onCanvasMouseDown = (e) => {
                if (cardRef.current.id) return;
                panRef.current = { dragging: true, startX: e.clientX, startY: e.clientY, origX: pan.x, origY: pan.y };
            };
            const onMouseMove = (e) => {
                if (cardRef.current.id) {
                    const dx = (e.clientX - cardRef.current.startX) / scale;
                    const dy = (e.clientY - cardRef.current.startY) / scale;
                    setCardPos(prev => ({
                        ...prev,
                        [cardRef.current.id]: { x: cardRef.current.origX + dx, y: cardRef.current.origY + dy },
                    }));
                } else if (panRef.current.dragging) {
                    setPan({
                        x: panRef.current.origX + (e.clientX - panRef.current.startX),
                        y: panRef.current.origY + (e.clientY - panRef.current.startY),
                    });
                }
            };
            const onMouseUp = () => {
                panRef.current.dragging = false;
                cardRef.current.id = null;
            };
            const startCardDrag = (e, id) => {
                e.stopPropagation();
                const pos = cardPos[id] || { x: 0, y: 0 };
                cardRef.current = { id, startX: e.clientX, startY: e.clientY, origX: pos.x, origY: pos.y };
            };
            const onWheel = (e) => {
                e.preventDefault();
                const delta = -e.deltaY * 0.001;
                const newScale = Math.min(2, Math.max(0.3, scale + delta));
                if (newScale === scale) return;
                const rect = canvasRef.current?.getBoundingClientRect();
                if (!rect) { setScale(newScale); return; }
                const cx = e.clientX - rect.left;
                const cy = e.clientY - rect.top;
                const ratio = newScale / scale;
                setPan({
                    x: cx - 40 - (cx - pan.x - 40) * ratio,
                    y: cy - 40 - (cy - pan.y - 40) * ratio,
                });
                setScale(newScale);
            };
            const reset = () => {
                setPan({ x: 0, y: 0 });
                setScale(1.0);
                // Also reset every card back to its slot position so user can
                // recover from a messy drag session.
                const fresh = {};
                voices.forEach((v, i) => {
                    const s = CANVAS_CARD_POSITIONS[i % CANVAS_CARD_POSITIONS.length];
                    fresh[v.id] = { x: s.x, y: s.y, rotate: s.rotate };
                });
                const userSlot = CANVAS_CARD_POSITIONS[voices.length % CANVAS_CARD_POSITIONS.length];
                fresh['__user'] = { x: userSlot.x, y: userSlot.y, rotate: userSlot.rotate };
                setCardPos(fresh);
            };

            return html`
                <aside class="h-full flex flex-col border-l border-white/5 bg-surface-dim/40 shrink-0" style=${{ width: Math.min(mapWidth, mapMaxWidth()) + 'px' }}>
                    <!-- Archive header -->
                    <div class="flex items-center justify-between px-6 h-14 border-b border-white/5 shrink-0">
                        <div class="flex items-center gap-2">
                            <span class="material-symbols-outlined text-primary/60" style=${{ fontSize: '16px' }}>menu_book</span>
                            <span class="text-[10px] font-black uppercase tracking-[0.35em] text-on-surface-variant/70">${t('chat.voiceMap')}</span>
                        </div>
                        <div class="flex items-center gap-1">
                            <button
                                onClick=${handleSummary}
                                disabled=${history.length < 2 || summaryLoading}
                                class="no-shine px-2 h-7 rounded-md btn-ghost text-[9px] uppercase tracking-wider flex items-center gap-1 disabled:opacity-30"
                                title="Summarize each voice"
                            >
                                ${summaryLoading
                                    ? html`<span class="material-symbols-outlined animate-spin" style=${{ fontSize: '12px' }}>progress_activity</span>`
                                    : html`<span class="material-symbols-outlined" style=${{ fontSize: '12px' }}>summarize</span>`
                                }
                                <span>${t('chat.summary')}</span>
                            </button>
                            <button onClick=${reset}
                                class="no-shine px-2 h-7 rounded-md btn-ghost text-[9px] uppercase tracking-wider"
                                title="Reset view"
                            ><span>${t('chat.reset')}</span></button>
                            <span class="text-[9px] font-bold text-on-surface-variant/40 w-9 text-center">${Math.round(scale * 100)}%</span>
                            <button onClick=${() => setShowVoiceMap(false)}
                                class="w-7 h-7 rounded-md btn-ghost flex items-center justify-center"
                                title="Close"
                            ><span class="material-symbols-outlined" style=${{ fontSize: '14px' }}>close</span></button>
                        </div>
                    </div>

                    <!-- Canvas -->
                    <div
                        ref=${canvasRef}
                        class="flex-1 relative overflow-hidden cursor-grab active:cursor-grabbing"
                        style=${{
                            backgroundImage: 'radial-gradient(circle, rgba(255,255,255,0.06) 1px, transparent 1px)',
                            backgroundSize: '18px 18px',
                        }}
                        onMouseDown=${onCanvasMouseDown}
                        onMouseMove=${onMouseMove}
                        onMouseUp=${onMouseUp}
                        onMouseLeave=${onMouseUp}
                        onWheel=${onWheel}
                    >
                        <div
                            class="absolute top-0 left-0 origin-top-left"
                            style=${{ transform: `translate(${pan.x + 40}px, ${pan.y + 40}px) scale(${scale})` }}
                        >
                            ${voices.map((v, idx) => {
                                const color = getColor(v.id);
                                const pos = cardPos[v.id] || { x: 0, y: 0, rotate: 0 };
                                const ava = v.avatar || '☁️';
                                const recent = v.messages.slice(-3);
                                return html`
                                    <div
                                        key=${v.id}
                                        class="absolute w-[255px] cursor-grab active:cursor-grabbing select-none"
                                        style=${{ left: pos.x + 'px', top: pos.y + 'px', transform: `rotate(${pos.rotate}deg)`, transformOrigin: 'center center' }}
                                        onMouseDown=${(e) => startCardDrag(e, v.id)}
                                    >
                                        <div class="rounded-[20px] bg-surface-container border border-outline/15 shadow-xl shadow-black/40 overflow-hidden">
                                            <!-- Header -->
                                            <div class="flex items-center gap-2.5 px-4 pt-3 pb-2.5 border-b border-outline/10">
                                                <div
                                                    class="w-8 h-8 rounded-full border flex items-center justify-center text-base shrink-0 overflow-hidden"
                                                    style=${{ borderColor: color.ring, backgroundColor: color.bg }}
                                                >
                                                    ${!(typeof ava === 'string' && /^(https?:|\/|data:)/.test(ava))
                                                        ? html`<span>${ava}</span>`
                                                        : html`<img src=${ava} class="w-full h-full object-cover" />`
                                                    }
                                                </div>
                                                <div class="flex-1 min-w-0">
                                                    <p class="text-[10px] font-black uppercase tracking-[0.2em] text-on-surface truncate">${v.name}</p>
                                                    <p class="text-[8px] font-bold uppercase tracking-[0.15em] truncate" style=${{ color: color.text }}>${v.role || ''}</p>
                                                </div>
                                                <span class="text-[10px] font-black text-on-surface/20 shrink-0">${v.count || '—'}</span>
                                            </div>

                                            <!-- Body: summary (if available) → recent messages → empty -->
                                            <div class="px-4 py-3 min-h-[72px] flex flex-col gap-2">
                                                ${summaryLoading ? html`
                                                    <div class="flex items-center gap-2">
                                                        <span class="material-symbols-outlined text-on-surface-variant/40 animate-spin" style=${{ fontSize: '12px' }}>progress_activity</span>
                                                        <span class="text-[10px] text-on-surface-variant/35">${t('chat.summarizing')}</span>
                                                    </div>
                                                ` : summaryData[v.id] ? html`
                                                    <div
                                                        class="rounded-md pl-2.5 pr-2 py-2 border-l-2 bg-surface-container-high/40"
                                                        style=${{ borderLeftColor: color.border }}
                                                    >
                                                        <div class="text-[10px] leading-relaxed text-on-surface/80">
                                                            <${ShinyLines}
                                                                text=${summaryData[v.id]}
                                                                fontStr='10px "Manrope", sans-serif'
                                                                lineHeightPx=${16}
                                                            />
                                                        </div>
                                                    </div>
                                                ` : recent.length === 0 ? html`
                                                    <p class="text-[10px] italic text-on-surface-variant/25">${t('chat.waiting')}</p>
                                                ` : recent.map((msg, i) => {
                                                    const isLatest = i === recent.length - 1;
                                                    return html`
                                                        <div
                                                            key=${i}
                                                            class=${'text-[10px] italic leading-snug pl-2 border-l-2 ' +
                                                                (isLatest ? 'text-on-surface/75' : 'text-on-surface-variant/30')}
                                                            style=${{ borderLeftColor: isLatest ? color.border : 'rgba(255,255,255,0.06)' }}
                                                        >
                                                            <${ShinyLines}
                                                                text=${msg || ''}
                                                                fontStr='italic 10px "Manrope", sans-serif'
                                                                lineHeightPx=${13}
                                                                maxLines=${2}
                                                            />
                                                        </div>
                                                    `;
                                                })}
                                            </div>

                                            <!-- Footer: worldview quote -->
                                            <div class="px-4 py-2 border-t border-outline/10 bg-surface-container-high/40">
                                                <p class="text-[8px] font-black uppercase tracking-[0.2em] text-on-surface/25 truncate">
                                                    ${v.worldview ? `"${v.worldview.slice(0, 45)}"` : (v.category || '')}
                                                </p>
                                            </div>
                                        </div>
                                    </div>
                                `;
                            })}

                            <!-- User node -->
                            <div
                                class="absolute w-[255px] cursor-grab active:cursor-grabbing select-none"
                                style=${{
                                    left: (cardPos['__user']?.x || 0) + 'px',
                                    top: (cardPos['__user']?.y || 0) + 'px',
                                    transform: `rotate(${cardPos['__user']?.rotate || 0}deg)`,
                                }}
                                onMouseDown=${(e) => startCardDrag(e, '__user')}
                            >
                                <div class="rounded-[20px] bg-primary/10 border border-primary/25 shadow-xl shadow-black/40 overflow-hidden">
                                    <div class="flex items-center gap-2.5 px-4 pt-3 pb-2.5 border-b border-primary/20">
                                        <div class="w-8 h-8 rounded-full border border-primary/40 bg-primary/20 flex items-center justify-center shrink-0 overflow-hidden">
                                            ${userAvatar && /^(https?:|\/|data:)/.test(userAvatar)
                                                ? html`<img src=${userAvatar} class="w-full h-full object-cover" />`
                                                : html`<span class="text-sm">${userAvatar || '🙂'}</span>`
                                            }
                                        </div>
                                        <div class="flex-1 min-w-0">
                                            <p class="text-[10px] font-black uppercase tracking-[0.2em] text-primary">${t('chat.you')}</p>
                                            <p class="text-[8px] font-bold uppercase tracking-[0.15em] text-primary/60">${userCount} message${userCount === 1 ? '' : 's'}</p>
                                        </div>
                                    </div>
                                    <div class="px-4 py-3 min-h-[72px]">
                                        ${userLast ? html`
                                            <div class="text-[10px] text-on-surface/75 italic leading-snug pl-2 border-l-2 border-primary/40">
                                                <${ShinyLines}
                                                    text=${userLast}
                                                    fontStr='italic 10px "Manrope", sans-serif'
                                                    lineHeightPx=${13}
                                                    maxLines=${4}
                                                />
                                            </div>
                                        ` : html`
                                            <p class="text-[10px] italic text-on-surface-variant/25">${t('chat.silent')}</p>
                                        `}
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </aside>
            `;
        };

        // Drag handle to resize the voice-map sidebar
        const mapResizeRef = useRef({ startX: 0, startW: 0, dragging: false });
        const startMapResize = (e) => {
            e.preventDefault();
            mapResizeRef.current = { startX: e.clientX, startW: mapWidth, dragging: true };
            const onMove = (ev) => {
                if (!mapResizeRef.current.dragging) return;
                const dx = mapResizeRef.current.startX - ev.clientX;
                // Clamp to [320, window - 120] — leave a chat strip wide enough
                // that the user can see it, so the handle is always grabbable.
                const maxW = mapMaxWidth();
                const next = Math.max(320, Math.min(maxW, mapResizeRef.current.startW + dx));
                setMapWidth(next);
            };
            const onUp = () => {
                mapResizeRef.current.dragging = false;
                window.removeEventListener('mousemove', onMove);
                window.removeEventListener('mouseup', onUp);
            };
            window.addEventListener('mousemove', onMove);
            window.addEventListener('mouseup', onUp);
        };

        // ── More menu dropdown ────────────────────────────────────────────────
        const MoreMenu = () => {
            if (!showMoreMenu) return null;
            return html`
                <div
                    ref=${moreMenuRef}
                    class="absolute right-0 top-full mt-2 w-64 bg-surface-container/95 backdrop-blur-xl border border-white/10 rounded-2xl shadow-2xl z-50 overflow-hidden"
                >
                    <!-- Max speakers select -->
                    ${(selectedPersonas || []).length > 1 ? html`
                        <div class="px-4 py-3 border-b border-white/5 flex items-center justify-between gap-3">
                            <span class="text-xs text-on-surface font-semibold">${t('chat.maxSpeakers')}</span>
                            <select
                                value=${maxSpeakers}
                                onChange=${(e) => setMaxSpeakers(Number(e.target.value))}
                                class="text-xs text-on-surface bg-surface-container-high border border-white/10 rounded-lg px-2 py-1"
                            >
                                <option value=${0}>${t('chat.all')}</option>
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

        // ── Tools menu (popover above + button in input row) ──────────────────
        const ToolsMenu = () => {
            if (!showToolsMenu) return null;
            const Row = ({ label, desc, icon, active, color, onToggle }) => html`
                <button
                    onClick=${onToggle}
                    class=${'w-full flex items-start gap-3 px-4 py-3 transition-colors text-left ' + (active ? 'bg-white/[0.04]' : 'hover:bg-white/[0.03]')}
                >
                    <span class=${'material-symbols-outlined shrink-0 mt-0.5 ' + (active ? color : 'text-on-surface-variant/50')}>${icon}</span>
                    <div class="flex-1 min-w-0">
                        <div class="flex items-center justify-between gap-2">
                            <span class=${'text-xs font-semibold ' + (active ? 'text-on-surface' : 'text-on-surface/80')}>${label}</span>
                            <span class=${'w-8 h-4 rounded-full relative transition-colors ' + (active ? color.replace('text-', 'bg-') : 'bg-surface-container-highest')}>
                                <span class=${'absolute top-0.5 w-3 h-3 rounded-full bg-white transition-all ' + (active ? 'left-[18px]' : 'left-0.5')}></span>
                            </span>
                        </div>
                        <p class="text-[10px] text-on-surface-variant/50 mt-0.5 leading-snug">${desc}</p>
                    </div>
                </button>
            `;
            return html`
                <div
                    ref=${toolsMenuRef}
                    class="absolute left-0 bottom-full mb-2 w-72 bg-surface-container/95 backdrop-blur-xl border border-white/10 rounded-2xl shadow-2xl z-50 overflow-hidden"
                >
                    <${Row}
                        label=${t('chat.webSearch')}
                        desc=${t('chat.webSearchDesc')}
                        icon="travel_explore"
                        active=${webSearchMode}
                        color="text-secondary"
                        onToggle=${() => setWebSearchMode(v => !v)}
                    />
                    <div class="h-px bg-white/5"></div>
                    <${Row}
                        label=${t('chat.followUp')}
                        desc=${t('chat.followUpDesc')}
                        icon="quick_reference_all"
                        active=${followUpMode}
                        color="text-primary"
                        onToggle=${() => setFollowUpMode(v => !v)}
                    />
                </div>
            `;
        };

        // ── Main render ───────────────────────────────────────────────────────
        return html`
            <div class="h-full flex flex-row overflow-hidden bg-surface text-on-surface">
              <div class="h-full flex flex-col flex-1 min-w-0 overflow-hidden">

                <!-- ── Header ── -->
                <header class="flex justify-between items-center w-full px-8 h-20 bg-surface-dim/30 backdrop-blur-lg border-b border-white/5 z-10 shrink-0">
                    <div class="flex items-center gap-6">
                        <div>
                            <h2 class="text-xl md:text-2xl font-headline font-bold tracking-tight text-on-surface">${t('chat.council')}</h2>
                            <p class="text-[10px] uppercase tracking-[0.2em] text-primary/80 leading-none mt-0.5">${(selectedPersonas || []).length} ${(selectedPersonas || []).length === 1 ? t('chat.voice') : t('chat.voices')} ${t('chat.inSession')}</p>
                        </div>
                        <!-- Member Avatars cluster — click to edit members -->
                        <button
                            onClick=${() => setShowMembersPanel(true)}
                            class="no-shine hidden lg:flex -space-x-3 ml-4 cursor-pointer hover:opacity-80 transition-opacity"
                            title=${t('members.title')}
                        >
                            ${(selectedPersonas || []).slice(0, 4).map((p, idx) => {
                                const color = getColor(p.id);
                                const ava = p.avatar || '☁️';
                                return html`
                                    <div
                                        key=${p.id}
                                        class="w-8 h-8 rounded-full border-2 overflow-hidden shadow-sm flex items-center justify-center text-sm"
                                        style=${{ borderColor: color.ring, backgroundColor: color.bg }}
                                        title=${p.name}
                                    >
                                        ${!(typeof ava === 'string' && /^(https?:|\/|data:)/.test(ava))
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
                            <!-- Edit indicator on hover -->
                            <div class="w-8 h-8 rounded-full bg-surface-container border-2 border-dashed border-on-surface-variant/30 flex items-center justify-center text-on-surface-variant/60">
                                <span class="material-symbols-outlined" style=${{ fontSize: '14px' }}>add</span>
                            </div>
                        </button>
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
                            <!-- Voice Map -->
                            <span
                                class=${'material-symbols-outlined cursor-pointer transition-colors ' + ((selectedPersonas || []).length === 0 ? 'opacity-30 pointer-events-none' : 'hover:text-primary') + (showVoiceMap ? ' text-primary' : '')}
                                title="Voice map"
                                onClick=${() => setShowVoiceMap(v => !v)}
                            >map</span>

                            <!-- Summary -->
                            <span
                                class=${'material-symbols-outlined cursor-pointer transition-colors ' + (history.length < 2 || summaryLoading ? 'opacity-30 pointer-events-none' : 'hover:text-primary')}
                                title="Summary"
                                onClick=${handleSummary}
                            >${summaryLoading ? 'hourglass_empty' : 'summarize'}</span>

                            <!-- Share conversation -->
                            <span
                                class=${'material-symbols-outlined cursor-pointer transition-colors ' + (!(history && history.length) ? 'opacity-30 pointer-events-none' : 'hover:text-primary')}
                                title=${t('share.title')}
                                onClick=${() => onOpenShare?.({ messages: history, personas: selectedPersonas })}
                            >ios_share</span>

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
                  <div class="max-w-5xl mx-auto w-full px-6 py-8 space-y-8">
                    ${history.length === 0 && !isDebating ? html`
                        <div class="flex flex-col items-center justify-center h-full text-center space-y-4 opacity-30 select-none">
                            <div class="text-4xl">✦</div>
                            <p class="text-[11px] uppercase tracking-[0.35em] text-on-surface-variant/60">
                                The void awaits your transmission
                            </p>
                        </div>
                    ` : null}

                    ${history.map((m, idx) => renderMessage(m, idx))}

                    <!-- Typing indicator: only while the NEXT persona is warming up
                         (empty history OR last message is an empty stub from a just-
                         started persona). Hidden once their tokens start flowing, and
                         hidden during the post-stream options-generation phase. -->
                    ${(() => {
                        if (!isDebating) return null;
                        const last = history[history.length - 1];
                        const hasText = last && (last.text || '').trim().length > 0;
                        if (hasText) return null;  // persona is already speaking or options-gen phase
                        // If last exists and it's an empty assistant stub, show THAT persona.
                        // Otherwise fall back to a generic pulse (gap before first persona).
                        const pid = (last && last.personaId && last.personaId !== 'user') ? last.personaId : null;
                        const persona = pid
                            ? ((selectedPersonas || []).find(p => p.id === pid) || { name: pid, avatar: '☁️' })
                            : null;
                        const ava = persona?.avatar || '☁️';
                        const color = pid ? getColor(pid) : { border: 'rgba(175,171,159,0.25)', text: 'rgba(175,171,159,0.6)', bg: 'rgba(28,26,22,0.8)', ring: 'rgba(255,255,255,0.1)' };
                        return html`
                            <div class="flex items-start gap-4 animate-in">
                                <div
                                    class="w-10 h-10 rounded-full border-2 flex items-center justify-center text-lg shrink-0 overflow-hidden"
                                    style=${{ borderColor: color.ring, backgroundColor: color.bg }}
                                >
                                    ${persona
                                        ? (!(typeof ava === 'string' && /^(https?:|\/|data:)/.test(ava))
                                            ? html`<span>${ava}</span>`
                                            : html`<img src=${ava} class="w-full h-full object-cover" />`)
                                        : null}
                                </div>
                                <div class="space-y-1.5">
                                    ${persona ? html`
                                        <p class="text-[10px] font-bold uppercase tracking-widest ml-1" style=${{ color: color.text }}>
                                            ${persona.name}
                                        </p>
                                    ` : null}
                                    <div
                                        class="flex items-center gap-1.5 bg-surface-container/80 px-5 py-4 rounded-xl rounded-tl-sm border-t-2 h-[54px]"
                                        style=${{ borderTopColor: color.border }}
                                    >
                                        <span class="typing-dot w-1.5 h-1.5 rounded-full bg-primary/50" style=${{ animationDelay: '0ms' }}></span>
                                        <span class="typing-dot w-1.5 h-1.5 rounded-full bg-primary/50" style=${{ animationDelay: '200ms' }}></span>
                                        <span class="typing-dot w-1.5 h-1.5 rounded-full bg-primary/50" style=${{ animationDelay: '400ms' }}></span>
                                    </div>
                                </div>
                            </div>
                        `;
                    })()}
                  </div>
                </div>

                <!-- ── Footer input area ── -->
                <footer class="p-6 bg-surface-dim/40 backdrop-blur-2xl border-t border-white/5 shrink-0">
                    <div class="max-w-5xl mx-auto space-y-3">

                        <!-- Options pills: collapsed label by default; on hover the pills rise up
                             and float above the input as opaque chips (absolute so they don't push
                             layout; opaque bg so chat text behind doesn't bleed through). -->
                        ${options.length > 0 && !isDebating ? html`
                            <div class="group relative cursor-default animate-in -my-1">
                                <div class="flex items-center justify-center gap-1 text-[10px] uppercase tracking-[0.25em] text-primary/50 py-0.5 transition-opacity duration-200 group-hover:opacity-0">
                                    <span>${options.length} ${t('chat.suggested')}</span>
                                    <span class="material-symbols-outlined" style=${{ fontSize: '14px' }}>expand_more</span>
                                </div>
                                <div class="absolute left-0 right-0 bottom-0 flex flex-col items-center gap-2 opacity-0 translate-y-2 pointer-events-none group-hover:opacity-100 group-hover:translate-y-0 group-hover:pointer-events-auto transition-all duration-200">
                                    ${options.map((opt, i) => html`
                                        <button
                                            key=${i}
                                            onClick=${() => runRound(opt)}
                                            class="no-shine text-left px-5 py-2.5 text-xs font-semibold rounded-full bg-surface-container border border-primary/25 text-primary/75 hover:text-primary hover:border-primary/50 hover:bg-surface-container-high shadow-xl shadow-black/50 transition-colors"
                                        ><span>${opt}</span></button>
                                    `)}
                                </div>
                            </div>
                        ` : null}

                        <!-- Main input row -->
                        <div class="input-warm-focus flex items-center bg-surface-container-lowest border border-white/5 rounded-2xl p-2 transition-all duration-300">
                            <!-- Tools (web search / follow-up) -->
                            <div class="relative shrink-0">
                                <button
                                    onClick=${() => setShowToolsMenu(v => !v)}
                                    title="Tools"
                                    class=${'w-9 h-9 rounded-lg flex items-center justify-center transition-colors ' +
                                        (showToolsMenu || webSearchMode || followUpMode
                                            ? 'bg-primary/15 text-primary'
                                            : 'text-on-surface-variant/50 hover:text-primary hover:bg-white/5')}
                                >
                                    <span class="material-symbols-outlined" style=${{ fontSize: '20px' }}>add</span>
                                </button>
                                <${ToolsMenu} />
                                ${(webSearchMode || followUpMode) ? html`
                                    <span class="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-primary border border-surface-container-lowest"></span>
                                ` : null}
                            </div>
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
                                <!-- Send / Stop button: switches to stop while streaming -->
                                <button
                                    disabled=${!isDebating && !inputValue.trim()}
                                    onClick=${isDebating ? handleStop : () => runRound()}
                                    title=${isDebating ? 'Stop' : 'Send'}
                                    class="w-12 h-12 flex items-center justify-center rounded-xl btn-gradient shadow-lg shadow-primary/20 hover:scale-105 active:scale-95 transition-transform disabled:opacity-30 disabled:pointer-events-none"
                                >
                                    <span class="material-symbols-outlined" style=${{ fontVariationSettings: "'FILL' 1" }}>${isDebating ? 'stop' : 'send'}</span>
                                </button>
                            </div>
                        </div>

                        <!-- Stay Silent link + profile extract status -->
                        <div class="flex items-center justify-between px-1">
                            <button
                                disabled=${isDebating}
                                onClick=${() => runRound(null)}
                                class="text-[10px] font-black uppercase tracking-widest text-on-surface-variant/30 hover:text-primary transition-colors disabled:opacity-30"
                            >${t('chat.staySilent')}</button>

                            ${extractStatus === 'done' ? html`
                                <div class="flex items-center gap-1.5 text-[10px] text-on-surface-variant/50 animate-in">
                                    <span class="material-symbols-outlined text-sm" style=${{ fontSize: '14px' }}>auto_stories</span>
                                    ${t('chat.profileUpdated')}
                                </div>
                            ` : html`<span></span>`}
                        </div>
                    </div>
                </footer>

              </div>

              <!-- ── Voice Map resize handle ── -->
              ${showVoiceMap ? html`
                <div
                    onMouseDown=${startMapResize}
                    class="w-1 h-full cursor-col-resize bg-transparent hover:bg-primary/30 transition-colors shrink-0"
                    title="Drag to resize"
                ></div>
              ` : null}

              <!-- ── Voice Map sidebar ── -->
              <${VoiceMapSidebar} />

              <!-- ── Members panel ── -->
              <${MembersPanel} />


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
                                class="text-sm text-on-surface-variant/50 hover:text-primary transition-colors"
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
                                class="mt-3 text-sm text-on-surface-variant/50 hover:text-primary transition-colors"
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
