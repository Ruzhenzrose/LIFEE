// --- State ---
const API_BASE = "/api";
let currentState = null;
let history = [];
let isSimulating = false;

// --- DOM Elements ---
const els = {
    viewInit: document.getElementById('view-init'),
    viewSim: document.getElementById('view-simulation'),
    narrativeBox: document.getElementById('narrative-box'),
    inputBox: document.getElementById('user-input'),
    sendBtn: document.getElementById('btn-send'),
    chipsContainer: document.getElementById('options-container'),
    loadingSim: document.getElementById('loading-sim'),
    loadingInit: document.getElementById('loading-init'),
    statusBar: document.getElementById('status-bar'),
    epiphanyView: document.getElementById('view-epiphany'),
    epiphanyText: document.getElementById('epiphany-text'),

    // Stats
    stats: {
        age: document.getElementById('stat-age'),
        health: document.getElementById('stat-health'),
        wealth: document.getElementById('stat-wealth'),
        happiness: document.getElementById('stat-happiness'),
        capability: document.getElementById('stat-capability')
    },
    bars: {
        health: document.getElementById('bar-health'),
        wealth: document.getElementById('bar-wealth'),
        happiness: document.getElementById('bar-happiness'),
        capability: document.getElementById('bar-capability')
    }
};

// --- Helper Functions ---
async function postData(endpoint, data) {
    try {
        const response = await fetch(`${API_BASE}${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(`API Error: ${response.statusText}`);
        return await response.json();
    } catch (error) {
        console.error(error);
        appendMessage('system', "⚠️ Connection to Parallel Universe interrupted. Please check the backend.");
        return null;
    }
}

function appendMessage(sender, text) {
    const row = document.createElement('div');
    row.className = `message-row ${sender}-message`;

    const avatar = document.createElement('div');
    avatar.className = `avatar avatar-${sender}`;
    avatar.innerHTML = sender === 'ai' ? '<span class="material-icons-outlined" style="font-size: 18px; color: white;">auto_awesome</span>' : 'U';

    const content = document.createElement('div');
    content.className = 'message-content';
    content.innerHTML = text.replace(/\n/g, '<br>');

    row.appendChild(avatar); // Order depends on flex-direction, but this is fine structure
    row.appendChild(content);

    els.narrativeBox.appendChild(row);
    // Auto scroll
    els.narrativeBox.scrollTop = els.narrativeBox.scrollHeight;

    // Ensure simulation view is visible
    if (sender === 'user' && !currentState) {
        // Still in init phase visually, wait for response
    } else {
        els.viewInit.classList.remove('active');
        els.viewSim.classList.add('active'); // Should be visible from start actually
    }
}

function updateStats(attrs, age) {
    els.statusBar.style.display = 'flex';

    els.stats.age.innerText = age.toFixed(1);

    const updateStat = (key) => {
        const val = attrs[key];
        els.stats[key].innerText = val;
        els.bars[key].style.width = `${Math.min(Math.max(val, 0), 100)}%`;
    };

    updateStat('health');
    updateStat('wealth');
    updateStat('happiness');
    updateStat('capability');
}

function renderChips(options) {
    els.chipsContainer.innerHTML = '';
    options.forEach(opt => {
        const chip = document.createElement('button');
        chip.className = 'chip';
        chip.innerText = opt;
        chip.onclick = () => handleInput(opt);
        els.chipsContainer.appendChild(chip);
    });
    // Auto-scroll chat after chips change layout height
    requestAnimationFrame(() => {
        els.narrativeBox.scrollTop = els.narrativeBox.scrollHeight;
    });
}

// --- Core Logic ---

async function handleInput(text = null) {
    if (isSimulating) return;

    const input = text || els.inputBox.value.trim();
    if (!input) return;

    // Clear input
    els.inputBox.value = '';
    els.chipsContainer.innerHTML = ''; // Hide chips while thinking

    // User Message
    appendMessage('user', input);

    if (!currentState) {
        // --- Phase 1: Init ---
        els.loadingInit.style.display = 'block';
        const profile = await postData('/init', { user_input: input });
        els.loadingInit.style.display = 'none';

        if (profile) {
            currentState = profile;
            history.push(`【初始状态】${profile.narrative_start}`);

            // UI Transition
            els.viewInit.style.display = 'none'; // Hide welcome
            els.viewSim.style.display = 'flex'; // Show chat

            updateStats(profile.attributes, profile.age);
            appendMessage('ai', profile.narrative_start + "\n\n模拟开始。如果你在现实中做出了第一个选择，会是什么？");
        }
    } else {
        // --- Phase 2: Simulation ---
        isSimulating = true;
        els.loadingSim.style.display = 'flex';

        const payload = {
            current_state: currentState,
            user_choice: input,
            history: history
        };

        const result = await postData('/simulation', payload);
        els.loadingSim.style.display = 'none';
        isSimulating = false;

        if (result) {
            // Update State
            Object.assign(currentState.attributes, result.new_attributes);
            currentState.age = result.new_age;
            history.push(result.history_entry);

            // Update UI
            updateStats(currentState.attributes, currentState.age);

            const msg = `📅 ${result.time_passed}\n${result.narrative}`;
            appendMessage('ai', msg);

            if (result.is_concluded) {
                await generateEpiphany(result.conclusion);
            } else {
                renderChips(result.next_options);
            }
        }
    }
}

async function generateEpiphany(conclusion = null) {
    appendMessage('ai', "Simulation Concluded. Analyzing timeline for insights...");

    const payload = {
        history: history,
        dilemma: currentState.current_dilemma,
        final_state: currentState,
        conclusion: conclusion
    };

    const result = await postData('/epiphany', payload);

    if (result) {
        els.epiphanyView.style.display = 'block';
        els.epiphanyText.innerHTML = result.epiphany.replace(/\n/g, '<br>');

        if (result.report_url) {
            const btn = document.getElementById('btn-download-report');
            btn.href = result.report_url;
            document.getElementById('report-container').style.display = 'block';
        }

        // Scroll to new content
        els.narrativeBox.scrollTop = els.narrativeBox.scrollHeight;
    }
}

// --- Event Listeners ---
els.sendBtn.addEventListener('click', () => handleInput());

els.inputBox.addEventListener('keypress', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleInput();
    }
});

// Sidebar Toggle (Responsive)
const sidebar = document.querySelector('.sidebar');
const menuBtn = document.querySelector('.menu-btn');

menuBtn.addEventListener('click', () => {
    if (window.innerWidth <= 768) {
        sidebar.classList.toggle('open');
    } else {
        sidebar.classList.toggle('collapsed');
    }
});

// Close sidebar when clicking outside on mobile
document.addEventListener('click', (e) => {
    if (window.innerWidth <= 768 &&
        sidebar.classList.contains('open') &&
        !sidebar.contains(e.target) &&
        !menuBtn.contains(e.target)) {
        sidebar.classList.remove('open');
    }
});

// Scroll chat to bottom when input area resizes (e.g. chips appear/disappear)
const inputWrapper = document.querySelector('.input-area-wrapper');
const chatContainer = document.getElementById('chat-container');

const resizeObserver = new ResizeObserver(() => {
    // With flex layout the chat auto-sizes, just ensure scroll stays at bottom
    els.narrativeBox.scrollTop = els.narrativeBox.scrollHeight;
});
if (inputWrapper) resizeObserver.observe(inputWrapper);

// --- Navigation & App Logic ---

function showElement(id, displayType = 'block') {
    document.getElementById(id).style.display = displayType;
}

function hideElement(id) {
    document.getElementById(id).style.display = 'none';
}

window.openApp = function (appName) {
    if (appName === 'simulator') {
        hideElement('view-home');
        hideElement('tarot-container');
        hideElement('decision-container');
        showElement('app-container', 'flex');

        // If no state, ensure init view is active
        if (!currentState) {
            els.viewInit.classList.add('active');
            els.viewSim.classList.remove('active');
        }
    } else if (appName === 'tarot') {
        hideElement('view-home');
        hideElement('app-container');
        hideElement('decision-container');
        showElement('tarot-container', 'flex');
    } else if (appName === 'decision') {
        hideElement('view-home');
        hideElement('app-container');
        hideElement('tarot-container');
        showElement('decision-container', 'flex');
    }
};

window.goHome = function () {
    showElement('view-home', 'flex');
    hideElement('app-container');
    hideElement('tarot-container');
    hideElement('decision-container');
};

window.resetSimulator = function () {
    if (confirm("Are you sure you want to restart? Current progress will be lost.")) {
        currentState = null;
        history = [];
        isSimulating = false;

        els.narrativeBox.innerHTML = '';
        els.epiphanyView.style.display = 'none';
        els.epiphanyText.innerHTML = '';
        document.getElementById('report-container').style.display = 'none';

        // Reset stats UI
        ['health', 'wealth', 'happiness', 'capability'].forEach(key => {
            els.stats[key].innerText = '--';
            els.bars[key].style.width = '0%';
        });
        els.stats.age.innerText = '--';

        // Return to Init View
        els.viewInit.classList.add('active');
        els.viewSim.classList.remove('active');
        els.statusBar.style.display = 'none';

        // Open sidebar on mobile if closed? No, keep as is.
    }
};

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    // Start at Home
    goHome();
});
