const { useState, useEffect, useRef } = React;
const { Icon, AvatarDisplay } = window;

// --- Labs & Tools (secondary pages) ---

const LifeSimulator = () => {
    const [decision, setDecision] = useState('');
    const [timeline, setTimeline] = useState([
        { year: 'Age 22', title: 'Graduation Crossroads', detail: 'You’re choosing between stability and creativity.' },
        { year: 'Age 23', title: 'First Commit', detail: 'A small choice becomes a habit — and a direction.' }
    ]);

    const runSim = () => {
        const d = (decision || '').trim();
        if (!d) return;
        const outcomes = [
            'Your clarity increases — momentum follows.',
            'A new constraint appears, forcing a better plan.',
            'A mentor shows up earlier than expected.',
            'You trade comfort for growth, and it pays off.'
        ];
        const nextAge = 24 + Math.min(10, Math.floor(timeline.length / 2));
        const outcome = outcomes[Math.floor(Math.random() * outcomes.length)];
        setTimeline(prev => ([
            ...prev,
            { year: `Age ${nextAge}`, title: 'Decision', detail: d },
            { year: `Age ${nextAge}`, title: 'Trajectory Shift', detail: outcome }
        ]));
        setDecision('');
    };

    return (
        <div className="p-6 md:p-12 max-w-5xl mx-auto animate-in space-y-10 pb-32">
            <div className="text-center space-y-3">
                <h2 className="text-4xl md:text-6xl font-serif italic tracking-tight">Life Simulator</h2>
                <p className="text-[10px] uppercase font-black tracking-[0.4em] opacity-40">Predicting your trajectory</p>
            </div>

            <div className="bg-white p-8 md:p-10 rounded-[60px] border border-[#F0EDEA] shadow-xl relative overflow-hidden">
                <div className="absolute top-0 right-0 p-8 opacity-5"><Icon name="Activity" size={64} /></div>

                <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_360px] gap-8 items-start">
                    <div className="relative">
                        <div className="absolute left-4 top-2 bottom-2 w-px bg-blue-brand/15" />
                        <div className="space-y-6 pl-10">
                            {timeline.map((t, idx) => (
                                <div key={`${t.year}-${idx}`} className="relative">
                                    <div className="absolute -left-[30px] top-2 w-3 h-3 rounded-full bg-blue-brand shadow-[0_0_12px_rgba(152,166,212,0.35)]" />
                                    <div className="bg-[#FDFBF7] rounded-[40px] border-2 border-dashed border-blue-brand/20 p-6">
                                        <div className="flex items-center justify-between gap-3">
                                            <span className="text-[10px] font-black uppercase tracking-[0.3em] opacity-40">{t.year}</span>
                                            <span className="text-[10px] font-black uppercase tracking-[0.2em] text-blue-brand">{t.title}</span>
                                        </div>
                                        <p className="mt-3 text-sm italic opacity-70 leading-relaxed">{t.detail}</p>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>

                    <div className="bg-[#FDFBF7] rounded-[40px] border border-[#E8E6E0] p-6 md:p-8 space-y-6">
                        <div className="space-y-2">
                            <h4 className="text-[10px] font-black uppercase tracking-[0.35em] opacity-40">Input a decision</h4>
                            <textarea
                                value={decision}
                                onChange={(e) => setDecision(e.target.value)}
                                placeholder="e.g. Take the offer, but keep weekends for a passion project..."
                                className="w-full h-28 p-5 bg-white rounded-[28px] border-2 border-transparent focus-blue-brand text-sm leading-relaxed italic no-scrollbar shadow-inner"
                            />
                        </div>
                        <button
                            onClick={runSim}
                            disabled={!decision.trim()}
                            className="w-full py-5 bg-blue-brand text-white rounded-full font-black text-[10px] uppercase tracking-widest shadow-[0_4px_14px_rgba(152,166,212,0.35)] transition-all active:scale-95 disabled:opacity-20"
                        >
                            Run Simulation
                        </button>
                        <div className="text-[10px] opacity-50 leading-relaxed">
                            This is a lightweight timeline UI. If you want true AI-driven branching outcomes, we can plug it into your existing model / endpoint next.
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

const TAROT_DECK = [
    { id: 0, name: "The Fool", icon: "Wind", desc: "Beginnings, potential, leap of faith." },
    { id: 1, name: "The Magician", icon: "Zap", desc: "Manifestation, resourcefulness." },
    { id: 2, name: "The High Priestess", icon: "Moon", desc: "Intuition, sacred knowledge." },
    { id: 3, name: "The Empress", icon: "Flower", desc: "Femininity, beauty, nature." },
    { id: 4, name: "The Emperor", icon: "Shield", desc: "Authority, structure, stability." },
    { id: 5, name: "The Hierophant", icon: "Book", desc: "Spiritual wisdom, traditions." },
    { id: 6, name: "The Lovers", icon: "Heart", desc: "Love, harmony, relationships." },
    { id: 7, name: "The Chariot", icon: "Navigation", desc: "Control, willpower, victory." },
    { id: 8, name: "Strength", icon: "Sun", desc: "Courage, persuasion, compassion." },
    { id: 9, name: "The Hermit", icon: "Flame", desc: "Introspection, solitude, guidance." },
    { id: 10, name: "Wheel of Fortune", icon: "RefreshCw", desc: "Destiny, cycles, turning point." },
    { id: 11, name: "Justice", icon: "Scale", desc: "Fairness, truth, law, cause." },
    { id: 12, name: "The Hanged Man", icon: "Anchor", desc: "Pause, surrender, letting go." },
    { id: 13, name: "Death", icon: "Scissors", desc: "Endings, change, transition." },
    { id: 14, name: "Temperance", icon: "Droplets", desc: "Balance, moderation, patience." },
    { id: 15, name: "The Devil", icon: "Lock", desc: "Shadow self, attachment, restriction." },
    { id: 16, name: "The Tower", icon: "Zap", desc: "Sudden change, upheaval, revelation." },
    { id: 17, name: "The Star", icon: "Star", desc: "Hope, faith, renewal, peace." },
    { id: 18, name: "The Moon", icon: "CloudMoon", desc: "Illusion, fear, anxiety, intuition." },
    { id: 19, name: "The Sun", icon: "Sun", desc: "Positivity, success, vitality." },
    { id: 20, name: "Judgement", icon: "Bell", desc: "Rebirth, inner calling, absolution." },
    { id: 21, name: "The World", icon: "Globe", desc: "Completion, integration, travel." }
];

const AITarot = () => {
    const [selectedCards, setSelectedCards] = useState({});

    const toggleCard = (id) => setSelectedCards(p => ({ ...(p || {}), [id]: !p?.[id] }));

    return (
        <div className="p-6 md:p-12 max-w-[1400px] mx-auto animate-in space-y-10 pb-32">
            <div className="text-center space-y-3">
                <h2 className="text-4xl md:text-7xl font-serif italic tracking-tighter text-blue-brand">AI Tarot</h2>
                <p className="text-[10px] uppercase font-black tracking-[0.4em] opacity-40">Consult the 22 Major Arcana</p>
            </div>

            <div className="flex items-center justify-center min-h-[420px]">
                <div className="w-full overflow-x-auto no-scrollbar py-12 px-[10%] md:px-[20%] mask-linear-tarot">
                    <div className="flex flex-nowrap gap-6 md:gap-10 min-w-max">
                        {TAROT_DECK.map((card) => {
                            const flipped = !!selectedCards?.[card.id];
                            return (
                                <button
                                    type="button"
                                    key={card.id}
                                    onClick={() => toggleCard(card.id)}
                                    className="shrink-0 w-[180px] md:w-[220px] aspect-[2/3.5] perspective-1000 group cursor-pointer transition-transform hover:scale-[1.03] outline-none"
                                    aria-label={`Tarot card ${card.name}`}
                                >
                                    <div className={`relative w-full h-full duration-700 preserve-3d shadow-xl rounded-[32px] ${flipped ? 'rotate-y-180' : ''}`}>
                                        {/* Card back */}
                                        <div className="absolute inset-0 backface-hidden bg-white border border-[#F0EDEA] rounded-[32px] flex flex-col items-center justify-center p-8 text-center shadow-sm">
                                            <div className="w-16 h-16 rounded-full bg-[#FDFBF7] flex items-center justify-center mb-10 border border-[#E8E6E0]">
                                                <Icon name="Moon" size={28} className="text-[#5D576B] opacity-40" />
                                            </div>
                                            <div className="text-[10px] font-black opacity-20 tracking-[0.4em] uppercase">
                                                CARD {String(card.id + 1).padStart(2, '0')}
                                            </div>
                                        </div>

                                        {/* Card face */}
                                        <div className="absolute inset-0 backface-hidden rotate-y-180 bg-white border-2 border-blue-brand rounded-[32px] p-8 flex flex-col items-center justify-center text-center">
                                            <div className="w-16 h-16 rounded-full bg-blue-brand/5 flex items-center justify-center mb-6">
                                                <Icon name={card.icon} size={32} className="text-blue-brand" />
                                            </div>
                                            <div className="text-xl font-serif italic font-black mb-4 uppercase leading-tight text-[#1A1A1A]">
                                                {card.name}
                                            </div>
                                            <div className="h-px w-10 bg-blue-brand/20 mb-4" />
                                            <div className="text-[10px] italic leading-relaxed text-[#5D576B] font-medium uppercase tracking-widest opacity-80">
                                                {card.desc}
                                            </div>
                                        </div>
                                    </div>
                                </button>
                            );
                        })}
                    </div>
                </div>
            </div>

            <div className="bg-white/70 backdrop-blur-md p-10 rounded-[50px] border border-[#F0EDEA] shadow-xl text-center space-y-4 max-w-2xl mx-auto relative">
                <div className="absolute top-0 right-0 p-8 opacity-5 pointer-events-none"><Icon name="Moon" size={64} /></div>
                <p className="text-xs opacity-60 leading-relaxed italic px-4">
                    "The Arcana is a mirror to your current chapter. Browse the 22 archetypes, pick three, and let the meaning unfold."
                </p>
                <div className="pt-2">
                    <button
                        type="button"
                        onClick={() => {}}
                        className="px-16 py-5 bg-blue-brand text-white rounded-full font-black text-[10px] uppercase tracking-[0.4em] shadow-lg shadow-[0_4px_14px_rgba(152,166,212,0.35)] hover:-translate-y-0.5 transition-all active:scale-95"
                    >
                        INTERPRET MY SPREAD
                    </button>
                </div>
            </div>
        </div>
    );
};

const TarotReadingModal = ({ isOpen, decisionLabel, onClose, onInterpret }) => {
    const [selectedCards, setSelectedCards] = useState({});

    useEffect(() => {
        if (!isOpen) setSelectedCards({});
    }, [isOpen]);

    if (!isOpen) return null;

    const pickedCards = TAROT_DECK.filter(card => selectedCards?.[card.id]);

    const toggleCard = (id) => {
        setSelectedCards(prev => {
            const next = { ...(prev || {}) };
            if (next[id]) {
                delete next[id];
                return next;
            }
            if (Object.keys(next).length >= 3) return next;
            next[id] = true;
            return next;
        });
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 md:p-8">
            <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" onClick={onClose}></div>
            <div className="relative w-full max-w-[1280px] max-h-[90vh] overflow-hidden bg-[#FDFBF7] rounded-[40px] md:rounded-[56px] border border-[#F0EDEA] shadow-2xl animate-in">
                <div className="flex items-center justify-between px-6 md:px-8 pt-6 md:pt-8 pb-2">
                    <div className="space-y-2 pr-4">
                        <div className="text-[10px] font-black uppercase tracking-[0.35em] opacity-35">Tarot Consultation</div>
                        <h3 className="text-2xl md:text-4xl font-serif italic tracking-tight text-blue-brand">Draw for This Decision</h3>
                        <p className="text-xs md:text-sm text-[#5D576B] italic max-w-2xl">
                            {decisionLabel ? `Decision in focus: "${decisionLabel}"` : 'Focus on the choice in front of you, then draw three cards.'}
                        </p>
                    </div>
                    <button onClick={onClose} className="shrink-0 w-11 h-11 rounded-full border border-[#E8E6E0] bg-white flex items-center justify-center text-[#5D576B]/60 hover:text-blue-brand hover:border-blue-brand/30 transition-all">
                        <Icon name="X" size={18} />
                    </button>
                </div>

                <div className="overflow-y-auto max-h-[calc(90vh-96px)] px-4 md:px-8 pb-6 md:pb-8">
                    <div className="flex items-center justify-center min-h-[360px]">
                        <div className="w-full overflow-x-auto no-scrollbar py-8 md:py-12 px-[2%] md:px-[8%] mask-linear-tarot">
                            <div className="flex flex-nowrap gap-4 md:gap-8 min-w-max">
                                {TAROT_DECK.map((card) => {
                                    const flipped = !!selectedCards?.[card.id];
                                    const order = pickedCards.findIndex(x => x.id === card.id);
                                    return (
                                        <button
                                            type="button"
                                            key={card.id}
                                            onClick={() => toggleCard(card.id)}
                                            className="shrink-0 w-[150px] md:w-[200px] aspect-[2/3.5] perspective-1000 group cursor-pointer transition-transform hover:scale-[1.03] outline-none"
                                            aria-label={`Tarot card ${card.name}`}
                                        >
                                            <div className={`relative w-full h-full duration-700 preserve-3d shadow-xl rounded-[32px] ${flipped ? 'rotate-y-180' : ''}`}>
                                                <div className="absolute inset-0 backface-hidden bg-white border border-[#F0EDEA] rounded-[32px] flex flex-col items-center justify-center p-8 text-center shadow-sm">
                                                    <div className="w-14 h-14 rounded-full bg-[#FDFBF7] flex items-center justify-center mb-8 border border-[#E8E6E0]">
                                                        <Icon name="Moon" size={24} className="text-[#5D576B] opacity-40" />
                                                    </div>
                                                    <div className="text-[10px] font-black opacity-20 tracking-[0.4em] uppercase">
                                                        CARD {String(card.id + 1).padStart(2, '0')}
                                                    </div>
                                                </div>

                                                <div className="absolute inset-0 backface-hidden rotate-y-180 bg-white border-2 border-blue-brand rounded-[32px] p-6 md:p-8 flex flex-col items-center justify-center text-center">
                                                    {order >= 0 && (
                                                        <div className="absolute top-4 right-4 w-8 h-8 rounded-full bg-blue-brand text-white text-[10px] font-black flex items-center justify-center">
                                                            {order + 1}
                                                        </div>
                                                    )}
                                                    <div className="w-14 h-14 rounded-full bg-blue-brand/5 flex items-center justify-center mb-5">
                                                        <Icon name={card.icon} size={28} className="text-blue-brand" />
                                                    </div>
                                                    <div className="text-lg md:text-xl font-serif italic font-black mb-4 uppercase leading-tight text-[#1A1A1A]">
                                                        {card.name}
                                                    </div>
                                                    <div className="h-px w-10 bg-blue-brand/20 mb-4" />
                                                    <div className="text-[10px] italic leading-relaxed text-[#5D576B] font-medium uppercase tracking-widest opacity-80">
                                                        {card.desc}
                                                    </div>
                                                </div>
                                            </div>
                                        </button>
                                    );
                                })}
                            </div>
                        </div>
                    </div>

                    <div className="bg-white/80 backdrop-blur-md p-6 md:p-10 rounded-[36px] md:rounded-[50px] border border-[#F0EDEA] shadow-xl text-center space-y-4 max-w-3xl mx-auto relative">
                        <div className="absolute top-0 right-0 p-8 opacity-5 pointer-events-none"><Icon name="Moon" size={64} /></div>
                        <p className="text-xs opacity-60 leading-relaxed italic px-4">
                            Draw exactly three cards. The spread will be read as present tension, hidden influence, and likely transformation around this one decision.
                        </p>
                        <div className="flex flex-wrap items-center justify-center gap-2 min-h-[32px]">
                            {pickedCards.length > 0 ? pickedCards.map(card => (
                                <span key={card.id} className="px-3 py-1.5 rounded-full bg-blue-brand/8 border border-blue-brand/15 text-[10px] font-black uppercase tracking-[0.15em] text-blue-brand">
                                    {card.name}
                                </span>
                            )) : (
                                <span className="text-[10px] font-black uppercase tracking-[0.3em] opacity-25">No cards drawn yet</span>
                            )}
                        </div>
                        <div className="pt-2 flex flex-col sm:flex-row justify-center gap-3">
                            <button
                                type="button"
                                onClick={onClose}
                                className="px-8 py-4 bg-white text-[#5D576B] rounded-full font-black text-[10px] uppercase tracking-[0.3em] border border-[#E8E6E0] hover:border-blue-brand/30 transition-all"
                            >
                                Close
                            </button>
                            <button
                                type="button"
                                disabled={pickedCards.length !== 3}
                                onClick={() => onInterpret?.(pickedCards)}
                                className="px-10 md:px-16 py-4 md:py-5 bg-blue-brand text-white rounded-full font-black text-[10px] uppercase tracking-[0.35em] shadow-lg shadow-[0_4px_14px_rgba(152,166,212,0.35)] hover:-translate-y-0.5 transition-all active:scale-95 disabled:opacity-20"
                            >
                                INTERPRET MY SPREAD
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

const DecisionLab = () => {
    const [items, setItems] = useState([
        { id: 'growth', label: 'Career Growth', weight: 8.5 },
        { id: 'burnout', label: 'Mental Burnout', weight: -6.2 }
    ]);
    const [newLabel, setNewLabel] = useState('');
    const [newWeight, setNewWeight] = useState(2);

    const total = items.reduce((sum, x) => sum + (Number(x.weight) || 0), 0);
    const clamp = (n, a, b) => Math.max(a, Math.min(b, n));
    const clarity = clamp(Math.round(((total + 20) / 40) * 100), 0, 100);

    const add = () => {
        const label = (newLabel || '').trim();
        if (!label) return;
        const w = clamp(Number(newWeight) || 0, -10, 10);
        setItems(prev => ([...prev, { id: `${Date.now()}`, label, weight: w }]));
        setNewLabel('');
        setNewWeight(2);
    };

    const updateWeight = (id, weight) => {
        setItems(prev => prev.map(x => x.id === id ? ({ ...x, weight }) : x));
    };

    const remove = (id) => setItems(prev => prev.filter(x => x.id !== id));

    return (
        <div className="p-6 md:p-12 max-w-6xl mx-auto animate-in space-y-10 pb-32 text-left">
            <div className="text-center space-y-3">
                <h2 className="text-4xl md:text-6xl font-serif italic tracking-tight">Decision Lab</h2>
                <p className="text-[10px] uppercase font-black tracking-[0.4em] opacity-40">Quantifying the intangible</p>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                <div className="bg-white p-8 md:p-10 rounded-[60px] border border-[#F0EDEA] shadow-sm space-y-8">
                    <div className="flex items-center justify-between">
                        <h3 className="text-[10px] font-black uppercase tracking-widest opacity-30">Pros / Cons Weight Matrix</h3>
                        <div className="text-[10px] font-black uppercase tracking-[0.25em] opacity-40">Total: {total.toFixed(1)}</div>
                    </div>

                    <div className="space-y-4">
                        {items.map(x => {
                            const isPro = (Number(x.weight) || 0) >= 0;
                            return (
                                <div key={x.id} className={`p-5 rounded-[28px] border ${isPro ? 'bg-green-50/40 border-green-100' : 'bg-red-50/40 border-red-100'}`}>
                                    <div className="flex items-center justify-between gap-4">
                                        <div className="min-w-0">
                                            <div className="font-bold text-sm truncate">{x.label}</div>
                                            <div className="mt-2 flex items-center gap-3">
                                                <input
                                                    type="range"
                                                    min={-10}
                                                    max={10}
                                                    step={0.5}
                                                    value={x.weight}
                                                    onChange={(e) => updateWeight(x.id, Number(e.target.value))}
                                                    className="w-full"
                                                />
                                                <div className={`shrink-0 text-xs font-black ${isPro ? 'text-green-700' : 'text-red-700'}`}>
                                                    {isPro ? '+' : ''}{Number(x.weight).toFixed(1)}
                                                </div>
                                            </div>
                                        </div>
                                        <button onClick={() => remove(x.id)} className="w-9 h-9 rounded-full bg-white/80 border border-[#E8E6E0] flex items-center justify-center text-[#5D576B]/60 hover:text-blue-brand hover:border-blue-brand/30 transition-all">
                                            <Icon name="X" size={16} />
                                        </button>
                                    </div>
                                </div>
                            );
                        })}
                    </div>

                    <div className="p-6 rounded-[40px] border-2 border-dashed border-[#D1CEC7] bg-[#FDFBF7] space-y-4">
                        <div className="text-[10px] font-black uppercase tracking-[0.3em] opacity-40">Add variable</div>
                        <input
                            value={newLabel}
                            onChange={(e) => setNewLabel(e.target.value)}
                            placeholder="Variable name..."
                            className="w-full h-12 px-5 bg-white rounded-full border-2 border-transparent focus-blue-brand text-sm"
                        />
                        <div className="flex items-center gap-4">
                            <input
                                type="range"
                                min={-10}
                                max={10}
                                step={0.5}
                                value={newWeight}
                                onChange={(e) => setNewWeight(Number(e.target.value))}
                                className="flex-1"
                            />
                            <div className="w-16 text-right text-xs font-black opacity-60">{newWeight >= 0 ? '+' : ''}{Number(newWeight).toFixed(1)}</div>
                        </div>
                        <button
                            onClick={add}
                            disabled={!newLabel.trim()}
                            className="w-full py-4 bg-blue-brand text-white rounded-full font-black text-[10px] uppercase tracking-widest shadow-[0_4px_14px_rgba(152,166,212,0.35)] transition-all active:scale-95 disabled:opacity-20"
                        >
                            Add
                        </button>
                    </div>
                </div>

                <div className="bg-white p-8 md:p-10 rounded-[60px] border border-[#F0EDEA] shadow-sm flex flex-col justify-center text-center space-y-8 relative overflow-hidden">
                    <div className="absolute top-0 right-0 p-8 opacity-5"><Icon name="Layers" size={64} /></div>
                    <div className="w-36 h-36 rounded-full border-8 border-blue-brand/10 border-t-blue-brand flex items-center justify-center mx-auto">
                        <span className="text-4xl font-black text-blue-brand">{clarity}%</span>
                    </div>
                    <div className="space-y-2 max-w-sm mx-auto">
                        <h4 className="font-bold text-sm">Rational Clarity Score</h4>
                        <p className="text-xs opacity-50 italic leading-relaxed">
                            A quick heuristic from your weights. Use it as a mirror — then ask what your emotions are protecting.
                        </p>
                    </div>

                    <div className="grid grid-cols-2 gap-4 max-w-md mx-auto w-full">
                        <div className="p-5 rounded-[32px] bg-[#FDFBF7] border border-[#E8E6E0] text-left">
                            <div className="text-[10px] font-black uppercase tracking-[0.3em] opacity-40">Emotional</div>
                            <div className="mt-3 text-sm italic opacity-70">Name the fear behind the biggest negative weight.</div>
                        </div>
                        <div className="p-5 rounded-[32px] bg-[#FDFBF7] border border-[#E8E6E0] text-left">
                            <div className="text-[10px] font-black uppercase tracking-[0.3em] opacity-40">Rational</div>
                            <div className="mt-3 text-sm italic opacity-70">Identify the one variable that changes everything.</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

const PersonaBuilder = ({ onSave, onCancel }) => {
    const [step, setStep] = useState(1);
    const [newP, setNewP] = useState({ name: '', role: '', worldview: '', avatar: '👤', voice: '', knowledge: '' });
    const emojis = ['👤', '🎭', '🛡️', '🌱', '🦉', '💎', '🌩️', '🌊', '🔥', '🎀', '🧸', '☁️'];
    return (
        <div className="max-w-2xl mx-auto w-full pt-8 md:pt-12 px-4 font-sans animate-in">
            <div className="mb-8 flex items-center justify-between">
                <button onClick={onCancel} className="text-[10px] font-bold uppercase tracking-widest opacity-40 flex items-center gap-2"><Icon name="X" size={14} /> Cancel</button>
                <div className="flex gap-2">
                    {[1, 2, 3].map(s => <div key={s} className={`w-2.5 h-2.5 rounded-full ${s <= step ? 'bg-blue-brand shadow-[0_0_8px_rgba(152,166,212,0.4)]' : 'bg-slate-200'}`} />)}
                </div>
            </div>
            <div className="bg-white p-6 md:p-12 rounded-[40px] md:rounded-[60px] shadow-sm border border-[#F0EDEA] space-y-8">
                {step === 1 && (
                    <div className="space-y-6">
                        <h2 className="text-xl md:text-2xl font-serif italic text-center uppercase text-[#1A1A1A]">Step 1: Identity</h2>
                        <input placeholder="Name..." className="w-full p-4 bg-[#FDFBF7] rounded-2xl border border-[#F0EDEA] focus-blue-brand" value={newP.name} onChange={e => setNewP({...newP, name: e.target.value})} />
                        <input placeholder="Role / Identity" className="w-full p-4 bg-[#FDFBF7] rounded-2xl border border-[#F0EDEA] uppercase text-xs focus-blue-brand" value={newP.role} onChange={e => setNewP({...newP, role: e.target.value})} />
                        <div className="flex flex-wrap gap-2 justify-center pt-2">{emojis.map(e => <button key={e} onClick={() => setNewP({...newP, avatar: e})} className={`p-3 rounded-xl transition-all border-2 ${newP.avatar === e ? 'border-blue-brand bg-white' : 'border-transparent bg-slate-50'}`}>{e}</button>)}</div>
                    </div>
                )}
                {step === 2 && (
                    <div className="space-y-6">
                        <h2 className="text-xl md:text-2xl font-serif italic text-center uppercase">Step 2: Soul</h2>
                        <textarea placeholder="Worldview Statement..." className="w-full h-32 p-5 bg-[#FDFBF7] rounded-2xl border border-[#F0EDEA] text-sm italic focus-blue-brand" value={newP.worldview} onChange={e => setNewP({...newP, worldview: e.target.value})} />
                        <textarea placeholder="Voice Sample..." className="w-full h-24 p-5 bg-[#FDFBF7] rounded-2xl border border-[#F0EDEA] text-sm focus-blue-brand" value={newP.voice} onChange={e => setNewP({...newP, voice: e.target.value})} />
                    </div>
                )}
                <div className="flex gap-3">
                    {step > 1 && <button onClick={() => setStep(step-1)} className="flex-1 py-4 bg-slate-50 text-neutral-400 rounded-full font-bold text-xs uppercase border">Back</button>}
                    <button onClick={() => step < 2 ? setStep(step+1) : onSave(newP)} disabled={step === 1 ? (!newP.name || !newP.role) : !newP.worldview} className="flex-[2] py-4 bg-[#1A1A1A] text-white rounded-full font-bold text-xs uppercase shadow-xl disabled:opacity-20 transition-all">{step < 2 ? 'CONTINUE' : 'ARCHIVE VOICE'}</button>
                </div>
            </div>
        </div>
    );
};

window.TAROT_DECK = TAROT_DECK;
window.LifeSimulator = LifeSimulator;
window.AITarot = AITarot;
window.TarotReadingModal = TarotReadingModal;
window.DecisionLab = DecisionLab;
window.PersonaBuilder = PersonaBuilder;
