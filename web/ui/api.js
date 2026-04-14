var LIFEE_API = "/decision";
var LIFEE_API_TIMEOUT_MS = 60000;
var LIFEE_STREAM_TIMEOUT_MS = 90000;

async function copyToClipboard(text) {
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
}

async function fetchLifeeDecision(payload, url) {
    if (!url) url = LIFEE_API;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), LIFEE_API_TIMEOUT_MS);
    let res;

    try {
        res = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "include",
            body: JSON.stringify(payload),
            signal: controller.signal
        });
    } catch (err) {
        if (err?.name === 'AbortError') {
            throw new Error(`LIFEE API timed out after ${Math.round(LIFEE_API_TIMEOUT_MS / 1000)}s`);
        }
        throw err;
    } finally {
        clearTimeout(timer);
    }

    if (!res.ok) {
        const text = await res.text();
        throw new Error("LIFEE API failed: " + text);
    }

    return res.json();
}

var sleep = (ms) => new Promise(r => setTimeout(r, ms));

async function fetchText(url) {
    const res = await fetch(url, { method: 'GET' });
    if (!res.ok) throw new Error(`fetchText failed: ${res.status}`);
    return res.text();
}

async function fetchLifeeDecisionStream(payload, { onMessage, onMessageUpdate, onOptions } = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), LIFEE_STREAM_TIMEOUT_MS);
    let res;

    try {
        res = await fetch(`${LIFEE_API}?stream=1`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "include",
            body: JSON.stringify(payload),
            signal: controller.signal
        });
    } catch (err) {
        if (err?.name === 'AbortError') {
            throw new Error(`LIFEE API stream timed out after ${Math.round(LIFEE_STREAM_TIMEOUT_MS / 1000)}s`);
        }
        throw err;
    }

    if (!res.ok) {
        clearTimeout(timer);
        const text = await res.text();
        throw new Error("LIFEE API stream failed: " + text);
    }

    // 后端返回 JSON（非 SSE）：可能是余额不足或需要验证
    const ct = res.headers.get('content-type') || '';
    if (ct.includes('application/json')) {
        clearTimeout(timer);
        const data = await res.json();
        if (data?.needsVerification) {
            window.__lifeeNeedsVerification = true;
        }
        if (data?.needsPayment) {
            window.__lifeeNeedsPayment = true;
            window.__lifeeBalance = data.balance || 0;
        }
        return;
    }

    if (!res.body) {
        clearTimeout(timer);
        throw new Error("Streaming not supported in this browser.");
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    let done = false;

    const flushEventBlock = async (block) => {
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

        if (eventName === "session") {
            if (data?.sessionId) window.__lifeeSessionId = data.sessionId;
        } else if (eventName === "messageStart") {
            if (data?.personaId) {
                window.__currentStreamPid = data.personaId;
                window.__currentStreamText = "";
                await onMessage?.({ personaId: data.personaId, text: "" });
            }
        } else if (eventName === "messageChunk") {
            if (data?.chunk && window.__currentStreamPid) {
                window.__currentStreamText = (window.__currentStreamText || "") + data.chunk;
                await onMessageUpdate?.({ personaId: window.__currentStreamPid, text: window.__currentStreamText });
            }
        } else if (eventName === "messageEnd") {
            window.__currentStreamPid = null;
        } else if (eventName === "message") {
            if (data && typeof data === "object") await onMessage?.(data);
        } else if (eventName === "options") {
            const opts = (data && typeof data === "object") ? data.options : [];
            onOptions?.(Array.isArray(opts) ? opts : []);
        } else if (eventName === "error") {
            const errMsg = (data && typeof data === "object") ? (data.error || JSON.stringify(data)) : String(data);
            throw new Error(errMsg);
        } else if (eventName === "done") {
            if (typeof data?.balance === 'number') window.__lifeeBalance = data.balance;
            done = true;
        }
    };

    try {
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
    } catch (err) {
        if (err?.name === 'AbortError') {
            throw new Error(`LIFEE API stream timed out after ${Math.round(LIFEE_STREAM_TIMEOUT_MS / 1000)}s`);
        }
        throw err;
    } finally {
        clearTimeout(timer);
    }
}

async function fetchLifeeDecisionProgressive(payload, { onMessage, onOptions } = {}) {
    const personas = Array.isArray(payload?.personas) ? payload.personas : [];
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
        await sleep(0);
    }
    onOptions?.(lastOptions);
}

var TURNSTILE_SITEKEY = '0x4AAAAAAC8YCs3sdJ7Sz6Kl';
var isLocalPreviewHost = () => ['localhost', '127.0.0.1'].includes(window.location.hostname);

async function verifyHumanTokenWithServer(token) {
    try {
        const response = await fetch('/verify-human', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ token }),
        });
        const data = await response.json().catch(() => ({}));
        if (response.ok && data?.ok !== false) return { ok: true };
        if (isLocalPreviewHost()) return { ok: true, bypassed: true };
        return { ok: false, message: data?.message || 'Human verification failed on server.' };
    } catch (_) {
        if (isLocalPreviewHost()) return { ok: true, bypassed: true };
        return { ok: false, message: 'Verification service is unreachable. Please retry.' };
    }
}
