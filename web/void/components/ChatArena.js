(() => {
    const { useState, useEffect, useLayoutEffect, useRef, useMemo } = React;
    const html = htm.bind(window.__voidH || React.createElement);

    // ══════════════════════════════════════════════════════════════════════
    //  CharBlurText — per-character blur-to-sharp reveal as text streams in.
    //  Newly-arrived chars get their own <span.cb-c.is-new> with a CSS
    //  `blur(5px) → 0` + opacity 0 → 1 animation. Already-rendered chars
    //  become plain inline spans so layout stays identical between states.
    //  Regenerate / non-prefix updates reset seenLen so the whole replacement
    //  doesn't flash-animate. Respects prefers-reduced-motion.
    // ══════════════════════════════════════════════════════════════════════
    const CB_STYLE_ID = 'cb-char-blur-style';
    const ensureCharBlurStyles = () => {
        if (typeof document === 'undefined') return;
        if (document.getElementById(CB_STYLE_ID)) return;
        const style = document.createElement('style');
        style.id = CB_STYLE_ID;
        style.textContent = `
            .cb-wrap { white-space: pre-wrap; word-wrap: break-word; }
            .cb-c    { display: inline; white-space: pre-wrap; }
            .cb-c.is-new {
                display: inline-block;
                opacity: 0;
                filter: blur(5px);
                transform: translateY(1px);
                animation: cbCharIn 420ms cubic-bezier(0.22, 1, 0.36, 1) forwards;
            }
            @keyframes cbCharIn {
                0%   { opacity: 0; filter: blur(5px); transform: translateY(1px); }
                60%  { opacity: 1; }
                100% { opacity: 1; filter: blur(0); transform: none; }
            }
            @media (prefers-reduced-motion: reduce) {
                .cb-c.is-new { animation: none; opacity: 1; filter: none; transform: none; }
            }
        `;
        document.head.appendChild(style);
    };

    const CharBlurText = ({ text }) => {
        const seenLenRef = useRef(null);
        const prevTextRef = useRef('');

        useLayoutEffect(() => { ensureCharBlurStyles(); }, []);

        const next = text || '';
        if (seenLenRef.current === null) {
            // First render: treat any initial text as seen (avoid flash-
            // animating history when reopening a chat).
            seenLenRef.current = next.length;
            prevTextRef.current = next;
        } else {
            const prev = prevTextRef.current || '';
            if (!next.startsWith(prev)) seenLenRef.current = next.length;
        }
        const seenAtRender = Math.min(seenLenRef.current, next.length);

        useLayoutEffect(() => {
            prevTextRef.current = next;
            seenLenRef.current = next.length;
        });

        if (next.length === 0) return null;

        const seen = next.slice(0, seenAtRender);
        const fresh = next.slice(seenAtRender);

        const onAnimEnd = (e) => {
            const el = e.target;
            if (el && el.classList && el.classList.contains('is-new')) {
                el.classList.remove('is-new');
            }
        };

        const freshSpans = [];
        for (let i = 0; i < fresh.length; i++) {
            freshSpans.push(
                html`<span key=${'n' + (seenAtRender + i)} class="cb-c is-new" onAnimationEnd=${onAnimEnd}>${fresh[i]}</span>`
            );
        }

        return html`
            <span class="cb-wrap">
                ${seen ? html`<span class="cb-c">${seen}</span>` : null}
                ${freshSpans}
            </span>
        `;
    };

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
        onLogin,
        initialMessages = [],
        initialOptions = [],
        parentSessionId = "",
        initialMode = null,
        onSessionCreated,
        onOpenShare,
        debateSettings,
        setDebateSettings,
    }) => {
        // ── State ─────────────────────────────────────────────────────────────
        const [history, setHistory]             = useState(initialMessages);
        const [options, setOptions]             = useState(initialOptions || []);
        const [isDebating, setIsDebating]       = useState(false);
        const [sessionId, setSessionId]         = useState(parentSessionId || '');
        const [inputValue, setInputValue]       = useState('');
        const [credits, setCredits]             = useState(null);
        const [showPaywall, setShowPaywall]     = useState(false);
        const [redeemCode, setRedeemCode]       = useState('');
        // 4 个共享设置从 props 派生（提到 App 顶层 + localStorage 持久化），
        // 让 home 输入框旁的 + 工具菜单和 chat 内的设置面板共享同一份 state。
        // setter 包装成支持函数式更新（v => !v 之类）以兼容现有调用。
        const _ds = debateSettings || { followUpMode: false, webSearchMode: false, maxSpeakers: 0, language: '' };
        const followUpMode = !!_ds.followUpMode;
        const webSearchMode = !!_ds.webSearchMode;
        const maxSpeakers = Number(_ds.maxSpeakers) || 0;
        const language = typeof _ds.language === 'string' ? _ds.language : '';
        const _patchDS = (key, next) => {
            if (typeof setDebateSettings !== 'function') return;
            setDebateSettings(prev => {
                const base = prev || {};
                const cur = base[key];
                const resolved = typeof next === 'function' ? next(cur) : next;
                return { ...base, [key]: resolved };
            });
        };
        const setFollowUpMode  = (v) => _patchDS('followUpMode', v);
        const setWebSearchMode = (v) => _patchDS('webSearchMode', v);
        const setMaxSpeakers   = (v) => _patchDS('maxSpeakers', v);
        const setLanguage      = (v) => _patchDS('language', v);
        // Pending answers for the latest unanswered follow-up card:
        //   { [questionIdx]: selectedOptionText }
        // Answered follow-ups derive their state from the next user message in history,
        // so this only holds the in-flight form.
        const [followupAnswers, setFollowupAnswers] = useState({});
        const [extractStatus, setExtractStatus] = useState(''); // '' | 'extracting' | 'done'
        const [summaryData, setSummaryData]     = useState({});
        // Warming-up stage from SSE `event: status`. Values: null (idle or
        // bubble has tokens), "kb_search" (RAG ranking running), "picked:<id>"
        // (first speaker resolved, waiting for LLM TTFT).
        const [warmupStage, setWarmupStage]     = useState(null);
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
        // Roadmap 模式：基于对话推出 3-6 条人生路径选项。每条只一句话，
        // 用户感兴趣的话再点 Plan 触发 /plan-30-days 出完整方案。
        // pathOptions: { id, label, summary }[]
        const [pathOptions, setPathOptions]   = useState([]);
        const [pathLoading, setPathLoading]   = useState(false);
        const [pathError, setPathError]       = useState('');
        const [showPlanModal, setShowPlanModal] = useState(false);
        const [planData, setPlanData]         = useState(null);
        const [planLoading, setPlanLoading]   = useState(false);
        const [planWeek, setPlanWeek]         = useState(0);
        const [showMoreMenu, setShowMoreMenu]   = useState(false);
        const [showToolsMenu, setShowToolsMenu] = useState(false);
        const [showVoiceMap, setShowVoiceMap]   = useState(false);
        const [showMembersPanel, setShowMembersPanel] = useState(false);
        // Keep ~120px of chat visible so the user can always see there's a chat
        // on the left (and grab the resize handle to pull the map back).
        // roadmap 模式下放开 120px 留白，允许真正全屏（思维导图横向铺得开）
        const mapMaxWidth = () => {
            const w = typeof window !== 'undefined' ? window.innerWidth : 1280;
            return pathOptions.length > 0 ? w : Math.max(320, w - 120);
        };
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

        // 显示节流已经搬到后端（lifee/api.py，按 ~30 字/秒分发 SSE）。
        // 前端只负责把 chunk 拼起来塞给 commitMessage，零节流、零 race。
        const flushThrottle = () => {};   // 兼容旧 callsite，noop

        const makeSseHandlers = (myRound) => ({
            onSession:       (sid) => commitSession(sid, 'sse', myRound),
            onMessage:       (msg) => commitMessage(msg, 'sse', myRound),
            onMessageUpdate: (msg) => commitMessage(msg, 'sse', myRound),
            onOptions:       (opts) => commitOptions(opts, 'sse', myRound),
            onStatus:        (stage) => {
                if (roundIdRef.current !== myRound) return;
                setWarmupStage(stage);
            },
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
            setPathOptions([]);
            setPathError('');
            setIsDebating(false);
            autoStartedRef.current = false;
        }, [parentSessionId]);

        // Absorb late-arriving initialMessages for the current session. Parent
        // (restoreSession) now flips the view before the REST call resolves, so
        // initialMessages lands after the session-id sync above. Only fill in
        // if we haven't started building history locally yet (empty or just
        // the optimistic user message), otherwise an in-flight round would be
        // stomped.
        useEffect(() => {
            if ((parentSessionId || '') !== (sessionIdRef.current || '')) return;
            if (!initialMessages || initialMessages.length === 0) return;
            setHistory(prev => {
                const noRealContent = prev.every(m => !(m.text || '').length);
                if (prev.length === 0 || (prev.length <= initialMessages.length && noRealContent)) {
                    return initialMessages;
                }
                return prev;
            });
        }, [initialMessages]);

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
            if (isDebating) return; // this tab is already the streamer
            let cancelled = false;
            (async () => {
                try {
                    // Cheap probe first so we don't trigger a 404 logged in the
                    // browser's Network tab when nothing is actively generating.
                    const r = await fetch(`/sessions/${encodeURIComponent(sessionId)}/generation-status`, {
                        credentials: 'include',
                    });
                    if (!r.ok) return;
                    const status = await r.json().catch(() => null);
                    if (!status?.active) return;
                    if (cancelled) return;

                    const myRound = ++roundIdRef.current;
                    stoppedRef.current = false;
                    setIsDebating(true);
                    try {
                        await fetchLifeeObserveStream(sessionId, makeSseHandlers(myRound));
                    } catch (e) {
                        if (!e?.notActive) console.warn('[observe]', e);
                    } finally {
                        if (!cancelled && roundIdRef.current === myRound) setIsDebating(false);
                    }
                } catch (_) { /* probe failed (network etc.) — skip observe */ }
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
            flushThrottle();                       // commit any pending typewriter text from previous round
            const myRound = ++roundIdRef.current;  // claim this round
            stoppedRef.current = false;            // reopen Realtime gate for the new round
            const isActive = () => roundIdRef.current === myRound;
            setIsDebating(true);
            setWarmupStage(null);
            setFollowupAnswers({});
            // 清空上一轮的 options。否则新一轮还在 streaming 时，旧选项会顶在
            // 第一个角色后面、第二个角色前面，看上去像"选项跑前面了"。
            setOptions([]);
            const cleanInput = (userInput ?? inputValue ?? '').toString().trim();

            if (cleanInput) {
                // 给乐观插入的用户消息一个 seq —— 否则带 seq 的 assistant 消息排序时
                // 会把没有 seq 的用户消息挤到列表末尾。用 (max existing seq + 1)，
                // 后端真实的 seq 大概率也是这个值；即使对不上，相对顺序还是对的。
                setHistory(prev => {
                    const maxSeq = prev.reduce((m, x) => (typeof x.seq === 'number' && x.seq > m ? x.seq : m), 0);
                    return [...prev, { personaId: 'user', text: cleanInput, seq: maxSeq + 1 }];
                });
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
                    personas: (selectedPersonas || []).map(p => ({
                        id: p.id, name: p.name,
                        soul: p.soul || '',           // gen-* 角色必须把 soul 带过去后端才能拼 system prompt
                        knowledge: p.knowledge || '',
                        emoji: p.avatar || '✨',
                    })),
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
                if (isActive()) { setIsDebating(false); setWarmupStage(null); }
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
                    // 后端 /summarize 返一次性 JSON——前端做 typewriter 让文字
                    // 逐字流入卡片，纯视觉效果。saveSummaryEntry 存全文，刷新
                    // 后从 cache 读到的也是全文（cache 命中时不再走动画分支）。
                    const full = res.summaries;
                    summaryAtCountRef.current = history.length;
                    saveSummaryEntry(sessionIdRef.current || sessionId, full, history.length);
                    const keys = Object.keys(full);
                    const partial = Object.fromEntries(keys.map(k => [k, '']));
                    const idx = Object.fromEntries(keys.map(k => [k, 0]));
                    setSummaryData(partial);
                    setShowVoiceMap(true);
                    const FPS = 30;
                    const STEP = 2;       // ~60 chars/sec
                    const tick = () => {
                        let done = true;
                        const next = { ...partial };
                        for (const k of keys) {
                            if (idx[k] < full[k].length) {
                                idx[k] = Math.min(full[k].length, idx[k] + STEP);
                                partial[k] = full[k].slice(0, idx[k]);
                                next[k] = partial[k];
                                done = false;
                            }
                        }
                        setSummaryData(next);
                        if (!done) setTimeout(tick, 1000 / FPS);
                    };
                    tick();
                } else {
                    setSummaryData({ _error: 'No summary returned' });
                }
            } catch (e) {
                setSummaryData({ _error: e.message || 'Network error' });
            } finally {
                setSummaryLoading(false);
            }
        };

        // ── Roadmap：从对话推 3-6 条人生路径 ────────────────────────────────
        // 调 /path-options 拿一个简短的路径列表（不含详细节点），用作起点。
        // 每条路径上点 Plan 才会调 /plan-30-days 出完整方案。
        const generateRoadmap = async () => {
            if (pathLoading) return;
            setPathLoading(true);
            setPathError('');
            setShowVoiceMap(true);
            // roadmap 模式下默认把 voice map 拉到全屏，便于看完整思维导图
            if (typeof window !== 'undefined') {
                setMapWidth(window.innerWidth);
            }
            try {
                const payload = sessionId
                    ? JSON.stringify({ sessionId, language: language || 'Chinese', situation: context?.situation || '' })
                    : JSON.stringify({
                        messages: history
                            .filter(m => m.personaId !== 'system' && m.personaId !== 'lifee-followup')
                            .slice(-12)
                            .map(m => ({ personaId: m.personaId, text: (m.text || '').slice(0, 240) })),
                        language: language || 'Chinese',
                        situation: context?.situation || '',
                    });
                const r = await window.fetch('/path-options', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: payload,
                });
                if (!r.ok) {
                    const txt = await r.text();
                    throw new Error(`Server ${r.status}: ${txt.slice(0, 100)}`);
                }
                const res = await r.json();
                if (res?.error && (!res?.paths || res.paths.length < 2)) throw new Error(res.error);
                const paths = Array.isArray(res?.paths) ? res.paths : [];
                if (paths.length < 2) throw new Error('Not enough paths returned');
                setPathOptions(paths);
            } catch (e) {
                setPathError(e?.message || 'Roadmap generation failed');
                setTimeout(() => setPathError(''), 4000);
            } finally {
                setPathLoading(false);
            }
        };

        const generatePlan = async (chosenOption = '') => {
            if (planLoading) return;
            setPlanLoading(true);
            setPlanData(null);
            setPlanWeek(0);
            setShowPlanModal(true);
            try {
                const payload = sessionId
                    ? JSON.stringify({ sessionId, language: language || 'Chinese', situation: context?.situation || '', chosenOption })
                    : JSON.stringify({
                        messages: history
                            .filter(m => m.personaId !== 'system' && m.personaId !== 'lifee-followup')
                            .slice(-10)
                            .map(m => ({ personaId: m.personaId, text: (m.text || '').slice(0, 200) })),
                        language: language || 'Chinese',
                        situation: context?.situation || '',
                        chosenOption,
                    });
                const r = await window.fetch('/plan-30-days', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: payload,
                });
                const res = await r.json();
                if (res?.plan?.weeks) setPlanData(res.plan);
            } catch (_) {
                /* swallow — modal shows fallback */
            } finally {
                setPlanLoading(false);
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
        // Parse a lifee-followup message's content, which is a JSON envelope
        // `{"__lifee_followup__": {intro, questions: [...]}}`. Returns null if the
        // content isn't valid JSON yet (still streaming) or doesn't match the shape.
        const parseFollowupEnvelope = (text) => {
            if (!text || typeof text !== 'string') return null;
            const trimmed = text.trim();
            if (!trimmed.startsWith('{')) return null;
            try {
                const parsed = JSON.parse(trimmed);
                const data = parsed && parsed.__lifee_followup__;
                if (data && Array.isArray(data.questions)) return data;
            } catch (_) {}
            return null;
        };

        // Parse numbered answers from a user reply ("1. 英国\n2. 独自一人") into
        // { [qIdx]: answerText }. Falls back to empty map if no structured lines.
        const parseSubmittedAnswers = (text) => {
            const out = {};
            if (!text) return out;
            for (const raw of String(text).split('\n')) {
                const m = raw.trim().match(/^(\d+)\s*[\.、]\s*(.+)$/);
                if (m) {
                    const qi = parseInt(m[1], 10) - 1;
                    if (qi >= 0) out[qi] = m[2].trim();
                }
            }
            return out;
        };

        const renderMessage = (m, idx, lastPersonaIdx = -1) => {
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
                            <div class="no-shine bg-surface-container/80 backdrop-blur-md px-5 py-4 rounded-xl rounded-tr-sm text-on-surface shadow-sm leading-relaxed border-r-2 border-on-surface-variant/20 text-sm max-w-full">
                                <p class="whitespace-pre-wrap break-words">${m.text || ''}</p>
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

            // Follow-up: render as a structured form card (persistable via history).
            // If the content isn't a valid JSON envelope — legacy messages from before
            // the JSON refactor, or a chunk still streaming — fall through to the plain
            // LIFEE bubble below so nothing disappears.
            const followupEnvelope = isFollowUp ? parseFollowupEnvelope(m.text) : null;
            if (isFollowUp && followupEnvelope) {
                const data = followupEnvelope;
                const nextUserMsg = history.slice(idx + 1).find(x => x.personaId === 'user');
                const isAnswered = !!nextUserMsg;
                const submittedAnswers = isAnswered ? parseSubmittedAnswers(nextUserMsg.text) : null;
                const qs = data.questions || [];
                const getAnswer = (qi) => isAnswered ? (submittedAnswers[qi] || '') : (followupAnswers[qi] || '');
                const answeredCount = Object.keys(followupAnswers).length;
                const sendAnswers = () => {
                    const parts = qs
                        .map((q, qi) => followupAnswers[qi] ? `${qi + 1}. ${followupAnswers[qi]}` : null)
                        .filter(Boolean);
                    if (!parts.length) return;
                    const message = parts.join('\n');
                    setFollowupAnswers({});
                    runRound(message);
                };
                return html`
                    <div key=${idx} class="w-full max-w-full animate-in">
                        <div class=${`rounded-2xl border bg-surface-container/70 backdrop-blur-md p-4 space-y-3 transition-opacity ${
                            isAnswered ? 'border-white/10 opacity-70' : 'border-primary/25'
                        }`}>
                            ${data.intro ? html`
                                <p class="text-xs text-on-surface/70 italic leading-relaxed">${data.intro}</p>
                            ` : null}
                            ${qs.map((q, qi) => {
                                const current = getAnswer(qi);
                                const isPillMatch = (q.options || []).includes(current);
                                const freeText = isPillMatch ? '' : current;
                                return html`
                                    <div key=${qi} class="space-y-1.5">
                                        <p class="text-sm font-semibold text-on-surface">
                                            <span class="text-primary/60 mr-2">Q${qi + 1}.</span>${q.q}
                                        </p>
                                        <div class="flex flex-wrap gap-2 pl-6">
                                            ${(q.options || []).map((opt, oi) => {
                                                const isSel = current === opt;
                                                const baseCls = isSel
                                                    ? 'bg-primary/15 border border-primary text-primary'
                                                    : 'bg-surface-container-high/80 border border-white/15 text-on-surface/80';
                                                const hoverCls = isAnswered ? '' : ' hover:border-primary/50 hover:text-primary hover:bg-surface-container';
                                                return html`
                                                    <button
                                                        key=${oi}
                                                        disabled=${isAnswered}
                                                        onClick=${isAnswered ? null : () => setFollowupAnswers(prev => {
                                                            if (prev[qi] === opt) {
                                                                const { [qi]: _, ...rest } = prev;
                                                                return rest;
                                                            }
                                                            return { ...prev, [qi]: opt };
                                                        })}
                                                        class=${'no-shine text-xs px-3 py-1.5 rounded-full transition-colors ' + baseCls + hoverCls + (isAnswered ? ' cursor-default' : '')}
                                                    >
                                                        <span class=${`mr-1.5 ${isSel ? 'text-primary/80' : 'text-primary/50'}`}>${String.fromCharCode(65 + oi)}</span>${opt}
                                                    </button>
                                                `;
                                            })}
                                        </div>
                                        <div class="pl-6 pt-1">
                                            <input
                                                type="text"
                                                placeholder=${t('chat.followUpCustom') || 'Or write your own…'}
                                                value=${freeText}
                                                readOnly=${isAnswered}
                                                onInput=${isAnswered ? null : (e) => {
                                                    const v = e.target.value;
                                                    setFollowupAnswers(prev => {
                                                        if (!v.trim()) {
                                                            const { [qi]: _, ...rest } = prev;
                                                            return rest;
                                                        }
                                                        return { ...prev, [qi]: v };
                                                    });
                                                }}
                                                class=${`no-shine w-full text-xs px-3 py-1.5 rounded-lg bg-transparent border transition-colors focus:outline-none placeholder-on-surface/25 ${
                                                    freeText
                                                        ? 'border-primary/50 text-primary'
                                                        : 'border-white/10 text-on-surface/80' + (isAnswered ? '' : ' focus:border-primary/40')
                                                }`}
                                            />
                                        </div>
                                    </div>
                                `;
                            })}
                            ${!isAnswered ? html`
                                <div class="flex items-center justify-end pt-1">
                                    <button
                                        onClick=${sendAnswers}
                                        disabled=${answeredCount === 0}
                                        class=${`no-shine text-xs font-semibold uppercase tracking-widest px-5 py-2 rounded-full transition-all ${
                                            answeredCount === 0
                                                ? 'bg-surface-container-high/40 text-on-surface/30 cursor-not-allowed'
                                                : 'bg-primary text-on-primary hover:bg-primary/90'
                                        }`}
                                    >${t('chat.submitAnswers') || 'Send'}</button>
                                </div>
                            ` : null}
                        </div>
                    </div>
                `;
            }

            // Persona message (or follow-up fallback for legacy / partially-streamed content)
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
                            class="no-shine bg-surface-container/80 backdrop-blur-md px-5 py-4 rounded-tl-none rounded-tr-xl rounded-br-xl rounded-bl-[2.5rem] text-on-surface shadow-sm leading-relaxed border-l-2 text-sm"
                            style=${{ borderLeftColor: color.border }}
                        >
                            <${CharBlurText} text=${m.text || ''} />
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
                        ${idx === lastPersonaIdx && options.length > 0 && !isDebating && !(inputValue && inputValue.trim()) ? html`
                            <div class="flex flex-wrap gap-2 pt-2 animate-in">
                                ${options.map((opt, i) => html`
                                    <button
                                        key=${i}
                                        onClick=${() => runRound(opt)}
                                        class="no-shine text-left px-4 py-2 text-xs font-semibold rounded-full bg-surface-container-high/70 border border-primary/25 text-primary/80 hover:text-primary hover:border-primary/60 hover:bg-surface-container transition-colors"
                                    ><span>${opt}</span></button>
                                `)}
                            </div>
                        ` : null}
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
                if (!out['__timeline_a']) {
                    out['__timeline_a'] = { x: 18, y: 660 };
                }
                if (!out['__timeline_b']) {
                    out['__timeline_b'] = { x: 296, y: 660 };
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
            // Fit-to-view: 把所有卡片的 bbox 居中并缩放到画布大小，保留用户拖动后的
            // 位置（不重置卡片到默认槽位）。卡片宽 255px、高估算 320px（头+三条最近消息）；
            // transform 里有 +40px 偏移要算进 pan 反推。
            const fitToView = () => {
                const rect = canvasRef.current?.getBoundingClientRect();
                if (!rect) return;
                const ids = [...voices.map(v => v.id), '__user'];
                pathOptions.forEach(p => ids.push(`__path_${p.id}`));
                const positions = ids.map(id => cardPos[id]).filter(Boolean);
                if (!positions.length) {
                    setPan({ x: 0, y: 0 });
                    setScale(1.0);
                    return;
                }
                const CARD_W = 255;
                const CARD_H = 320;
                const PAD = 40;       // px breathing inside viewport
                const OFFSET = 40;    // matches translate(+40, +40) in transform

                let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
                for (const p of positions) {
                    minX = Math.min(minX, p.x);
                    minY = Math.min(minY, p.y);
                    maxX = Math.max(maxX, p.x + CARD_W);
                    maxY = Math.max(maxY, p.y + CARD_H);
                }
                const contentW = Math.max(1, maxX - minX);
                const contentH = Math.max(1, maxY - minY);
                const viewW = Math.max(100, rect.width - 2 * PAD);
                const viewH = Math.max(100, rect.height - 2 * PAD);
                const newScale = Math.min(2, Math.max(0.3, Math.min(viewW / contentW, viewH / contentH)));

                const cx = (minX + maxX) / 2;
                const cy = (minY + maxY) / 2;
                setPan({
                    x: rect.width / 2 - OFFSET - cx * newScale,
                    y: rect.height / 2 - OFFSET - cy * newScale,
                });
                setScale(newScale);
            };
            const reset = fitToView;

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
                            <button
                                onClick=${generateRoadmap}
                                disabled=${history.length < 2 || pathLoading}
                                class=${`no-shine px-2 h-7 rounded-md btn-ghost text-[9px] uppercase tracking-wider flex items-center gap-1 disabled:opacity-30 ${pathOptions.length > 0 ? 'text-secondary' : ''}`}
                                title="Sketch 3-6 possible life paths from this conversation"
                            >
                                ${pathLoading
                                    ? html`<span class="material-symbols-outlined animate-spin" style=${{ fontSize: '12px' }}>progress_activity</span>`
                                    : html`<span class="material-symbols-outlined" style=${{ fontSize: '12px' }}>route</span>`
                                }
                                <span>${t('chat.roadmap') || 'Roadmap'}</span>
                            </button>
                            <button onClick=${reset}
                                class="no-shine px-2 h-7 rounded-md btn-ghost text-[9px] uppercase tracking-wider"
                                title="Fit all cards into view"
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
                            <!-- ── 思维导图连线：从 YOU 卡右侧中心拉 Bezier 到每张 path 卡左侧中心（左→右思维导图） ── -->
                            ${pathOptions.length > 0 ? html`
                                <svg
                                    class="absolute top-0 left-0 pointer-events-none"
                                    style=${{ width: '1px', height: '1px', overflow: 'visible' }}
                                >
                                    ${pathOptions.map((p, pi) => {
                                        const userPosL = cardPos['__user'] || { x: 0, y: 0 };
                                        const id = `__path_${p.id}`;
                                        // path 默认槽位：右侧一列（>=5 条切两列），垂直按 index 分布
                                        const COLS = pathOptions.length >= 5 ? 2 : 1;
                                        const col = pi % COLS;
                                        const row = Math.floor(pi / COLS);
                                        const ROW_PER_COL = Math.ceil(pathOptions.length / COLS);
                                        const ROW_GAP = 150;
                                        const startY = userPosL.y + 75 - ((ROW_PER_COL - 1) * ROW_GAP) / 2;
                                        const fallback = {
                                            x: userPosL.x + 360 + col * 290,
                                            y: startY + row * ROW_GAP,
                                        };
                                        const pathPos = cardPos[id] || fallback;
                                        // 连接 YOU 右侧中心 → path 左侧中心
                                        const x1 = userPosL.x + 255;
                                        const y1 = userPosL.y + 75;
                                        const x2 = pathPos.x;
                                        const y2 = pathPos.y + 60;
                                        const dx = Math.max(60, Math.abs(x2 - x1) / 2);
                                        const colors = ['#e8a84c', '#8a9a6c', '#c47a6c', '#f59e0b', '#10b981', '#f43f5e'];
                                        const c = colors[pi % colors.length];
                                        return html`
                                            <g key=${`line-${p.id}`}>
                                                <path
                                                    d=${`M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`}
                                                    stroke=${c}
                                                    stroke-width="1.8"
                                                    stroke-opacity="0.55"
                                                    fill="none"
                                                    stroke-linecap="round"
                                                />
                                                <circle cx=${x1} cy=${y1} r="3" fill=${c} fill-opacity="0.65" />
                                                <circle cx=${x2} cy=${y2} r="3.5" fill=${c} fill-opacity="0.9" />
                                            </g>
                                        `;
                                    })}
                                </svg>
                            ` : null}

                            ${voices.map((v, idx) => {
                                const color = getColor(v.id);
                                const pos = cardPos[v.id] || { x: 0, y: 0, rotate: 0 };
                                const ava = v.avatar || '☁️';
                                const recent = v.messages.slice(-3);
                                // Roadmap 模式下角色卡缩成小头像，给思维导图让位
                                if (pathOptions.length > 0) {
                                    const userPosL = cardPos['__user'] || { x: 0, y: 0 };
                                    // 默认槽位：YOU 卡左侧竖排，避免和右边 path 卡重叠
                                    const miniFallback = { x: userPosL.x - 60, y: userPosL.y + idx * 52, rotate: 0 };
                                    const miniPos = cardPos[v.id] || miniFallback;
                                    const isAvaUrl = typeof ava === 'string' && /^(https?:|\/|data:)/.test(ava);
                                    return html`
                                        <div
                                            key=${v.id}
                                            class="absolute cursor-grab active:cursor-grabbing select-none group"
                                            style=${{ left: miniPos.x + 'px', top: miniPos.y + 'px' }}
                                            onMouseDown=${(e) => startCardDrag(e, v.id)}
                                            title=${`${v.name} · ${v.role || ''}`}
                                        >
                                            <div
                                                class="w-11 h-11 rounded-full border flex items-center justify-center text-base shrink-0 overflow-hidden shadow-lg shadow-black/40 transition-transform group-hover:scale-110"
                                                style=${{ borderColor: color.ring, backgroundColor: color.bg }}
                                            >
                                                ${isAvaUrl
                                                    ? html`<img src=${ava} class="w-full h-full object-cover" />`
                                                    : html`<span>${ava}</span>`}
                                            </div>
                                            <!-- 悬停显示名字气泡 -->
                                            <div class="absolute left-12 top-1/2 -translate-y-1/2 px-2 py-1 rounded-md bg-surface-container/95 border border-white/10 text-[9px] font-bold uppercase tracking-widest text-on-surface whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
                                                ${v.name}
                                            </div>
                                        </div>
                                    `;
                                }
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

                            <!-- ── Roadmap path 卡片：YOU 节点右侧排开（思维导图左→右） ── -->
                            ${pathOptions.map((p, pi) => {
                                const id = `__path_${p.id}`;
                                const userPosL = cardPos['__user'] || { x: 0, y: 0 };
                                // 默认槽位：YOU 节点右侧 360px 起，>=5 条时切两列，垂直按 index 分布并居中对齐 YOU
                                const COLS = pathOptions.length >= 5 ? 2 : 1;
                                const col = pi % COLS;
                                const row = Math.floor(pi / COLS);
                                const ROW_PER_COL = Math.ceil(pathOptions.length / COLS);
                                const ROW_GAP = 150;
                                const startY = userPosL.y + 75 - ((ROW_PER_COL - 1) * ROW_GAP) / 2;
                                const fallback = {
                                    x: userPosL.x + 360 + col * 290,
                                    y: startY + row * ROW_GAP,
                                };
                                const pos = cardPos[id] || fallback;
                                const palettes = [
                                    { bg: 'bg-primary/10', text: 'text-primary', bdr: 'border-primary/60', hover: 'hover:bg-primary/10' },
                                    { bg: 'bg-secondary/10', text: 'text-secondary', bdr: 'border-secondary/60', hover: 'hover:bg-secondary/10' },
                                    { bg: 'bg-tertiary/10', text: 'text-tertiary', bdr: 'border-tertiary/60', hover: 'hover:bg-tertiary/10' },
                                    { bg: 'bg-amber-500/10', text: 'text-amber-300', bdr: 'border-amber-500/60', hover: 'hover:bg-amber-500/10' },
                                    { bg: 'bg-emerald-500/10', text: 'text-emerald-300', bdr: 'border-emerald-500/60', hover: 'hover:bg-emerald-500/10' },
                                    { bg: 'bg-rose-500/10', text: 'text-rose-300', bdr: 'border-rose-500/60', hover: 'hover:bg-rose-500/10' },
                                ];
                                const c = palettes[pi % palettes.length];
                                return html`
                                    <div
                                        key=${p.id}
                                        class="absolute w-[255px] cursor-grab active:cursor-grabbing select-none"
                                        style=${{ left: pos.x + 'px', top: pos.y + 'px' }}
                                        onMouseDown=${(e) => startCardDrag(e, id)}
                                    >
                                        <div class="rounded-[20px] bg-surface-container border border-outline/15 shadow-xl shadow-black/40 overflow-hidden">
                                            <div class=${`px-4 py-2.5 border-b border-white/10 flex items-center justify-between ${c.bg}`}>
                                                <span class=${`text-[8px] font-black uppercase tracking-[0.28em] ${c.text}`}>PATH ${String.fromCharCode(65 + pi)}</span>
                                                <button
                                                    onMouseDown=${(e) => e.stopPropagation()}
                                                    onClick=${() => generatePlan(p.label || '')}
                                                    disabled=${planLoading}
                                                    class=${`no-shine text-[7px] font-black uppercase tracking-[0.1em] px-2 py-0.5 rounded-full border ${c.bdr} ${c.text} ${c.hover} transition-all whitespace-nowrap disabled:opacity-40`}
                                                    title="Generate full 30-day plan for this path"
                                                >Plan →</button>
                                            </div>
                                            <div class="px-4 py-3.5">
                                                <div class=${`font-headline text-sm font-black leading-snug text-on-surface mb-1.5`}>${p.label || ''}</div>
                                                ${p.summary ? html`
                                                    <div class="text-[10px] leading-relaxed text-on-surface-variant/70">${p.summary}</div>
                                                ` : null}
                                            </div>
                                        </div>
                                    </div>
                                `;
                            })}

                            <!-- Roadmap loading hint：YOU 卡右侧临时显示 -->
                            ${pathLoading && pathOptions.length === 0 ? (() => {
                                const userPosL = cardPos['__user'] || { x: 0, y: 0 };
                                return html`
                                    <div
                                        class="absolute pointer-events-none"
                                        style=${{ left: (userPosL.x + 360) + 'px', top: (userPosL.y + 60) + 'px' }}
                                    >
                                        <div class="px-4 py-3 rounded-2xl bg-surface-container/80 border border-white/10 backdrop-blur text-[10px] text-on-surface-variant/60 flex items-center gap-2">
                                            <span class="material-symbols-outlined animate-spin" style=${{ fontSize: '14px' }}>progress_activity</span>
                                            <span>Sketching paths…</span>
                                        </div>
                                    </div>
                                `;
                            })() : null}
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
                            <span class=${'no-shine w-8 h-4 rounded-full relative transition-colors ' + (active ? color.replace('text-', 'bg-') : 'bg-surface-container-highest')}>
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
                        color="text-primary"
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

                    ${(() => {
                        // Compute the last persona-reply index so renderMessage can
                        // pin the suggested-follow-up pills under it.
                        let lastPersonaIdx = -1;
                        for (let i = history.length - 1; i >= 0; i--) {
                            const pid = history[i]?.personaId;
                            if (pid && pid !== 'user' && pid !== 'system' && pid !== 'lifee-followup') {
                                lastPersonaIdx = i;
                                break;
                            }
                        }
                        return history.map((m, idx) => renderMessage(m, idx, lastPersonaIdx));
                    })()}

                    <!-- Warming-up indicator. Three states:
                         • Multi-persona + no picked speaker → cluster avatars + shimmery
                           "Convening the council" (or "Searching archives" during RAG).
                         • Picked speaker (or single-persona fallback) → that persona's
                           avatar + shimmery "Gathering their thoughts".
                         • Any persona stub has text → hide (the bubble takes over). -->
                    ${(() => {
                        if (!isDebating) return null;
                        const last = history[history.length - 1];
                        if (last && last.personaId && last.personaId !== 'user' && (last.text || '').length > 0) return null;

                        const pickedId = warmupStage && warmupStage.startsWith('picked:')
                            ? warmupStage.slice('picked:'.length)
                            : null;
                        const picked = pickedId
                            ? ((selectedPersonas || []).find(p => p.id === pickedId) || null)
                            : null;

                        const numSelected = (selectedPersonas || []).length;
                        const isImg = (a) => typeof a === 'string' && /^(https?:|\/|data:)/.test(a);

                        if (numSelected > 1 && !picked) {
                            const clusterLabel = warmupStage === 'kb_search'
                                ? t('warmup.searchingKb')
                                : t('warmup.convening');
                            const members = (selectedPersonas || []).slice(0, 4);
                            return html`
                                <div class="flex items-start gap-4 w-full pr-14 animate-in">
                                    <div class="flex -space-x-3 shrink-0">
                                        ${members.map(p => {
                                            const c = getColor(p.id);
                                            const a = p.avatar || '☁️';
                                            return html`
                                                <div
                                                    key=${p.id}
                                                    class="w-10 h-10 rounded-full border-2 flex items-center justify-center text-lg overflow-hidden"
                                                    style=${{ borderColor: c.ring, backgroundColor: c.bg }}
                                                >
                                                    ${!isImg(a)
                                                        ? html`<span>${a}</span>`
                                                        : html`<img src=${a} class="w-full h-full object-cover" />`
                                                    }
                                                </div>
                                            `;
                                        })}
                                    </div>
                                    <div class="flex-1 min-w-0 pt-2">
                                        <p class="warmup-status text-[11px] leading-relaxed">
                                            <span class="mr-1 opacity-70">*</span>${clusterLabel}<span class="ml-0.5">…</span>
                                        </p>
                                    </div>
                                </div>
                            `;
                        }

                        const speaker = picked || (selectedPersonas || [])[0];
                        if (!speaker) return null;
                        const color = getColor(speaker.id);
                        const ava = speaker.avatar || '☁️';
                        return html`
                            <div class="flex items-start gap-4 w-full pr-14 animate-in">
                                <div
                                    class="w-10 h-10 rounded-full border-2 flex items-center justify-center text-lg shrink-0 overflow-hidden"
                                    style=${{ borderColor: color.ring, backgroundColor: color.bg }}
                                >
                                    ${!isImg(ava)
                                        ? html`<span>${ava}</span>`
                                        : html`<img src=${ava} class="w-full h-full object-cover" />`
                                    }
                                </div>
                                <div class="space-y-1.5 flex-1 min-w-0">
                                    <p class="text-[10px] font-bold uppercase tracking-widest ml-1" style=${{ color: color.text }}>
                                        ${speaker.name}
                                    </p>
                                    <p class="warmup-status text-[11px] leading-relaxed ml-1">
                                        <span class="mr-1 opacity-70">*</span>${t('warmup.organizing')}<span class="ml-0.5">…</span>
                                    </p>
                                </div>
                            </div>
                        `;
                    })()}
                  </div>
                </div>

                <!-- ── Footer input area ── -->
                <footer class="p-6 bg-surface-dim/40 backdrop-blur-2xl border-t border-white/5 shrink-0">
                    <div class="max-w-5xl mx-auto space-y-3">

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

                <!-- ── Roadmap error toast ── -->
                ${pathError ? html`
                    <div class="fixed top-24 right-4 z-50 text-xs text-rose-300 bg-rose-900/80 border border-rose-500/30 px-4 py-3 rounded-2xl shadow-lg backdrop-blur-md">
                        Roadmap: ${pathError}
                        <button onClick=${() => setPathError('')} class="ml-2 opacity-50 hover:opacity-100">✕</button>
                    </div>
                ` : null}

                <!-- ── 30-Day Plan modal ── -->
                ${showPlanModal ? html`
                    <div
                        class="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
                        onClick=${() => setShowPlanModal(false)}
                    >
                        <div
                            class="bg-surface-container/95 backdrop-blur-xl border border-white/10 rounded-2xl shadow-2xl w-full max-w-2xl max-h-[85vh] flex flex-col overflow-hidden"
                            onClick=${(e) => e.stopPropagation()}
                        >
                            <div class="px-6 py-5 border-b border-white/10 flex items-center justify-between shrink-0">
                                <div>
                                    <div class="text-[9px] font-black uppercase tracking-[0.3em] text-primary mb-1">${t('chat.actionPlan') || 'Action Plan'}</div>
                                    <div class="text-lg font-headline italic font-bold text-on-surface">${t('chat.first30Days') || 'My First 30 Days'}</div>
                                </div>
                                <button
                                    onClick=${() => setShowPlanModal(false)}
                                    class="w-8 h-8 rounded-full border border-white/15 text-on-surface-variant/60 hover:text-on-surface flex items-center justify-center"
                                >✕</button>
                            </div>

                            ${planLoading ? html`
                                <div class="flex-1 flex items-center justify-center gap-3 p-10">
                                    <span class="material-symbols-outlined animate-spin text-primary/60" style=${{ fontSize: '20px' }}>progress_activity</span>
                                    <span class="text-xs text-on-surface-variant/60">${t('chat.planCrafting') || 'Crafting your 30-day plan…'}</span>
                                </div>
                            ` : null}

                            ${!planLoading && planData?.weeks ? html`
                                <div class="px-6 py-3 border-b border-white/10 flex gap-2 overflow-x-auto no-scrollbar shrink-0">
                                    ${planData.weeks.map((week, wi) => html`
                                        <button
                                            key=${week.id || wi}
                                            onClick=${() => setPlanWeek(wi)}
                                            class=${`shrink-0 px-4 py-2 rounded-xl text-[11px] font-black uppercase tracking-wider transition-all border ${
                                                planWeek === wi
                                                    ? 'bg-on-surface text-surface border-on-surface'
                                                    : 'bg-surface-container-high/40 text-on-surface-variant/70 border-white/10 hover:border-white/25'
                                            }`}
                                        >${week.label || `Week ${wi + 1}`}</button>
                                    `)}
                                </div>
                                ${(() => {
                                    const week = planData.weeks[planWeek];
                                    if (!week) return null;
                                    return html`
                                        <div class="flex-1 overflow-y-auto no-scrollbar px-6 py-4">
                                            ${week.goal ? html`
                                                <div class="bg-surface-container-high/50 border border-white/10 rounded-xl px-4 py-3 mb-4 text-xs text-on-surface-variant/80 leading-relaxed">
                                                    <span class="font-black text-on-surface">Week ${planWeek + 1}：</span>${week.goal}
                                                </div>
                                            ` : null}
                                            <div class="flex flex-col gap-2.5">
                                                ${(week.tasks || []).map((task, ti) => html`
                                                    <div key=${ti} class="bg-surface-container-high/40 border border-white/10 rounded-xl px-4 py-3 flex gap-3 items-start">
                                                        <div class="w-[18px] h-[18px] rounded-full border border-white/30 shrink-0 mt-0.5"></div>
                                                        <div class="min-w-0 flex-1">
                                                            <div class="text-[13px] font-black text-on-surface mb-1">${task.title || ''}</div>
                                                            <div class="text-[11px] text-on-surface-variant/65 leading-relaxed mb-2">${task.description || ''}</div>
                                                            ${(task.tags || []).length > 0 ? html`
                                                                <div class="flex flex-wrap gap-1">
                                                                    ${(task.tags || []).map((tag, tgi) => {
                                                                        const palettes = ['bg-primary/15 text-primary', 'bg-secondary/15 text-secondary', 'bg-tertiary/15 text-tertiary', 'bg-amber-500/15 text-amber-300'];
                                                                        return html`<span key=${tgi} class=${`text-[9px] px-2 py-0.5 rounded-full font-bold ${palettes[tgi % palettes.length]}`}>${tag}</span>`;
                                                                    })}
                                                                </div>
                                                            ` : null}
                                                        </div>
                                                    </div>
                                                `)}
                                            </div>
                                            ${planWeek < planData.weeks.length - 1 ? html`
                                                <div class="flex justify-center mt-4">
                                                    <button
                                                        onClick=${() => setPlanWeek(w => w + 1)}
                                                        class="w-8 h-8 rounded-full border border-white/15 hover:border-white/40 text-on-surface-variant/60 hover:text-on-surface flex items-center justify-center"
                                                        title="Next week"
                                                    ><span class="material-symbols-outlined" style=${{ fontSize: '14px' }}>expand_more</span></button>
                                                </div>
                                            ` : null}
                                        </div>
                                    `;
                                })()}
                            ` : null}

                            ${!planLoading && !planData?.weeks ? html`
                                <div class="flex-1 flex items-center justify-center p-10 text-xs text-on-surface-variant/50">
                                    ${t('chat.planFailed') || 'Failed to generate plan. Try again.'}
                                </div>
                            ` : null}
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

                    /* Warming-up status line — italic, warm-amber shimmer
                       (Claude-style "*Building Phase 4…*" look) */
                    .warmup-status {
                        font-style: italic;
                        letter-spacing: 0.04em;
                        background-image: linear-gradient(
                            90deg,
                            rgba(232, 168, 76, 0.30) 0%,
                            rgba(252, 227, 168, 1)   50%,
                            rgba(232, 168, 76, 0.30) 100%
                        );
                        background-size: 220% 100%;
                        -webkit-background-clip: text;
                                background-clip: text;
                        -webkit-text-fill-color: transparent;
                        animation: warmupShimmer 2.4s linear infinite;
                    }
                    @keyframes warmupShimmer {
                        0%   { background-position: 200% 50%; }
                        100% { background-position: -200% 50%; }
                    }
                    @media (prefers-reduced-motion: reduce) {
                        .warmup-status { animation: none; }
                    }
                `}</style>
            </div>
        `;
    };

    // ── Register in VOID_VIEWS ────────────────────────────────────────────────
    window.VOID_VIEWS = window.VOID_VIEWS || {};
    window.VOID_VIEWS.debate = (props) => html`<${ChatArena} ...${props} />`;

})();
