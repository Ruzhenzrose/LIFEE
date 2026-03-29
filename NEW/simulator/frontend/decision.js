// ─── Quantitative Decision Module ────────────────────────────────
const DECISION_API = "/api";

const DIMENSION_META = {
    financial: { label: '财务影响', emoji: '💰', color: '#4dd0e1' },
    risk: { label: '风险水平', emoji: '⚠️', color: '#ff7043', invert: true },
    growth: { label: '成长潜力', emoji: '📈', color: '#66bb6a' },
    time_cost: { label: '时间成本', emoji: '⏰', color: '#ffa726', invert: true },
    wellbeing: { label: '幸福感', emoji: '😊', color: '#ab47bc' },
    feasibility: { label: '可行性', emoji: '✅', color: '#42a5f5' },
};

const OPTION_COLORS = [
    'rgba(77, 208, 225, 0.7)',
    'rgba(255, 112, 67, 0.7)',
    'rgba(102, 187, 106, 0.7)',
    'rgba(171, 71, 188, 0.7)',
];
const OPTION_FILLS = [
    'rgba(77, 208, 225, 0.12)',
    'rgba(255, 112, 67, 0.12)',
    'rgba(102, 187, 106, 0.12)',
    'rgba(171, 71, 188, 0.12)',
];

// ─── Start Analysis ──────────────────────────────────────────────

window.startDecisionAnalysis = async function () {
    const input = document.getElementById('decision-input');
    const dilemma = input.value.trim();
    if (!dilemma) {
        input.placeholder = '✨ 请先描述你的决策困境…';
        input.focus();
        return;
    }

    // Switch to loading
    document.getElementById('decision-setup').style.display = 'none';
    document.getElementById('decision-result').style.display = 'none';
    document.getElementById('decision-loading').style.display = 'flex';

    try {
        const response = await fetch(`${DECISION_API}/decision/analyze`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ dilemma }),
        });

        if (!response.ok) throw new Error(`API Error: ${response.statusText}`);
        const data = await response.json();

        document.getElementById('decision-loading').style.display = 'none';
        document.getElementById('decision-result').style.display = 'flex';

        renderDecisionResult(data);
    } catch (err) {
        console.error('Decision analysis failed:', err);
        document.getElementById('decision-loading').style.display = 'none';
        document.getElementById('decision-setup').style.display = 'flex';
        alert('⚠️ 决策分析失败，请检查后端是否运行。');
    }
};

// ─── Render Results ──────────────────────────────────────────────

function renderDecisionResult(data) {
    const options = data.options || [];

    // 1. Radar chart
    drawRadarChart(options);

    // 2. Comparison table
    renderComparisonTable(options);

    // 3. Scenario cards
    renderScenarios(options);

    // 4. Recommendation
    renderRecommendation(data.recommendation || '');
}

// ─── Radar Chart (Pure Canvas) ───────────────────────────────────

function drawRadarChart(options) {
    const container = document.getElementById('radar-chart-container');
    container.innerHTML = '';

    const canvas = document.createElement('canvas');
    const size = Math.min(container.clientWidth, 420);
    canvas.width = size;
    canvas.height = size;
    canvas.style.width = size + 'px';
    canvas.style.height = size + 'px';
    container.appendChild(canvas);

    const ctx = canvas.getContext('2d');
    const cx = size / 2;
    const cy = size / 2;
    const radius = size * 0.35;
    const dims = Object.keys(DIMENSION_META);
    const n = dims.length;
    const angleStep = (2 * Math.PI) / n;
    const startAngle = -Math.PI / 2;

    // Draw grid rings
    ctx.strokeStyle = 'rgba(255,255,255,0.08)';
    ctx.lineWidth = 1;
    for (let ring = 1; ring <= 5; ring++) {
        const r = (radius / 5) * ring;
        ctx.beginPath();
        for (let i = 0; i <= n; i++) {
            const angle = startAngle + i * angleStep;
            const x = cx + r * Math.cos(angle);
            const y = cy + r * Math.sin(angle);
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        }
        ctx.closePath();
        ctx.stroke();
    }

    // Draw axes + labels
    ctx.font = '12px Roboto, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    for (let i = 0; i < n; i++) {
        const angle = startAngle + i * angleStep;
        const x1 = cx + radius * Math.cos(angle);
        const y1 = cy + radius * Math.sin(angle);

        ctx.strokeStyle = 'rgba(255,255,255,0.1)';
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.lineTo(x1, y1);
        ctx.stroke();

        // Label
        const labelR = radius + 28;
        const lx = cx + labelR * Math.cos(angle);
        const ly = cy + labelR * Math.sin(angle);
        ctx.fillStyle = '#c4c7c5';
        const meta = DIMENSION_META[dims[i]];
        ctx.fillText(`${meta.emoji} ${meta.label}`, lx, ly);
    }

    // Draw data polygons
    options.forEach((opt, idx) => {
        ctx.beginPath();
        const color = OPTION_COLORS[idx % OPTION_COLORS.length];
        const fill = OPTION_FILLS[idx % OPTION_FILLS.length];

        for (let i = 0; i <= n; i++) {
            const dim = dims[i % n];
            const val = (opt.scores[dim] || 0) / 100;
            const angle = startAngle + (i % n) * angleStep;
            const r = radius * val;
            const x = cx + r * Math.cos(angle);
            const y = cy + r * Math.sin(angle);
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        }
        ctx.closePath();

        ctx.fillStyle = fill;
        ctx.fill();
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.stroke();

        // Draw dots
        for (let i = 0; i < n; i++) {
            const dim = dims[i];
            const val = (opt.scores[dim] || 0) / 100;
            const angle = startAngle + i * angleStep;
            const r = radius * val;
            const x = cx + r * Math.cos(angle);
            const y = cy + r * Math.sin(angle);
            ctx.beginPath();
            ctx.arc(x, y, 3.5, 0, 2 * Math.PI);
            ctx.fillStyle = color;
            ctx.fill();
        }
    });

    // Legend
    const legend = document.createElement('div');
    legend.className = 'radar-legend';
    options.forEach((opt, idx) => {
        const item = document.createElement('div');
        item.className = 'radar-legend-item';
        const dot = document.createElement('span');
        dot.className = 'legend-dot';
        dot.style.backgroundColor = OPTION_COLORS[idx % OPTION_COLORS.length];
        const label = document.createElement('span');
        label.textContent = `${opt.name} (EV: ${opt.expected_value})`;
        item.appendChild(dot);
        item.appendChild(label);
        legend.appendChild(item);
    });
    container.appendChild(legend);
}

// ─── Comparison Table ────────────────────────────────────────────

function renderComparisonTable(options) {
    const container = document.getElementById('decision-table-container');
    const dims = Object.keys(DIMENSION_META);

    let html = '<table class="decision-table"><thead><tr><th>维度</th>';
    options.forEach((opt, i) => {
        html += `<th style="color:${OPTION_COLORS[i % OPTION_COLORS.length]}">${opt.name}</th>`;
    });
    html += '</tr></thead><tbody>';

    dims.forEach(dim => {
        const meta = DIMENSION_META[dim];
        html += `<tr><td>${meta.emoji} ${meta.label}</td>`;

        // Find best value for highlighting
        const values = options.map(o => o.scores[dim] || 0);
        const bestVal = meta.invert ? Math.min(...values) : Math.max(...values);

        options.forEach(opt => {
            const val = opt.scores[dim] || 0;
            const isBest = val === bestVal;
            const cls = isBest ? 'best-score' : '';
            html += `<td class="${cls}">${val}</td>`;
        });
        html += '</tr>';
    });

    // EV row
    html += '<tr class="ev-row"><td>📊 期望值</td>';
    const evs = options.map(o => o.expected_value);
    const bestEV = Math.max(...evs);
    options.forEach(opt => {
        const isBest = opt.expected_value === bestEV;
        html += `<td class="${isBest ? 'best-score' : ''}">${opt.expected_value}</td>`;
    });
    html += '</tr></tbody></table>';

    container.innerHTML = html;
}

// ─── Scenario Cards ─────────────────────────────────────────────

function renderScenarios(options) {
    const container = document.getElementById('decision-scenarios');
    container.innerHTML = '<h3>🎯 情景分析</h3>';

    const grid = document.createElement('div');
    grid.className = 'scenario-grid';

    options.forEach((opt, idx) => {
        const card = document.createElement('div');
        card.className = 'scenario-card';
        card.style.borderColor = OPTION_COLORS[idx % OPTION_COLORS.length];

        card.innerHTML = `
            <h4 style="color:${OPTION_COLORS[idx % OPTION_COLORS.length]}">${opt.name}</h4>
            <p class="scenario-desc">${opt.description}</p>
            <div class="scenario-item best">
                <span class="scenario-label">🌟 最佳</span>
                <span>${opt.scenarios.best_case}</span>
            </div>
            <div class="scenario-item likely">
                <span class="scenario-label">📋 最可能</span>
                <span>${opt.scenarios.most_likely}</span>
            </div>
            <div class="scenario-item worst">
                <span class="scenario-label">⚡ 最差</span>
                <span>${opt.scenarios.worst_case}</span>
            </div>
        `;
        grid.appendChild(card);
    });

    container.appendChild(grid);
}

// ─── Recommendation ──────────────────────────────────────────────

function renderRecommendation(text) {
    const container = document.getElementById('decision-recommendation');
    const html = text
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/^## (.+)$/gm, '<h3>$1</h3>')
        .replace(/^# (.+)$/gm, '<h2>$1</h2>')
        .replace(/\n/g, '<br>');
    container.innerHTML = `<h3>🤖 AI 综合建议</h3><div class="rec-text">${html}</div>`;
}

// ─── Reset ───────────────────────────────────────────────────────

window.resetDecision = function () {
    document.getElementById('decision-input').value = '';
    document.getElementById('radar-chart-container').innerHTML = '';
    document.getElementById('decision-table-container').innerHTML = '';
    document.getElementById('decision-scenarios').innerHTML = '';
    document.getElementById('decision-recommendation').innerHTML = '';

    document.getElementById('decision-result').style.display = 'none';
    document.getElementById('decision-loading').style.display = 'none';
    document.getElementById('decision-setup').style.display = 'flex';
};

// ─── Enter key support ──────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    const q = document.getElementById('decision-input');
    if (q) {
        q.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                startDecisionAnalysis();
            }
        });
    }
});
