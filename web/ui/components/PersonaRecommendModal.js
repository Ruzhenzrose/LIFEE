const { useState, useEffect, useRef } = React;

// 随便抽 N 个 persona（LLM 推荐失败时的兜底）
function randomPicks(personas, n = 2) {
    const pool = (personas || []).filter(p => p && p.id);
    for (let i = pool.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [pool[i], pool[j]] = [pool[j], pool[i]];
    }
    return pool.slice(0, n);
}

// ── Skeleton card ─────────────────────────────────────────────────────────────
const SkeletonCard = () => (
    <div className="rounded-[22px] border-2 border-[#F0EDEA] bg-white p-4 flex flex-col gap-3 animate-pulse">
        <div className="w-10 h-10 rounded-full bg-[#F0EDEA]" />
        <div className="h-3 bg-[#F0EDEA] rounded-full w-3/4" />
        <div className="h-2 bg-[#F0EDEA] rounded-full w-1/2" />
        <div className="h-2 bg-[#F0EDEA] rounded-full w-full" />
    </div>
);

// ── Persona card ──────────────────────────────────────────────────────────────
const PersonaCard = ({ persona, isSelected, onToggle, isGenerated }) => {
    if (!persona || !persona.id) return null;
    const voiceText = typeof persona.voice === 'string' ? persona.voice : '';
    return (
        <button
            type="button"
            onClick={() => onToggle(persona.id)}
            className={`relative text-left rounded-[22px] p-4 border-2 transition-all duration-150 flex flex-col gap-2 ${
                isSelected
                    ? 'border-blue-brand bg-blue-brand/5 shadow-md'
                    : 'border-[#F0EDEA] bg-white hover:border-blue-brand/30 hover:shadow-sm'
            }`}
        >
            {isGenerated && (
                <span className="absolute top-2 left-3 text-[8px] uppercase tracking-widest font-black text-violet-400/80 leading-none">
                    ✦ AI
                </span>
            )}
            <div className={`absolute top-3 right-3 w-5 h-5 rounded-full border-2 flex items-center justify-center transition-all ${
                isSelected ? 'bg-blue-brand border-blue-brand' : 'border-[#D8D5D0]'
            }`}>
                {isSelected && <Icon name="Check" size={11} className="text-white" />}
            </div>

            {persona.cover_url ? (
                <div
                    className="w-10 h-10 rounded-full bg-[#F0EDEA] overflow-hidden flex-shrink-0"
                    style={{ backgroundImage: `url(${persona.cover_url})`, backgroundSize: 'cover', backgroundPosition: persona.cover_position || '50% 30%' }}
                />
            ) : (
                <div className={`w-10 h-10 rounded-full flex items-center justify-center text-xl flex-shrink-0 ${isGenerated ? 'bg-violet-50' : 'bg-[#F0EDEA]'}`}>
                    {persona.avatar || '?'}
                </div>
            )}

            <div className="min-w-0 pr-4">
                <p className="font-serif italic font-bold text-[#1A1A1A] text-sm leading-tight truncate">{persona.name || ''}</p>
                <p className="text-[9px] uppercase tracking-widest text-[#5D576B]/50 mt-0.5 leading-tight">{persona.role || ''}</p>
            </div>

            {voiceText.length > 0 && (
                <p className="text-[10px] text-[#5D576B]/60 italic leading-relaxed line-clamp-2">
                    "{voiceText.slice(0, 72)}{voiceText.length > 72 ? '…' : ''}"
                </p>
            )}
        </button>
    );
};

// ── Component ─────────────────────────────────────────────────────────────────
const PersonaRecommendModal = ({ isOpen, onClose, situation, periods, personas, selectedIds, onConfirm }) => {
    const [picks, setPicks] = useState([]);
    const [recommended, setRecommended] = useState([]);
    const [generated, setGenerated] = useState([]);
    const [loading, setLoading] = useState(false);
    const [generating, setGenerating] = useState(false);
    const abortRef = useRef(null);

    useEffect(() => {
        if (!isOpen) {
            // Cancel any in-flight requests when modal closes
            if (abortRef.current) {
                abortRef.current.abort();
                abortRef.current = null;
            }
            return;
        }

        // Reset state for fresh open
        setPicks([]);
        setRecommended([]);
        setGenerated([]);
        setLoading(true);
        setGenerating(true);

        // Create abort controller for this session
        const ctrl = new AbortController();
        abortRef.current = ctrl;
        const signal = ctrl.signal;

        // ── 1. Recommend from existing personas ──────────────────────────────
        const recPromise = fetch('/recommend-personas', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            signal,
            body: JSON.stringify({
                situation,
                periods: periods || [],
                persona_ids: (personas || []).map(p => p.id)
            })
        })
        .then(r => r.json())
        .then(data => {
            if (signal.aborted) return [];
            const ids = Array.isArray(data.ids) ? data.ids : [];
            let recs = ids.map(id => (personas || []).find(p => p.id === id)).filter(Boolean).slice(0, 2);
            if (recs.length === 0) recs = randomPicks(personas, 2);
            setRecommended(recs);
            setPicks(recs.map(p => p.id));
            setLoading(false);
            return recs;
        })
        .catch(() => {
            if (signal.aborted) return [];
            const recs = randomPicks(personas, 2);
            setRecommended(recs);
            setPicks(recs.map(p => p.id));
            setLoading(false);
            return recs;
        });

        // ── 2. Generate brand-new personas in parallel ───────────────────────
        recPromise.then(recs => {
            if (signal.aborted) return;
            const existingIds = (recs || []).map(p => p.id);
            return fetch('/generate-personas', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                signal,
                body: JSON.stringify({
                    situation,
                    periods: periods || [],
                    existing_ids: existingIds,
                })
            });
        })
        .then(r => {
            if (!r || signal.aborted) return null;
            return r.json();
        })
        .then(data => {
            if (!data || signal.aborted) { setGenerating(false); return; }
            if (Array.isArray(data.personas) && data.personas.length > 0) {
                setGenerated(data.personas);
            }
            setGenerating(false);
        })
        .catch((err) => {
            if (!signal.aborted) setGenerating(false);
        });

        return () => {
            ctrl.abort();
            abortRef.current = null;
        };
    }, [isOpen]);

    if (!isOpen) return null;

    const toggle = (id) =>
        setPicks(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);

    const handleConfirm = () => {
        const safeSelectedIds = Array.isArray(selectedIds) ? selectedIds : [];
        const mergedIds = [...new Set([...safeSelectedIds, ...picks])];
        const pickedGenerated = generated.filter(p => picks.includes(p.id));
        onConfirm({ ids: mergedIds, generatedPersonas: pickedGenerated });
    };

    return (
        <div
            className="fixed inset-0 z-[100] flex items-end md:items-center justify-center p-0 md:p-4"
            onClick={onClose}
        >
            <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" onClick={e => e.stopPropagation()} />
            <div
                className="relative bg-[#FDFBF7] rounded-t-[40px] md:rounded-[40px] shadow-2xl w-full md:max-w-lg flex flex-col"
                style={{ maxHeight: '90vh' }}
                onClick={e => e.stopPropagation()}
            >
                {/* Mobile drag pill */}
                <div className="w-10 h-1 bg-[#E0DDD8] rounded-full mx-auto mt-4 flex-shrink-0 md:hidden" />

                {/* Close */}
                <button
                    onClick={onClose}
                    className="absolute top-5 right-6 w-8 h-8 rounded-full bg-[#F0EDEA] flex items-center justify-center text-[#5D576B]/60 hover:text-[#5D576B] transition-colors z-10"
                >
                    <Icon name="X" size={16} />
                </button>

                {/* Header */}
                <div className="flex-shrink-0 px-8 pt-8 pb-5 md:px-10 md:pt-10">
                    <p className="text-[9px] uppercase tracking-[0.3em] font-black text-blue-brand/50 mb-2">✦ Just for you</p>
                    <h2 className="text-2xl font-serif italic tracking-tight text-[#1A1A1A] leading-snug pr-8">
                        These voices might resonate
                    </h2>
                    <p className="text-[10px] text-[#5D576B]/50 mt-1.5">Based on what you shared · tap to select or deselect</p>
                </div>

                {/* Scrollable content */}
                <div className="flex-1 overflow-y-auto no-scrollbar px-8 md:px-10 pb-4 space-y-5">

                    {/* ── 2 recommended from roster ── */}
                    {loading ? (
                        <div className="grid grid-cols-2 gap-3">
                            <SkeletonCard /><SkeletonCard />
                        </div>
                    ) : (
                        <div className="grid grid-cols-2 gap-3">
                            {recommended.map(persona => (
                                <PersonaCard
                                    key={persona.id}
                                    persona={persona}
                                    isSelected={picks.includes(persona.id)}
                                    onToggle={toggle}
                                    isGenerated={false}
                                />
                            ))}
                        </div>
                    )}

                    {/* ── 2 AI-generated new personas ── */}
                    {generating && !loading && (
                        <div>
                            <p className="text-[9px] uppercase tracking-[0.3em] font-black text-violet-400/70 mb-2 flex items-center gap-1.5">
                                <span className="inline-block w-3 h-3 border-2 border-violet-300 border-t-transparent rounded-full animate-spin" />
                                Creating new voices just for you…
                            </p>
                            <div className="grid grid-cols-2 gap-3">
                                <SkeletonCard /><SkeletonCard />
                            </div>
                        </div>
                    )}

                    {!generating && generated.length > 0 && (
                        <div>
                            <p className="text-[9px] uppercase tracking-[0.3em] font-black text-violet-400/80 mb-2">
                                ✦ Voices created for you
                            </p>
                            <div className="grid grid-cols-2 gap-3">
                                {generated.slice(0, 2).map(persona => (
                                    <PersonaCard
                                        key={persona.id}
                                        persona={persona}
                                        isSelected={picks.includes(persona.id)}
                                        onToggle={toggle}
                                        isGenerated={true}
                                    />
                                ))}
                            </div>
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className="flex-shrink-0 px-8 pb-8 md:px-10 md:pb-10 pt-4 border-t border-[#F0EDEA] space-y-3">
                    <button
                        onClick={handleConfirm}
                        disabled={picks.length === 0 || loading}
                        className="w-full py-4 bg-blue-brand text-white rounded-full font-black uppercase tracking-[0.2em] text-[11px] shadow-lg hover:shadow-xl hover:translate-y-[-1px] transition-all active:scale-95 disabled:opacity-30"
                    >
                        Add to My Panel & Continue
                    </button>
                    <button
                        onClick={() => onConfirm({ ids: Array.isArray(selectedIds) ? selectedIds : [], generatedPersonas: [] })}
                        className="w-full py-2 text-[10px] uppercase tracking-[0.2em] font-black text-[#5D576B]/40 hover:text-[#5D576B]/70 transition-colors"
                    >
                        Skip — I'll choose my own
                    </button>
                </div>
            </div>
        </div>
    );
};

window.PersonaRecommendModal = PersonaRecommendModal;
