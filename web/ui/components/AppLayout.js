const { useState, useEffect, useRef } = React;
const { Icon } = window;

const COMING_SOON_MSG = 'New feature coming soon';

const AppLayout = ({ children, activeView, setView, user, isAdmin, onOpenAdmin, onLogin, onSignOut, onNewChat, savedSessions = [], setSavedSessions, setSessionMessages, setSessionId, setSelectedIds, personas = [] }) => {
    const [isCollapsed, setIsCollapsed] = useState(false);
    const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
    const scrollContainerRef = useRef(null);

    const footerItems = (window.LIFEE_UI_NAV && Array.isArray(window.LIFEE_UI_NAV.footerItems))
        ? window.LIFEE_UI_NAV.footerItems
        : [
            { id: 'my-chats', label: 'My Chats', icon: 'Archive', view: 'my-chats' },
            { id: 'my-personas', label: 'My Personas', icon: 'Users', view: 'my-personas' },
            { id: 'help', label: 'Help', icon: 'HelpCircle', view: 'help' },
            { id: 'settings', label: 'Settings', icon: 'Settings', view: 'settings' }
        ];

    const rawLabToolItems = (window.LIFEE_UI_NAV && Array.isArray(window.LIFEE_UI_NAV.labToolItems))
        ? window.LIFEE_UI_NAV.labToolItems
        : [
            { id: 'life-simulator', label: 'Life Simulator', icon: 'Activity', view: 'life-simulator' },
            { id: 'ai-tarot', label: 'AI Tarot', icon: 'Moon', view: 'ai-tarot' },
            { id: 'decision-lab', label: 'Decision Lab', icon: 'Layers', view: 'decision-lab' }
        ];
    const labToolItems = rawLabToolItems.filter(item => item.id !== 'ai-tarot' && item.view !== 'ai-tarot');
    const primaryItems = [
        { id: 'home', label: 'Home', icon: 'House', view: 'home' },
        { id: 'community', label: 'Community', icon: 'Globe2', view: 'community' }
    ];
    const sortedSessions = [...savedSessions].sort((a, b) => {
        const aTime = a.updated_at ? new Date(a.updated_at).getTime() : 0;
        const bTime = b.updated_at ? new Date(b.updated_at).getTime() : 0;
        return bTime - aTime;
    });
    const starredSessions = sortedSessions.filter(s => s.starred);
    const recentSessions = sortedSessions.filter(s => !s.starred).slice(0, 8);
    const displayName = user?.user_metadata?.name || user?.email?.split('@')[0] || 'Guest';

    useEffect(() => {
        const el = scrollContainerRef.current;
        if (!el) return;
        el.scrollTo({ top: 0, left: 0, behavior: 'auto' });
        el.scrollTop = 0;
        requestAnimationFrame(() => {
            if (!scrollContainerRef.current) return;
            scrollContainerRef.current.scrollTo({ top: 0, left: 0, behavior: 'auto' });
            scrollContainerRef.current.scrollTop = 0;
        });
    }, [activeView]);

    useEffect(() => {
        // Render lucide icons after React updates (avoid per-icon DOM mutation).
        if (window.lucide && typeof window.lucide.createIcons === 'function') {
            requestAnimationFrame(() => window.lucide.createIcons());
        }
    }, [activeView, isCollapsed, isMobileMenuOpen, user]);

    const handleMobileNewChat = () => {
        onNewChat();
        setIsMobileMenuOpen(false);
    };

    const restoreSession = async (s) => {
        const res = await fetch(`/sessions/${s.id}/messages`, { credentials: 'include' }).then(r => r.json());
        if (res?.messages) {
            setSessionMessages(res.messages.map(m => ({ personaId: m.persona_id || m.role, text: m.content })));
            setSessionId(s.id);
            if (s.personas && s.personas.length && setSelectedIds) {
                const ids = s.personas.map(pid => {
                    const found = personas.find(p => p.id === pid || p.id === pid.toLowerCase().replace(/\s+/g, '') || p.name === pid);
                    return found?.id;
                }).filter(Boolean);
                if (ids.length) setSelectedIds(ids);
            }
            setView('debate');
        }
        setIsMobileMenuOpen(false);
    };

    const renderSessionRow = (s) => (
        <div
            key={s.id}
            className="group flex items-start gap-2 rounded-2xl border border-transparent px-3 py-3 transition-all hover:border-[#ECE7DE] hover:bg-white/78"
        >
            <button onClick={() => restoreSession(s)} className="flex min-w-0 flex-1 items-start gap-3 text-left">
                <div className={`mt-1 h-2 w-2 rounded-full ${s.starred ? 'bg-[#E5BE73]' : 'bg-[#D9DDEA]'}`} />
                <div className="min-w-0 flex-1">
                    <div className="truncate text-xs font-bold text-[#3F3B4B]">{s.title || 'Untitled'}</div>
                    <div className="mt-1 truncate text-[10px] uppercase tracking-[0.18em] text-[#8D88A0]">
                        {(s.personas || []).slice(0, 2).join(' · ') || 'Conversation'}
                    </div>
                </div>
            </button>
            <div className={`session-actions flex items-center gap-1 transition-opacity opacity-0 group-hover:opacity-100 ${isCollapsed ? 'md:hidden' : ''}`}>
                <button title="Star" onClick={async (e) => {
                    e.stopPropagation();
                    const newVal = !s.starred;
                    await fetch(`/sessions/${s.id}`, { method: 'PATCH', credentials: 'include', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({starred: newVal}) });
                    setSavedSessions(prev => prev.map(x => x.id === s.id ? {...x, starred: newVal} : x));
                }} className={`rounded-full p-1 transition-colors ${s.starred ? 'text-[#E5BE73]' : 'text-[#A39DB2] hover:text-[#E5BE73]'}`}>
                    <Icon name="Star" size={12} />
                </button>
                <button title="Rename" onClick={async (e) => {
                    e.stopPropagation();
                    const newTitle = prompt('Rename conversation:', s.title || '');
                    if (newTitle === null || newTitle === s.title) return;
                    await fetch(`/sessions/${s.id}`, { method: 'PATCH', credentials: 'include', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({title: newTitle}) });
                    setSavedSessions(prev => prev.map(x => x.id === s.id ? {...x, title: newTitle} : x));
                }} className="rounded-full p-1 text-[#A39DB2] transition-colors hover:text-[#98A6D4]">
                    <Icon name="Pencil" size={12} />
                </button>
                <button title="Delete" onClick={async (e) => {
                    e.stopPropagation();
                    if (!confirm('Delete this conversation?')) return;
                    await fetch(`/sessions/${s.id}`, { method: 'DELETE', credentials: 'include' });
                    setSavedSessions(prev => prev.filter(x => x.id !== s.id));
                    setSessionId(null);
                    setSessionMessages([]);
                    setView('home');
                }} className="rounded-full p-1 text-[#A39DB2] transition-colors hover:text-[#D27F7F]">
                    <Icon name="Trash2" size={12} />
                </button>
            </div>
        </div>
    );

    return (
        <div className="relative flex h-screen overflow-hidden bg-[#FDFBF7] text-[#5D576B]">
            <div className="pointer-events-none absolute inset-0">
                <div className="absolute left-[18%] top-0 h-80 w-80 rounded-full bg-[#DCE4FB]/50 blur-3xl" />
                <div className="absolute bottom-[10%] right-[8%] h-72 w-72 rounded-full bg-[#EEF1FB] blur-3xl" />
            </div>
            {isMobileMenuOpen && <div className="fixed inset-0 bg-black/20 backdrop-blur-sm z-40 md:hidden" onClick={() => setIsMobileMenuOpen(false)} />}
            <aside className={`sidebar-transition fixed inset-y-0 left-0 z-50 flex flex-col border-r border-[#EAE6DE] bg-[#F8F6F1]/94 backdrop-blur-xl md:relative md:translate-x-0 ${isMobileMenuOpen ? 'translate-x-0 w-[280px]' : '-translate-x-full w-[280px] md:translate-x-0'} ${!isCollapsed ? 'md:w-[258px]' : 'md:w-[78px]'}`}>
                <div className="flex flex-1 flex-col overflow-y-auto no-scrollbar px-4 pb-6 pt-6 md:px-5">
                    <div className={`mb-6 border-b border-[#E6E1D7] pb-5 ${isCollapsed ? 'md:items-center' : ''}`}>
                        <div className="flex items-start justify-between gap-3">
                            <button onClick={() => setIsMobileMenuOpen(false)} className="rounded-2xl p-2 text-blue-brand hover:bg-white/80 md:hidden"><Icon name="X" size={20} /></button>
                            <div className={`${isCollapsed ? 'md:hidden' : 'block'} flex-1`}>
                                <button onClick={() => setView('home')} className="text-left">
                                    <div className="font-serif text-3xl font-black italic tracking-tight text-blue-brand">LIFEE</div>
                                    <div className="mt-2 text-[10px] font-black uppercase tracking-[0.3em] text-[#AAA3B7]">Your Life & Friend Coach</div>
                                </button>
                            </div>
                            <button onClick={() => setIsCollapsed(!isCollapsed)} className="hidden rounded-2xl p-2 text-blue-brand transition-all hover:bg-white/80 md:block">
                                <Icon name={isCollapsed ? 'PanelLeftOpen' : 'PanelLeftClose'} size={18} />
                            </button>
                        </div>
                        {isCollapsed && (
                            <button onClick={() => setView('home')} className="mt-1 hidden text-xl font-black italic tracking-tight text-blue-brand md:block">
                                L
                            </button>
                        )}
                    </div>

                    <button onClick={handleMobileNewChat} className={`mb-5 flex items-center gap-3 rounded-[18px] border border-[#E8E6E0] bg-white/92 font-bold text-[#4F495E] shadow-[0_10px_24px_rgba(152,166,212,0.08)] transition-all hover:-translate-y-[1px] hover:shadow-[0_14px_30px_rgba(152,166,212,0.12)] ${isCollapsed ? 'md:justify-center md:px-0 md:py-3' : 'px-4 py-3.5 text-sm'}`}>
                        <Icon name="Plus" size={20} className="text-blue-brand" />
                        <span className={isCollapsed ? 'md:hidden' : 'block'}>New Chat</span>
                    </button>

                    <nav className="flex-1 space-y-6">
                        <div className="space-y-1">
                            {!isCollapsed && <div className="px-3 text-[10px] font-black uppercase tracking-[0.3em] text-[#B0A9BA]">Navigate</div>}
                            {primaryItems.map(item => (
                                <button
                                    key={item.id}
                                    onClick={() => { setView(item.view); setIsMobileMenuOpen(false); }}
                                    className={`flex w-full items-center rounded-2xl transition-all ${isCollapsed ? 'md:justify-center md:px-0 md:py-3' : 'gap-3 px-4 py-3 text-sm font-bold'} ${activeView === item.view ? 'bg-[#EAF0FF] text-blue-brand shadow-[0_10px_24px_rgba(152,166,212,0.14)]' : 'text-[#746E84] hover:bg-white/70'}`}
                                >
                                    <Icon name={item.icon} size={18} />
                                    <span className={isCollapsed ? 'md:hidden' : 'block'}>{item.label}</span>
                                </button>
                            ))}
                        </div>

                        <div className="space-y-2">
                            {!isCollapsed && <div className="px-3 text-[10px] font-black uppercase tracking-[0.3em] text-[#B0A9BA]">Conversations</div>}
                            {isCollapsed ? (
                                <button onClick={() => setIsCollapsed(false)} className="hidden rounded-2xl border border-[#E8E6E0] bg-white/80 p-3 text-blue-brand transition-all hover:bg-white md:flex md:justify-center">
                                    <Icon name="MessageSquareText" size={18} />
                                </button>
                            ) : (
                                <div className="space-y-2">
                                    {starredSessions.length > 0 && (
                                        <div className="space-y-2">
                                            <div className="px-3 text-[10px] font-black uppercase tracking-[0.26em] text-[#C3B5A0]">Starred</div>
                                            {starredSessions.map(renderSessionRow)}
                                        </div>
                                    )}
                                    <div className="space-y-2">
                                        <div className="px-3 text-[10px] font-black uppercase tracking-[0.26em] text-[#B0A9BA]">{starredSessions.length > 0 ? 'Recent' : 'Archive'}</div>
                                        {recentSessions.length > 0 ? recentSessions.map(renderSessionRow) : (
                                            <div className="rounded-2xl border border-dashed border-[#E5E1D8] px-4 py-5 text-xs italic text-[#A49CAC]">No conversations yet</div>
                                        )}
                                    </div>
                                </div>
                            )}
                        </div>

                        <div className="space-y-1">
                            {!isCollapsed && <div className="px-3 text-[10px] font-black uppercase tracking-[0.3em] text-[#B0A9BA]">Labs & Tools</div>}
                            {labToolItems.map(item => (
                                <button
                                    key={item.id}
                                    onClick={() => {
                                        if (item.view === 'life-simulator' || item.view === 'decision-lab') {
                                            alert(COMING_SOON_MSG);
                                            return;
                                        }
                                        setView(item.view);
                                        setIsMobileMenuOpen(false);
                                    }}
                                    className={`w-full rounded-2xl transition-all ${isCollapsed ? 'md:px-0 md:py-3 md:text-center' : 'px-4 py-3 text-left text-xs font-bold'} ${activeView === item.view ? 'bg-[#EEF2FF] text-blue-brand' : 'text-[#746E84] hover:bg-white/70'}`}
                                >
                                    <span className={`flex items-center ${isCollapsed ? 'justify-center' : 'gap-3'}`}>
                                        <Icon name={item.icon} size={17} />
                                        <span className={isCollapsed ? 'md:hidden' : 'block'}>{item.label}</span>
                                    </span>
                                </button>
                            ))}
                        </div>
                    </nav>

                    <div className="mt-6 border-t border-[#E6E1D7] pt-5">
                        {!isCollapsed ? (
                            <div className="rounded-[24px] border border-[#E8E6E0] bg-white/88 p-4 shadow-[0_12px_32px_rgba(152,166,212,0.10)]">
                                <div className="flex items-center gap-3">
                                    <div className="flex h-12 w-12 items-center justify-center overflow-hidden rounded-full bg-[#EEF2FF] text-sm font-black text-blue-brand">
                                        {user ? <Icon name="User" size={18} /> : displayName.slice(0, 1).toUpperCase()}
                                    </div>
                                    <div className="min-w-0 flex-1">
                                        <div className="truncate text-sm font-bold text-[#3F3B4B]">{displayName}</div>
                                        <div className="text-[10px] font-black uppercase tracking-[0.22em] text-[#A59DB3]">{user ? 'Signed in' : 'Guest mode'}</div>
                                    </div>
                                </div>

                                <div className="mt-4 space-y-1.5">
                                    {footerItems.map(item => (
                                        <button
                                            key={item.id}
                                            onClick={() => { setView(item.view); setIsMobileMenuOpen(false); }}
                                            className={`flex w-full items-center gap-3 rounded-2xl px-3 py-2.5 text-xs font-bold transition-all ${activeView === item.view ? 'bg-[#EEF2FF] text-blue-brand' : 'text-[#746E84] hover:bg-[#FAF8F4]'}`}
                                        >
                                            <Icon name={item.icon} size={16} />
                                            <span>{item.label}</span>
                                        </button>
                                    ))}
                                    {isAdmin && (
                                        <button onClick={onOpenAdmin} className="flex w-full items-center gap-3 rounded-2xl px-3 py-2.5 text-xs font-bold text-[#746E84] transition-all hover:bg-[#FAF8F4]">
                                            <Icon name="Shield" size={16} />
                                            <span>Admin</span>
                                        </button>
                                    )}
                                </div>

                                <button
                                    onClick={user ? onSignOut : onLogin}
                                    className={`mt-4 w-full rounded-full px-4 py-3 text-[10px] font-black uppercase tracking-[0.24em] transition-all ${user ? 'border border-[#E8E6E0] bg-[#FAF8F4] text-[#746E84] hover:bg-white' : 'bg-blue-brand text-white shadow-[0_10px_26px_rgba(152,166,212,0.26)] hover:bg-[#8795C4]'}`}
                                >
                                    {user ? 'Sign Out' : 'Sign In'}
                                </button>
                            </div>
                        ) : (
                            <div className="hidden items-center gap-2 md:flex md:flex-col">
                                {footerItems.map(item => (
                                    <button
                                        key={item.id}
                                        onClick={() => { setView(item.view); setIsMobileMenuOpen(false); }}
                                        className={`rounded-2xl p-3 transition-all ${activeView === item.view ? 'bg-[#EEF2FF] text-blue-brand' : 'text-[#746E84] hover:bg-white/80'}`}
                                        title={item.label}
                                    >
                                        <Icon name={item.icon} size={18} />
                                    </button>
                                ))}
                                {isAdmin && (
                                    <button onClick={onOpenAdmin} className="rounded-2xl p-3 text-[#746E84] transition-all hover:bg-white/80" title="Admin">
                                        <Icon name="Shield" size={18} />
                                    </button>
                                )}
                                <button onClick={user ? onSignOut : onLogin} className="rounded-full bg-[#EEF2FF] p-3 text-blue-brand transition-all hover:bg-white" title={user ? 'Sign Out' : 'Sign In'}>
                                    <Icon name={user ? 'LogOut' : 'LogIn'} size={18} />
                                </button>
                            </div>
                        )}
                    </div>
                </div>
            </aside>

            <div className="relative z-10 flex flex-1 flex-col overflow-hidden">
                <header className="sticky top-0 z-30 border-b border-[#ECE7DE]/80 bg-[#FDFBF7]/90 px-4 py-3.5 backdrop-blur-md md:px-8">
                    <div className="mx-auto flex w-full max-w-[1480px] items-center justify-between">
                        <div className="flex items-center gap-3">
                            <button onClick={() => setIsMobileMenuOpen(true)} className="rounded-2xl p-2 text-blue-brand transition-all hover:bg-white md:hidden"><Icon name="Menu" size={22} /></button>
                            <button onClick={() => setView('home')} className="text-left md:hidden">
                                <div className="font-serif text-2xl font-black italic tracking-tight text-blue-brand">LIFEE</div>
                            </button>
                            <div className="hidden md:block">
                                <div className="text-[10px] font-black uppercase tracking-[0.3em] text-[#A59DB3]">
                                    {activeView === 'home' ? 'Council Chamber' : activeView.replace(/-/g, ' ')}
                                </div>
                            </div>
                        </div>
                        <div className="flex items-center gap-3 md:gap-4">
                            <button onClick={() => setView('community')} className={`rounded-full border px-4 py-2 text-[10px] font-black uppercase tracking-[0.22em] transition-all ${activeView === 'community' ? 'border-blue-brand bg-[#EEF2FF] text-blue-brand' : 'border-[#E8E6E0] bg-white/80 text-[#746E84] hover:border-[#D7DEEF] hover:text-blue-brand'}`}>Community</button>
                            {user ? (
                                <button onClick={onSignOut} className="flex h-10 w-10 items-center justify-center rounded-full bg-blue-brand text-white shadow-[0_10px_26px_rgba(152,166,212,0.24)] transition-all hover:bg-[#8795C4]"><Icon name="LogOut" size={15} /></button>
                            ) : (
                                <button onClick={onLogin} className="rounded-full bg-blue-brand px-5 py-2.5 text-[10px] font-black uppercase tracking-[0.22em] text-white shadow-[0_10px_26px_rgba(152,166,212,0.24)] transition-all hover:bg-[#8795C4]">Sign In</button>
                            )}
                        </div>
                    </div>
                </header>
                <main key={activeView} ref={scrollContainerRef} className="flex-1 overflow-y-auto no-scrollbar">
                    <div className="mx-auto w-full max-w-[1480px]">{children}</div>
                </main>
            </div>
        </div>
    );
};

// --- Labs & Tools (secondary pages) ---

window.AppLayout = AppLayout;
