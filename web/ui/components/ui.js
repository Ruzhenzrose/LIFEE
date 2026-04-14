const { useState, useEffect, useRef } = React;

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
const USER_AVATAR_CHOICES = ['✨', '🌿', '🔥', '🕯️', '🪞', '🦉', '🌊', '💎', '🎭', '🛡️', '🌱', '☁️'];

const pickRandom = (arr) => arr[Math.floor(Math.random() * arr.length)];

const getOrCreateDefaultUserAvatar = () => {
    try {
        const existing = window.localStorage.getItem(USER_AVATAR_DEFAULT_KEY);
        if (existing) return existing;
        const next = pickRandom(USER_AVATAR_CHOICES);
        window.localStorage.setItem(USER_AVATAR_DEFAULT_KEY, next);
        return next;
    } catch (_) {
        return '👤';
    }
};

const loadUserAvatar = () => {
    try {
        return window.localStorage.getItem(USER_AVATAR_KEY) || getOrCreateDefaultUserAvatar();
    } catch (_) {
        return '👤';
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
        return '👤';
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
const DEFAULT_PERSONA_ICONS = ['✨', '🌿', '🔥', '🕯️', '🪞', '🦉', '🌊', '💎', '🎭', '🛡️', '🌱', '☁️', '👤'];

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
                    <div className="absolute -top-10 -left-8 text-[120px] opacity-[0.08] select-none">{avatar || '👤'}</div>
                    <div className="absolute -bottom-12 -right-8 text-[140px] opacity-[0.07] select-none">{avatar || '👤'}</div>
                    <div className="absolute inset-0 flex items-center justify-center">
                        <div className="w-20 h-20 rounded-[28px] bg-white/70 border border-white shadow-sm flex items-center justify-center">
                            <AvatarDisplay avatar={avatar || '👤'} className="w-full h-full text-3xl opacity-60" />
                        </div>
                    </div>
                </>
            )}
            <div className="absolute inset-0 bg-gradient-to-br from-white/60 via-transparent to-transparent pointer-events-none" />
        </div>
    );
};

// Expose to global scope
window.Icon = Icon;
window.AvatarDisplay = AvatarDisplay;
window.PatternCover = PatternCover;
window.pickRandom = pickRandom;
window.loadUserAvatar = loadUserAvatar;
window.saveUserAvatar = saveUserAvatar;
window.rotateUserDefaultAvatar = rotateUserDefaultAvatar;
window.fileToDataURL = fileToDataURL;
window.loadPersonaAvatarOverrides = loadPersonaAvatarOverrides;
window.savePersonaAvatarOverrides = savePersonaAvatarOverrides;
window.loadPersonaCoverOverrides = loadPersonaCoverOverrides;
window.savePersonaCoverOverrides = savePersonaCoverOverrides;
window.USER_AVATAR_KEY = USER_AVATAR_KEY;
window.USER_AVATAR_DEFAULT_KEY = USER_AVATAR_DEFAULT_KEY;
window.DEFAULT_PERSONA_ICONS = DEFAULT_PERSONA_ICONS;
