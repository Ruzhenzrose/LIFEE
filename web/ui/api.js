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

// Internal: drain an SSE response body into handler callbacks.
// Shared by the active POST stream (debate) and the observer GET stream (resume).
// Accumulators are LOCAL to each invocation so concurrent streams (original +
// observer) can't interfere via shared global state.
async function _drainLifeeSSE(res, handlers, resetIdle) {
    const { onMessage, onMessageUpdate, onOptions, onSession, onStatus } = handlers || {};
    if (!res.body) throw new Error("Streaming not supported in this browser.");
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    let done = false;
    let streamPid = null;       // local: current persona id within THIS stream
    let streamText = "";        // local: accumulated text within THIS stream

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
            if (data?.sessionId) {
                window.__lifeeSessionId = data.sessionId;
                try { await onSession?.(data.sessionId); } catch (_) {}
            }
        } else if (eventName === "status") {
            // Warming-up phase signal: "kb_search" / "picked:<id>" / etc.
            // Frontend translates the stage code into a shimmery italic line.
            if (data && typeof data === "object" && data.stage) {
                try { await onStatus?.(data.stage); } catch (_) {}
            }
        } else if (eventName === "messageStart") {
            // Don't clear the warming-up status here — the bubble is still
            // empty. Clear on the first real messageChunk instead.
            if (data?.personaId) {
                streamPid = data.personaId;
                streamText = "";
                await onMessage?.({ personaId: data.personaId, text: "" });
            }
        } else if (eventName === "messageChunk") {
            if (data?.chunk && streamPid) {
                const wasEmpty = streamText.length === 0;
                streamText += data.chunk;
                if (wasEmpty) {
                    try { await onStatus?.(null); } catch (_) {}
                }
                await onMessageUpdate?.({ personaId: streamPid, text: streamText });
            }
        } else if (eventName === "messageEnd") {
            streamPid = null;
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

    while (!done) {
        const { value, done: streamDone } = await reader.read();
        if (streamDone) break;
        resetIdle && resetIdle();
        buf += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buf.indexOf("\n\n")) !== -1) {
            const block = buf.slice(0, idx).trimEnd();
            buf = buf.slice(idx + 2);
            await flushEventBlock(block);
        }
    }
}

// Attach to an in-flight generation for a session (resume after coming back
// from another view/tab/device). Uses the same SSE parser as the active stream
// so the observer gets smooth token-level updates + loading UX.
// Returns a promise; rejects with an informative Error if no active stream.
async function fetchLifeeObserveStream(sessionId, handlers = {}) {
    const res = await fetch(`/sessions/${encodeURIComponent(sessionId)}/observe-stream`, {
        method: "GET",
        credentials: "include",
    });
    if (res.status === 404) {
        const err = new Error("no active generation");
        err.notActive = true;
        throw err;
    }
    if (!res.ok) throw new Error(`observe-stream ${res.status}`);
    await _drainLifeeSSE(res, handlers);
}

async function fetchLifeeDecisionStream(payload, handlers = {}) {
    // No client-side timeout: backend task is detached, so a long stream can
    // run as long as the server says it's running; observer reconnects cover
    // the "tab was idle" case.
    const res = await fetch(`${LIFEE_API}?stream=1`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(payload),
    });

    if (!res.ok) {
        const text = await res.text();
        throw new Error("LIFEE API stream failed: " + text);
    }

    // Backend may return JSON (not SSE) for quota responses
    const ct = res.headers.get('content-type') || '';
    if (ct.includes('application/json')) {
        const data = await res.json();
        if (data?.needsPayment) {
            window.__lifeeNeedsPayment = true;
            window.__lifeeBalance = data.balance || 0;
        }
        return;
    }

    await _drainLifeeSSE(res, handlers);
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
