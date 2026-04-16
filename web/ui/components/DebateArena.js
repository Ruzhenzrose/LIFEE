const { useState, useEffect, useRef, useMemo } = React;
const { Icon, AvatarDisplay } = window;
const { TarotReadingModal, TAROT_DECK } = window;

// Pre-set card positions — 2-column grid, visible at default 82% zoom
// Col A: x=18  Col B: x=288   Row gap: ~185px
const CANVAS_CARD_POSITIONS = [
    { x: 18,  y: 28,  rotate: -1   },  // A1
    { x: 288, y: 18,  rotate: 0.8  },  // B1
    { x: 18,  y: 213, rotate: 0.7  },  // A2
    { x: 288, y: 203, rotate: -0.9 },  // B2
    { x: 18,  y: 398, rotate: -0.8 },  // A3
    { x: 288, y: 388, rotate: 1    },  // B3
    { x: 18,  y: 583, rotate: 0.6  },  // A4
    { x: 288, y: 573, rotate: -0.7 },  // B4
];

const DebateArena = ({
    context,
    selectedPersonas,
    setView,
    ensureSession,
    persistMessage,
    buildContextBlock,
    userAvatar,
    user,
    initialMessages = [],
    parentSessionId = ""
}) => {
    const [history, setHistory] = useState(initialMessages);
    const [options, setOptions] = useState([]);
    const [isDebating, setIsDebating] = useState(false);
    const [sessionId, setSessionId] = useState(parentSessionId || "");
    const [inputValue, setInputValue] = useState('');
    const [tarotDecision, setTarotDecision] = useState('');
    const [tarotModalOpen, setTarotModalOpen] = useState(false);
    const [credits, setCredits] = useState(null);
    const [showPaywall, setShowPaywall] = useState(false);
    const [showVerify, setShowVerify] = useState(false);
    const [verifyError, setVerifyError] = useState('');
    const verifyRef = useRef(null);
    const verifyWidgetRef = useRef(null);
    const [redeemCode, setRedeemCode] = useState('');
    const [followUpMode, setFollowUpMode] = useState(false);
    const [webSearchMode, setWebSearchMode] = useState(false);
    const [maxSpeakers, setMaxSpeakers] = useState(0);
    const [showSummaryPanel, setShowSummaryPanel] = useState(false);
    const [summaryData, setSummaryData] = useState({});
    const [summaryLoading, setSummaryLoading] = useState(false);
    const summaryAtCountRef = useRef(0); // 上次 summary 时的消息数
    const [language, setLanguage] = useState(() => localStorage.getItem('lifee_lang') || '');

    // 用户档案自动提取
    const sessionIdRef = useRef(sessionId);
    useEffect(() => { sessionIdRef.current = sessionId; }, [sessionId]);

    const [extractStatus, setExtractStatus] = useState(''); // '' | 'extracting' | 'done'
    const extractTimerRef = useRef(null);

    const fireExtractMemory = (sid) => {
        if (!user?.id || !sid) return;
        supabaseClient.from('profiles').select('user_memory').eq('id', user.id).maybeSingle()
            .then(({ data }) => {
                window.fetch('/extract-memory', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include',
                    body: JSON.stringify({ sessionId: sid, userId: user.id, currentMemory: data?.user_memory || '' }),
                }).then(r => r.json()).then(res => {
                    if (res?.updated) {
                        setExtractStatus('done');
                        clearTimeout(extractTimerRef.current);
                        extractTimerRef.current = setTimeout(() => setExtractStatus(''), 3000);
                    }
                }).catch(() => {});
            }).catch(() => {});
    };


    // Canvas state
    const [canvasScale, setCanvasScale] = useState(0.82);
    const [canvasPan, setCanvasPan] = useState({ x: 0, y: 0 });
    const isPanningRef = useRef(false);
    const panStartRef = useRef({ x: 0, y: 0 });
    const panOriginRef = useRef({ x: 0, y: 0 });
    const [showCanvas, setShowCanvas] = useState(false); // mobile toggle

    // Card drag state (positions keyed by card id)
    const [cardPositions, setCardPositions] = useState({});
    const [draggingCardId, setDraggingCardId] = useState(null);
    const draggingCardRef = useRef(null); // { cardId, startMouseX, startMouseY, startCardX, startCardY, rotate, scale }

    // Resize handle state
    const [canvasWidth, setCanvasWidth] = useState(440);
    const [isResizing, setIsResizing] = useState(false);
    const isResizingRef = useRef(false);
    const resizeStartRef = useRef({ x: 0, width: 0 });

    useEffect(() => {
        const onMouseMove = (e) => {
            if (!isResizingRef.current) return;
            const dx = resizeStartRef.current.x - e.clientX; // drag left = canvas wider
            const next = Math.min(Math.max(resizeStartRef.current.width + dx, 240), window.innerWidth * 0.70);
            setCanvasWidth(next);
        };
        const onMouseUp = () => {
            if (draggingCardRef.current) {
                draggingCardRef.current = null;
                setDraggingCardId(null);
                document.body.style.cursor = '';
                document.body.style.userSelect = '';
            }
            if (!isResizingRef.current) return;
            isResizingRef.current = false;
            setIsResizing(false);
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
        };
        window.addEventListener('mousemove', onMouseMove);
        window.addEventListener('mouseup', onMouseUp);
        return () => {
            window.removeEventListener('mousemove', onMouseMove);
            window.removeEventListener('mouseup', onMouseUp);
        };
    }, []);

    const startResize = (e) => {
        e.preventDefault();
        isResizingRef.current = true;
        setIsResizing(true);
        resizeStartRef.current = { x: e.clientX, width: canvasWidth };
        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';
    };

    const detectLang = (text) => {
        const ch = (text || '').trim()[0] || '';
        if (/[\u3040-\u30ff]/.test(ch)) return 'Japanese';
        if (/[\uac00-\ud7af]/.test(ch)) return 'Korean';
        if (/[\u4e00-\u9fff]/.test(ch)) return 'Chinese';
        return 'English';
    };
    const scrollRef = useRef(null);
    const inputFieldRef = useRef(null);
    const hasTarotMaster = selectedPersonas.some(p => p.id === 'tarot-master');
    const tarotMasterPersona = selectedPersonas.find(p => p.id === 'tarot-master') || null;
    const debatePersonas = selectedPersonas.filter(p => p.id !== 'tarot-master');

    // Group messages by persona for the canvas
    const personaSummaries = useMemo(() => {
        const map = {};
        history.forEach(m => {
            if (!m.text || m.personaId === 'user' || m.personaId === 'system' || m.personaId === 'lifee-followup') return;
            if (!map[m.personaId]) map[m.personaId] = [];
            map[m.personaId].push(m.text);
        });
        return map;
    }, [history]);

    useEffect(() => { if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight; }, [history]);

    useEffect(() => { setSessionId(parentSessionId || ""); }, [parentSessionId]);

    useEffect(() => {
        const url = user?.id ? `/credits?userId=${user.id}` : '/credits';
        fetch(url, { credentials: 'include' }).then(r => r.json()).then(d => {
            if (typeof d.balance === 'number') setCredits(d.balance);
        }).catch(() => {});
    }, [user]);

    // Canvas pan/zoom handlers
    const handleCanvasMouseDown = (e) => {
        if (e.button !== 0) return;
        isPanningRef.current = true;
        panStartRef.current = { x: e.clientX, y: e.clientY };
        panOriginRef.current = { ...canvasPan };
        e.currentTarget.style.cursor = 'grabbing';
    };
    const handleCanvasMouseMove = (e) => {
        // Card drag takes priority over canvas pan
        if (draggingCardRef.current) {
            const { cardId, startMouseX, startMouseY, startCardX, startCardY, rotate, scale } = draggingCardRef.current;
            const dx = (e.clientX - startMouseX) / scale;
            const dy = (e.clientY - startMouseY) / scale;
            setCardPositions(prev => ({ ...prev, [cardId]: { x: startCardX + dx, y: startCardY + dy, rotate } }));
            return;
        }
        if (!isPanningRef.current) return;
        setCanvasPan({
            x: panOriginRef.current.x + (e.clientX - panStartRef.current.x),
            y: panOriginRef.current.y + (e.clientY - panStartRef.current.y)
        });
    };
    const handleCanvasMouseUp = (e) => {
        if (draggingCardRef.current) {
            draggingCardRef.current = null;
            setDraggingCardId(null);
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
            if (e.currentTarget) e.currentTarget.style.cursor = 'grab';
            return;
        }
        isPanningRef.current = false;
        if (e.currentTarget) e.currentTarget.style.cursor = 'grab';
    };

    // Card drag start – called from each card's onMouseDown
    const handleCardMouseDown = (e, cardId, baseX, baseY, baseRotate) => {
        e.stopPropagation(); // prevent canvas pan
        const currentPos = cardPositions[cardId];
        draggingCardRef.current = {
            cardId,
            startMouseX: e.clientX,
            startMouseY: e.clientY,
            startCardX: currentPos ? currentPos.x : baseX,
            startCardY: currentPos ? currentPos.y : baseY,
            rotate: currentPos ? currentPos.rotate : baseRotate,
            scale: canvasScale,
        };
        setDraggingCardId(cardId);
        document.body.style.cursor = 'grabbing';
        document.body.style.userSelect = 'none';
    };
    const handleCanvasWheel = (e) => {
        e.preventDefault();
        const delta = -e.deltaY / 600;
        setCanvasScale(s => Math.min(2.5, Math.max(0.25, s + delta)));
    };
    const resetCanvas = () => { setCanvasScale(0.82); setCanvasPan({ x: 0, y: 0 }); };

    const runRound = async (userInput = null) => {
        setIsDebating(true);
        const cleanInput = (userInput ?? inputValue ?? "").toString().trim();

        if (cleanInput) {
            setHistory(prev => [...prev, { personaId: "user", text: cleanInput }]);
            setInputValue('');
        }

        try {
            const situation = (context.situation || "").trim();

            const payload = {
                situation: situation || "Start the internal debate.",
                userInput: cleanInput,
                personas: debatePersonas.map(p => ({ id: p.id, name: p.name })),
                sessionId: sessionId,
                userId: user?.id || "",
                language: language || detectLang(cleanInput || situation),
                moderator: followUpMode,
                webSearch: webSearchMode,
                maxSpeakers: maxSpeakers
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
                        if (updated.length > 0 && updated[updated.length - 1].personaId === msg.personaId) {
                            updated[updated.length - 1] = { ...msg };
                        }
                        return updated;
                    });
                },
                onOptions: (opts) => {
                    setOptions(Array.isArray(opts) ? opts : []);
                }
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
                console.warn('stream failed; fallback to non-stream', streamErr);
                const data = await fetchLifeeDecision(payload);
                if (data?.needsVerification) { setVerifyError(''); setShowVerify(true); return; }
                if (data?.needsPayment) { setCredits(data.balance || 0); setShowPaywall(true); return; }
                if (Array.isArray(data?.messages)) for (const m of data.messages) await handlers.onMessage(m);
                if (Array.isArray(data?.options)) handlers.onOptions(data.options);
                if (data?.sessionId) setSessionId(data.sessionId);
                if (typeof data?.balance === 'number') setCredits(data.balance);
            }
        } catch (e) {
            console.error(e);
            setHistory(prev => [...prev, { personaId: "system", text: `(${e?.message || 'Request failed'})` }]);
            setOptions([]);
        } finally {
            setIsDebating(false);
            // 每轮结束后尝试提取档案（后端判断是否够 5 条新用户消息）
            fireExtractMemory(sessionIdRef.current);
        }
    };

    const copyText = (text) => { copyToClipboard(text); };

    const quoteText = (text, name) => {
        const quote = `"${text}" — ${name}\n\n`;
        setInputValue(prev => quote + prev);
        inputFieldRef.current?.focus();
    };

    const openTarotForDecision = (decision) => {
        setTarotDecision((decision || '').trim());
        setTarotModalOpen(true);
    };

    const handleInterpretTarot = async (cards) => {
        if (!tarotMasterPersona) return;
        const focus = tarotDecision || (context?.situation || '').trim() || 'this decision';
        const drawnCards = Array.isArray(cards) ? cards : [];
        const drawn = drawnCards.map(card => card.name).join(', ');
        setTarotModalOpen(false);
        const spreadPrompt = `Read a three-card tarot spread for this decision: "${focus}". Cards drawn: ${drawn}. Interpret them in this order: present tension, hidden influence, likely transformation. Keep the reading grounded in the decision and end with one concrete next step.`;
        const spreadSummary = `[Tarot spread for "${focus}"] ${drawn}`;
        setIsDebating(true);
        setHistory(prev => [...prev, { personaId: 'user', text: spreadSummary }]);
        try {
            const contextBlock = buildContextBlock();
            const situation = (context.situation || "").trim();
            const finalSituation = contextBlock
                ? `Context:\n${contextBlock}\n\nUser situation:\n${situation || "Start the internal debate."}\n\nDecision for tarot reading:\n${focus}`
                : `${situation || "Start the internal debate."}\n\nDecision for tarot reading:\n${focus}`;
            const payload = {
                situation: finalSituation,
                userInput: spreadPrompt,
                personas: [{ id: tarotMasterPersona.id, name: tarotMasterPersona.name, knowledge: tarotMasterPersona.knowledge || '' }],
                context: contextBlock
            };
            const handlers = {
                onMessage: async (msg) => {
                    setHistory(prev => [...prev, msg]);
                },
                onOptions: () => {}
            };
            try {
                await fetchLifeeDecisionStream(payload, handlers);
            } catch (streamErr) {
                console.warn('tarot stream failed; fallback', streamErr);
                await fetchLifeeDecisionProgressive(payload, handlers);
            }
        } catch (e) {
            console.error(e);
            setHistory(prev => [...prev, { personaId: "system", text: `(${e?.message || 'Tarot reading failed'})` }]);
        } finally {
            setIsDebating(false);
        }
    };

    const autoStartedRef = useRef(false);
    useEffect(() => {
        if (autoStartedRef.current) return;
        if (!debatePersonas?.length) return;
        const initial = (context?.situation || '').trim();
        if (!initial) return;
        autoStartedRef.current = true;
        runRound(initial);
    }, [debatePersonas?.length]);

    // ── Canvas panel ──────────────────────────────────────────────────────────
    const CanvasPanel = () => (
        <div className="flex flex-col h-full">
            {/* Canvas toolbar */}
            <div className="px-4 py-3 flex items-center justify-between border-b border-[#F0EDEA] bg-white shrink-0">
                <span className="text-[9px] font-black uppercase tracking-[0.3em] text-[#5D576B]/40">VOICE MAP</span>
                <div className="flex items-center gap-1.5">
                    <button
                        onClick={() => setCanvasScale(s => Math.min(2.5, s + 0.15))}
                        className="w-6 h-6 rounded-full bg-[#FDFBF7] border border-[#E8E6E0] text-sm font-bold flex items-center justify-center hover:border-blue-brand transition-all"
                    >+</button>
                    <span className="text-[9px] font-bold text-[#5D576B]/40 w-8 text-center">{Math.round(canvasScale * 100)}%</span>
                    <button
                        onClick={() => setCanvasScale(s => Math.max(0.25, s - 0.15))}
                        className="w-6 h-6 rounded-full bg-[#FDFBF7] border border-[#E8E6E0] text-sm font-bold flex items-center justify-center hover:border-blue-brand transition-all"
                    >−</button>
                    <button
                        onClick={resetCanvas}
                        className="w-6 h-6 rounded-full bg-[#FDFBF7] border border-[#E8E6E0] text-[9px] flex items-center justify-center hover:border-blue-brand transition-all"
                        title="Reset view"
                    ><Icon name="RotateCcw" size={10} /></button>
                </div>
            </div>

            {/* Pannable canvas */}
            <div
                className="flex-1 overflow-hidden cursor-grab select-none relative"
                style={{
                    backgroundImage: 'radial-gradient(circle, #C8C5BE 1px, transparent 1px)',
                    backgroundSize: '22px 22px',
                    backgroundColor: '#F5F4F0'
                }}
                onMouseDown={handleCanvasMouseDown}
                onMouseMove={handleCanvasMouseMove}
                onMouseUp={handleCanvasMouseUp}
                onMouseLeave={handleCanvasMouseUp}
                onWheel={handleCanvasWheel}
            >
                {/* World transform */}
                <div
                    style={{
                        transform: `translate(${canvasPan.x + 20}px, ${canvasPan.y + 20}px) scale(${canvasScale})`,
                        transformOrigin: '0 0',
                        width: '1000px',
                        height: '1000px',
                        position: 'relative',
                        pointerEvents: 'none'
                    }}
                >
                    {/* Section label */}
                    <div style={{ position: 'absolute', left: 30, top: 0 }}
                        className="text-[10px] font-black uppercase tracking-[0.4em] text-[#1A1A1A]/20">
                        VOICE ARCHIVE
                    </div>

                    {/* Persona cards */}
                    {debatePersonas.map((persona, idx) => {
                        const basePos = CANVAS_CARD_POSITIONS[idx % CANVAS_CARD_POSITIONS.length];
                        const overridePos = cardPositions[persona.id];
                        const pos = overridePos
                            ? overridePos
                            : { x: basePos.x, y: basePos.y + 28, rotate: basePos.rotate };
                        const msgs = personaSummaries[persona.id] || [];
                        const recentMsgs = msgs.slice(-3);
                        const hasContent = msgs.length > 0;
                        const isDraggingThis = draggingCardId === persona.id;
                        return (
                            <div
                                key={persona.id}
                                onMouseDown={(e) => handleCardMouseDown(e, persona.id, pos.x, pos.y, pos.rotate)}
                                style={{
                                    position: 'absolute',
                                    left: pos.x,
                                    top: pos.y,
                                    width: 255,
                                    transform: `rotate(${pos.rotate}deg)`,
                                    boxShadow: isDraggingThis
                                        ? '0 20px 60px rgba(0,0,0,0.18), 0 4px 12px rgba(0,0,0,0.10)'
                                        : hasContent
                                        ? '0 8px 32px rgba(0,0,0,0.10), 0 1px 4px rgba(0,0,0,0.06)'
                                        : '0 2px 8px rgba(0,0,0,0.06)',
                                    borderRadius: 20,
                                    background: '#fff',
                                    border: `1px solid ${isDraggingThis ? '#98A6D4' : '#F0EDEA'}`,
                                    overflow: 'hidden',
                                    pointerEvents: 'auto',
                                    cursor: isDraggingThis ? 'grabbing' : 'grab',
                                    zIndex: isDraggingThis ? 100 : 1,
                                    transition: isDraggingThis ? 'box-shadow 0.1s, border-color 0.1s' : 'box-shadow 0.2s',
                                    userSelect: 'none',
                                }}
                            >
                                {/* Card header */}
                                <div style={{ padding: '14px 16px 12px', borderBottom: '1px solid #F5F4F0', display: 'flex', alignItems: 'center', gap: 10 }}>
                                    <div style={{ width: 32, height: 32, borderRadius: '50%', background: '#FDFBF7', border: '1px solid #F0EDEA', overflow: 'hidden', flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                        <AvatarDisplay avatar={persona.avatar} className="w-full h-full text-base" />
                                    </div>
                                    <div style={{ minWidth: 0, flex: 1 }}>
                                        <div style={{ fontSize: 9, fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.2em', color: '#1A1A1A', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{persona.name}</div>
                                        <div style={{ fontSize: 7.5, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em', color: '#98A6D4', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{persona.role}</div>
                                    </div>
                                    <div style={{ fontSize: 9, fontWeight: 900, color: '#1A1A1A', opacity: 0.15, flexShrink: 0 }}>{msgs.length || '—'}</div>
                                </div>

                                {/* Card body – summary or recent messages */}
                                <div style={{ padding: '12px 16px', minHeight: 72, display: 'flex', flexDirection: 'column', gap: 8 }}>
                                    {summaryLoading ? (
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                            <div style={{ width: 12, height: 12, border: '2px solid #98A6D430', borderTopColor: '#98A6D4', borderRadius: '50%', animation: 'spin 1s linear infinite' }}></div>
                                            <span style={{ fontSize: 9, color: '#1A1A1A', opacity: 0.35 }}>Summarizing…</span>
                                        </div>
                                    ) : summaryData[persona.id] ? (
                                        <div style={{
                                            fontSize: 10,
                                            lineHeight: 1.7,
                                            color: '#1A1A1A',
                                            opacity: 0.8,
                                            borderLeft: '2px solid #98A6D4',
                                            paddingLeft: 8,
                                            background: '#F8F7FF',
                                            borderRadius: '0 8px 8px 0',
                                            padding: '8px 10px 8px 10px',
                                        }}>
                                            {summaryData[persona.id]}
                                        </div>
                                    ) : recentMsgs.length === 0 ? (
                                        <div style={{ fontSize: 9.5, fontStyle: 'italic', color: '#1A1A1A', opacity: 0.18 }}>Waiting to speak…</div>
                                    ) : (
                                        recentMsgs.map((msg, i) => {
                                            const isLatest = i === recentMsgs.length - 1;
                                            return (
                                                <div key={i} style={{
                                                    fontSize: 9.5,
                                                    fontStyle: 'italic',
                                                    lineHeight: 1.6,
                                                    color: '#1A1A1A',
                                                    opacity: isLatest ? 0.72 : 0.25,
                                                    borderLeft: `2px solid ${isLatest ? '#98A6D4' : '#E8E6E0'}`,
                                                    paddingLeft: 8
                                                }}>
                                                    {(msg || '').slice(0, 130)}{msg.length > 130 ? '…' : ''}
                                                </div>
                                            );
                                        })
                                    )}
                                </div>

                                {/* Card footer */}
                                <div style={{ padding: '8px 16px 10px', borderTop: '1px solid #F5F4F0', background: '#FDFBF7' }}>
                                    <div style={{ fontSize: 7.5, textTransform: 'uppercase', fontWeight: 900, letterSpacing: '0.2em', color: '#1A1A1A', opacity: 0.18, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                        {persona.worldview ? `"${(persona.worldview || '').slice(0, 45)}"` : persona.category || ''}
                                    </div>
                                </div>
                            </div>
                        );
                    })}

                    {/* User node – appears after first user message */}
                    {history.some(m => m.personaId === 'user') && (() => {
                        const userMsgs = history.filter(m => m.personaId === 'user');
                        const lastMsg = userMsgs[userMsgs.length - 1];
                        const idx = debatePersonas.length;
                        const basePos = CANVAS_CARD_POSITIONS[idx % CANVAS_CARD_POSITIONS.length];
                        const overridePos = cardPositions['user'];
                        const pos = overridePos
                            ? overridePos
                            : { x: basePos.x, y: basePos.y + 28, rotate: basePos.rotate };
                        const isDraggingThis = draggingCardId === 'user';
                        return (
                            <div
                                key="user-node"
                                onMouseDown={(e) => handleCardMouseDown(e, 'user', pos.x, pos.y, pos.rotate)}
                                style={{
                                    position: 'absolute',
                                    left: pos.x,
                                    top: pos.y,
                                    width: 220,
                                    transform: `rotate(${pos.rotate}deg)`,
                                    boxShadow: isDraggingThis
                                        ? '0 20px 60px rgba(152,166,212,0.45)'
                                        : '0 8px 32px rgba(152,166,212,0.25)',
                                    borderRadius: 20,
                                    background: '#98A6D4',
                                    overflow: 'hidden',
                                    pointerEvents: 'auto',
                                    cursor: isDraggingThis ? 'grabbing' : 'grab',
                                    zIndex: isDraggingThis ? 100 : 1,
                                    transition: isDraggingThis ? 'box-shadow 0.1s' : 'box-shadow 0.2s',
                                    userSelect: 'none',
                                }}
                            >
                                <div style={{ padding: '14px 16px 12px', display: 'flex', alignItems: 'center', gap: 10, borderBottom: '1px solid rgba(255,255,255,0.15)' }}>
                                    <div style={{ width: 32, height: 32, borderRadius: '50%', background: 'rgba(255,255,255,0.3)', overflow: 'hidden', flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                        <AvatarDisplay avatar={userAvatar || '🙂'} className="w-full h-full text-base" />
                                    </div>
                                    <div>
                                        <div style={{ fontSize: 9, fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.2em', color: '#fff' }}>YOU</div>
                                        <div style={{ fontSize: 7.5, fontWeight: 700, color: 'rgba(255,255,255,0.6)', letterSpacing: '0.1em' }}>{userMsgs.length} messages</div>
                                    </div>
                                </div>
                                <div style={{ padding: '12px 16px' }}>
                                    <div style={{ fontSize: 9.5, fontStyle: 'italic', color: '#fff', opacity: 0.85, lineHeight: 1.6, borderLeft: '2px solid rgba(255,255,255,0.4)', paddingLeft: 8 }}>
                                        {(lastMsg?.text || '').slice(0, 110)}{(lastMsg?.text || '').length > 110 ? '…' : ''}
                                    </div>
                                </div>
                            </div>
                        );
                    })()}
                </div>

                {/* Empty hint */}
                {history.length === 0 && (
                    <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                        <div className="text-center space-y-2">
                            <Icon name="LayoutDashboard" size={24} className="opacity-10 mx-auto" />
                            <p className="text-[9px] uppercase tracking-[0.3em] opacity-20">Cards appear as voices speak</p>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );

    return (
        <div className="h-[calc(100vh-64px)] flex flex-col overflow-hidden font-sans animate-in">

            {/* ── Top bar ── */}
            <div className="px-4 py-3 border-b border-[#F0EDEA] bg-white flex items-center justify-between z-10 shrink-0">
                <div className="flex -space-x-2">
                    {selectedPersonas.map(p => (
                        <div key={p.id} className="w-8 h-8 rounded-full border-2 border-white overflow-hidden shadow-sm">
                            <AvatarDisplay avatar={p.avatar} className="w-full h-full text-xs" />
                        </div>
                    ))}
                </div>
                <div className="flex items-center gap-2">
                    {/* Canvas toggle */}
                    <button
                        onClick={() => setShowCanvas(v => !v)}
                        className={`flex items-center gap-1.5 text-[10px] font-bold px-3 py-1.5 rounded-full border transition-all ${showCanvas ? 'bg-blue-brand text-white border-blue-brand' : 'border-[#E8E6E0] text-[#5D576B]/60'}`}
                    >
                        <Icon name="LayoutDashboard" size={12} />
                        MAP
                    </button>
                    <button
                        onClick={() => setView('summary')}
                        className="flex items-center gap-2 text-xs font-bold text-[#E6C6C1] px-4 py-2 border border-[#E6C6C1] rounded-full hover:bg-[#E6C6C1] hover:text-white transition-all"
                    >
                        <Icon name="PauseCircle" size={14} /> STOP & DECIDE
                    </button>
                    <button
                        disabled={history.length < 2 || summaryLoading}
                        onClick={() => {
                            // 没有新消息 → 直接显示缓存
                            if (summaryAtCountRef.current === history.length && Object.keys(summaryData).length > 0 && !summaryData._error) {
                                setShowCanvas(true);
                                return;
                            }
                            // 有 sessionId 时只发 ID（后端从 Supabase 加载），避免 Railway 代理 ~2.5KB body 限制
                            const payload = sessionId
                                ? JSON.stringify({ sessionId, language: language || 'Chinese' })
                                : JSON.stringify({
                                    messages: history
                                        .filter(m => m.personaId !== 'user' && m.personaId !== 'system' && m.personaId !== 'lifee-followup')
                                        .slice(-4)
                                        .map(m => ({ personaId: m.personaId, text: (m.text || '').slice(0, 150) })),
                                    language: language || 'Chinese',
                                });
                            setSummaryLoading(true);
                            setSummaryData({});
                            setTimeout(async () => {
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
                                        setShowCanvas(true);
                                    } else {
                                        setSummaryData({ _error: 'No summary returned' });
                                    }
                                } catch (e) {
                                    setSummaryData({ _error: e.message || 'Network error' });
                                } finally { setSummaryLoading(false); }
                            }, 300);
                        }}
                        className="flex items-center gap-2 text-xs font-bold text-blue-brand px-4 py-2 border border-blue-brand rounded-full hover:bg-blue-brand hover:text-white transition-all disabled:opacity-30"
                    >
                        <Icon name="FileText" size={14} /> {summaryLoading ? 'Summarizing...' : 'Summary'}
                    </button>
                </div>
            </div>

            {/* ── Two-column body ── */}
            <div className="flex flex-1 overflow-hidden">

                {/* LEFT: Chat panel */}
                <div className={`flex flex-col flex-1 overflow-hidden ${showCanvas ? 'hidden md:flex' : 'flex'}`}>

                    {/* Messages */}
                    <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 md:p-6 space-y-8 pb-4 no-scrollbar">
                        {history.map((m, idx) => {
                            const isUser = m.personaId === 'user';
                            const isFollowUp = m.personaId === 'lifee-followup';
                            const p = isUser
                                ? { name: 'YOU', avatar: (userAvatar || loadUserAvatar()) }
                                : isFollowUp
                                ? { name: 'LIFEE', avatar: '💬' }
                                : (selectedPersonas.find(x => x.id === m.personaId) || (window.INITIAL_PERSONAS || []).find(x => x.id === m.personaId) || (m.personaId === "system" ? { name: "SYSTEM", avatar: "⚠️" } : { name: m.personaId || 'Voice', avatar: '☁️' }));
                            return (
                                <div key={idx} className={`flex gap-4 md:gap-5 ${isUser ? 'flex-row-reverse' : 'items-start'} animate-in`}>
                                    <div className={`w-10 h-10 rounded-full border flex items-center justify-center shadow-sm shrink-0 bg-white overflow-hidden ${isUser ? 'border-blue-brand/30' : 'border-[#F0EDEA]'}`}>
                                        <AvatarDisplay avatar={p.avatar} className="w-full h-full text-2xl" />
                                    </div>
                                    <div className={`max-w-[85%] md:max-w-[75%] flex flex-col ${isUser ? 'items-end' : 'items-start'}`}>
                                        <span className="text-[10px] font-black opacity-30 tracking-widest uppercase mb-1.5">{p.name}</span>
                                        <div className={`p-4 md:p-5 rounded-[24px] text-sm shadow-sm leading-relaxed ${isUser ? 'bg-blue-brand text-white rounded-tr-none' : 'bg-white border border-[#F0EDEA] rounded-tl-none'}`}>{m.text}</div>
                                        <div className={`flex gap-4 mt-2 px-1 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
                                            <button onClick={() => copyText(m.text)} className="flex items-center gap-1.5 text-[10px] font-bold text-blue-brand/60 hover:text-blue-brand transition-colors uppercase tracking-widest"><Icon name="Copy" size={12} /> Copy</button>
                                            <button onClick={() => quoteText(m.text, p.name)} className="flex items-center gap-1.5 text-[10px] font-bold text-blue-brand/60 hover:text-blue-brand transition-colors uppercase tracking-widest"><Icon name="Quote" size={12} /> Quote</button>
                                        </div>
                                    </div>
                                </div>
                            );
                        })}
                        {isDebating && (
                            <div className="animate-pulse flex gap-4">
                                <div className="w-10 h-10 bg-slate-200 rounded-full" />
                                <div className="h-14 w-56 bg-white border rounded-3xl" />
                            </div>
                        )}
                    </div>

                    {/* Input area */}
                    <div className="px-4 md:px-6 py-4 bg-gradient-to-t from-[#FDFBF7] via-[#FDFBF7] to-transparent shrink-0 border-t border-[#F5F4F0]">
                        <div className="space-y-3">
                            {/* Option buttons */}
                            {options.length > 0 && !isDebating && (
                                <div className="flex flex-wrap justify-center gap-2 animate-in">
                                    {options.map((opt, i) => (
                                        <div key={i} className="flex items-center gap-2">
                                            <button onClick={() => runRound(opt)} className="px-4 py-2 bg-white/90 border border-blue-brand/20 rounded-full text-xs font-bold hover:bg-blue-brand hover:text-white transition-all shadow-sm">{opt}</button>
                                            {hasTarotMaster && (
                                                <button type="button" onClick={() => openTarotForDecision(opt)} className="w-8 h-8 rounded-full bg-white border border-blue-brand/20 flex items-center justify-center text-blue-brand hover:bg-blue-brand hover:text-white transition-all shadow-sm" title="Draw tarot for this decision">
                                                    <Icon name="Moon" size={13} />
                                                </button>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            )}

                            {/* Controls row */}
                            <div className="flex items-center justify-center gap-3 flex-wrap">
                                {credits !== null && <span className="text-xs text-neutral-400">Credits: {credits}</span>}
                                <button onClick={() => setFollowUpMode(!followUpMode)} className={`text-xs px-2 py-1 rounded border transition-all ${followUpMode ? 'bg-blue-brand text-white border-blue-brand' : 'text-neutral-400 border-neutral-200 hover:border-blue-brand'}`}>
                                    {followUpMode ? '追问 ON' : '追问'}
                                </button>
                                <button onClick={() => setWebSearchMode(!webSearchMode)} className={`text-xs px-2 py-1 rounded border transition-all ${webSearchMode ? 'bg-blue-brand text-white border-blue-brand' : 'text-neutral-400 border-neutral-200 hover:border-blue-brand'}`}>
                                    {webSearchMode ? '🔍 ON' : '🔍'}
                                </button>
                                {debatePersonas.length > 1 && (
                                    <select value={maxSpeakers} onChange={(e) => setMaxSpeakers(Number(e.target.value))} className="text-xs text-neutral-400 bg-transparent border border-neutral-200 rounded px-2 py-1">
                                        <option value={0}>All speak</option>
                                        {Array.from({length: debatePersonas.length - 1}, (_, i) => (
                                            <option key={i+1} value={i+1}>{i+1} speak</option>
                                        ))}
                                    </select>
                                )}
                                <select value={language} onChange={(e) => { setLanguage(e.target.value); localStorage.setItem('lifee_lang', e.target.value); }} className="text-xs text-neutral-400 bg-transparent border border-neutral-200 rounded px-2 py-1">
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

                            {/* Input row */}
                            <div className="flex gap-3">
                                <button disabled={isDebating} onClick={() => runRound(null)} className="hidden md:block shrink-0 px-6 py-4 bg-blue-brand text-white rounded-full font-bold shadow-xl transition-all hover:translate-y-[-2px] disabled:opacity-50 uppercase tracking-widest text-[10px]">STAY SILENT</button>
                                {hasTarotMaster && (
                                    <button type="button" disabled={isDebating} onClick={() => openTarotForDecision((inputValue || '').trim() || (context?.situation || '').trim())} className="hidden md:flex w-12 h-12 shrink-0 self-end rounded-full bg-white border border-[#E8E6E0] items-center justify-center text-blue-brand shadow-xl hover:border-blue-brand/30 transition-all disabled:opacity-50" title="Open tarot spread">
                                        <Icon name="Moon" size={18} />
                                    </button>
                                )}
                                <div className="relative flex-1">
                                    <textarea
                                        ref={inputFieldRef}
                                        maxLength={1000}
                                        rows={2}
                                        placeholder="..."
                                        disabled={isDebating}
                                        style={{height: 'auto'}}
                                        className="w-full min-h-[52px] max-h-[140px] bg-white rounded-2xl shadow-xl border-2 border-transparent focus:border-blue-brand transition-all duration-300 px-5 py-3 focus:outline-none text-sm resize-none overflow-y-auto leading-relaxed"
                                        value={inputValue}
                                        onChange={(e) => { setInputValue(e.target.value); e.target.style.height = 'auto'; e.target.style.height = Math.min(e.target.scrollHeight, 140) + 'px'; }}
                                        onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey && inputValue) { e.preventDefault(); runRound(); } }}
                                    />
                                    {inputValue.length > 400 && <div className="absolute bottom-1 right-5 text-[10px] text-neutral-300">{inputValue.length}/1000</div>}
                                </div>
                                {extractStatus === 'done' && (
                                    <div className="flex items-center gap-1.5 px-2 py-1 text-[10px] opacity-50" style={{ transition: 'opacity 0.3s' }}>
                                        <Icon name="BookUser" size={12} />
                                        Profile updated
                                    </div>
                                )}
                            </div>
                            {hasTarotMaster && (
                                <div className="md:hidden flex justify-center">
                                    <button type="button" disabled={isDebating} onClick={() => openTarotForDecision((inputValue || '').trim() || (context?.situation || '').trim())} className="px-5 py-3 rounded-full bg-white border border-[#E8E6E0] text-[10px] font-black uppercase tracking-[0.25em] text-blue-brand shadow-sm disabled:opacity-50">Draw Tarot</button>
                                </div>
                            )}
                        </div>
                    </div>
                </div>

                {/* ── Resize handle (desktop only) ── */}
                <div
                    className={`${showCanvas ? 'hidden md:flex' : 'hidden'} shrink-0 items-center justify-center relative resize-handle-root`}
                    style={{ width: 8, cursor: 'col-resize', zIndex: 20 }}
                    onMouseDown={startResize}
                >
                    {/* Track line */}
                    <div
                        className="resize-handle-line w-px h-full transition-colors duration-150"
                        style={{ background: isResizing ? '#98A6D4' : '#E8E6E0' }}
                    />
                    {/* Arrow pill */}
                    <div
                        className="resize-handle-pill absolute flex items-center justify-center rounded-full shadow-lg pointer-events-none select-none transition-all duration-150"
                        style={{
                            width: 28,
                            height: 28,
                            background: isResizing ? '#98A6D4' : '#fff',
                            border: `1.5px solid ${isResizing ? '#98A6D4' : '#D1CEC7'}`,
                            top: '50%',
                            left: '50%',
                            marginTop: -14,
                            marginLeft: -14,
                            opacity: isResizing ? 1 : 0,
                            transform: isResizing ? 'scale(1)' : 'scale(0.7)',
                        }}
                    >
                        <svg width="16" height="8" viewBox="0 0 16 8" fill="none">
                            <path d="M4.5 4H1M1 4L3 2M1 4L3 6" stroke={isResizing ? '#fff' : '#98A6D4'} strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
                            <path d="M11.5 4H15M15 4L13 2M15 4L13 6" stroke={isResizing ? '#fff' : '#98A6D4'} strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
                        </svg>
                    </div>
                </div>
                <style>{`
                    .resize-handle-root:hover .resize-handle-line { background: #98A6D4 !important; }
                    .resize-handle-root:hover .resize-handle-pill { opacity: 1 !important; transform: scale(1) !important; }
                    @keyframes spin { to { transform: rotate(360deg); } }
                    @keyframes slideInRight { from { transform: translateX(100%); } to { transform: translateX(0); } }
                `}</style>

                {/* RIGHT: Visual canvas panel – always visible on md+, toggled on mobile */}
                <div
                    className={`${showCanvas ? 'flex' : 'hidden'} shrink-0 flex-col overflow-hidden`}
                    style={{ width: canvasWidth }}
                >
                    <CanvasPanel />
                </div>
            </div>

            {/* ── Modals ── */}
            <TarotReadingModal
                isOpen={tarotModalOpen}
                decisionLabel={tarotDecision}
                onClose={() => setTarotModalOpen(false)}
                onInterpret={handleInterpretTarot}
            />
            {showVerify && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
                    <div className="bg-white rounded-2xl p-8 max-w-sm mx-4 shadow-2xl text-center">
                        <div className="text-4xl mb-4">🛡️</div>
                        <h3 className="text-lg font-bold mb-2">Please verify you're human</h3>
                        <div ref={verifyRef} className="flex justify-center mb-4"></div>
                        {(() => {
                            setTimeout(() => {
                                if (verifyRef.current && window.turnstile && !verifyWidgetRef.current) {
                                    verifyWidgetRef.current = window.turnstile.render(verifyRef.current, {
                                        sitekey: TURNSTILE_SITEKEY,
                                        callback: async (token) => {
                                            const result = await verifyHumanTokenWithServer(token);
                                            if (result.ok) {
                                                setVerifyError('');
                                                setShowVerify(false);
                                                verifyWidgetRef.current = null;
                                            } else {
                                                setVerifyError(result.message || 'Human verification failed. Please retry.');
                                            }
                                        },
                                        theme: 'light',
                                    });
                                }
                            }, 100);
                            return null;
                        })()}
                        {verifyError && <div className="text-xs text-[#C97A7A] bg-[#FDF1F1] border border-[#F7D7D7] px-4 py-3 rounded-2xl mb-4">{verifyError}</div>}
                        <button onClick={() => setShowVerify(false)} className="text-sm text-neutral-400 hover:text-neutral-600">Cancel</button>
                    </div>
                </div>
            )}
            {/* Summary error toast */}
            {summaryData._error && (
                <div className="fixed top-20 right-4 z-50 text-xs text-[#C97A7A] bg-[#FDF1F1] border border-[#F7D7D7] px-4 py-3 rounded-2xl shadow-lg animate-in" style={{animation: 'slideInRight 0.3s ease-out'}}>
                    {summaryData._error}
                    <button onClick={() => setSummaryData({})} className="ml-2 opacity-40 hover:opacity-100">✕</button>
                </div>
            )}
            {showPaywall && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
                    <div className="bg-white rounded-2xl p-8 max-w-sm mx-4 shadow-2xl text-center">
                        <div className="text-4xl mb-4">🔒</div>
                        <h3 className="text-lg font-bold mb-2">Credits Used Up</h3>
                        <p className="text-sm text-neutral-500 mb-6">Enter a redeem code to continue the conversation.</p>
                        <input type="text" placeholder="Enter redeem code" value={redeemCode} onChange={(e) => setRedeemCode(e.target.value)} className="w-full px-4 py-3 border rounded-lg mb-4 text-center text-lg tracking-widest uppercase" />
                        <button
                            onClick={async () => {
                                const res = await fetch('/credits/redeem', {
                                    method: 'POST',
                                    headers: { 'Content-Type': 'application/json' },
                                    credentials: 'include',
                                    body: JSON.stringify({ code: redeemCode, userId: user?.id || "" })
                                }).then(r => r.json());
                                if (res.ok) { setCredits(res.balance); setShowPaywall(false); setRedeemCode(''); }
                                else alert(res.message || 'Invalid code');
                            }}
                            className="w-full py-3 bg-blue-brand text-white rounded-lg font-bold"
                        >Redeem</button>
                        <button onClick={() => setShowPaywall(false)} className="mt-3 text-sm text-neutral-400">Cancel</button>
                    </div>
                </div>
            )}
        </div>
    );
};

const CommunityView = ({ communityTab, setCommunityTab, favoriteIds, onToggleFavorite }) => (
    <div className="p-6 md:p-12 max-w-[1200px] mx-auto animate-in space-y-12">
        <div className="flex flex-col items-center space-y-6">
            <h2 className="text-3xl md:text-5xl font-serif italic tracking-tight text-center">Community Archives</h2>
            <div className="flex justify-center px-4 w-full"><div className="inline-flex bg-white/60 backdrop-blur-md p-1.5 rounded-full border-2 border-white shadow-lg whitespace-nowrap">{['DEBATE', 'PERSONA'].map(tab => <button key={tab} onClick={() => setCommunityTab(tab)} className={`px-8 md:px-12 py-2.5 md:py-3 rounded-full text-[10px] font-black uppercase tracking-[0.2em] transition-all duration-300 ${communityTab === tab ? 'bg-blue-brand text-white shadow-lg scale-105' : 'text-[#5D576B]/40 hover:text-blue-brand'}`}>{tab}</button>)}</div></div>
        </div>
        {communityTab === 'DEBATE' ? (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 md:gap-8 animate-in">{[1, 2, 3, 4].map(i => <div key={i} className="bg-white p-8 rounded-[48px] border border-[#E8E6E0] shadow-sm hover:shadow-xl hover:-translate-y-1 transition-all cursor-pointer group"><div className="flex items-center gap-5 mb-6"><div className="w-12 h-12 rounded-2xl bg-[#FDFBF7] flex items-center justify-center text-2xl group-hover:scale-110 transition-transform">🎭</div><div><h4 className="font-bold text-lg text-[#1A1A1A]">Shared Reflection #{i}204</h4><p className="text-[10px] uppercase font-bold text-blue-brand tracking-widest">3 Voices Engaging</p></div></div><p className="text-sm italic opacity-60 leading-relaxed line-clamp-2">"Exploring the complex tension between the safety of the known and the fear of the unknown during graduation..."</p><div className="mt-8 pt-6 border-t border-slate-50 flex justify-between items-center text-[10px] font-black uppercase tracking-widest opacity-30"><span>Reflected 2 days ago</span><span className="group-hover:text-blue-brand transition-colors">Enter Archive →</span></div></div>)}</div>
        ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6 md:gap-8 animate-in">
                {INITIAL_PERSONAS.map(p => {
                    const isFav = favoriteIds?.includes(p.id);
                    return (
                        <div key={p.id} className="relative p-6 md:p-8 bg-white rounded-[40px] shadow-xl border-2 border-white/20 hover:scale-[1.03] transition-all flex flex-col aspect-[3/4] overflow-hidden group">
                            <button
                                onClick={(e) => { e.stopPropagation(); onToggleFavorite?.(p); }}
                                className={`absolute top-5 right-5 w-9 h-9 rounded-full border flex items-center justify-center z-20 transition-all ${isFav ? 'bg-blue-brand text-white border-blue-brand' : 'bg-white border-[#E8E6E0] text-[#5D576B]/40 hover:text-blue-brand'}`}
                                title={isFav ? 'Remove from favorites' : 'Add to My Personas'}
                            >
                                <Icon name="Star" size={16} />
                            </button>
                            <div className="mb-6 flex items-center justify-center w-14 h-14 md:w-18 md:h-18 relative overflow-hidden group-hover:scale-110 transition-transform origin-center">
                                <div className="absolute inset-0 bg-slate-50 rounded-[24px] transform rotate-6 scale-90 opacity-40 group-hover:bg-blue-brand/10 transition-colors" />
                                <AvatarDisplay avatar={p.avatar} className="w-10 h-10 md:w-14 md:h-14 text-4xl md:text-5xl relative z-10" />
                            </div>
                            <div className="mt-auto text-left space-y-2">
                                <h4 className="font-black text-xl md:text-2xl text-[#1A1A1A] tracking-tighter uppercase italic">{p.name}</h4>
                                <p className="text-[7px] md:text-[8px] uppercase font-black tracking-widest text-blue-brand/80">COMMUNITY CREATION</p>
                                <p className="text-[10px] md:text-xs italic opacity-40 leading-relaxed line-clamp-2">"{p.worldview}"</p>
                            </div>
                        </div>
                    );
                })}
            </div>
        )}
    </div>
);

window.DebateArena = DebateArena;
window.CommunityView = CommunityView;
