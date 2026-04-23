(() => {
    const { useState, useEffect, useRef } = React;
    const html = htm.bind(React.createElement);

    // ── Keyword fallback (mirrors old UI; used when /recommend-personas returns empty) ──
    const PERSONA_KEYWORDS = {
        'buffett':        ['invest', 'money', 'offer', 'salary', 'cash', 'compensation', 'stock', 'value', 'financial', 'wealth', 'return', 'long-term'],
        'munger':         ['decision', 'choice', 'choose', 'weigh', 'invert', 'mistake', 'bias', 'tradeoff', 'pros and cons', 'offer', 'compare'],
        'drucker':        ['career', 'job', 'work', 'first job', 'offer', 'manage', 'skill', 'strength', 'contribute', 'role', 'position', 'hired', 'effectiveness'],
        'welch':          ['company', 'boss', 'leader', 'team', 'performance', 'hire', 'culture', 'candor', 'win', 'execute', 'job', 'promotion'],
        'architect':      ['startup', 'founder', 'build', 'product', 'series', 'seed', 'venture', 'equity', 'stage', 'business', 'bd', 'operations'],
        'shannon':        ['engineer', 'tech', 'software', 'data', 'signal', 'information', 'noise', 'algorithm'],
        'turing':         ['code', 'software', 'ai', 'algorithm', 'machine', 'program', 'computer', 'automate'],
        'vonneumann':     ['game', 'strategy', 'optimize', 'rational', 'theory', 'model', 'math'],
        'serene':         ['empty', 'lonely', 'sad', 'hurt', 'feel', 'lost', 'confused', 'alone', 'hollow', 'numb'],
        'caretaker':      ['anxious', 'worry', 'stress', 'burnout', 'tired', 'overwhelm', 'pressure', 'scared', 'afraid', 'exhausted'],
        'rebel':          ['stuck', 'trapped', 'break', 'quit', 'leave', 'escape', 'change', 'disrupt', 'unconventional'],
        'audrey-hepburn': ['relationship', 'love', 'crush', 'partner', 'romance', 'dating', 'heart', 'feelings'],
        'krishnamurti':   ['meaning', 'why', 'purpose', 'philosophy', 'life', 'question', 'freedom', 'who am i', 'truth'],
        'lacan':          ['desire', 'unconscious', 'identity', 'self', 'pattern', 'repeat'],
        'tarot-master':   ['uncertain', 'unknown', 'crossroads', 'torn', 'sign', 'fate', 'future', 'destiny'],
    };
    const FALLBACK_IDS = ['munger', 'caretaker', 'rebel'];

    function scorePersonas(situation, allPersonas) {
        const text = String(situation || '').toLowerCase();
        const scores = {};
        for (const [id, keywords] of Object.entries(PERSONA_KEYWORDS)) {
            scores[id] = keywords.reduce((acc, kw) => acc + (text.includes(kw) ? 1 : 0), 0);
        }
        const ranked = Object.entries(scores).filter(([, s]) => s > 0).sort(([, a], [, b]) => b - a).map(([id]) => id);
        const ids = ranked.length >= 2 ? ranked : [...new Set([...ranked, ...FALLBACK_IDS])];
        return ids.slice(0, 2).map(id => (allPersonas || []).find(p => p.id === id)).filter(Boolean);
    }

    // ── Skeleton card ──
    const SkeletonCard = () => html`
        <div class="rounded-2xl border border-white/10 bg-surface-container-high/40 p-4 flex flex-col gap-3 animate-pulse">
            <div class="w-10 h-10 rounded-full bg-white/5"></div>
            <div class="h-3 bg-white/5 rounded-full w-3/4"></div>
            <div class="h-2 bg-white/5 rounded-full w-1/2"></div>
            <div class="h-2 bg-white/5 rounded-full w-full"></div>
        </div>
    `;

    // ── Persona card ──
    const PersonaCard = ({ persona, isSelected, onToggle, isGenerated }) => {
        if (!persona || !persona.id) return null;
        const voiceText = typeof persona.voice === 'string' ? persona.voice : '';
        return html`
            <button
                type="button"
                onClick=${() => onToggle(persona.id)}
                class=${`no-shine relative text-left rounded-2xl p-4 border transition-all duration-150 flex flex-col gap-2 ${
                    isSelected
                        ? 'border-primary bg-primary/10 shadow-md shadow-primary/20'
                        : 'border-white/15 bg-surface-container-high/80 hover:border-primary/40 hover:bg-surface-container'
                }`}
            >
                ${isGenerated ? html`
                    <span class="absolute top-2 left-3 text-[8px] uppercase tracking-widest font-black text-secondary/80 leading-none">✦ AI</span>
                ` : null}
                <div class=${`absolute top-3 right-3 w-5 h-5 rounded-full border-2 flex items-center justify-center transition-all ${
                    isSelected ? 'bg-primary border-primary' : 'border-white/25'
                }`}>
                    ${isSelected ? html`<span class="material-symbols-outlined text-on-primary" style=${{ fontSize: '12px' }}>check</span>` : null}
                </div>

                ${persona.cover_url ? html`
                    <div
                        class="w-10 h-10 rounded-full bg-surface-container overflow-hidden shrink-0"
                        style=${{ backgroundImage: `url(${persona.cover_url})`, backgroundSize: 'cover', backgroundPosition: persona.cover_position || '50% 30%' }}
                    ></div>
                ` : html`
                    <div class=${`w-10 h-10 rounded-full flex items-center justify-center text-xl shrink-0 ${isGenerated ? 'bg-secondary/15' : 'bg-surface-container'}`}>
                        ${persona.avatar || '?'}
                    </div>
                `}

                <div class="min-w-0 pr-4">
                    <p class="font-headline font-bold text-on-surface text-sm leading-tight truncate">${persona.name || ''}</p>
                    <p class="text-[9px] uppercase tracking-widest text-on-surface-variant/60 mt-0.5 leading-tight">${persona.role || ''}</p>
                </div>

                ${voiceText ? html`
                    <p class="text-[10px] text-on-surface-variant/70 italic leading-relaxed line-clamp-2">
                        "${voiceText.slice(0, 72)}${voiceText.length > 72 ? '…' : ''}"
                    </p>
                ` : null}
            </button>
        `;
    };

    // ── Main modal ──
    const VoidPersonaRecommendModal = ({ isOpen, onClose, situation, personas, selectedIds, onConfirm }) => {
        const [picks, setPicks]             = useState([]);
        const [recommended, setRecommended] = useState([]);
        const [generated, setGenerated]     = useState([]);
        const [loading, setLoading]         = useState(false);
        const [generating, setGenerating]   = useState(false);
        const abortRef = useRef(null);

        useEffect(() => {
            if (!isOpen) {
                if (abortRef.current) { abortRef.current.abort(); abortRef.current = null; }
                return;
            }
            setPicks([]);
            setRecommended([]);
            setGenerated([]);
            setLoading(true);
            setGenerating(true);

            const ctrl = new AbortController();
            abortRef.current = ctrl;
            const signal = ctrl.signal;

            const recPromise = fetch('/recommend-personas', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                signal,
                body: JSON.stringify({
                    situation,
                    periods: [],
                    persona_ids: (personas || []).map(p => p.id),
                })
            })
            .then(r => r.json())
            .then(data => {
                if (signal.aborted) return [];
                const ids = Array.isArray(data.ids) && data.ids.length >= 1 ? data.ids : null;
                const recs = ids
                    ? ids.map(id => (personas || []).find(p => p.id === id)).filter(Boolean).slice(0, 2)
                    : scorePersonas(situation, personas || []);
                setRecommended(recs);
                setPicks(recs.map(p => p.id));
                setLoading(false);
                return recs;
            })
            .catch(() => {
                if (signal.aborted) return [];
                const recs = scorePersonas(situation, personas || []);
                setRecommended(recs);
                setPicks(recs.map(p => p.id));
                setLoading(false);
                return recs;
            });

            recPromise.then(recs => {
                if (signal.aborted) return;
                const existingIds = (recs || []).map(p => p.id);
                return fetch('/generate-personas', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include',
                    signal,
                    body: JSON.stringify({ situation, periods: [], existing_ids: existingIds }),
                });
            })
            .then(r => r && !signal.aborted ? r.json() : null)
            .then(data => {
                if (!data || signal.aborted) { setGenerating(false); return; }
                if (Array.isArray(data.personas) && data.personas.length > 0) setGenerated(data.personas);
                setGenerating(false);
            })
            .catch(() => { if (!signal.aborted) setGenerating(false); });

            return () => { ctrl.abort(); abortRef.current = null; };
        }, [isOpen]);

        if (!isOpen) return null;

        const toggle = (id) => setPicks(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);

        const handleConfirm = () => {
            const safeSelectedIds = Array.isArray(selectedIds) ? selectedIds : [];
            const mergedIds = [...new Set([...safeSelectedIds, ...picks])];
            const pickedGenerated = generated.filter(p => picks.includes(p.id));
            onConfirm({ ids: mergedIds, generatedPersonas: pickedGenerated });
        };

        const handleSkip = () => onConfirm({
            ids: Array.isArray(selectedIds) ? selectedIds : [],
            generatedPersonas: [],
        });

        return html`
            <div class="fixed inset-0 z-[100] flex items-center justify-center p-4">
                <div class="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick=${onClose}></div>
                <div
                    class="relative bg-surface-container/95 backdrop-blur-2xl rounded-2xl border border-white/15 shadow-2xl w-full max-w-xl max-h-[88vh] flex flex-col"
                    onClick=${(e) => e.stopPropagation()}
                >
                    <button
                        onClick=${onClose}
                        class="absolute top-4 right-5 text-on-surface/50 hover:text-on-surface/90 transition-colors z-10"
                        aria-label="Close"
                    >
                        <span class="material-symbols-outlined" style=${{ fontSize: '20px' }}>close</span>
                    </button>

                    <div class="shrink-0 px-8 pt-8 pb-4">
                        <p class="text-[9px] uppercase tracking-[0.3em] font-bold text-primary/70 mb-2">✦ Just for you</p>
                        <h2 class="text-2xl font-headline italic font-bold text-on-surface leading-snug pr-8">These voices might resonate</h2>
                        <p class="text-[10px] text-on-surface-variant/60 mt-1.5">Based on what you shared · tap to select or deselect</p>
                    </div>

                    <div class="flex-1 overflow-y-auto no-scrollbar px-8 pb-4 space-y-5">
                        ${loading ? html`
                            <div class="grid grid-cols-2 gap-3">
                                <${SkeletonCard} /><${SkeletonCard} />
                            </div>
                        ` : html`
                            <div class="grid grid-cols-2 gap-3">
                                ${recommended.map(p => html`<${PersonaCard}
                                    key=${p.id}
                                    persona=${p}
                                    isSelected=${picks.includes(p.id)}
                                    onToggle=${toggle}
                                    isGenerated=${false}
                                />`)}
                            </div>
                        `}

                        ${generating && !loading ? html`
                            <div>
                                <p class="text-[9px] uppercase tracking-[0.3em] font-bold text-secondary/80 mb-2 flex items-center gap-1.5">
                                    <span class="inline-block w-3 h-3 border-2 border-secondary/60 border-t-transparent rounded-full animate-spin"></span>
                                    Creating new voices just for you…
                                </p>
                                <div class="grid grid-cols-2 gap-3">
                                    <${SkeletonCard} /><${SkeletonCard} />
                                </div>
                            </div>
                        ` : null}

                        ${!generating && generated.length > 0 ? html`
                            <div>
                                <p class="text-[9px] uppercase tracking-[0.3em] font-bold text-secondary/80 mb-2">✦ Voices created for you</p>
                                <div class="grid grid-cols-2 gap-3">
                                    ${generated.slice(0, 2).map(p => html`<${PersonaCard}
                                        key=${p.id}
                                        persona=${p}
                                        isSelected=${picks.includes(p.id)}
                                        onToggle=${toggle}
                                        isGenerated=${true}
                                    />`)}
                                </div>
                            </div>
                        ` : null}
                    </div>

                    <div class="shrink-0 px-8 pb-8 pt-4 border-t border-white/10 space-y-3">
                        <button
                            onClick=${handleConfirm}
                            disabled=${picks.length === 0 || loading}
                            class="no-shine w-full py-3.5 bg-primary text-on-primary rounded-full font-bold uppercase tracking-[0.2em] text-[11px] shadow-lg hover:bg-primary/90 transition-all disabled:opacity-30 disabled:cursor-not-allowed"
                        >Add to My Panel & Continue</button>
                        <button
                            onClick=${handleSkip}
                            class="no-shine w-full py-2 text-[10px] uppercase tracking-[0.2em] font-bold text-on-surface/40 hover:text-on-surface/70 transition-colors"
                        >Skip — I'll choose my own</button>
                    </div>
                </div>
            </div>
        `;
    };

    window.VoidPersonaRecommendModal = VoidPersonaRecommendModal;
})();
