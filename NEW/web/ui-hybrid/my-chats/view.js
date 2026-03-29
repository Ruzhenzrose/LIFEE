(() => {
  // My Chats view (extracted from index.html)
  const html = htm.bind(React.createElement);
  window.LIFEE_VIEWS = window.LIFEE_VIEWS || {};

  window.LIFEE_VIEWS.myChats = ({
    onBack,
    refreshChatSessions,
    chatSessionsLoading,
    chatSessions,
    chatDetailSession,
    loadSessionDetail,
    deleteSession,
    uploadChatToCommunity,
    chatDetailMessages,
    chatDetailSummaries,
    buildShareTextFromSession,
    copyToClipboard,
    setChatStatus,
    chatStatus
  }) => {
    return html`
      <div className="p-6 md:p-12 max-w-[1300px] mx-auto animate-in space-y-8">
        <div className="flex items-center justify-between">
          <button
            onClick=${onBack}
            className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest opacity-40 hover:opacity-100 transition-all"
          >
            <${Icon} name="ChevronLeft" size=${14} /> Back
          </button>
          <h2 className="text-2xl md:text-4xl font-serif italic tracking-tight text-[#1A1A1A]">My Chats</h2>
          <button onClick=${refreshChatSessions} className="text-[10px] font-black uppercase tracking-widest text-blue-brand">Refresh</button>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="md:col-span-1 space-y-4">
            <div className="text-[10px] uppercase tracking-[0.2em] opacity-50">Sessions</div>
            <div className="bg-white rounded-[28px] border border-[#F0EDEA] p-4 space-y-3 max-h-[60vh] overflow-y-auto no-scrollbar">
              ${chatSessionsLoading ? html`<div className="text-xs opacity-40">Loading...</div>` : null}
              ${!chatSessionsLoading && (chatSessions || []).length === 0 ? html`<div className="text-xs opacity-40">No chats yet</div>` : null}
              ${(chatSessions || []).map(s => html`
                <div
                  key=${s.id}
                  className=${`p-3 rounded-2xl border ${chatDetailSession?.id === s.id ? 'border-blue-brand bg-blue-brand/5' : 'border-[#F0EDEA]'} transition-all`}
                >
                  <div className="text-xs font-bold text-[#1A1A1A] truncate">${s.title || 'New Chat'}</div>
                  <div className="text-[10px] opacity-40 mt-1">Updated: ${new Date(s.updated_at || s.latest_message_at || Date.now()).toLocaleString()}</div>
                  <div className="mt-3 flex gap-2">
                    <button
                      onClick=${() => loadSessionDetail?.(s)}
                      className="flex-1 py-2 bg-white border border-[#E8E6E0] rounded-full text-[10px] font-bold uppercase tracking-[0.2em] hover:shadow-md"
                    >
                      View
                    </button>
                    <button
                      onClick=${() => deleteSession?.(s)}
                      className="flex-1 py-2 bg-[#FDF1F1] border border-[#F7D7D7] rounded-full text-[10px] font-bold uppercase tracking-[0.2em] hover:shadow-md text-[#C97A7A]"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              `)}
            </div>
          </div>

          <div className="md:col-span-2 space-y-4">
            <div className="text-[10px] uppercase tracking-[0.2em] opacity-50">Details & Actions</div>
            <div className="bg-white rounded-[28px] border border-[#F0EDEA] p-6 space-y-5 min-h-[40vh]">
              ${!chatDetailSession ? html`<div className="text-xs opacity-40">Select a chat to view details.</div>` : null}
              ${chatDetailSession ? html`
                <${React.Fragment}>
                  <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
                    <div>
                      <div className="text-lg font-bold text-[#1A1A1A]">${chatDetailSession.title || 'New Chat'}</div>
                      <div className="text-[10px] opacity-40">Session ID: ${chatDetailSession.id}</div>
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick=${() => uploadChatToCommunity?.(chatDetailSession, chatDetailMessages, chatDetailSummaries)}
                        className="px-4 py-2 bg-blue-brand text-white rounded-full text-[10px] font-black uppercase tracking-[0.2em] shadow-lg"
                      >
                        Upload to Community
                      </button>
                      <button
                        onClick=${() => {
                          const text = buildShareTextFromSession?.(chatDetailSession.title, chatDetailMessages, chatDetailSummaries) || '';
                          copyToClipboard?.(text);
                          setChatStatus?.('Copied');
                        }}
                        className="px-4 py-2 bg-white border border-[#E8E6E0] rounded-full text-[10px] font-black uppercase tracking-[0.2em] hover:shadow-md"
                      >
                        Copy Text
                      </button>
                    </div>
                  </div>
                  <textarea
                    className="w-full h-72 md:h-80 p-5 bg-[#FDFBF7] rounded-3xl border border-[#F0EDEA] text-xs md:text-sm leading-relaxed focus-blue-brand no-scrollbar"
                    readOnly
                    value=${buildShareTextFromSession?.(chatDetailSession.title, chatDetailMessages, chatDetailSummaries) || ''}
                  />
                  ${chatStatus ? html`<div className="text-xs text-blue-brand">${chatStatus}</div>` : null}
                </${React.Fragment}>
              ` : null}
            </div>
          </div>
        </div>
      </div>
    `;
  };
})();

