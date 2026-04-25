(() => {
    const { useState, useEffect, useRef } = React;

    // -------------------------------------------------------------------------
    // VoidIcon — Material Symbols Outlined wrapper
    // -------------------------------------------------------------------------
    const VoidIcon = ({ name, size = 24, filled = false, className = '' }) => {
        return React.createElement(
            'span',
            {
                className: 'material-symbols-outlined ' + className,
                style: {
                    fontSize: size,
                    fontVariationSettings: filled ? "'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 24"
                                                  : "'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24",
                    userSelect: 'none',
                    lineHeight: 1,
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                }
            },
            name
        );
    };

    // -------------------------------------------------------------------------
    // AvatarDisplay — emoji text or image URL, with optional halo ring
    // -------------------------------------------------------------------------
    // ringColor: any Tailwind/CSS color string, e.g. '#22D3EE', 'cyan', null
    // ringWidth: ring border width in px (default 2)
    const AvatarDisplay = ({ avatar, className = '', ringColor = null, ringWidth = 2 }) => {
        const isImage = typeof avatar === 'string' &&
            (avatar.startsWith('data:image') || avatar.startsWith('http') || avatar.startsWith('/'));

        const ringStyle = ringColor
            ? {
                boxShadow: `0 0 0 ${ringWidth}px ${ringColor}, 0 0 12px 2px ${ringColor}40`,
              }
            : {};

        return React.createElement(
            'div',
            {
                className: `flex items-center justify-center overflow-hidden ${className}`,
                style: ringStyle,
            },
            isImage
                ? React.createElement('img', {
                      src: avatar,
                      alt: 'Avatar',
                      className: 'w-full h-full object-cover',
                  })
                : React.createElement(
                      'span',
                      { className: 'text-current leading-none select-none' },
                      avatar
                  )
        );
    };

    // -------------------------------------------------------------------------
    // Avatar choices
    // -------------------------------------------------------------------------
    const USER_AVATAR_KEY = 'lifee_user_avatar';
    const USER_AVATAR_DEFAULT_KEY = 'lifee_user_avatar_default';
    const USER_AVATAR_CHOICES = [
        '✨', '🌿', '🔥', '🕯️', '🪞', '🦉',
        '🌊', '💎', '🎭', '🛡️', '🌱', '☁️',
    ];

    const PERSONA_AVATAR_OVERRIDES_KEY = 'lifee_persona_avatar_overrides';
    const PERSONA_COVER_OVERRIDES_KEY  = 'lifee_persona_cover_overrides';
    const DEFAULT_PERSONA_ICONS = [
        '✨', '🌿', '🔥', '🕯️', '🪞', '🦉',
        '🌊', '💎', '🎭', '🛡️', '🌱', '☁️', '👤',
    ];

    // -------------------------------------------------------------------------
    // Helpers
    // -------------------------------------------------------------------------
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

    const fileToDataURL = (file) =>
        new Promise((resolve, reject) => {
            try {
                const reader = new FileReader();
                reader.onload  = () => resolve(String(reader.result || ''));
                reader.onerror = () => reject(new Error('Failed to read file'));
                reader.readAsDataURL(file);
            } catch (e) {
                reject(e);
            }
        });

    // -------------------------------------------------------------------------
    // Persona avatar / cover overrides (localStorage)
    // -------------------------------------------------------------------------
    const loadPersonaAvatarOverrides = () => {
        try {
            const raw = window.localStorage.getItem(PERSONA_AVATAR_OVERRIDES_KEY);
            if (!raw) return {};
            const parsed = JSON.parse(raw);
            return parsed && typeof parsed === 'object' ? parsed : {};
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
            return parsed && typeof parsed === 'object' ? parsed : {};
        } catch (_) {
            return {};
        }
    };

    const savePersonaCoverOverrides = (map) => {
        try {
            window.localStorage.setItem(PERSONA_COVER_OVERRIDES_KEY, JSON.stringify(map || {}));
        } catch (_) {}
    };

    // -------------------------------------------------------------------------
    // copyToClipboard — mirrors api.js but self-contained
    // -------------------------------------------------------------------------
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

    // -------------------------------------------------------------------------
    // Expose to global scope
    // -------------------------------------------------------------------------
    window.VoidIcon                   = VoidIcon;
    window.AvatarDisplay              = AvatarDisplay;
    window.pickRandom                 = pickRandom;
    window.loadUserAvatar             = loadUserAvatar;
    window.saveUserAvatar             = saveUserAvatar;
    window.rotateUserDefaultAvatar    = rotateUserDefaultAvatar;
    window.getOrCreateDefaultUserAvatar = getOrCreateDefaultUserAvatar;
    window.fileToDataURL              = fileToDataURL;
    window.loadPersonaAvatarOverrides = loadPersonaAvatarOverrides;
    window.savePersonaAvatarOverrides = savePersonaAvatarOverrides;
    window.loadPersonaCoverOverrides  = loadPersonaCoverOverrides;
    window.savePersonaCoverOverrides  = savePersonaCoverOverrides;
    window.copyToClipboard            = copyToClipboard;
    window.USER_AVATAR_KEY            = USER_AVATAR_KEY;
    window.USER_AVATAR_DEFAULT_KEY    = USER_AVATAR_DEFAULT_KEY;
    window.USER_AVATAR_CHOICES        = USER_AVATAR_CHOICES;
    window.DEFAULT_PERSONA_ICONS      = DEFAULT_PERSONA_ICONS;
})();
