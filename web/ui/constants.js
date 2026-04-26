// --- Auth shim: 本地 LIFEE API 冒充 supabase-js 接口，让旧组件零改动切换 ---
// 所有 `supabaseClient.auth.*` 和部分 `supabaseClient.from('profiles').*` 会路由到
// /auth/* /user/* 端点。未覆盖到的 from(table) 调用返回空数据（降级）。
var supabaseClient = (function () {
    var listeners = [];
    function _emit(event, session) {
        try { listeners.forEach(function (cb) { cb(event, session); }); } catch (_) {}
    }
    async function _json(url, opts) {
        opts = opts || {};
        opts.credentials = 'include';
        opts.headers = Object.assign({ 'Content-Type': 'application/json' }, opts.headers || {});
        if (opts.body && typeof opts.body !== 'string') opts.body = JSON.stringify(opts.body);
        try {
            var r = await fetch(url, opts);
            if (!r.ok && r.status !== 200 && r.status !== 400) {
                return { __err: r.status };
            }
            return await r.json();
        } catch (e) {
            return { __err: e.message || String(e) };
        }
    }
    function _userShape(u) {
        if (!u || !u.id) return null;
        return {
            id: u.id,
            email: u.email,
            user_metadata: u.user_metadata || {},
            app_metadata: u.app_metadata || {},
        };
    }

    var auth = {
        async signInWithPassword(arg) {
            var data = await _json('/auth/login', { method: 'POST', body: { email: arg.email, password: arg.password } });
            if (!data.ok) return { data: null, error: { message: data.message || 'Login failed', needs_verify: !!data.needs_verify } };
            var user = _userShape(data.user);
            _emit('SIGNED_IN', { user: user });
            return { data: { user: user, session: { user: user } }, error: null };
        },
        async signUp(arg) {
            var data = await _json('/auth/signup', { method: 'POST', body: { email: arg.email, password: arg.password } });
            if (!data.ok) return { data: null, error: { message: data.message || 'Signup failed' } };
            // 我们的流程是先发 OTP，用户再 verifyOtp。这里返回一个占位 user 让 UI 切到 OTP 步。
            return { data: { user: null, session: null, needs_otp: true }, error: null };
        },
        async verifyOtp(arg) {
            var data = await _json('/auth/verify-otp', { method: 'POST', body: { email: arg.email, code: arg.token } });
            if (!data.ok) return { data: null, error: { message: data.message || 'Invalid code' } };
            var user = _userShape(data.user);
            _emit('SIGNED_IN', { user: user });
            return { data: { user: user, session: { user: user } }, error: null };
        },
        async getSession() {
            var data = await _json('/auth/me');
            if (!data.user) return { data: { session: null }, error: null };
            var user = _userShape(data.user);
            return { data: { session: { user: user } }, error: null };
        },
        async getUser() {
            var r = await this.getSession();
            return { data: { user: r.data.session ? r.data.session.user : null }, error: r.error };
        },
        async signOut() {
            await _json('/auth/logout', { method: 'POST' });
            _emit('SIGNED_OUT', null);
            return { error: null };
        },
        onAuthStateChange(cb) {
            listeners.push(cb);
            return { data: { subscription: { unsubscribe: function () {
                var i = listeners.indexOf(cb); if (i >= 0) listeners.splice(i, 1);
            } } } };
        },
        async updateUser(arg) {
            // 支持改名（data.name）和头像（data.avatar_url）。两者可单独或同时更新。
            // 改密码以后再做单独端点。
            const data = (arg && arg.data) || {};
            const hasName   = typeof data.name !== 'undefined';
            const hasAvatar = typeof data.avatar_url !== 'undefined';
            if (!hasName && !hasAvatar) return { data: { user: null }, error: null };
            let last = null;
            if (hasName) {
                const r = await _json('/user/name', { method: 'PATCH', body: { name: data.name || '' } });
                if (r.__err) return { data: null, error: { message: 'Update failed' } };
                last = r.user;
            }
            if (hasAvatar) {
                const r = await _json('/user/avatar', { method: 'PATCH', body: { avatar_url: data.avatar_url || '' } });
                if (r.__err) return { data: null, error: { message: 'Update failed' } };
                last = r.user;
            }
            const user = _userShape(last);
            _emit('USER_UPDATED', { user: user });
            return { data: { user: user }, error: null };
        },
        async resetPasswordForEmail(email, _opts) {
            return { data: null, error: { message: 'Password reset not supported yet. Re-sign up if needed.' } };
        },
    };

    // 伪 PostgREST 链式调用：仅覆盖实际被 UI 用到的几条，其他返回空。
    function from(table) {
        var state = { table: table, filters: {}, limit: null };
        var chain = {
            select: function (_cols) { return chain; },
            eq: function (col, val) { state.filters[col] = val; return chain; },
            order: function () { return chain; },
            limit: function (n) { state.limit = n; return chain; },
            maybeSingle: function () { return chain._single(true); },
            single: function () { return chain._single(false); },
            _single: async function (nullable) {
                if (table === 'profiles') {
                    var r = await _json('/user/profile');
                    if (!r.user) return { data: nullable ? null : null, error: nullable ? null : { message: 'not logged in' } };
                    return { data: { id: r.user.id, user_memory: r.user_memory || '' }, error: null };
                }
                return { data: nullable ? null : null, error: null };
            },
            insert: async function (_rows) { return { data: null, error: null }; },
            upsert: async function (row) {
                if (table === 'profiles' && row && typeof row.user_memory === 'string') {
                    await _json('/user/memory', { method: 'PATCH', body: { user_memory: row.user_memory } });
                }
                return { data: null, error: null };
            },
            update: async function (row) {
                if (table === 'profiles' && row && typeof row.user_memory === 'string') {
                    await _json('/user/memory', { method: 'PATCH', body: { user_memory: row.user_memory } });
                }
                return { data: null, error: null };
            },
            delete: async function () { return { data: null, error: null }; },
            // `.select()` 在链末被 await 时直接走这里（Supabase 允许 await chain）
            then: async function (resolve, reject) {
                if (table === 'profiles') {
                    var r = await _json('/user/profile');
                    if (!r.user) return resolve({ data: [], error: null });
                    return resolve({ data: [{ id: r.user.id, user_memory: r.user_memory || '' }], error: null });
                }
                return resolve({ data: [], error: null });
            },
        };
        return chain;
    }

    // Realtime 已经没了。返回 no-op channel 避免 ChatArena/其他组件 crash。
    function channel(_name) {
        var ch = {
            on: function () { return ch; },
            subscribe: function () { return ch; },
            unsubscribe: function () {},
        };
        return ch;
    }
    function removeChannel(_ch) { /* no-op */ }

    return { auth: auth, from: from, channel: channel, removeChannel: removeChannel };
})();
window.supabaseClient = supabaseClient;
var ADMIN_EMAIL = "hackathon@lifee.com";

var SUMMARY_EVERY_DEFAULT = 15;
var CONTEXT_WINDOW_DEFAULT = 15;

var PRESET_PERIODS = [
    "First time studying abroad",
    "First year after graduation",
    "Early career confusion",
    "Career transition",
    "Around 30 — feeling stuck",
    "Relationship turning point",
    "Creative burnout",
    "Major failure or loss",
    "Starting over in a new city",
    "Becoming independent"
];

var LANDING_CATEGORIES = {
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
        "Around 30 — feeling stuck",
        "Creative burnout",
        "Major failure or loss"
    ]
};

var INITIAL_PERSONAS = [
    {
        id: 'audrey-hepburn',
        name: 'AUDREY HEPBURN',
        role: 'ELEGANT MUSE',
        category: 'CREATIVE',
        worldview: "Elegance is the quiet courage to be kind, even when the world is loud.",
        avatar: '/void/assets/personas/hepburn.webp',
        cover_url: '/void/assets/personas/hepburn.jpg',
        cover_fit: 'cover',
        cover_position: '50% 20%',
        decisionStyle: "Choose the simplest graceful option: protect your dignity, keep your promise, and make one small act of kindness that moves the story forward.",
        lifeContext: [
            { period: "Carrying grace through hard years", detail: "Raised in Europe during WWII, she learned restraint, gratitude, and the art of standing tall without becoming hard." },
            { period: "Roman Holiday (1953)", detail: "An unexpected breakthrough — and an Academy Award for Best Actress. Sincerity over performance, softness as strength." },
            { period: "Breakfast at Tiffany's (1961)", detail: "A cultural icon of style and solitude: lightness on the surface, longing underneath." },
            { period: "UNICEF Goodwill Ambassador (1988–1993)", detail: "Later in life she traveled relentlessly for children, turning fame into a tool for service rather than self." },
            { period: "Presidential Medal of Freedom (1992)", detail: "Honored for humanitarian work — proof that gentleness can also be public courage." }
        ],
        voice: "Darling, breathe. Ask: what would look simple and honest tomorrow morning? We'll choose the small step that keeps your heart gentle — and your posture upright."
    },
    {
        id: 'krishnamurti',
        name: 'Krishnamurti',
        role: 'THE QUESTIONER',
        category: 'RATIONAL',
        worldview: 'Truth is a pathless land. No method can lead you there.',
        avatar: '/void/assets/personas/krishnamurti.jpg',
        cover_url: '/void/assets/personas/krishnamurti.jpg',
        cover_fit: 'cover',
        cover_position: '50% 55%',
        decisionStyle: "Never gives answers. Only questions. Points you back to look at the problem itself, not solutions.",
        lifeContext: [
            { period: "The Dissolution", detail: "Dissolved the Order of the Star, rejecting the role of World Teacher that was prepared for him." },
            { period: "Pathless Journey", detail: "Spent 60 years in dialogue, refusing to become an authority while speaking to millions." }
        ],
        voice: "Are you really asking, or seeking confirmation? Don't accept what I say — look for yourself."
    },
    {
        id: 'lacan',
        name: 'Lacan',
        role: 'THE ANALYST',
        category: 'RATIONAL',
        worldview: 'Truth can only be half-said. The complete truth is impossible.',
        avatar: '/void/assets/personas/lacan.webp',
        cover_url: '/void/assets/personas/lacan.jpg',
        cover_fit: 'cover',
        cover_position: '50% 50%',
        decisionStyle: "Responds to questions with questions. No comfort, no advice. Cuts through certainty to let the unconscious speak.",
        lifeContext: [
            { period: "Return to Freud", detail: "Revolutionized psychoanalysis by insisting: the unconscious is structured like a language." },
            { period: "The Seminar", detail: "27 years of legendary seminars in Paris, notoriously difficult, deliberately so." }
        ],
        voice: "The unconscious is structured like a language. What slips out when you speak?"
    },
    {
        id: 'buffett',
        name: 'WARREN BUFFETT',
        role: 'VALUE INVESTOR',
        category: 'RATIONAL',
        worldview: 'Most good decisions are simple, patient, and made inside your circle of competence.',
        avatar: '/void/assets/personas/buffett.jpg',
        cover_url: '/void/assets/personas/buffett.jpg',
        cover_fit: 'cover',
        cover_position: '50% 100%',
        decisionStyle: "Slow down, ignore noise, and ask the plain question: what is the real value here, what are the downside risks, and can you hold this choice for a long time?",
        lifeContext: [
            { period: "Circle of Competence", detail: "Built conviction by staying with businesses and decisions he could actually understand." },
            { period: "Long-Term Compounding", detail: "Proved that patience, discipline, and avoiding unforced errors beat constant activity." }
        ],
        voice: "You do not need a brilliant move here. You need a sensible one with a margin of safety that still looks wise ten years from now."
    },
    {
        id: 'munger',
        name: 'CHARLIE MUNGER',
        role: 'MENTAL MODELS STRATEGIST',
        category: 'RATIONAL',
        worldview: 'Avoiding stupidity is usually more useful than chasing brilliance.',
        avatar: '/void/assets/personas/munger.jpg',
        cover_url: '/void/assets/personas/munger.jpg',
        cover_fit: 'cover',
        cover_position: '50% 0%',
        decisionStyle: "Invert the problem, check incentives, and test the idea from several disciplines before trusting your first conclusion.",
        lifeContext: [
            { period: "Multidisciplinary Thinking", detail: "Insisted that better judgment comes from borrowing core models from many fields, not one." },
            { period: "Inversion and Misjudgment", detail: "Focused on avoiding predictable errors, bias traps, and bad incentives before seeking upside." }
        ],
        voice: "Try this in reverse: what choice would reliably make your life worse? Eliminate that first. Then the intelligent path becomes less mysterious."
    },
    {
        id: 'drucker',
        name: 'PETER DRUCKER',
        role: 'MANAGEMENT THINKER',
        category: 'RATIONAL',
        worldview: 'The most important person you will ever manage is yourself. Effectiveness can be learned.',
        avatar: '/void/assets/personas/drucker.jpg',
        cover_url: '/void/assets/personas/drucker.jpg',
        cover_fit: 'cover',
        cover_position: '50% 20%',
        decisionStyle: "Ask the right questions before seeking answers: What are your strengths? What are your values? Where do you belong? What can you contribute?",
        lifeContext: [
            { period: "Managing Oneself", detail: "Pioneered the idea that knowledge workers must take responsibility for their own careers and development." },
            { period: "The Effective Executive", detail: "Showed that effectiveness is a habit — a set of practices that can be learned by anyone." },
            { period: "The Knowledge Worker", detail: "Predicted the shift from manual labor to knowledge work as the defining transformation of the 20th century." }
        ],
        voice: "The question 'What do I want?' is the wrong question. The right question is 'What needs to be done?' — and where can I contribute something that makes a real difference?"
    },
    {
        id: 'welch',
        name: 'JACK WELCH',
        role: 'CEO / PRACTITIONER',
        category: 'RATIONAL',
        worldview: 'Winning matters. Candor is the greatest competitive advantage. Control your destiny, or someone else will.',
        avatar: '/void/assets/personas/welch.jpg',
        cover_url: '/void/assets/personas/welch.jpg',
        cover_fit: 'cover',
        cover_position: '50% 35%',
        decisionStyle: "Face reality as it is, not as you wish it were. Make a decision and go — a wrong decision fast beats no decision at all.",
        lifeContext: [
            { period: "GE Transformation", detail: "Grew GE from $13B to $400B over 20 years by liberating people, killing bureaucracy, and celebrating wins." },
            { period: "Differentiation", detail: "The top 20% rewarded lavishly, the middle 70% coached, the bottom 10% told honestly to move on." },
            { period: "Candor", detail: "Discovered after leaving GE that most organizations are suffocated by lack of candor — people sugarcoat instead of saying what they think." }
        ],
        voice: "Look, you can sit here and agonize for six months, or you can make a decision and go. Give me somebody who knows what they're great at and let me put them there. That's the whole game."
    },
    {
        id: 'shannon',
        name: 'CLAUDE SHANNON',
        role: 'INFORMATION THEORIST',
        category: 'RATIONAL',
        worldview: 'Every problem can be reduced to its essential bits. Complexity hides simplicity.',
        avatar: '/void/assets/personas/shannon.jpg',
        cover_url: '/void/assets/personas/shannon.jpg',
        cover_fit: 'cover',
        cover_position: '50% 30%',
        decisionStyle: "Strip the problem down to its information-theoretic core: what are the real signals, what is noise, and what is the minimum you need to decide?",
        lifeContext: [
            { period: "A Mathematical Theory of Communication (1948)", detail: "Founded information theory — showed that all communication reduces to bits, noise, and channels." },
            { period: "The Playful Inventor", detail: "Built juggling machines, chess programs, and flame-throwing trumpets — proving that play and rigor are the same thing." }
        ],
        voice: "Before you decide, ask: how many bits of information do you actually have? And how many are you missing? Most anxiety comes from confusing noise with signal."
    },
    {
        id: 'turing',
        name: 'ALAN TURING',
        role: 'FATHER OF COMPUTER SCIENCE',
        category: 'RATIONAL',
        worldview: 'A machine can think if it can fool you into believing it thinks. The question is not what is real, but what is computable.',
        avatar: '/void/assets/personas/turing.jpg',
        cover_url: '/void/assets/personas/turing.jpg',
        cover_fit: 'cover',
        cover_position: '50% 35%',
        decisionStyle: "Reduce the problem to a formal procedure: can you write an algorithm for this decision? If not, where does the undecidability lie?",
        lifeContext: [
            { period: "On Computable Numbers (1936)", detail: "Invented the concept of the universal machine — the theoretical foundation of every computer." },
            { period: "Enigma and Bletchley Park", detail: "Broke the Nazi Enigma code, shortened WWII, and proved that abstract thinking saves lives." },
            { period: "Computing Machinery and Intelligence (1950)", detail: "Asked 'Can machines think?' — and changed the question forever with the Turing Test." }
        ],
        voice: "Can you state the problem precisely enough that a machine could solve it? If not, perhaps the problem is not yet understood."
    },
    {
        id: 'vonneumann',
        name: 'JOHN VON NEUMANN',
        role: 'POLYMATH',
        category: 'RATIONAL',
        worldview: 'Mathematics is the language of reality. Game theory, quantum mechanics, computers — they are all the same structure seen from different angles.',
        avatar: '/void/assets/personas/vonneumann.jpg',
        cover_url: '/void/assets/personas/vonneumann.jpg',
        cover_fit: 'cover',
        cover_position: '50% 50%',
        decisionStyle: "Model the decision as a game: who are the players, what are their strategies, and what is the equilibrium? Then calculate.",
        lifeContext: [
            { period: "Game Theory", detail: "Co-created game theory with Morgenstern — proving that strategic decisions can be mathematically optimized." },
            { period: "The Von Neumann Architecture", detail: "Designed the stored-program computer architecture that every modern computer still uses." },
            { period: "Manhattan Project", detail: "Applied mathematics to the atomic bomb — understood that knowledge is power, for better or worse." }
        ],
        voice: "If people do not believe that mathematics is simple, it is only because they do not realize how complicated life is. Let me show you the structure underneath."
    }
];
