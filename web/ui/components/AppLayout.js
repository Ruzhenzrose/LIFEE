const { useState, useEffect, useRef } = React;
const { Icon } = window;

const AppLayout = ({ children, activeView, setView, user, isAdmin, onOpenAdmin, onLogin, onSignOut, onNewChat }) => {
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

    return (
        <div className="flex h-screen overflow-hidden bg-[#FDFBF7]">
            {isMobileMenuOpen && <div className="fixed inset-0 bg-black/20 backdrop-blur-sm z-40 md:hidden" onClick={() => setIsMobileMenuOpen(false)} />}
            <aside className={`sidebar-transition fixed inset-y-0 left-0 z-50 bg-[#F8F6F2] border-r border-[#E8E6E0] flex flex-col p-4 md:relative md:translate-x-0 ${isMobileMenuOpen ? 'translate-x-0 w-[280px]' : '-translate-x-full w-[280px] md:translate-x-0'} ${!isCollapsed ? 'md:w-[260px]' : 'md:w-[72px]'}`}>
                <div className="flex-1 overflow-y-auto no-scrollbar flex flex-col">
                    <button onClick={() => setIsCollapsed(!isCollapsed)} className="p-3 mb-4 rounded-xl hover:bg-white/60 transition-all text-blue-brand self-start hidden md:block"><Icon name="Menu" size={20} /></button>
                    <button onClick={() => setIsMobileMenuOpen(false)} className="p-3 mb-4 rounded-xl hover:bg-white/60 text-blue-brand md:hidden self-end"><Icon name="X" size={20} /></button>
                    <button onClick={handleMobileNewChat} className={`flex items-center gap-3 bg-white border border-[#E8E6E0] rounded-2xl shadow-sm hover:shadow-md transition-all font-bold text-[#5D576B] ${isCollapsed ? 'md:p-3 md:justify-center mb-8' : 'px-6 py-4 mb-8 text-sm'}`}>
                        <Icon name="Plus" size={20} className="text-blue-brand" />
                        <span className={isCollapsed ? 'md:hidden' : 'block'}>New Chat</span>
                    </button>
                    <nav className="space-y-1">
                        <div className={`text-[10px] uppercase font-bold tracking-widest opacity-30 px-4 mb-2 ${isCollapsed ? 'md:hidden' : 'block'}`}>Archives</div>
                        <button className={`w-full text-left rounded-xl hover:bg-white/60 transition-colors flex items-center ${isCollapsed ? 'md:p-3 md:justify-center' : 'px-4 py-3 text-xs opacity-60 italic truncate'}`}>
                            <Icon name="MessageSquare" size={14} className={isCollapsed ? "md:text-blue-brand" : "mr-2 opacity-40"} />
                            <span className={isCollapsed ? 'md:hidden' : 'block'}>"Recent thoughts..."</span>
                        </button>

                        <div className={`text-[10px] uppercase font-bold tracking-widest opacity-30 px-4 mt-6 mb-2 ${isCollapsed ? 'md:hidden' : 'block'}`}>Labs & Tools</div>
                        {labToolItems.map(item => (
                            <button
                                key={item.id}
                                onClick={() => { setView(item.view); setIsMobileMenuOpen(false); }}
                                className={`w-full text-left rounded-xl transition-all flex items-center ${isCollapsed ? 'md:p-3 md:justify-center' : 'px-4 py-3 text-xs font-bold'} ${activeView === item.view ? 'bg-blue-brand/10 text-blue-brand shadow-sm' : 'hover:bg-white/60 opacity-60'}`}
                            >
                                <Icon name={item.icon} size={isCollapsed ? 18 : 16} className={activeView === item.view ? "text-blue-brand" : (isCollapsed ? "opacity-60" : "mr-2 opacity-60")} />
                                {!isCollapsed && <span>{item.label}</span>}
                            </button>
                        ))}
                    </nav>
                </div>
                <div className="pt-4 border-t border-[#E8E6E0] space-y-1">
                    {footerItems.map(item => (
                        <button
                            key={item.id}
                            onClick={() => { setView(item.view); setIsMobileMenuOpen(false); }}
                            className={`w-full flex items-center font-bold hover:bg-white/60 rounded-xl transition-all ${isCollapsed ? 'p-3 justify-center' : 'gap-3 px-4 py-2.5 text-xs'} ${activeView === item.view ? 'text-blue-brand' : ''}`}
                        >
                            <Icon name={item.icon} size={18} />
                            <span className={isCollapsed ? 'md:hidden' : 'block'}>{item.label}</span>
                        </button>
                    ))}
                    {isAdmin && (
                        <button onClick={onOpenAdmin} className={`w-full flex items-center font-bold hover:bg-white/60 rounded-xl transition-all ${isCollapsed ? 'p-3 justify-center' : 'gap-3 px-4 py-2.5 text-xs'}`}>
                            <Icon name="Shield" size={18} />
                            <span className={isCollapsed ? 'md:hidden' : 'block'}>Admin</span>
                        </button>
                    )}
                </div>
            </aside>

            <div className="flex-1 flex flex-col overflow-hidden relative">
                <header className="h-16 flex items-center justify-between px-4 md:px-8 bg-[#FDFBF7]/80 backdrop-blur-md z-30 sticky top-0 border-b border-[#E8E6E0]/30">
                    <div className="flex items-center gap-3">
                        <button onClick={() => setIsMobileMenuOpen(true)} className="p-2 md:hidden text-blue-brand"><Icon name="Menu" size={24} /></button>
                        <div className="flex items-center gap-2 cursor-pointer" onClick={() => setView('home')}><span className="font-serif italic font-black text-blue-brand tracking-tighter text-xl md:text-2xl">LIFEE</span></div>
                    </div>
                    <div className="flex items-center gap-3 md:gap-8">
                        <button onClick={() => setView('community')} className={`text-[9px] md:text-[10px] font-black uppercase tracking-[0.1em] md:tracking-[0.2em] transition-all hover:text-blue-brand ${activeView === 'community' ? 'text-blue-brand underline underline-offset-8 font-bold' : 'text-[#5D576B]/60'}`}>Community</button>
                        {user ? (
                            <button onClick={onSignOut} className="w-8 h-8 md:w-9 md:h-9 rounded-full bg-blue-brand text-white border-2 border-white shadow-lg flex items-center justify-center"><Icon name="LogOut" size={14} /></button>
                        ) : (
                            <button onClick={onLogin} className="px-4 py-1.5 md:px-8 md:py-2.5 bg-blue-brand text-white rounded-full text-[9px] md:text-[10px] font-black uppercase tracking-widest shadow-lg active:scale-95 transition-all hover:bg-[#8795c4]">Sign In</button>
                        )}
                    </div>
                </header>
                <main key={activeView} className="flex-1 overflow-y-auto no-scrollbar"><div className="w-full max-w-[1400px] mx-auto">{children}</div></main>
            </div>
        </div>
    );
};

// --- Labs & Tools (secondary pages) ---

window.AppLayout = AppLayout;
