        const { useState, useEffect, useRef } = React;

        const copyToClipboard = async (text) => {
            try {
                if (navigator?.clipboard?.writeText) {
                    await navigator.clipboard.writeText(text);
                    return true;
                }
            } catch (_) {}
            try {
                const el = document.createElement('textarea');
                el.value = text;
                el.setAttribute('readonly', '');
                el.style.position = 'fixed';
                el.style.left = '-9999px';
                document.body.appendChild(el);
                el.select();
                document.execCommand('copy');
                document.body.removeChild(el);
                return true;
            } catch (_) {
                return false;
            }
        };

        // --- Supabase ---
        const SUPABASE_URL = "https://ncoqeewtbmzrfizoxomi.supabase.co";
        const SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5jb3FlZXd0Ym16cmZpem94b21pIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzAwODc2OTMsImV4cCI6MjA4NTY2MzY5M30.rfG9Ei63zEi82hbwk6ulZ-tFrAHkuBht8HbSexPZb9g";
        const supabaseClient = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
        const ADMIN_EMAIL = "hackathon@lifee.com";

        const SUMMARY_EVERY_DEFAULT = 15;
        const CONTEXT_WINDOW_DEFAULT = 15;

        const PRESET_PERIODS = [
            "First time studying abroad",
            "First year after graduation",
            "Early career confusion",
            "Career transition",
            "Around 30 鈥?feeling stuck",
            "Relationship turning point",
            "Creative burnout",
            "Major failure or loss",
            "Starting over in a new city",
            "Becoming independent"
        ];

        const LANDING_CATEGORIES = {
            scenario: [
                "My first job",
                "First time studying abroad",
                "First year after graduation",
                "Career transition",
                "Relationship turning point",
                "Starting over in a new city",
                "Becoming independent"
            ],
            problemType: [
                "Early career confusion",
                "Around 30 鈥?feeling stuck",
                "Creative burnout",
                "Major failure or loss"
            ]
        };

        const INITIAL_PERSONAS = [
            {
                id: 'audrey-hepburn',
                name: 'AUDREY HEPBURN',
                role: 'ELEGANT MUSE',
                category: 'CREATIVE',
                worldview: "Elegance is the quiet courage to be kind, even when the world is loud.",
                avatar: '馃晩锔?,
                cover_url: 'https://upload.wikimedia.org/wikipedia/commons/e/ed/My_Fair_Lady_Audrey_Hepburn.jpg',
                cover_fit: 'cover',
                cover_position: '50% 20%',
                decisionStyle: "Choose the simplest graceful option: protect your dignity, keep your promise, and make one small act of kindness that moves the story forward.",
                lifeContext: [
                    { period: "Carrying grace through hard years", detail: "Raised in Europe during WWII, she learned restraint, gratitude, and the art of standing tall without becoming hard." },
                    { period: "Roman Holiday (1953)", detail: "An unexpected breakthrough 鈥?and an Academy Award for Best Actress. Sincerity over performance, softness as strength." },
                    { period: "Breakfast at Tiffany鈥檚 (1961)", detail: "A cultural icon of style and solitude: lightness on the surface, longing underneath." },
                    { period: "UNICEF Goodwill Ambassador (1988鈥?993)", detail: "Later in life she traveled relentlessly for children, turning fame into a tool for service rather than self." },
                    { period: "Presidential Medal of Freedom (1992)", detail: "Honored for humanitarian work 鈥?proof that gentleness can also be public courage." }
                ],
                voice: "Darling, breathe. Ask: what would look simple and honest tomorrow morning? We'll choose the small step that keeps your heart gentle 鈥?and your posture upright."
            },
            {
                id: 'krishnamurti',
                name: 'Krishnamurti',
                role: 'THE QUESTIONER',
                category: 'RATIONAL',
                worldview: 'Truth is a pathless land. No method can lead you there.',
                avatar: '馃尶',
                decisionStyle: "Never gives answers. Only questions. Points you back to look at the problem itself, not solutions.",
                lifeContext: [
                    { period: "The Dissolution", detail: "Dissolved the Order of the Star, rejecting the role of World Teacher that was prepared for him." },
                    { period: "Pathless Journey", detail: "Spent 60 years in dialogue, refusing to become an authority while speaking to millions." }
                ],
                voice: "Are you really asking, or seeking confirmation? Don't accept what I say 鈥?look for yourself."
            },
            {
                id: 'lacan',
                name: 'Lacan',
                role: 'THE ANALYST',
                category: 'RATIONAL',
                worldview: 'Truth can only be half-said. The complete truth is impossible.',
                avatar: '馃獮',
                decisionStyle: "Responds to questions with questions. No comfort, no advice. Cuts through certainty to let the unconscious speak.",
                lifeContext: [
                    { period: "Return to Freud", detail: "Revolutionized psychoanalysis by insisting: the unconscious is structured like a language." },
                    { period: "The Seminar", detail: "27 years of legendary seminars in Paris, notoriously difficult, deliberately so." }
                ],
                voice: "The unconscious is structured like a language. What slips out when you speak?"
            }
        ];

        // 鉁?LIFEE API (JSON: { messages: [...], options: [...] })
        const LIFEE_API = "https://lifee-q94l.onrender.com/decision";

        async function fetchLifeeDecision(payload, url = LIFEE_API) {
            const res = await fetch(url, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });

            if (!res.ok) {
                const text = await res.text();
                throw new Error("LIFEE API failed: " + text);
            }

            return res.json();
        }

        const sleep = (ms) => new Promise(r => setTimeout(r, ms));

        async function fetchText(url) {
            const res = await fetch(url, { method: 'GET' });
            if (!res.ok) throw new Error(`fetchText failed: ${res.status}`);
            return res.text();
        }

        async function fetchLifeeDecisionStream(payload, { onMessage, onOptions } = {}) {
            const res = await fetch(`${LIFEE_API}?stream=1`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });

            if (!res.ok) {
                const text = await res.text();
                throw new Error("LIFEE API stream failed: " + text);
            }

            if (!res.body) {
                throw new Error("Streaming not supported in this browser.");
            }

            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let buf = "";
            let done = false;

            const flushEventBlock = async (block) => {
                // Ignore comments
                if (!block || block.startsWith(":")) return;
                const lines = block.split("\n").filter(Boolean);
                let eventName = "message";
                const dataLines = [];
                for (const line of lines) {
                    if (line.startsWith("event:")) eventName = line.slice(6).trim();
                    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
                }
                const dataStr = dataLines.join("\n");
                if (!dataStr) return;

                let data = dataStr;
                try { data = JSON.parse(dataStr); } catch (_) {}

                if (eventName === "message") {
                    if (data && typeof data === "object") await onMessage?.(data);
                } else if (eventName === "options") {
                    const opts = (data && typeof data === "object") ? data.options : [];
                    onOptions?.(Array.isArray(opts) ? opts : []);
                } else if (eventName === "error") {
                    const errMsg = (data && typeof data === "object") ? (data.error || JSON.stringify(data)) : String(data);
                    throw new Error(errMsg);
                } else if (eventName === "done") {
                    done = true;
                }
            };

            while (!done) {
                const { value, done: streamDone } = await reader.read();
                if (streamDone) break;
                buf += decoder.decode(value, { stream: true });
                let idx;
                while ((idx = buf.indexOf("\n\n")) !== -1) {
                    const block = buf.slice(0, idx).trimEnd();
                    buf = buf.slice(idx + 2);
                    await flushEventBlock(block);
                }
            }
        }

        async function fetchLifeeDecisionProgressive(payload, { onMessage, onOptions } = {}) {
            // 榛樿锛氭寜 persona 閫愪釜璇锋眰锛屽厛鍑虹涓€涓鑹茬殑娑堟伅锛屽啀鍑轰笅涓€涓紙浣撴劅鏇村揩锛?            const personas = Array.isArray(payload?.personas) ? payload.personas : [];
            if (personas.length <= 1) {
                const data = await fetchLifeeDecision(payload);
                if (Array.isArray(data?.messages)) {
                    for (const m of data.messages) await onMessage?.(m);
                }
                if (Array.isArray(data?.options)) onOptions?.(data.options);
                else onOptions?.([]);
                return;
            }

            const earlier = [];
            let lastOptions = [];
            for (let i = 0; i < personas.length; i++) {
                const p = personas[i];
                const situationWithEarlier = earlier.length
                    ? `${(payload?.situation || "").trim()}\n\nEarlier voices:\n${earlier.map(m => `- ${m.personaId}: ${String(m.text || '').replace(/\n/g, ' ')}`).join('\n')}`
                    : payload?.situation;

                const singlePayload = { ...payload, situation: situationWithEarlier, personas: [p] };
                const data = await fetchLifeeDecision(singlePayload);
                if (Array.isArray(data?.messages)) {
                    for (const m of data.messages) {
                        earlier.push(m);
                        await onMessage?.(m);
                    }
                }
                if (Array.isArray(data?.options)) lastOptions = data.options;
                // 缁?React 涓€娆℃覆鏌撴満浼氾紱澶氳鑹叉椂鍔犵煭鏆傚欢杩熼伩鍏?Gemini rate limit
                if (i < personas.length - 1) await sleep(2000);
                else await sleep(0);
            }
            onOptions?.(lastOptions);
        }

        const Icon = ({ name, size = 24, className = "" }) => (
            <i data-lucide={name} className={className} style={{ width: size, height: size, display: 'inline-flex' }}></i>
        );
                        const AvatarDisplay = ({ avatar, className = "" }) => {
            const isImage = typeof avatar === 'string' && (avatar.startsWith('data:image') || avatar.startsWith('http'));
            return (
                <div className={`flex items-center justify-center overflow-hidden ${className}`}>
                    {isImage ? (
                        <img src={avatar} alt="Avatar" className="w-full h-full object-cover" />
                    ) : (
                        <span className="text-current leading-none">{avatar}</span>
                    )}
                </div>
            );
        };

        // --- User avatar (local, upload or random icon) ---
        const USER_AVATAR_KEY = 'lifee_user_avatar';
        const USER_AVATAR_DEFAULT_KEY = 'lifee_user_avatar_default';
        const USER_AVATAR_CHOICES = ['鉁?, '馃尶', '馃敟', '馃暞锔?, '馃獮', '馃', '馃寠', '馃拵', '馃幁', '馃洝锔?, '馃尡', '鈽侊笍'];

        const pickRandom = (arr) => arr[Math.floor(Math.random() * arr.length)];

        const getOrCreateDefaultUserAvatar = () => {
            try {
                const existing = window.localStorage.getItem(USER_AVATAR_DEFAULT_KEY);
                if (existing) return existing;
                const next = pickRandom(USER_AVATAR_CHOICES);
                window.localStorage.setItem(USER_AVATAR_DEFAULT_KEY, next);
                return next;
            } catch (_) {
                return '馃懁';
            }
        };

        const loadUserAvatar = () => {
            try {
                return window.localStorage.getItem(USER_AVATAR_KEY) || getOrCreateDefaultUserAvatar();
            } catch (_) {
                return '馃懁';
            }
        };

        const saveUserAvatar = (avatar) => {
            try {
                if (avatar) window.localStorage.setItem(USER_AVATAR_KEY, avatar);
                else window.localStorage.removeItem(USER_AVATAR_KEY);
            } catch (_) {}
        };

        const rotateUserDefaultAvatar = () => {
            try {
                const next = pickRandom(USER_AVATAR_CHOICES);
                window.localStorage.setItem(USER_AVATAR_DEFAULT_KEY, next);
                return next;
            } catch (_) {
                return '馃懁';
            }
        };

        const fileToDataURL = (file) => new Promise((resolve, reject) => {
            try {
                const reader = new FileReader();
                reader.onload = () => resolve(String(reader.result || ''));
                reader.onerror = () => reject(new Error('Failed to read file'));
                reader.readAsDataURL(file);
            } catch (e) {
                reject(e);
            }
        });

        // --- Persona avatar overrides (local) ---
        const PERSONA_AVATAR_OVERRIDES_KEY = 'lifee_persona_avatar_overrides';
        const PERSONA_COVER_OVERRIDES_KEY = 'lifee_persona_cover_overrides';
        const DEFAULT_PERSONA_ICONS = ['鉁?, '馃尶', '馃敟', '馃暞锔?, '馃獮', '馃', '馃寠', '馃拵', '馃幁', '馃洝锔?, '馃尡', '鈽侊笍', '馃懁'];

        const loadPersonaAvatarOverrides = () => {
            try {
                const raw = window.localStorage.getItem(PERSONA_AVATAR_OVERRIDES_KEY);
                if (!raw) return {};
                const parsed = JSON.parse(raw);
                return (parsed && typeof parsed === 'object') ? parsed : {};
            } catch (_) {
                return {};
            }
        };

        const savePersonaAvatarOverrides = (map) => {
            try {
                window.localStorage.setItem(PERSONA_AVATAR_OVERRIDES_KEY, JSON.stringify(map || {}));
            } catch (_) {}
        };

        const loadPersonaCoverOverrides = () => {
            try {
                const raw = window.localStorage.getItem(PERSONA_COVER_OVERRIDES_KEY);
                if (!raw) return {};
                const parsed = JSON.parse(raw);
                return (parsed && typeof parsed === 'object') ? parsed : {};
            } catch (_) {
                return {};
            }
        };

        const savePersonaCoverOverrides = (map) => {
            try {
                window.localStorage.setItem(PERSONA_COVER_OVERRIDES_KEY, JSON.stringify(map || {}));
            } catch (_) {}
        };

        const PatternCover = ({ avatar }) => {
            const isImage = typeof avatar === 'string' && (avatar.startsWith('data:image') || avatar.startsWith('http'));
            return (
                <div className="absolute inset-0">
                    <div className="absolute inset-0 bg-gradient-to-br from-white via-[#FDFBF7] to-[#F3F1EC]" />
                    {isImage ? (
                        <>
                            <div className="absolute inset-0 opacity-[0.16]">
                                <img src={avatar} alt="cover motif" className="w-full h-full object-cover grayscale scale-110 blur-[2px]" loading="lazy" />
                            </div>
                            <div className="absolute inset-0 bg-white/50" />
                        </>
                    ) : (
                        <>
                            <div className="absolute -top-10 -left-8 text-[120px] opacity-[0.08] select-none">{avatar || '馃懁'}</div>
                            <div className="absolute -bottom-12 -right-8 text-[140px] opacity-[0.07] select-none">{avatar || '馃懁'}</div>
                            <div className="absolute inset-0 flex items-center justify-center">
                                <div className="w-20 h-20 rounded-[28px] bg-white/70 border border-white shadow-sm flex items-center justify-center">
                                    <AvatarDisplay avatar={avatar || '馃懁'} className="w-full h-full text-3xl opacity-60" />
                                </div>
                            </div>
                        </>
                    )}
                    <div className="absolute inset-0 bg-gradient-to-br from-white/60 via-transparent to-transparent pointer-events-none" />
                </div>
            );
        };

        const AuthModal = ({ isOpen, onClose, onAuthed, onGuest }) => {
            const [mode, setMode] = useState('login');
            const [email, setEmail] = useState('');
            const [password, setPassword] = useState('');
            const [loading, setLoading] = useState(false);
            const [message, setMessage] = useState('');

            if (!isOpen) return null;

            const handleAuth = async () => {
                setLoading(true);
                setMessage('');
                try {
                    if (mode === 'login') {
                        const { data, error } = await supabaseClient.auth.signInWithPassword({ email, password });
                        if (error) throw error;
                        if (data?.user) onAuthed(data.user);
                    } else {
                        const { data, error } = await supabaseClient.auth.signUp({ email, password });
                        if (error) throw error;
                        if (data?.user) {
                            setMessage('Sign-up successful. Please verify your email, then sign in.');
                        }
                    }
                } catch (err) {
                    setMessage(err?.message || 'Operation failed. Please try again.');
                } finally {
                    setLoading(false);
                }
            };

            return (
                <div className="fixed inset-0 z-50 flex items-center justify-center">
                    <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" onClick={onClose}></div>
                    <div className="relative w-full max-w-md bg-white rounded-[36px] shadow-2xl border border-[#F0EDEA] p-10 animate-in">
                        <div className="flex items-center justify-between mb-8">
                            <h2 className="text-xl font-serif italic text-[#1A1A1A]">{mode === 'login' ? 'Sign in' : 'Sign up'}</h2>
                            <button onClick={onClose} className="text-xs font-bold uppercase tracking-widest opacity-40 hover:opacity-100">
                                <Icon name="X" size={14} />
                            </button>
                        </div>
                        <div className="space-y-4">
                            <input type="email" placeholder="Email" className="w-full p-4 bg-[#FDFBF7] rounded-3xl border border-[#F0EDEA] transition-all focus-blue-brand" value={email} onChange={(e) => setEmail(e.target.value)} />
                            <input type="password" placeholder="Password" className="w-full p-4 bg-[#FDFBF7] rounded-3xl border border-[#F0EDEA] transition-all focus-blue-brand" value={password} onChange={(e) => setPassword(e.target.value)} />
                            {message && (
                                <div className="text-xs text-[#C97A7A] bg-[#FDF1F1] border border-[#F7D7D7] px-4 py-3 rounded-2xl">{message}</div>
                            )}
                            <button onClick={handleAuth} disabled={loading || !email || !password} className="w-full py-4 bg-blue-brand text-white rounded-full font-bold uppercase text-xs tracking-[0.2em] shadow-xl disabled:opacity-40">
                                {loading ? 'Working...' : (mode === 'login' ? 'Sign in' : 'Sign up')}
                            </button>
                            <button onClick={() => setMode(mode === 'login' ? 'signup' : 'login')} className="w-full text-xs uppercase tracking-[0.2em] opacity-50 hover:opacity-100">
                                {mode === 'login' ? "Don't have an account? Sign up" : 'Already have an account? Sign in'}
                            </button>
                            <div className="flex items-center gap-3 my-4">
                                <div className="flex-1 h-px bg-[#E8E6E0]"></div>
                                <div className="text-[9px] uppercase tracking-[0.2em] opacity-40">Guest</div>
                                <div className="flex-1 h-px bg-[#E8E6E0]"></div>
                            </div>
                            <button onClick={() => { onGuest?.(); }} className="w-full py-3 bg-white border border-[#E8E6E0] rounded-full font-bold uppercase text-[10px] tracking-[0.2em] hover:shadow-md">Continue as Guest</button>
                        </div>
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
            const emojis = ['馃懁', '馃幁', '馃洝锔?, '馃尡', '馃', '馃拵', '馃尒锔?, '馃寠', '馃敟', '馃巰', '馃Ц', '鈽侊笍'];

            useEffect(() => {
                if (!isOpen || !persona) return;
                setDraft({
                    name: persona.name || '',
                    role: persona.role || '',
                    worldview: persona.worldview || '',
                    voice: persona.voice || '',
                    avatar: persona.avatar || '馃懁'
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
                                <div className={`text-[10px] uppercase font-bold tracking-widest opacity-30 px-4 mb-2 ${isCollapsed ? 'md:hidden' : 'block'}`}>History</div>
                                <button className={`w-full text-left rounded-xl hover:bg-white/60 transition-colors flex items-center ${isCollapsed ? 'md:p-3 md:justify-center' : 'px-4 py-3 text-xs opacity-60 italic truncate'}`}>
                                    <Icon name="MessageSquare" size={14} className={isCollapsed ? "md:text-blue-brand" : "mr-2 opacity-40"} />
                                    <span className={isCollapsed ? 'md:hidden' : 'block'}>"Recent thoughts..."</span>
                                </button>
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

        const PersonaBuilder = ({ onSave, onCancel }) => {
            const [step, setStep] = useState(1);
            const [newP, setNewP] = useState({ name: '', role: '', worldview: '', avatar: '馃懁', voice: '', knowledge: '' });
            const emojis = ['馃懁', '馃幁', '馃洝锔?, '馃尡', '馃', '馃拵', '馃尒锔?, '馃寠', '馃敟', '馃巰', '馃Ц', '鈽侊笍'];
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

        const DebateArena = ({
            context,
            selectedPersonas,
            setView,
            ensureSession,
            persistMessage,
            buildContextBlock,
            userAvatar
        }) => {
            const [history, setHistory] = useState([]);
            const [options, setOptions] = useState([]);
            const [isDebating, setIsDebating] = useState(false);
            const [inputValue, setInputValue] = useState('');
            const scrollRef = useRef(null);
            const inputFieldRef = useRef(null);

            useEffect(() => { if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight; }, [history]);

            const runRound = async (userInput = null) => {
                setIsDebating(true);
                const cleanInput = (userInput ?? inputValue ?? "").toString().trim();

                if (cleanInput) {
                    setHistory(prev => [...prev, { personaId: "user", text: cleanInput }]);
                    await persistMessage('user', cleanInput);
                    setInputValue('');
                }

                try {
                    const contextBlock = buildContextBlock();
                    const situation = (context.situation || "").trim();
                    const finalSituation = contextBlock
                        ? `Context:\n${contextBlock}\n\nUser situation:\n${situation || "Start the internal debate."}`
                        : (situation || "Start the internal debate.");

                    const payload = {
                        situation: finalSituation,
                        userInput: cleanInput,
                        personas: selectedPersonas.map(p => ({ id: p.id, name: p.name, knowledge: p.knowledge || '' })),
                        context: contextBlock
                    };

                    const handlers = {
                        onMessage: async (msg) => {
                            setHistory(prev => [...prev, msg]);
                            const role = msg.personaId === 'system' ? 'system' : 'assistant';
                            await persistMessage(role, msg.text || '');
                        },
                        onOptions: (opts) => {
                            setOptions(Array.isArray(opts) ? opts : []);
                        }
                    };

                    // Render free tier doesn't support SSE 鈥?use progressive JSON directly
                    await fetchLifeeDecisionProgressive(payload, handlers);
                } catch (e) {
                    console.error(e);
                    setHistory(prev => [...prev, { personaId: "system", text: `(Request failed) ${e.message}` }]);
                    setOptions([]);
                } finally {
                    setIsDebating(false);
                }
            };

            const copyText = (text) => { copyToClipboard(text); };

            const quoteText = (text, name) => {
                const quote = `"${text}" 鈥?${name}\n\n`;
                setInputValue(prev => quote + prev);
                inputFieldRef.current?.focus();
            };

            const autoStartedRef = useRef(false);
            useEffect(() => {
                if (autoStartedRef.current) return;
                if (!selectedPersonas?.length) return;
                const initial = (context?.situation || '').trim();
                if (!initial) return;
                autoStartedRef.current = true;
                runRound(initial);
            }, [selectedPersonas?.length]);

            return (
                <div className="h-[calc(100vh-64px)] flex flex-col overflow-hidden font-sans animate-in">
                    <div className="p-4 border-b border-[#F0EDEA] bg-white flex items-center justify-between z-10">
                        <div className="flex -space-x-2">{selectedPersonas.map(p => <div key={p.id} className="w-8 h-8 rounded-full border-2 border-white overflow-hidden shadow-sm"><AvatarDisplay avatar={p.avatar} className="w-full h-full text-xs" /></div>)}</div>
                        <button onClick={() => setView('summary')} className="flex items-center gap-2 text-xs font-bold text-[#E6C6C1] px-4 py-2 border border-[#E6C6C1] rounded-full hover:bg-[#E6C6C1] hover:text-white transition-all"><Icon name="PauseCircle" size={14} /> STOP & DECIDE</button>
                    </div>
                    <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 md:p-8 space-y-10 pb-64 no-scrollbar">
                        {history.map((m, idx) => {
                            const isUser = m.personaId === 'user';
                            const p = isUser
                                ? { name: 'YOU', avatar: (userAvatar || loadUserAvatar()) }
                                : (selectedPersonas.find(x => x.id === m.personaId) || (m.personaId === "system" ? { name: "SYSTEM", avatar: "鈿狅笍" } : { name: 'Voice', avatar: '鈽侊笍' }));
                            return (
                                <div key={idx} className={`flex gap-4 md:gap-5 ${isUser ? 'flex-row-reverse' : 'items-start'} animate-in`}>
                                    <div className={`w-10 h-10 md:w-11 md:h-11 rounded-full border flex items-center justify-center shadow-sm shrink-0 bg-white overflow-hidden ${isUser ? 'border-blue-brand/30' : 'border-[#F0EDEA]'}`}><AvatarDisplay avatar={p.avatar} className="w-full h-full text-2xl" /></div>
                                    <div className={`max-w-[85%] md:max-w-[70%] flex flex-col ${isUser ? 'items-end' : 'items-start'}`}>
                                        <span className="text-[10px] font-black opacity-30 tracking-widest uppercase mb-1.5">{p.name}</span>
                                        <div className={`p-4 md:p-5 rounded-[24px] md:rounded-[28px] text-sm shadow-sm transition-all duration-300 leading-relaxed ${isUser ? 'bg-blue-brand text-white rounded-tr-none' : 'bg-white border border-[#F0EDEA] rounded-tl-none'}`}>{m.text}</div>
                                        <div className={`flex gap-4 mt-2 px-1 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
                                            <button onClick={() => copyText(m.text)} className="flex items-center gap-1.5 text-[10px] font-bold text-blue-brand/60 hover:text-blue-brand transition-colors uppercase tracking-widest"><Icon name="Copy" size={12} /> Copy</button>
                                            <button onClick={() => quoteText(m.text, p.name)} className="flex items-center gap-1.5 text-[10px] font-bold text-blue-brand/60 hover:text-blue-brand transition-colors uppercase tracking-widest"><Icon name="Quote" size={12} /> Quote</button>
                                        </div>
                                    </div>
                                </div>
                            );
                        })}
                        {isDebating && <div className="animate-pulse flex gap-4"><div className="w-10 h-10 bg-slate-200 rounded-full" /><div className="h-14 w-64 bg-white border rounded-3xl" /></div>}
                    </div>
                    <div className="p-4 md:p-8 bg-gradient-to-t from-[#FDFBF7] via-[#FDFBF7] to-transparent">
                        <div className="max-w-3xl mx-auto space-y-4">
                            {options.length > 0 && !isDebating && <div className="flex flex-wrap justify-center gap-2 mb-2 animate-in">{options.map((opt, i) => <button key={i} onClick={() => runRound(opt)} className="px-4 py-2 bg-white/90 border border-blue-brand/20 rounded-full text-xs font-bold hover:bg-blue-brand hover:text-white transition-all shadow-sm">{opt}</button>)}</div>}
                            <div className="flex gap-3">
                                <button disabled={isDebating} onClick={() => runRound(null)} className="hidden md:block flex-1 py-5 bg-blue-brand text-white rounded-full font-bold shadow-xl transition-all hover:translate-y-[-2px] disabled:opacity-50 uppercase tracking-widest text-xs">STAY SILENT</button>
                                <div className="relative flex-[3] group">
                                    <input ref={inputFieldRef} type="text" placeholder="..." disabled={isDebating} className="w-full h-14 bg-white rounded-full shadow-xl border-2 border-transparent focus:border-blue-brand transition-all duration-300 px-6 md:px-8 focus:outline-none text-sm" value={inputValue} onChange={(e) => setInputValue(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && inputValue) runRound(); }} />
                                    <div className="absolute inset-y-0 right-6 flex items-center pointer-events-none group-focus-within:opacity-0 transition-opacity"><Icon name="MessageCircle" size={22} className="text-blue-brand" /></div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            );
        };

        const CommunityView = ({ communityTab, setCommunityTab, favoriteIds, onToggleFavorite }) => (
            <div className="p-6 md:p-12 max-w-[1200px] mx-auto animate-in space-y-12">
                <div className="flex flex-col items-center space-y-6">
                    <h2 className="text-3xl md:text-5xl font-serif italic tracking-tight text-center">Community Archives</h2>
                    <div className="flex justify-center px-4 w-full"><div className="inline-flex bg-white/60 backdrop-blur-md p-1.5 rounded-full border-2 border-white shadow-lg whitespace-nowrap">{['DEBATE', 'PERSONA'].map(tab => <button key={tab} onClick={() => setCommunityTab(tab)} className={`px-8 md:px-12 py-2.5 md:py-3 rounded-full text-[10px] font-black uppercase tracking-[0.2em] transition-all duration-300 ${communityTab === tab ? 'bg-blue-brand text-white shadow-lg scale-105' : 'text-[#5D576B]/40 hover:text-blue-brand'}`}>{tab}</button>)}</div></div>
                </div>
                {communityTab === 'DEBATE' ? (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6 md:gap-8 animate-in">{[1, 2, 3, 4].map(i => <div key={i} className="bg-white p-8 rounded-[48px] border border-[#E8E6E0] shadow-sm hover:shadow-xl hover:-translate-y-1 transition-all cursor-pointer group"><div className="flex items-center gap-5 mb-6"><div className="w-12 h-12 rounded-2xl bg-[#FDFBF7] flex items-center justify-center text-2xl group-hover:scale-110 transition-transform">馃幁</div><div><h4 className="font-bold text-lg text-[#1A1A1A]">Shared Reflection #{i}204</h4><p className="text-[10px] uppercase font-bold text-blue-brand tracking-widest">3 Voices Engaging</p></div></div><p className="text-sm italic opacity-60 leading-relaxed line-clamp-2">"Exploring the complex tension between the safety of the known and the fear of the unknown during graduation..."</p><div className="mt-8 pt-6 border-t border-slate-50 flex justify-between items-center text-[10px] font-black uppercase tracking-widest opacity-30"><span>Reflected 2 days ago</span><span className="group-hover:text-blue-brand transition-colors">Enter Archive 鈫?/span></div></div>)}</div>
                ) : (
                    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6 md:gap-8 animate-in">
                        {INITIAL_PERSONAS.map(p => {
                            const isFav = favoriteIds?.includes(p.id);
                            return (
                                <div key={p.id} className="relative p-6 md:p-8 bg-white rounded-[40px] shadow-xl border-2 border-white/20 hover:scale-[1.03] transition-all flex flex-col aspect-[3/4] overflow-hidden group">
                                    <button
                                        onClick={(e) => { e.stopPropagation(); onToggleFavorite?.(p); }}
                                        className={`absolute top-5 right-5 w-9 h-9 rounded-full border flex items-center justify-center z-20 transition-all ${isFav ? 'bg-blue-brand text-white border-blue-brand' : 'bg-white border-[#E8E6E0] text-[#5D576B]/40 hover:text-blue-brand'}`}
                                        title={isFav ? 'Remove from favorites' : 'Add to My Personas'}
                                    >
                                        <Icon name="Star" size={16} />
                                    </button>
                                    <div className="mb-6 flex items-center justify-center w-14 h-14 md:w-18 md:h-18 relative overflow-hidden group-hover:scale-110 transition-transform origin-center">
                                        <div className="absolute inset-0 bg-slate-50 rounded-[24px] transform rotate-6 scale-90 opacity-40 group-hover:bg-blue-brand/10 transition-colors" />
                                        <AvatarDisplay avatar={p.avatar} className="w-10 h-10 md:w-14 md:h-14 text-4xl md:text-5xl relative z-10" />
                                    </div>
                                    <div className="mt-auto text-left space-y-2">
                                        <h4 className="font-black text-xl md:text-2xl text-[#1A1A1A] tracking-tighter uppercase italic">{p.name}</h4>
                                        <p className="text-[7px] md:text-[8px] uppercase font-black tracking-widest text-blue-brand/80">COMMUNITY CREATION</p>
                                        <p className="text-[10px] md:text-xs italic opacity-40 leading-relaxed line-clamp-2">鈥渰p.worldview}鈥?/p>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                )}
            </div>
        );

        // 鈹€鈹€ Job Offer Priority Modal 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
        const JOB_DIMENSIONS = [
            { id: 1, label: 'Money (short-term income)' },
            { id: 2, label: 'Growth potential' },
            { id: 3, label: 'Industry outlook' },
            { id: 4, label: 'Job stability' },
            { id: 5, label: 'Life experience' },
        ];
        const STAGES = ['Seed', 'Angel', 'Series A', 'Series B', 'Series C', 'Public', 'Big Tech'];
        const ROLES = ['Product', 'BD', 'Engineering', 'Operations', 'Mgmt Trainee'];
        const EQUITY_OPTS = ['Yes', 'No', 'Unclear'];
        const CLARITY_OPTS = ['Clear', 'Vague'];
        const REPORTS_OPTS = ['Founder', 'Mid-level', 'Unknown'];
        const PillSelect = ({ options, value, onChange }) => (
            <div className="flex flex-wrap gap-1.5 mt-1.5">
                {options.map(opt => (
                    <button key={opt} type="button" onClick={() => onChange(value === opt ? '' : opt)} className={`px-3 py-1.5 rounded-full text-[10px] font-black uppercase tracking-wider transition-all ${value === opt ? 'bg-blue-brand text-white shadow-sm' : 'bg-[#F0EDEA] text-[#5D576B]/60 hover:bg-[#E8E5E0]'}`}>{opt}</button>
                ))}
            </div>
        );
        const newOffer = () => ({ id: Math.random().toString(36).slice(2), company: '', stage: '', role: '', cash: '', equity: '', clarity: '', reportsTo: '', notes: '' });
        const JobOfferModal = ({ isOpen, onClose, onConfirm }) => {
            const [step, setStep] = useState(1);
            const [items, setItems] = useState([...JOB_DIMENSIONS]);
            const [offers, setOffers] = useState([newOffer(), newOffer()]);
            const dragIndexRef = useRef(null);
            const [dragOverIndex, setDragOverIndex] = useState(null);
            const touchDragIndex = useRef(null);
            useEffect(() => { if (isOpen) { setStep(1); setItems([...JOB_DIMENSIONS]); setOffers([newOffer(), newOffer()]); } }, [isOpen]);
            if (!isOpen) return null;
            const onDragStart = (i) => { dragIndexRef.current = i; };
            const onDragOver = (e, i) => { e.preventDefault(); if (dragIndexRef.current === null || dragIndexRef.current === i) return; setDragOverIndex(i); setItems(prev => { const next = [...prev]; const [moved] = next.splice(dragIndexRef.current, 1); next.splice(i, 0, moved); dragIndexRef.current = i; return next; }); };
            const onDragEnd = () => { dragIndexRef.current = null; setDragOverIndex(null); };
            const onTouchStart = (e, i) => { touchDragIndex.current = i; };
            const onTouchMove = (e) => { e.preventDefault(); const touch = e.touches[0]; const el = document.elementFromPoint(touch.clientX, touch.clientY); if (!el) return; const item = el.closest('[data-drag-index]'); if (!item) return; const overIndex = parseInt(item.dataset.dragIndex, 10); if (isNaN(overIndex) || touchDragIndex.current === null || touchDragIndex.current === overIndex) return; setDragOverIndex(overIndex); setItems(prev => { const next = [...prev]; const [moved] = next.splice(touchDragIndex.current, 1); next.splice(overIndex, 0, moved); touchDragIndex.current = overIndex; return next; }); };
            const onTouchEnd = () => { touchDragIndex.current = null; setDragOverIndex(null); };
            const updateOffer = (id, field, val) => setOffers(prev => prev.map(o => o.id === id ? { ...o, [field]: val } : o));
            const removeOffer = (id) => setOffers(prev => prev.filter(o => o.id !== id));
            const handleFinalConfirm = () => {
                const ranked = items.map((item, i) => `${i + 1}. ${item.label}`).join('\n');
                const offerTexts = offers.map((o, i) => { const name = `Offer ${String.fromCharCode(65 + i)}${o.company ? ` 鈥?${o.company}` : ''}`; const fields = [o.stage && `Stage: ${o.stage}`, o.role && `Role: ${o.role}`, o.cash && `Cash comp: ${o.cash}`, o.equity && `Equity: ${o.equity}`, o.clarity && `Role clarity: ${o.clarity}`, o.reportsTo && `Reports to: ${o.reportsTo}`].filter(Boolean).map(f => `  鈥?${f}`).join('\n'); const notesLine = o.notes ? `\n  Notes: ${o.notes}` : ''; return `${name}${fields ? '\n' + fields : ''}${notesLine}`; }).join('\n\n');
                onConfirm(`I'm not sure which job offer to choose.\n\nMy priorities (most 鈫?least important):\n${ranked}\n\n${offerTexts}`);
                onClose();
            };
            const labelCls = "text-[9px] uppercase tracking-[0.2em] font-black text-[#5D576B]/40 mb-1";
            const inputCls = "w-full bg-[#F8F6F2] border border-[#E8E6E0] rounded-[12px] px-3 py-2.5 text-sm text-[#1A1A1A] placeholder:text-[#5D576B]/30 focus:outline-none focus:border-blue-brand transition-colors";
            return (
                <div className="fixed inset-0 z-[100] flex items-end md:items-center justify-center p-0 md:p-4" onClick={onClose}>
                    <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" />
                    <div className="relative bg-[#FDFBF7] rounded-t-[40px] md:rounded-[40px] shadow-2xl w-full md:max-w-lg flex flex-col" style={{maxHeight:'90vh'}} onClick={e => e.stopPropagation()}>
                        <div className="w-10 h-1 bg-[#E0DDD8] rounded-full mx-auto mt-4 md:hidden flex-shrink-0" />
                        <button onClick={onClose} className="absolute top-5 right-6 w-8 h-8 rounded-full bg-[#F0EDEA] flex items-center justify-center text-[#5D576B]/60 hover:text-[#5D576B] transition-colors z-10"><Icon name="X" size={16} /></button>
                        {step === 1 ? (
                            <div className="flex flex-col gap-5 p-8 md:p-10 overflow-y-auto no-scrollbar">
                                <div className="text-center space-y-1.5 pr-4">
                                    <p className="text-[9px] uppercase tracking-[0.3em] font-black text-blue-brand/40">Step 1 of 2</p>
                                    <h2 className="text-2xl font-serif italic tracking-tight text-[#1A1A1A] leading-snug">What matters most to you?</h2>
                                    <p className="text-[9px] uppercase tracking-[0.25em] font-black text-[#5D576B]/40">Drag to rank 路 most 鈫?least important</p>
                                </div>
                                <div className="flex flex-col gap-2.5">
                                    {items.map((item, i) => (
                                        <div key={item.id} data-drag-index={String(i)} draggable onDragStart={() => onDragStart(i)} onDragOver={e => onDragOver(e, i)} onDragEnd={onDragEnd} onTouchStart={e => onTouchStart(e, i)} onTouchMove={onTouchMove} onTouchEnd={onTouchEnd} style={{touchAction:'none'}} className={`flex items-center gap-3 bg-white border-2 rounded-[18px] px-4 py-3.5 cursor-grab active:cursor-grabbing select-none transition-all duration-150 ${dragOverIndex === i ? 'border-blue-brand shadow-md scale-[1.02]' : 'border-[#F0EDEA] hover:border-blue-brand/30 hover:shadow-sm'}`}>
                                            <span className="text-[11px] font-black text-blue-brand/40 w-4 text-center tabular-nums">{i + 1}</span>
                                            <div className="flex-1 min-w-0"><p className="font-bold text-[#1A1A1A] text-sm leading-tight">{item.label}</p></div>
                                            <Icon name="GripVertical" size={15} className="text-[#5D576B]/25 flex-shrink-0" />
                                        </div>
                                    ))}
                                </div>
                                <button onClick={() => setStep(2)} className="w-full py-4 bg-blue-brand text-white rounded-full font-black uppercase tracking-[0.2em] text-[11px] shadow-lg hover:shadow-xl hover:translate-y-[-1px] transition-all active:scale-95 mt-1">Next 鈥?Add Your Offers</button>
                            </div>
                        ) : (
                            <>
                                <div className="flex-shrink-0 px-8 pt-8 md:px-10 md:pt-10 pb-4">
                                    <button onClick={() => setStep(1)} className="flex items-center gap-1 text-[9px] uppercase tracking-[0.2em] font-black text-[#5D576B]/40 hover:text-blue-brand transition-colors mb-3"><Icon name="ChevronLeft" size={12} /> Back</button>
                                    <p className="text-[9px] uppercase tracking-[0.3em] font-black text-blue-brand/40">Step 2 of 2</p>
                                    <h2 className="text-2xl font-serif italic tracking-tight text-[#1A1A1A] mt-1">Tell me about the offers</h2>
                                </div>
                                <div className="flex-1 overflow-y-auto no-scrollbar px-8 md:px-10 pb-4 space-y-4">
                                    {offers.map((offer, idx) => (
                                        <div key={offer.id} className="bg-white border border-[#F0EDEA] rounded-[24px] p-5 space-y-4">
                                            <div className="flex items-center justify-between">
                                                <span className="text-[10px] font-black uppercase tracking-[0.2em] text-blue-brand/50">Offer {String.fromCharCode(65 + idx)}</span>
                                                {offers.length > 1 && <button onClick={() => removeOffer(offer.id)} className="w-6 h-6 rounded-full bg-[#F0EDEA] flex items-center justify-center text-[#5D576B]/40 hover:text-red-400 transition-colors"><Icon name="X" size={12} /></button>}
                                            </div>
                                            <div><p className={labelCls}>Company name</p><input type="text" className={inputCls} placeholder="e.g. Acme Corp" value={offer.company} onChange={e => updateOffer(offer.id, 'company', e.target.value)} /></div>
                                            <div><p className={labelCls}>Stage</p><PillSelect options={STAGES} value={offer.stage} onChange={v => updateOffer(offer.id, 'stage', v)} /></div>
                                            <div><p className={labelCls}>Role type</p><PillSelect options={ROLES} value={offer.role} onChange={v => updateOffer(offer.id, 'role', v)} /></div>
                                            <div><p className={labelCls}>Total cash comp</p><input type="text" className={inputCls} placeholder="e.g. 楼500k / year" value={offer.cash} onChange={e => updateOffer(offer.id, 'cash', e.target.value)} /></div>
                                            <div><p className={labelCls}>Equity</p><PillSelect options={EQUITY_OPTS} value={offer.equity} onChange={v => updateOffer(offer.id, 'equity', v)} /></div>
                                            <div><p className={labelCls}>Role clarity</p><PillSelect options={CLARITY_OPTS} value={offer.clarity} onChange={v => updateOffer(offer.id, 'clarity', v)} /></div>
                                            <div><p className={labelCls}>Reports to</p><PillSelect options={REPORTS_OPTS} value={offer.reportsTo} onChange={v => updateOffer(offer.id, 'reportsTo', v)} /></div>
                                            <div><p className={labelCls}>Anything else worth noting?</p><textarea className={`${inputCls} resize-none h-20 leading-relaxed`} placeholder="Culture, commute, gut feeling, red flags..." value={offer.notes} onChange={e => updateOffer(offer.id, 'notes', e.target.value)} /></div>
                                        </div>
                                    ))}
                                    <button onClick={() => setOffers(prev => [...prev, newOffer()])} className="w-full py-3 border-2 border-dashed border-[#E0DDD8] rounded-[20px] text-[10px] font-black uppercase tracking-[0.2em] text-[#5D576B]/40 hover:border-blue-brand/40 hover:text-blue-brand/60 transition-all flex items-center justify-center gap-2"><Icon name="Plus" size={14} /> Add another offer</button>
                                </div>
                                <div className="flex-shrink-0 px-8 pb-8 md:px-10 md:pb-10 pt-4 border-t border-[#F0EDEA]">
                                    <button onClick={handleFinalConfirm} className="w-full py-4 bg-blue-brand text-white rounded-full font-black uppercase tracking-[0.2em] text-[11px] shadow-lg hover:shadow-xl hover:translate-y-[-1px] transition-all active:scale-95">Let Them Debate This</button>
                                </div>
                            </>
                        )}
                    </div>
                </div>
            );
        };

        // 鈹€鈹€ Persona Recommendation Modal 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
        const randomPicks = (arr, n) => {
            const pool = (arr || []).filter(p => p && p.id);
            for (let i = pool.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [pool[i], pool[j]] = [pool[j], pool[i]]; }
            return pool.slice(0, n);
        };
        const PersonaRecommendModal = ({ isOpen, onClose, situation, periods, personas, selectedIds, onConfirm }) => {
            const [picks, setPicks] = useState([]);
            const [recommended, setRecommended] = useState([]);
            const [loading, setLoading] = useState(false);
            useEffect(() => {
                if (!isOpen) return;
                setLoading(true);
                const applyRecs = (recs) => { setRecommended(recs); setPicks(recs.map(p => p.id)); setLoading(false); };
                fetch('/recommend-personas', { method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'include', body: JSON.stringify({ situation, periods: periods||[], persona_ids: personas.map(p => p.id) }) })
                    .then(r => r.json())
                    .then(data => {
                        const ids = Array.isArray(data.ids) ? data.ids : [];
                        const recs = ids.map(id => personas.find(p => p.id === id)).filter(Boolean).slice(0, 4);
                        applyRecs(recs.length > 0 ? recs : randomPicks(personas, 2));
                    })
                    .catch(() => applyRecs(randomPicks(personas, 2)));
            }, [isOpen]);
            if (!isOpen) return null;
            const toggle = (id) => setPicks(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
            const handleConfirm = () => { onConfirm([...new Set([...selectedIds, ...picks])]); };
            return (
                <div className="fixed inset-0 z-[100] flex items-end md:items-center justify-center p-0 md:p-4" onClick={onClose}>
                    <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" />
                    <div className="relative bg-[#FDFBF7] rounded-t-[40px] md:rounded-[40px] shadow-2xl w-full md:max-w-lg flex flex-col" style={{maxHeight:'90vh'}} onClick={e => e.stopPropagation()}>
                        <div className="w-10 h-1 bg-[#E0DDD8] rounded-full mx-auto mt-4 flex-shrink-0 md:hidden" />
                        <button onClick={onClose} className="absolute top-5 right-6 w-8 h-8 rounded-full bg-[#F0EDEA] flex items-center justify-center text-[#5D576B]/60 hover:text-[#5D576B] transition-colors z-10"><Icon name="X" size={16} /></button>
                        <div className="flex-shrink-0 px-8 pt-8 pb-5 md:px-10 md:pt-10">
                            <p className="text-[9px] uppercase tracking-[0.3em] font-black text-blue-brand/50 mb-2">鉁?Just for you</p>
                            <h2 className="text-2xl font-serif italic tracking-tight text-[#1A1A1A] leading-snug pr-8">These voices might resonate</h2>
                            <p className="text-[10px] text-[#5D576B]/50 mt-1.5">Based on what you shared 路 tap to select or deselect</p>
                        </div>
                        <div className="flex-1 overflow-y-auto no-scrollbar px-8 md:px-10 pb-4">
                            {loading ? (<div className="grid grid-cols-2 gap-3">{[0,1,2,3].map(i => (<div key={i} className="rounded-[22px] border-2 border-[#F0EDEA] bg-white p-4 flex flex-col gap-3 animate-pulse"><div className="w-10 h-10 rounded-full bg-[#F0EDEA]" /><div className="h-3 bg-[#F0EDEA] rounded-full w-3/4" /><div className="h-2 bg-[#F0EDEA] rounded-full w-1/2" /><div className="h-2 bg-[#F0EDEA] rounded-full w-full" /></div>))}</div>) : (
                            <div className="grid grid-cols-2 gap-3">
                                {recommended.map(persona => {
                                    const isSel = picks.includes(persona.id);
                                    return (
                                        <button key={persona.id} type="button" onClick={() => toggle(persona.id)} className={`relative text-left rounded-[22px] p-4 border-2 transition-all duration-150 flex flex-col gap-2 ${isSel ? 'border-blue-brand bg-blue-brand/5 shadow-md' : 'border-[#F0EDEA] bg-white hover:border-blue-brand/30 hover:shadow-sm'}`}>
                                            <div className={`absolute top-3 right-3 w-5 h-5 rounded-full border-2 flex items-center justify-center transition-all ${isSel ? 'bg-blue-brand border-blue-brand' : 'border-[#D8D5D0]'}`}>{isSel && <Icon name="Check" size={11} className="text-white" />}</div>
                                            {persona.cover_url ? (<div className="w-10 h-10 rounded-full bg-[#F0EDEA] overflow-hidden flex-shrink-0" style={{backgroundImage:`url(${persona.cover_url})`,backgroundSize:'cover',backgroundPosition:persona.cover_position||'50% 30%'}} />) : (<div className="w-10 h-10 rounded-full bg-[#F0EDEA] flex items-center justify-center text-xl flex-shrink-0">{persona.avatar||'?'}</div>)}
                                            <div className="min-w-0 pr-4"><p className="font-serif italic font-bold text-[#1A1A1A] text-sm leading-tight truncate">{persona.name}</p><p className="text-[9px] uppercase tracking-widest text-[#5D576B]/50 mt-0.5 leading-tight">{persona.role}</p></div>
                                            {persona.voice && <p className="text-[10px] text-[#5D576B]/60 italic leading-relaxed line-clamp-2">"{persona.voice.slice(0,72)}{persona.voice.length>72?'鈥?:''}"</p>}
                                        </button>
                                    );
                                })}
                            </div>
                        </div>
                            )}
                        </div>
                        <div className="flex-shrink-0 px-8 pb-8 md:px-10 md:pb-10 pt-4 border-t border-[#F0EDEA] space-y-3">
                            <button onClick={handleConfirm} disabled={picks.length===0||loading} className="w-full py-4 bg-blue-brand text-white rounded-full font-black uppercase tracking-[0.2em] text-[11px] shadow-lg hover:shadow-xl hover:translate-y-[-1px] transition-all active:scale-95 disabled:opacity-30">Add to My Panel & Continue</button>
                            <button onClick={() => onConfirm(selectedIds)} className="w-full py-2 text-[10px] uppercase tracking-[0.2em] font-black text-[#5D576B]/40 hover:text-[#5D576B]/70 transition-colors">Skip 鈥?I'll choose my own</button>
                        </div>
                    </div>
                </div>
            );
        };

        function App() {
