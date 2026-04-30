const { useState, useEffect, useRef } = React;

const AuthModal = ({ isOpen, onClose, onAuthed, onGuest }) => {
    const [mode, setMode] = useState('login');
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [loading, setLoading] = useState(false);
    const [message, setMessage] = useState('');
    const [otpSent, setOtpSent] = useState(false);
    const [otpCode, setOtpCode] = useState('');
    // Turnstile 已移除：默认 true，UI 直接进入登录/注册表单
    const [humanVerified, setHumanVerified] = useState(true);
    const turnstileRef = useRef(null);
    const widgetIdRef = useRef(null);

    // 每次打开先重置到登录视图
    useEffect(() => {
        if (isOpen) {
            setMode('login');
            setOtpSent(false);
            setOtpCode('');
            setPassword('');
            setMessage('');
            setLoading(false);
        }
    }, [isOpen]);

    // 渲染 Turnstile widget
    useEffect(() => {
        if (!isOpen || humanVerified) return;
        const renderWidget = () => {
            if (turnstileRef.current && window.turnstile && widgetIdRef.current === null) {
                widgetIdRef.current = window.turnstile.render(turnstileRef.current, {
                    sitekey: TURNSTILE_SITEKEY,
                    callback: async (token) => {
                        const result = await verifyHumanTokenWithServer(token);
                        if (result.ok) {
                            setHumanVerified(true);
                            if (result.bypassed) {
                                setMessage('本地预览模式：已跳过服务器验证。');
                            }
                        } else {
                            setMessage(result.message || '人机验证失败，请重试。');
                        }
                    },
                    theme: 'light',
                });
            }
        };
        // turnstile script 可能还没加载完
        if (window.turnstile) renderWidget();
        else {
            const timer = setInterval(() => {
                if (window.turnstile) { clearInterval(timer); renderWidget(); }
            }, 200);
            return () => clearInterval(timer);
        }
        return () => {
            if (widgetIdRef.current !== null && window.turnstile) {
                window.turnstile.remove(widgetIdRef.current);
                widgetIdRef.current = null;
            }
        };
    }, [isOpen, humanVerified]);

    if (!isOpen) return null;

    const handleAuth = async () => {
        setLoading(true);
        setMessage('');
        try {
            if (mode === 'login') {
                const { data, error } = await supabaseClient.auth.signInWithPassword({ email, password });
                if (error) throw error;
                if (data?.user) onAuthed(data.user);
            } else if (otpSent) {
                // 验证 OTP 码
                const { data, error } = await supabaseClient.auth.verifyOtp({ email, token: otpCode, type: 'signup' });
                if (error) throw error;
                if (data?.user) onAuthed(data.user);
            } else {
                // 注册 → 发送验证码
                const { data, error } = await supabaseClient.auth.signUp({ email, password });
                if (error) throw error;
                setOtpSent(true);
                setMessage('验证码已发送到你的邮箱。');
            }
        } catch (err) {
            setMessage(err?.message || '操作失败，请稍后重试。');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
            <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" onClick={onClose}></div>
            <div className="relative w-full max-w-md bg-white rounded-[36px] shadow-2xl border border-[#F0EDEA] p-10 animate-in">
                <div className="flex items-center justify-between mb-8">
                    <h2 className="text-xl font-serif italic text-[#1A1A1A]">{mode === 'login' ? '登录' : '注册'}</h2>
                    <button onClick={onClose} className="text-xs font-bold uppercase tracking-widest opacity-40 hover:opacity-100">
                        <Icon name="X" size={14} />
                    </button>
                </div>
                {!humanVerified ? (
                    <div className="flex flex-col items-center gap-4 py-6">
                        <p className="text-sm text-neutral-500">请完成人机验证</p>
                        <div ref={turnstileRef}></div>
                        {message && (
                            <div className="w-full text-xs text-[#C97A7A] bg-[#FDF1F1] border border-[#F7D7D7] px-4 py-3 rounded-2xl">{message}</div>
                        )}
                    </div>
                ) : (
                <div className="space-y-4">
                    {otpSent ? (
                        <>
                            <p className="text-sm text-center text-neutral-500">请输入发送到 <strong>{email}</strong> 的 6 位验证码</p>
                            <input type="text" placeholder="000000" maxLength={6} className="w-full p-4 bg-[#FDFBF7] rounded-3xl border border-[#F0EDEA] text-center text-2xl tracking-[0.5em] font-mono" value={otpCode} onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, ''))} />
                            {message && (
                                <div className={`text-xs px-4 py-3 rounded-2xl ${message.includes('已发送') ? 'text-[#5a9a5a] bg-[#f1fdf1] border border-[#d7f7d7]' : 'text-[#C97A7A] bg-[#FDF1F1] border border-[#F7D7D7]'}`}>{message}</div>
                            )}
                            <button onClick={handleAuth} disabled={loading || otpCode.length !== 6} className="w-full py-4 bg-blue-brand text-white rounded-full font-bold uppercase text-xs tracking-[0.2em] shadow-xl disabled:opacity-40">
                                {loading ? '验证中...' : '验证'}
                            </button>
                            <button onClick={() => { setOtpSent(false); setOtpCode(''); setMessage(''); }} className="w-full text-xs uppercase tracking-[0.2em] opacity-50 hover:opacity-100">返回</button>
                        </>
                    ) : (
                    <>
                    <input type="email" placeholder="邮箱" className="w-full p-4 bg-[#FDFBF7] rounded-3xl border border-[#F0EDEA] transition-all focus-blue-brand" value={email} onChange={(e) => setEmail(e.target.value)} />
                    <input type="password" placeholder="密码" className="w-full p-4 bg-[#FDFBF7] rounded-3xl border border-[#F0EDEA] transition-all focus-blue-brand" value={password} onChange={(e) => setPassword(e.target.value)} />
                    {message && (
                        <div className="text-xs text-[#C97A7A] bg-[#FDF1F1] border border-[#F7D7D7] px-4 py-3 rounded-2xl">{message}</div>
                    )}
                    <button onClick={handleAuth} disabled={loading || !email || !password} className="w-full py-4 bg-blue-brand text-white rounded-full font-bold uppercase text-xs tracking-[0.2em] shadow-xl disabled:opacity-40">
                        {loading ? '处理中...' : (mode === 'login' ? '登录' : '注册')}
                    </button>
                    <button onClick={() => setMode(mode === 'login' ? 'signup' : 'login')} className="w-full text-xs uppercase tracking-[0.2em] opacity-50 hover:opacity-100">
                        {mode === 'login' ? '还没有账号？注册' : '已有账号？登录'}
                    </button>
                    </>
                    )}
                    <div className="flex items-center gap-3 my-4">
                        <div className="flex-1 h-px bg-[#E8E6E0]"></div>
                        <div className="text-[9px] uppercase tracking-[0.2em] opacity-40">游客</div>
                        <div className="flex-1 h-px bg-[#E8E6E0]"></div>
                    </div>
                    <button onClick={() => { onGuest?.(); }} className="w-full py-3 bg-white border border-[#E8E6E0] rounded-full font-bold uppercase text-[10px] tracking-[0.2em] hover:shadow-md">以游客身份继续</button>
                </div>
                )}
            </div>
        </div>
    );
};

const AdminPanel = ({ isOpen, onClose, personas, onRefresh }) => {
    const [selectedId, setSelectedId] = useState(personas?.[0]?.id || '');
    const [status, setStatus] = useState('');
    const [uploading, setUploading] = useState(false);

    useEffect(() => {
        if (personas?.length && !selectedId) {
            setSelectedId(personas[0].id);
        }
    }, [personas, selectedId]);

    if (!isOpen) return null;

    const selected = personas.find(p => p.id === selectedId);

    const uploadAsset = async (file, type) => {
        if (!file || !selected) return;
        setUploading(true);
        setStatus('');
        try {
            const ext = file.name.split('.').pop() || 'png';
            const path = `personas/${selected.id}/${type}.${ext}`;
            const { error: uploadError } = await supabaseClient.storage
                .from('persona-assets')
                .upload(path, file, { upsert: true });
            if (uploadError) throw uploadError;

            const { data: publicData } = supabaseClient.storage.from('persona-assets').getPublicUrl(path);
            const url = publicData?.publicUrl || null;
            if (!url) throw new Error('Unable to get public URL');

            const payload = {
                id: selected.id,
                name: selected.name || selected.id
            };
            if (type === 'avatar') payload.avatar_url = url;
            if (type === 'cover') payload.cover_url = url;

            const { error: upsertError } = await supabaseClient.from('personas').upsert(payload, { onConflict: 'id' });
            if (upsertError) throw upsertError;

            setStatus('Upload succeeded');
            await onRefresh?.();
        } catch (err) {
            setStatus(err?.message || 'Upload failed');
        } finally {
            setUploading(false);
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
            <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" onClick={onClose}></div>
            <div className="relative w-full max-w-2xl bg-white rounded-[36px] shadow-2xl border border-[#F0EDEA] p-8 animate-in">
                <div className="flex items-center justify-between mb-6">
                    <h2 className="text-xl font-serif italic text-[#1A1A1A]">Admin panel</h2>
                    <button onClick={onClose} className="text-xs font-bold uppercase tracking-widest opacity-40 hover:opacity-100">
                        <Icon name="X" size={14} />
                    </button>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div className="space-y-3">
                        <div className="text-[10px] uppercase tracking-[0.2em] opacity-50">Select persona</div>
                        <select
                            className="w-full p-3 rounded-2xl border border-[#F0EDEA] bg-[#FDFBF7] focus-blue-brand"
                            value={selectedId}
                            onChange={(e) => setSelectedId(e.target.value)}
                        >
                            {personas.map(p => (
                                <option key={p.id} value={p.id}>{p.name || p.id}</option>
                            ))}
                        </select>
                        <div className="text-xs opacity-60">Current: {selected?.name || selected?.id || '-'}</div>
                    </div>
                    <div className="space-y-4">
                        <div className="flex items-center gap-4">
                            <div className="w-16 h-16 rounded-2xl overflow-hidden border border-[#F0EDEA] bg-[#FDFBF7]">
                                <AvatarDisplay avatar={selected?.avatar} className="w-full h-full text-3xl" />
                            </div>
                            <div className="text-xs opacity-60">Avatar preview</div>
                        </div>
                        <label className="block text-xs uppercase tracking-[0.2em] opacity-60">Upload avatar</label>
                        <input type="file" accept="image/*" disabled={uploading} onChange={(e) => uploadAsset(e.target.files?.[0], 'avatar')} />

                        <label className="block text-xs uppercase tracking-[0.2em] opacity-60 mt-4">Upload cover</label>
                        <input type="file" accept="image/*" disabled={uploading} onChange={(e) => uploadAsset(e.target.files?.[0], 'cover')} />

                        {status && <div className="text-xs text-blue-brand">{status}</div>}
                    </div>
                </div>
            </div>
        </div>
    );
};

// Settings components moved to `web/ui/settings/view.js`

const PersonaEditModal = ({ isOpen, persona, onClose, onSave }) => {
    const [draft, setDraft] = useState(null);
    const emojis = ['👤', '🎭', '🛡️', '🌱', '🦉', '💎', '🌩️', '🌊', '🔥', '🎀', '🧸', '☁️'];

    useEffect(() => {
        if (!isOpen || !persona) return;
        setDraft({
            name: persona.name || '',
            role: persona.role || '',
            worldview: persona.worldview || '',
            voice: persona.voice || '',
            avatar: persona.avatar || '👤'
        });
    }, [isOpen, persona?.id]);

    if (!isOpen || !persona || !draft) return null;

    const save = () => {
        onSave?.({
            ...persona,
            name: draft.name,
            role: draft.role,
            worldview: draft.worldview,
            voice: draft.voice,
            avatar: draft.avatar
        });
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
            <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" onClick={onClose}></div>
            <div className="relative w-full max-w-2xl bg-white rounded-[36px] shadow-2xl border border-[#F0EDEA] p-8 md:p-10 animate-in">
                <div className="flex items-center justify-between mb-6">
                    <h2 className="text-xl font-serif italic text-[#1A1A1A]">Edit Persona</h2>
                    <button onClick={onClose} className="text-xs font-bold uppercase tracking-widest opacity-40 hover:opacity-100">
                        <Icon name="X" size={14} />
                    </button>
                </div>
                <div className="space-y-5">
                    <input
                        placeholder="Name..."
                        className="w-full p-4 bg-[#FDFBF7] rounded-2xl border border-[#F0EDEA] focus-blue-brand"
                        value={draft.name}
                        onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                    />
                    <input
                        placeholder="Role / Identity"
                        className="w-full p-4 bg-[#FDFBF7] rounded-2xl border border-[#F0EDEA] uppercase text-xs focus-blue-brand"
                        value={draft.role}
                        onChange={(e) => setDraft({ ...draft, role: e.target.value })}
                    />
                    <div className="flex flex-wrap gap-2 justify-center pt-1">
                        {emojis.map(e => (
                            <button
                                key={e}
                                onClick={() => setDraft({ ...draft, avatar: e })}
                                className={`p-3 rounded-xl transition-all border-2 ${draft.avatar === e ? 'border-blue-brand bg-white' : 'border-transparent bg-slate-50'}`}
                            >
                                {e}
                            </button>
                        ))}
                    </div>
                    <textarea
                        placeholder="Worldview Statement..."
                        className="w-full h-28 p-5 bg-[#FDFBF7] rounded-2xl border border-[#F0EDEA] text-sm italic focus-blue-brand"
                        value={draft.worldview}
                        onChange={(e) => setDraft({ ...draft, worldview: e.target.value })}
                    />
                    <textarea
                        placeholder="Voice Sample..."
                        className="w-full h-24 p-5 bg-[#FDFBF7] rounded-2xl border border-[#F0EDEA] text-sm focus-blue-brand"
                        value={draft.voice}
                        onChange={(e) => setDraft({ ...draft, voice: e.target.value })}
                    />
                    <button
                        onClick={save}
                        disabled={!draft.name || !draft.role}
                        className="w-full py-4 bg-blue-brand text-white rounded-full font-bold uppercase text-xs tracking-[0.2em] shadow-xl disabled:opacity-40"
                    >
                        Save
                    </button>
                </div>
            </div>
        </div>
    );
};

const PersonaIconEditorModal = ({ isOpen, persona, onClose, onSetAvatar, onUseDefault }) => {
    if (!isOpen || !persona) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
            <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" onClick={onClose}></div>
            <div className="relative w-full max-w-md bg-white rounded-[36px] shadow-2xl border border-[#F0EDEA] p-8 md:p-10 animate-in">
                <div className="flex items-center justify-between mb-6">
                    <div className="text-[10px] font-black uppercase tracking-[0.25em] opacity-40">Icon Editor</div>
                    <button onClick={onClose} className="text-xs font-bold uppercase tracking-widest opacity-40 hover:opacity-100">
                        <Icon name="X" size={14} />
                    </button>
                </div>
                <div className="space-y-5">
                    <div className="flex items-center gap-3 justify-center">
                        <div className="w-14 h-14 rounded-2xl bg-[#FDFBF7] border border-[#F0EDEA] overflow-hidden">
                            <AvatarDisplay avatar={persona?.avatar} className="w-full h-full text-2xl" />
                        </div>
                        <label className="cursor-pointer">
                            <span className="px-4 h-10 inline-flex items-center rounded-full bg-blue-brand text-white text-[10px] font-black uppercase tracking-[0.2em] shadow-lg hover:shadow-xl transition-all">
                                Upload icon
                            </span>
                            <input
                                type="file"
                                accept="image/*"
                                className="hidden"
                                onChange={async (e) => {
                                    const file = e.target.files?.[0];
                                    if (!file) return;
                                    try {
                                        const url = await fileToDataURL(file);
                                        onSetAvatar?.(url);
                                    } catch (err) {
                                        console.error(err);
                                    } finally {
                                        e.target.value = '';
                                    }
                                }}
                            />
                        </label>
                    </div>
                    <div className="flex flex-wrap gap-2 items-center justify-center">
                        {DEFAULT_PERSONA_ICONS.map(ic => (
                            <button
                                key={ic}
                                type="button"
                                onClick={() => onSetAvatar?.(ic)}
                                className="w-10 h-10 rounded-2xl bg-white border border-[#E8E6E0] flex items-center justify-center text-xl hover:shadow-md transition-all"
                                title="Choose a default icon"
                            >
                                {ic}
                            </button>
                        ))}
                    </div>
                    <div className="flex flex-col sm:flex-row gap-3 pt-1">
                        <button
                            type="button"
                            onClick={onUseDefault}
                            className="flex-1 px-4 h-11 rounded-full bg-[#FDFBF7] border border-[#E8E6E0] text-[10px] font-black uppercase tracking-[0.2em] hover:shadow-md transition-all"
                        >
                            Use default
                        </button>
                        <button
                            type="button"
                            onClick={onClose}
                            className="flex-1 px-4 h-11 rounded-full bg-blue-brand text-white text-[10px] font-black uppercase tracking-[0.2em] shadow-lg hover:shadow-xl transition-all"
                        >
                            Done
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
};

window.AuthModal = AuthModal;
window.AdminPanel = AdminPanel;
window.PersonaEditModal = PersonaEditModal;
window.PersonaIconEditorModal = PersonaIconEditorModal;
