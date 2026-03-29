(() => {
  // Settings components + view (extracted from index.html)
  const { useEffect, useState } = React;
  const html = htm.bind(React.createElement);
  window.LIFEE_VIEWS = window.LIFEE_VIEWS || {};

  const AccountModal = ({ isOpen, onClose, user, onSignOut, userAvatar, onUserAvatarChange }) => {
    const [displayName, setDisplayName] = useState('');
    const [loading, setLoading] = useState(false);
    const [status, setStatus] = useState('');

    useEffect(() => {
      let mounted = true;
      const load = async () => {
        if (!isOpen || !user) return;
        setStatus('');
        const { data } = await supabaseClient.from('profiles').select('display_name').eq('id', user.id).maybeSingle();
        if (!mounted) return;
        setDisplayName(data?.display_name || user.user_metadata?.name || '');
      };
      load();
      return () => { mounted = false; };
    }, [isOpen, user?.id]);

    if (!isOpen) return null;

    const saveProfile = async () => {
      if (!user) return;
      setLoading(true);
      setStatus('');
      try {
        const next = (displayName || '').trim() || null;
        const { error } = await supabaseClient
          .from('profiles')
          .upsert({ id: user.id, email: user.email, display_name: next }, { onConflict: 'id' });
        if (error) throw error;
        setStatus('Saved');
      } catch (e) {
        setStatus(e?.message || 'Save failed');
      } finally {
        setLoading(false);
      }
    };

    const resetPassword = async () => {
      if (!user?.email) return;
      setLoading(true);
      setStatus('');
      try {
        const { error } = await supabaseClient.auth.resetPasswordForEmail(user.email, { redirectTo: window.location.href });
        if (error) throw error;
        setStatus('Password reset email sent');
      } catch (e) {
        setStatus(e?.message || 'Send failed');
      } finally {
        setLoading(false);
      }
    };

    return html`
      <div className="fixed inset-0 z-50 flex items-center justify-center">
        <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" onClick=${onClose}></div>
        <div className="relative w-full max-w-lg bg-white rounded-[36px] shadow-2xl border border-[#F0EDEA] p-8 md:p-10 animate-in">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-xl font-serif italic text-[#1A1A1A]">Manage account</h2>
            <button onClick=${onClose} className="text-xs font-bold uppercase tracking-widest opacity-40 hover:opacity-100">
              <${Icon} name="X" size=${14} />
            </button>
          </div>
          <div className="space-y-5">
            <div className="p-4 rounded-3xl bg-[#FDFBF7] border border-[#F0EDEA]">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <div className="text-[10px] uppercase tracking-[0.2em] opacity-50 mb-2">Avatar</div>
                  <div className="text-xs opacity-60">Upload an image or use a random default icon (used as your chat avatar).</div>
                </div>
                <div className="w-14 h-14 rounded-2xl overflow-hidden border border-[#F0EDEA] bg-white shadow-sm shrink-0">
                  <${AvatarDisplay} avatar=${userAvatar || '👤'} className="w-full h-full text-3xl" />
                </div>
              </div>
              <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-3">
                <label className="py-3 px-4 bg-white border border-[#E8E6E0] rounded-full font-bold uppercase text-[10px] tracking-[0.2em] hover:shadow-md cursor-pointer text-center">
                  Upload avatar
                  <input
                    type="file"
                    accept="image/*"
                    className="hidden"
                    disabled=${loading}
                    onChange=${async (e) => {
                      const file = e.target.files?.[0];
                      if (!file) return;
                      setStatus('');
                      try {
                        const url = await fileToDataURL(file);
                        saveUserAvatar(url);
                        onUserAvatarChange?.(url);
                        setStatus('Avatar updated (saved locally)');
                      } catch (err) {
                        setStatus(err?.message || 'Avatar update failed');
                      } finally {
                        e.target.value = '';
                      }
                    }}
                  />
                </label>
                <button
                  type="button"
                  disabled=${loading}
                  onClick=${() => {
                    setStatus('');
                    saveUserAvatar(null);
                    const next = rotateUserDefaultAvatar();
                    onUserAvatarChange?.(next);
                    setStatus('Switched to a random default icon');
                  }}
                  className="py-3 bg-white border border-[#E8E6E0] rounded-full font-bold uppercase text-[10px] tracking-[0.2em] hover:shadow-md disabled:opacity-40"
                >
                  Random default
                </button>
              </div>
            </div>

            <div className="p-4 rounded-3xl bg-[#FDFBF7] border border-[#F0EDEA]">
              <div className="text-[10px] uppercase tracking-[0.2em] opacity-50 mb-2">Email</div>
              <div className="text-sm font-bold text-[#1A1A1A] break-all">${user?.email || '-'}</div>
            </div>

            <div className="space-y-2">
              <div className="text-[10px] uppercase tracking-[0.2em] opacity-50">Display name</div>
              <input
                className="w-full p-4 bg-[#FDFBF7] rounded-3xl border border-[#F0EDEA] transition-all focus-blue-brand"
                value=${displayName}
                onChange=${(e) => setDisplayName(e.target.value)}
                placeholder="Your name..."
              />
              <button onClick=${saveProfile} disabled=${loading} className="w-full py-4 bg-blue-brand text-white rounded-full font-bold uppercase text-xs tracking-[0.2em] shadow-xl disabled:opacity-40">
                ${loading ? 'Working...' : 'Save'}
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <button onClick=${resetPassword} disabled=${loading} className="py-4 bg-white border border-[#E8E6E0] rounded-full font-bold uppercase text-xs tracking-[0.2em] hover:shadow-md disabled:opacity-40">
                Reset password
              </button>
              <button onClick=${onSignOut} className="py-4 bg-[#1A1A1A] text-white rounded-full font-bold uppercase text-xs tracking-[0.2em] shadow-xl">
                Sign out
              </button>
            </div>

            ${status ? html`<div className="text-xs text-blue-brand">${status}</div>` : null}
          </div>
        </div>
      </div>
    `;
  };

  const ShareChatModal = ({ isOpen, onClose, shareText }) => {
    const [status, setStatus] = useState('');
    if (!isOpen) return null;

    const doCopy = async () => {
      setStatus('');
      const ok = await copyToClipboard(shareText || '');
      setStatus(ok ? 'Copied to clipboard' : 'Copy failed (please copy manually)');
    };

    const doDownload = () => {
      try {
        const blob = new Blob([shareText || ''], { type: 'text/plain;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `lifee-chat-${Date.now()}.txt`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
        setStatus('Downloaded');
      } catch (e) {
        setStatus(e?.message || 'Download failed');
      }
    };

    return html`
      <div className="fixed inset-0 z-50 flex items-center justify-center">
        <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" onClick=${onClose}></div>
        <div className="relative w-full max-w-3xl bg-white rounded-[36px] shadow-2xl border border-[#F0EDEA] p-8 md:p-10 animate-in">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-xl font-serif italic text-[#1A1A1A]">Share chat history</h2>
            <button onClick=${onClose} className="text-xs font-bold uppercase tracking-widest opacity-40 hover:opacity-100">
              <${Icon} name="X" size=${14} />
            </button>
          </div>
          <div className="space-y-4">
            <textarea
              className="w-full h-72 md:h-80 p-5 bg-[#FDFBF7] rounded-3xl border border-[#F0EDEA] text-xs md:text-sm leading-relaxed focus-blue-brand no-scrollbar"
              readOnly
              value=${shareText || ''}
            />
            <div className="flex flex-col md:flex-row gap-3">
              <button onClick=${doCopy} className="flex-1 py-4 bg-blue-brand text-white rounded-full font-bold uppercase text-xs tracking-[0.2em] shadow-xl">
                Copy
              </button>
              <button onClick=${doDownload} className="flex-1 py-4 bg-white border border-[#E8E6E0] rounded-full font-bold uppercase text-xs tracking-[0.2em] hover:shadow-md">
                Download
              </button>
            </div>
            ${status ? html`<div className="text-xs text-blue-brand">${status}</div>` : null}
          </div>
        </div>
      </div>
    `;
  };

  const SettingsView = ({
    user,
    isAdmin,
    onOpenAdmin,
    onSignOut,
    onBack,
    onOpenPersona,
    onOpenCommunityPersona,
    shareText,
    userAvatar,
    onUserAvatarChange
  }) => {
    const [accountOpen, setAccountOpen] = useState(false);
    const [shareOpen, setShareOpen] = useState(false);

    return html`
      <div className="p-6 md:p-12 max-w-[1100px] mx-auto animate-in space-y-10">
        <div className="flex items-center justify-between">
          <button onClick=${onBack} className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest opacity-40 hover:opacity-100 transition-all">
            <${Icon} name="ChevronLeft" size=${14} /> Back
          </button>
          <h2 className="text-2xl md:text-4xl font-serif italic tracking-tight text-[#1A1A1A]">Settings</h2>
          <div className="w-14" />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 md:gap-6">
          <button onClick=${() => setAccountOpen(true)} className="group text-left bg-white p-7 rounded-[36px] border border-[#F0EDEA] shadow-sm hover:shadow-xl hover:-translate-y-0.5 transition-all">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 rounded-2xl bg-[#FDFBF7] border border-[#F0EDEA] flex items-center justify-center text-blue-brand group-hover:bg-blue-brand/10 transition-colors">
                <${Icon} name="UserCog" size=${18} />
              </div>
              <div className="text-xs font-black uppercase tracking-[0.2em] opacity-60">Manage account</div>
            </div>
            <div className="text-sm italic opacity-60 leading-relaxed">Update your display name, reset your password, and sign out.</div>
            <div className="mt-5 text-[10px] font-black uppercase tracking-widest opacity-30 group-hover:text-blue-brand transition-colors">Open →</div>
          </button>

          <button onClick=${() => setShareOpen(true)} className="group text-left bg-white p-7 rounded-[36px] border border-[#F0EDEA] shadow-sm hover:shadow-xl hover:-translate-y-0.5 transition-all">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 rounded-2xl bg-[#FDFBF7] border border-[#F0EDEA] flex items-center justify-center text-blue-brand group-hover:bg-blue-brand/10 transition-colors">
                <${Icon} name="Share2" size=${18} />
              </div>
              <div className="text-xs font-black uppercase tracking-[0.2em] opacity-60">Share chat history</div>
            </div>
            <div className="text-sm italic opacity-60 leading-relaxed">Generate a shareable chat summary you can copy or download.</div>
            <div className="mt-5 text-[10px] font-black uppercase tracking-widest opacity-30 group-hover:text-blue-brand transition-colors">Open →</div>
          </button>

          <div className="group text-left bg-white p-7 rounded-[36px] border border-[#F0EDEA] shadow-sm hover:shadow-xl hover:-translate-y-0.5 transition-all flex flex-col">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 rounded-2xl bg-[#FDFBF7] border border-[#F0EDEA] flex items-center justify-center text-blue-brand group-hover:bg-blue-brand/10 transition-colors">
                <${Icon} name="Users" size=${18} />
              </div>
              <div className="text-xs font-black uppercase tracking-[0.2em] opacity-60">Persona</div>
            </div>
            <div className="text-sm italic opacity-60 leading-relaxed">Manage your Voices / browse community Personas.</div>
            <div className="mt-auto pt-5 flex flex-col gap-2">
              <button onClick=${onOpenPersona} className="w-full py-3 bg-blue-brand text-white rounded-full font-bold uppercase text-[10px] tracking-[0.2em] shadow-xl">
                Manage personas
              </button>
              <button onClick=${onOpenCommunityPersona} className="w-full py-3 bg-white border border-[#E8E6E0] rounded-full font-bold uppercase text-[10px] tracking-[0.2em] hover:shadow-md">
                Community persona
              </button>
              ${isAdmin ? html`
                <button onClick=${onOpenAdmin} className="w-full py-3 bg-[#1A1A1A] text-white rounded-full font-bold uppercase text-[10px] tracking-[0.2em] shadow-xl">
                  Admin panel
                </button>
              ` : null}
            </div>
          </div>
        </div>

        <${AccountModal}
          isOpen=${accountOpen}
          onClose=${() => setAccountOpen(false)}
          user=${user}
          onSignOut=${onSignOut}
          userAvatar=${userAvatar}
          onUserAvatarChange=${onUserAvatarChange}
        />
        <${ShareChatModal}
          isOpen=${shareOpen}
          onClose=${() => setShareOpen(false)}
          shareText=${shareText}
        />
      </div>
    `;
  };

  window.LIFEE_VIEWS.settings = (props) => html`<${SettingsView} ...${props} />`;
})();

