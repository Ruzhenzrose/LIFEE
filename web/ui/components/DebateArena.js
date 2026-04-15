const { useState, useEffect, useRef } = React;
const { Icon, AvatarDisplay } = window;
const { TarotReadingModal, TAROT_DECK } = window;

const DebateArena = ({
    context,
    selectedPersonas,
    setView,
    ensureSession,
    persistMessage,
    buildContextBlock,
    userAvatar,
    user,
    initialMessages = []
}) => {
    const [history, setHistory] = useState(initialMessages);
    const [options, setOptions] = useState([]);
    const [isDebating, setIsDebating] = useState(false);
    const [sessionId, setSessionId] = useState("");
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
    const [language, setLanguage] = useState(() => localStorage.getItem('lifee_lang') || '');
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

    useEffect(() => { if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight; }, [history]);

    // 页面加载时拉取余额
    useEffect(() => {
        const url = user?.id ? `/credits?userId=${user.id}` : '/credits';
        fetch(url, { credentials: 'include' }).then(r => r.json()).then(d => {
            if (typeof d.balance === 'number') setCredits(d.balance);
        }).catch(() => {});
    }, [user]);

    const runRound = async (userInput = null) => {
        setIsDebating(true);
        const cleanInput = (userInput ?? inputValue ?? "").toString().trim();

        if (cleanInput) {
            setHistory(prev => [...prev, { personaId: "user", text: cleanInput }]);
            await persistMessage('user', cleanInput);
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
                language: language || detectLang(cleanInput),
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
                    if (msg.text) {
                        const role = msg.personaId === 'system' ? 'system' : 'assistant';
                        await persistMessage(role, msg.text);
                    }
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

            // 先检查余额，不足直接弹付费墙
            if (credits !== null && credits <= 0) {
                setShowPaywall(true);
                setIsDebating(false);
                return;
            }

            // 流式模式：逐 chunk 实时显示
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
                if (data?.needsVerification) {
                    setVerifyError('');
                    setShowVerify(true);
                    return;
                }
                if (data?.needsPayment) {
                    setCredits(data.balance || 0);
                    setShowPaywall(true);
                    return;
                }
                if (Array.isArray(data?.messages)) {
                    for (const m of data.messages) await handlers.onMessage(m);
                }
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
        await persistMessage('user', spreadSummary);

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
                    const role = msg.personaId === 'system' ? 'system' : 'assistant';
                    await persistMessage(role, msg.text || '');
                },
                onOptions: () => {}
            };

            try {
                await fetchLifeeDecisionStream(payload, handlers);
            } catch (streamErr) {
                console.warn('tarot stream failed; fallback to progressive JSON calls', streamErr);
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

    return (
        <div className="h-[calc(100vh-64px)] flex flex-col overflow-hidden font-sans animate-in">
            <div className="p-4 border-b border-[#F0EDEA] bg-white flex items-center justify-between z-10">
                <div className="flex -space-x-2">{selectedPersonas.map(p => <div key={p.id} className="w-8 h-8 rounded-full border-2 border-white overflow-hidden shadow-sm"><AvatarDisplay avatar={p.avatar} className="w-full h-full text-xs" /></div>)}</div>
                <button onClick={() => setView('summary')} className="flex items-center gap-2 text-xs font-bold text-[#E6C6C1] px-4 py-2 border border-[#E6C6C1] rounded-full hover:bg-[#E6C6C1] hover:text-white transition-all"><Icon name="PauseCircle" size={14} /> STOP & DECIDE</button>
            </div>
            <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 md:p-8 space-y-10 pb-64 no-scrollbar">
                {history.map((m, idx) => {
                    const isUser = m.personaId === 'user';
                    const p = isUser
                        ? { name: 'YOU', avatar: (userAvatar || loadUserAvatar()) }
                        : (selectedPersonas.find(x => x.id === m.personaId) || (window.INITIAL_PERSONAS || []).find(x => x.id === m.personaId) || (m.personaId === "system" ? { name: "SYSTEM", avatar: "⚠️" } : { name: m.personaId || 'Voice', avatar: '☁️' }));
                    return (
                        <div key={idx} className={`flex gap-4 md:gap-5 ${isUser ? 'flex-row-reverse' : 'items-start'} animate-in`}>
                            <div className={`w-10 h-10 md:w-11 md:h-11 rounded-full border flex items-center justify-center shadow-sm shrink-0 bg-white overflow-hidden ${isUser ? 'border-blue-brand/30' : 'border-[#F0EDEA]'}`}><AvatarDisplay avatar={p.avatar} className="w-full h-full text-2xl" /></div>
                            <div className={`max-w-[85%] md:max-w-[70%] flex flex-col ${isUser ? 'items-end' : 'items-start'}`}>
                                <span className="text-[10px] font-black opacity-30 tracking-widest uppercase mb-1.5">{p.name}</span>
                                <div className={`p-4 md:p-5 rounded-[24px] md:rounded-[28px] text-sm shadow-sm transition-all duration-300 leading-relaxed ${isUser ? 'bg-blue-brand text-white rounded-tr-none' : 'bg-white border border-[#F0EDEA] rounded-tl-none'}`}>{m.text}</div>
                                <div className={`flex gap-4 mt-2 px-1 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
                                    <button onClick={() => copyText(m.text)} className="flex items-center gap-1.5 text-[10px] font-bold text-blue-brand/60 hover:text-blue-brand transition-colors uppercase tracking-widest"><Icon name="Copy" size={12} /> Copy</button>
                                    <button onClick={() => quoteText(m.text, p.name)} className="flex items-center gap-1.5 text-[10px] font-bold text-blue-brand/60 hover:text-blue-brand transition-colors uppercase tracking-widest"><Icon name="Quote" size={12} /> Quote</button>
                                </div>
                            </div>
                        </div>
                    );
                })}
                {isDebating && <div className="animate-pulse flex gap-4"><div className="w-10 h-10 bg-slate-200 rounded-full" /><div className="h-14 w-64 bg-white border rounded-3xl" /></div>}
            </div>
            <div className="p-4 md:p-8 bg-gradient-to-t from-[#FDFBF7] via-[#FDFBF7] to-transparent">
                <div className="max-w-3xl mx-auto space-y-4">
                    {options.length > 0 && !isDebating && (
                        <div className="flex flex-wrap justify-center gap-2 mb-2 animate-in">
                            {options.map((opt, i) => (
                                <div key={i} className="flex items-center gap-2">
                                    <button key={i} onClick={() => runRound(opt)} className="px-4 py-2 bg-white/90 border border-blue-brand/20 rounded-full text-xs font-bold hover:bg-blue-brand hover:text-white transition-all shadow-sm">{opt}</button>
                                    {hasTarotMaster && (
                                        <button
                                            type="button"
                                            onClick={() => openTarotForDecision(opt)}
                                            className="w-9 h-9 rounded-full bg-white border border-blue-brand/20 flex items-center justify-center text-blue-brand hover:bg-blue-brand hover:text-white transition-all shadow-sm"
                                            title="Draw tarot for this decision"
                                        >
                                            <Icon name="Moon" size={14} />
                                        </button>
                                    )}
                                </div>
                            ))}
                        </div>
                    )}
                    <div className="flex items-center justify-center gap-4 mb-2">
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
                    <div className="flex gap-3">
                        <button disabled={isDebating} onClick={() => runRound(null)} className="hidden md:block flex-1 py-5 bg-blue-brand text-white rounded-full font-bold shadow-xl transition-all hover:translate-y-[-2px] disabled:opacity-50 uppercase tracking-widest text-xs">STAY SILENT</button>
                        {hasTarotMaster && (
                            <button
                                type="button"
                                disabled={isDebating}
                                onClick={() => openTarotForDecision((inputValue || '').trim() || (context?.situation || '').trim())}
                                className="hidden md:flex w-14 h-14 shrink-0 rounded-full bg-white border border-[#E8E6E0] items-center justify-center text-blue-brand shadow-xl hover:border-blue-brand/30 transition-all disabled:opacity-50"
                                title="Open tarot spread"
                            >
                                <Icon name="Moon" size={20} />
                            </button>
                        )}
                        <div className="relative flex-[3] group">
                            <textarea ref={inputFieldRef} maxLength={1000} rows={2} placeholder="..." disabled={isDebating} style={{height: 'auto'}} className="w-full min-h-[56px] max-h-[150px] bg-white rounded-2xl shadow-xl border-2 border-transparent focus:border-blue-brand transition-all duration-300 px-6 md:px-8 py-3 focus:outline-none text-sm resize-none overflow-y-auto leading-relaxed" value={inputValue} onChange={(e) => { setInputValue(e.target.value); e.target.style.height = 'auto'; e.target.style.height = Math.min(e.target.scrollHeight, 150) + 'px'; }} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey && inputValue) { e.preventDefault(); runRound(); } }} />
                            {inputValue.length > 400 && <div className="absolute bottom-1 right-6 text-[10px] text-neutral-300">{inputValue.length}/1000</div>}
                        </div>
                    </div>
                    {hasTarotMaster && (
                        <div className="md:hidden flex justify-center">
                            <button
                                type="button"
                                disabled={isDebating}
                                onClick={() => openTarotForDecision((inputValue || '').trim() || (context?.situation || '').trim())}
                                className="px-5 py-3 rounded-full bg-white border border-[#E8E6E0] text-[10px] font-black uppercase tracking-[0.25em] text-blue-brand shadow-sm disabled:opacity-50"
                            >
                                Draw Tarot
                            </button>
                        </div>
                    )}
                </div>
            </div>
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
                            // 渲染 Turnstile widget
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
                        {verifyError && (
                            <div className="text-xs text-[#C97A7A] bg-[#FDF1F1] border border-[#F7D7D7] px-4 py-3 rounded-2xl mb-4">{verifyError}</div>
                        )}
                        <button onClick={() => setShowVerify(false)} className="text-sm text-neutral-400 hover:text-neutral-600">Cancel</button>
                    </div>
                </div>
            )}
            {showPaywall && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
                    <div className="bg-white rounded-2xl p-8 max-w-sm mx-4 shadow-2xl text-center">
                        <div className="text-4xl mb-4">🔒</div>
                        <h3 className="text-lg font-bold mb-2">Credits Used Up</h3>
                        <p className="text-sm text-neutral-500 mb-6">Enter a redeem code to continue the conversation.</p>
                        <input
                            type="text"
                            placeholder="Enter redeem code"
                            value={redeemCode}
                            onChange={(e) => setRedeemCode(e.target.value)}
                            className="w-full px-4 py-3 border rounded-lg mb-4 text-center text-lg tracking-widest uppercase"
                        />
                        <button
                            onClick={async () => {
                                const res = await fetch('/credits/redeem', {
                                    method: 'POST',
                                    headers: { 'Content-Type': 'application/json' },
                                    credentials: 'include',
                                    body: JSON.stringify({ code: redeemCode, userId: user?.id || "" })
                                }).then(r => r.json());
                                if (res.ok) {
                                    setCredits(res.balance);
                                    setShowPaywall(false);
                                    setRedeemCode('');
                                } else {
                                    alert(res.message || 'Invalid code');
                                }
                            }}
                            className="w-full py-3 bg-blue-brand text-white rounded-lg font-bold"
                        >
                            Redeem
                        </button>
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
                                <p className="text-[10px] md:text-xs italic opacity-40 leading-relaxed line-clamp-2">“{p.worldview}”</p>
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
