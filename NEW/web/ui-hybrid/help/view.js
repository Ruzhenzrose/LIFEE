(() => {
  // Help view (extracted from index.html)
  const html = htm.bind(React.createElement);
  window.LIFEE_VIEWS = window.LIFEE_VIEWS || {};

  window.LIFEE_VIEWS.help = ({ onBack }) => {
    return html`
      <div className="p-6 md:p-12 max-w-[900px] mx-auto animate-in space-y-8">
        <div className="flex items-center justify-between">
          <button
            onClick=${onBack}
            className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest opacity-40 hover:opacity-100 transition-all"
          >
            <${Icon} name="ChevronLeft" size=${14} /> Back
          </button>
          <h2 className="text-2xl md:text-4xl font-serif italic tracking-tight text-[#1A1A1A]">Help</h2>
          <div className="w-14" />
        </div>
        <div className="bg-white rounded-[36px] border border-[#F0EDEA] p-6 md:p-10 shadow-sm space-y-6">
          <div className="text-[10px] font-black uppercase tracking-[0.25em] opacity-40">Quick guide</div>
          <div className="space-y-4 text-sm leading-relaxed">
            <div>
              <div className="font-bold text-[#1A1A1A] mb-1">How do I start a conversation?</div>
              <div className="opacity-70">On the home screen, fill in the scenario, invite at least two Voices, then click “Commence Dialogue” at the bottom.</div>
            </div>
            <div>
              <div className="font-bold text-[#1A1A1A] mb-1">How do I change a Persona avatar?</div>
              <div className="opacity-70">Open a Persona’s detail page: use “Card background” on the left to upload a cover image; click the avatar icon below to open “Icon editor” to upload/choose an icon (used in the list top-left).</div>
            </div>
            <div>
              <div className="font-bold text-[#1A1A1A] mb-1">How do I export chat history?</div>
              <div className="opacity-70">Go to Settings → Share chat history to copy or download.</div>
            </div>
          </div>
          <div className="pt-4 border-t border-[#F0EDEA] text-xs opacity-60">
            For more detailed help, you can extend the entries in <code className="px-1 py-0.5 rounded bg-[#FDFBF7] border border-[#F0EDEA]">web/ui/data/navigation.js</code>.
          </div>
        </div>
      </div>
    `;
  };
})();

