(() => {
  // My Personas view (extracted from index.html)
  const html = htm.bind(React.createElement);
  window.LIFEE_VIEWS = window.LIFEE_VIEWS || {};

  window.LIFEE_VIEWS.myPersonas = ({
    onBack,
    displayPersonas,
    favoritePersonas,
    setEditPersona,
    uploadPersonaToCommunity,
    toggleFavoritePersona,
    goToCommunity,
    onNewPersona,
    chatStatus
  }) => {
    const myPersonas = (displayPersonas || []).filter(p => p.category === 'CUSTOM' || String(p.id || '').startsWith('custom-'));
    return html`
      <div className="p-6 md:p-12 max-w-[1300px] mx-auto animate-in space-y-10">
        <div className="flex items-center justify-between">
          <button
            onClick=${onBack}
            className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest opacity-40 hover:opacity-100 transition-all"
          >
            <${Icon} name="ChevronLeft" size=${14} /> Back
          </button>
          <h2 className="text-2xl md:text-4xl font-serif italic tracking-tight text-[#1A1A1A]">My Personas</h2>
          <button onClick=${onNewPersona} className="text-[10px] font-black uppercase tracking-widest text-blue-brand">New Persona</button>
        </div>

        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <div className="text-[10px] uppercase tracking-[0.2em] opacity-50">My Created Personas</div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
            ${myPersonas.length === 0 ? html`<div className="text-xs opacity-40">No custom personas</div>` : null}
            ${myPersonas.map(p => html`
              <div key=${p.id} className="relative p-6 bg-white rounded-[36px] border border-[#F0EDEA] shadow-sm hover:shadow-xl transition-all flex flex-col">
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-12 h-12 rounded-2xl bg-[#FDFBF7] border border-[#F0EDEA] flex items-center justify-center">
                    <${AvatarDisplay} avatar=${p.avatar} className="w-full h-full text-2xl" />
                  </div>
                  <div>
                    <div className="text-sm font-black text-[#1A1A1A]">${p.name}</div>
                    <div className="text-[9px] uppercase font-black tracking-widest text-blue-brand/60">${p.role}</div>
                  </div>
                </div>
                <p className="text-xs italic opacity-50 leading-relaxed line-clamp-3">“${p.worldview}”</p>
                <div className="mt-5 pt-5 border-t border-[#F0EDEA] flex gap-2">
                  <button
                    onClick=${() => setEditPersona?.(p)}
                    className="flex-1 py-2 bg-white border border-[#E8E6E0] rounded-full text-[10px] font-black uppercase tracking-[0.2em] hover:shadow-md"
                  >
                    Edit
                  </button>
                  <button
                    onClick=${() => uploadPersonaToCommunity?.(p)}
                    className="flex-1 py-2 bg-blue-brand text-white rounded-full text-[10px] font-black uppercase tracking-[0.2em] shadow-lg"
                  >
                    Upload
                  </button>
                </div>
              </div>
            `)}
          </div>
        </div>

        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <div className="text-[10px] uppercase tracking-[0.2em] opacity-50">Favorite Personas</div>
            <button onClick=${goToCommunity} className="text-[10px] font-black uppercase tracking-widest text-blue-brand">Go to Community</button>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
            ${(favoritePersonas || []).length === 0 ? html`<div className="text-xs opacity-40">No favorites yet</div>` : null}
            ${(favoritePersonas || []).map(p => html`
              <div key=${p.id} className="relative p-6 bg-white rounded-[36px] border border-[#F0EDEA] shadow-sm hover:shadow-xl transition-all flex flex-col">
                <button
                  onClick=${() => toggleFavoritePersona?.(p)}
                  className="absolute top-4 right-4 w-8 h-8 rounded-full border border-[#E8E6E0] flex items-center justify-center text-[#5D576B]/40 hover:text-blue-brand"
                >
                  <${Icon} name="X" size=${14} />
                </button>
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-12 h-12 rounded-2xl bg-[#FDFBF7] border border-[#F0EDEA] flex items-center justify-center">
                    <${AvatarDisplay} avatar=${p.avatar} className="w-full h-full text-2xl" />
                  </div>
                  <div>
                    <div className="text-sm font-black text-[#1A1A1A]">${p.name}</div>
                    <div className="text-[9px] uppercase font-black tracking-widest text-blue-brand/60">${p.role}</div>
                  </div>
                </div>
                <p className="text-xs italic opacity-50 leading-relaxed line-clamp-3">“${p.worldview}”</p>
              </div>
            `)}
          </div>
        </div>

        ${chatStatus ? html`<div className="text-xs text-blue-brand">${chatStatus}</div>` : null}
      </div>
    `;
  };
})();

