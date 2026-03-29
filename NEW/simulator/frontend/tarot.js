// ─── AI Tarot Module ─────────────────────────────────────────────
const TAROT_API = "/api";
let selectedSpread = "three_card";

// ─── Spread Selection ────────────────────────────────────────────

window.selectSpread = function (type) {
    selectedSpread = type;
    document.querySelectorAll('.spread-option').forEach(el => {
        el.classList.toggle('selected', el.dataset.spread === type);
    });
};

// ─── Start Reading ───────────────────────────────────────────────

window.startTarotReading = async function () {
    const question = document.getElementById('tarot-question').value.trim();
    if (!question) {
        document.getElementById('tarot-question').placeholder = '✨ 请先输入你的问题…';
        document.getElementById('tarot-question').focus();
        return;
    }

    // Switch to loading
    document.getElementById('tarot-setup').style.display = 'none';
    document.getElementById('tarot-result').style.display = 'none';
    document.getElementById('tarot-loading').style.display = 'flex';

    try {
        const response = await fetch(`${TAROT_API}/tarot/reading`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                question: question,
                spread_type: selectedSpread,
            }),
        });

        if (!response.ok) throw new Error(`API Error: ${response.statusText}`);
        const data = await response.json();

        // Hide loading, show result
        document.getElementById('tarot-loading').style.display = 'none';
        document.getElementById('tarot-result').style.display = 'flex';

        renderTarotCards(data.cards);
        renderReading(data.reading);
    } catch (err) {
        console.error('Tarot reading failed:', err);
        document.getElementById('tarot-loading').style.display = 'none';
        document.getElementById('tarot-setup').style.display = 'flex';
        alert('⚠️ 塔罗解读失败，请检查后端是否运行。');
    }
};

// ─── Card Rendering with Flip Animation ──────────────────────────

const CARD_BACK_SYMBOLS = ['✦', '☽', '★', '⊕', '♁', '☿', '♃', '♄', '♅', '♆'];

function renderTarotCards(cards) {
    const area = document.getElementById('tarot-cards-area');
    area.innerHTML = '';

    // Set layout class based on card count
    area.className = 'tarot-cards-area';
    if (cards.length === 1) area.classList.add('single-layout');
    else if (cards.length === 3) area.classList.add('three-layout');
    else area.classList.add('cross-layout');

    cards.forEach((card, index) => {
        const wrapper = document.createElement('div');
        wrapper.className = 'tarot-card-wrapper';
        wrapper.style.animationDelay = `${index * 0.15}s`;

        const cardEl = document.createElement('div');
        cardEl.className = 'tarot-card';
        cardEl.onclick = () => flipCard(cardEl);

        // Card Back
        const back = document.createElement('div');
        back.className = 'tarot-card-back';
        back.innerHTML = `
            <div class="card-back-pattern">
                <span class="card-back-symbol">${CARD_BACK_SYMBOLS[index % CARD_BACK_SYMBOLS.length]}</span>
            </div>
        `;

        // Card Front
        const front = document.createElement('div');
        front.className = 'tarot-card-front';
        const isReversed = card.orientation === 'reversed';
        front.innerHTML = `
            <div class="card-position-label">${card.position}</div>
            <div class="card-name-area ${isReversed ? 'reversed-card' : ''}">
                <div class="card-emoji">${getCardEmoji(card.name)}</div>
                <div class="card-name-cn">${card.name_cn}</div>
                <div class="card-name-en">${card.name}</div>
                <div class="card-orientation ${isReversed ? 'reversed' : 'upright'}">
                    ${card.orientation_cn}
                </div>
            </div>
            <div class="card-keywords">${card.keywords}</div>
        `;

        cardEl.appendChild(back);
        cardEl.appendChild(front);
        wrapper.appendChild(cardEl);
        area.appendChild(wrapper);

        // Auto-flip with staggered delay
        setTimeout(() => flipCard(cardEl), 800 + index * 500);
    });
}

function flipCard(cardEl) {
    if (!cardEl.classList.contains('flipped')) {
        cardEl.classList.add('flipped');
    }
}

function getCardEmoji(name) {
    const emojiMap = {
        'The Fool': '🃏', 'The Magician': '🎩', 'The High Priestess': '🌙',
        'The Empress': '👑', 'The Emperor': '🏛️', 'The Hierophant': '📿',
        'The Lovers': '❤️', 'The Chariot': '⚔️', 'Strength': '🦁',
        'The Hermit': '🏮', 'Wheel of Fortune': '🎡', 'Justice': '⚖️',
        'The Hanged Man': '🔮', 'Death': '💀', 'Temperance': '🏺',
        'The Devil': '😈', 'The Tower': '🗼', 'The Star': '⭐',
        'The Moon': '🌕', 'The Sun': '☀️', 'Judgement': '📯',
        'The World': '🌍',
    };
    // Check major arcana
    if (emojiMap[name]) return emojiMap[name];
    // Minor arcana — by suit
    if (name.includes('Wands')) return '🪄';
    if (name.includes('Cups')) return '🏆';
    if (name.includes('Swords')) return '⚔️';
    if (name.includes('Pentacles')) return '⭕';
    return '🎴';
}

// ─── Reading Text ────────────────────────────────────────────────

function renderReading(text) {
    const container = document.getElementById('tarot-reading-text');
    // Convert markdown-like text to HTML
    const html = text
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/^## (.+)$/gm, '<h3>$1</h3>')
        .replace(/^# (.+)$/gm, '<h2>$1</h2>')
        .replace(/\n/g, '<br>');
    container.innerHTML = html;
}

// ─── Reset ───────────────────────────────────────────────────────

window.resetTarot = function () {
    document.getElementById('tarot-question').value = '';
    document.getElementById('tarot-cards-area').innerHTML = '';
    document.getElementById('tarot-reading-text').innerHTML = '';

    document.getElementById('tarot-result').style.display = 'none';
    document.getElementById('tarot-loading').style.display = 'none';
    document.getElementById('tarot-setup').style.display = 'flex';
};

// ─── Enter key support ──────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    const q = document.getElementById('tarot-question');
    if (q) {
        q.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                startTarotReading();
            }
        });
    }
});
