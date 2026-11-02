// content.js — v4, clipboard-first + robust generation detection
console.log("[ChatGPT Bridge] Content Script v4 Injected.");

const PROXY_URL = "http://127.0.0.1:5000";

let isProcessing = false;
let tasksProcessed = 0;

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// ──────────────────────────────────────────────────────────────────────────────
// Message listeners from popup / background
// ──────────────────────────────────────────────────────────────────────────────
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === "GET_TASK_COUNT") {
        sendResponse({ count: tasksProcessed });
    }
    if (message.type === "RESET") {
        isProcessing = false;
        console.log("[ChatGPT Bridge] isProcessing reset by popup.");
        sendResponse({ ok: true });
    }
    return true;
});

// ──────────────────────────────────────────────────────────────────────────────
// Toast notification
// ──────────────────────────────────────────────────────────────────────────────
function showToast(msg, color = "#a78bfa") {
    let t = document.getElementById("gpt-bridge-toast");
    if (!t) {
        t = document.createElement("div");
        t.id = "gpt-bridge-toast";
        t.style.cssText = "position:fixed;bottom:20px;right:20px;padding:12px 20px;border-radius:8px;z-index:999999;font-weight:bold;font-size:14px;box-shadow:0 4px 12px rgba(0,0,0,0.3);transition:background 0.3s;";
        document.body.appendChild(t);
    }
    t.style.background = color;
    t.style.color = color === "#a78bfa" ? "#000" : "#fff";
    t.innerText = msg;
    clearTimeout(t._timeout);
    t._timeout = setTimeout(() => { if (t && t.parentNode) t.remove(); }, 5000);
}

// ──────────────────────────────────────────────────────────────────────────────
// Find the ChatGPT input box
// ──────────────────────────────────────────────────────────────────────────────
function findInput() {
    const selectors = [
        '#prompt-textarea',
        'div[contenteditable="true"][data-placeholder]',
        '.ProseMirror',
        'div[contenteditable="true"]',
        'textarea',
    ];
    for (const sel of selectors) {
        const el = document.querySelector(sel);
        if (el) {
            console.log("[ChatGPT Bridge] Input found:", sel);
            return el;
        }
    }
    return null;
}

// ──────────────────────────────────────────────────────────────────────────────
// Find the send button
// ──────────────────────────────────────────────────────────────────────────────
function findSendBtn() {
    const selectors = [
        'button[data-testid="send-button"]',
        'button[data-composer-submit]',
        'button[aria-label="Send message"]',
        'button[aria-label="Send prompt"]',
    ];
    for (const sel of selectors) {
        const el = document.querySelector(sel);
        if (el) return el;
    }
    // Generic fallback: last enabled submit-looking button in the form
    const btns = Array.from(document.querySelectorAll('form button[type="submit"], form button:not([type="button"])'));
    return btns.length > 0 ? btns[btns.length - 1] : null;
}

// ──────────────────────────────────────────────────────────────────────────────
// Inject text — NO clipboard API (requires focus). Uses execCommand + DataTransfer.
// ──────────────────────────────────────────────────────────────────────────────
async function injectText(input, text) {
    input.focus();
    await sleep(300);

    // Clear any existing text first
    document.execCommand('selectAll', false, null);
    document.execCommand('delete', false, null);
    await sleep(100);

    // --- Method 1: execCommand insertText (works for ProseMirror + textarea) ---
    input.focus();
    const inserted = document.execCommand('insertText', false, text);
    await sleep(400);

    let content = input.tagName === 'TEXTAREA' ? input.value : input.innerText;
    if (content.length > 20) {
        console.log("[ChatGPT Bridge] execCommand insertText success, length:", content.length);
        return;
    }
    console.warn("[ChatGPT Bridge] execCommand insertText failed, trying DataTransfer...");

    // --- Method 2: Synthetic paste event with DataTransfer ---
    // This does NOT require clipboard focus or user gesture.
    try {
        input.focus();
        const dt = new DataTransfer();
        dt.setData('text/plain', text);
        dt.setData('text/html', text.replace(/\n/g, '<br>'));
        const pasteEvent = new ClipboardEvent('paste', {
            clipboardData: dt,
            bubbles: true,
            cancelable: true,
        });
        input.dispatchEvent(pasteEvent);
        await sleep(400);

        content = input.tagName === 'TEXTAREA' ? input.value : input.innerText;
        if (content.length > 20) {
            console.log("[ChatGPT Bridge] DataTransfer paste success, length:", content.length);
            return;
        }
    } catch (e) {
        console.warn("[ChatGPT Bridge] DataTransfer paste failed:", e.message);
    }

    // --- Method 3: React native setter (textarea fallback) ---
    if (input.tagName === 'TEXTAREA') {
        const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
        nativeSetter.call(input, text);
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
        await sleep(300);
        content = input.value;
        if (content.length > 20) {
            console.log("[ChatGPT Bridge] React native setter success.");
            return;
        }
    }

    // --- Method 4: Manually set innerHTML + dispatch InputEvent ---
    try {
        input.focus();
        input.innerHTML = '';
        // For ProseMirror, set the text content directly
        const p = document.createElement('p');
        p.textContent = text;
        input.appendChild(p);
        input.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text }));
        await sleep(400);
        content = input.innerText;
        console.log("[ChatGPT Bridge] innerHTML method, length:", content.length);
    } catch (e) {
        console.error("[ChatGPT Bridge] All injection methods failed:", e.message);
    }
}

// ──────────────────────────────────────────────────────────────────────────────
// Detect if ChatGPT is still generating
// ──────────────────────────────────────────────────────────────────────────────
function isGenerating() {
    // If send button is visible & enabled → NOT generating
    const sendBtn = document.querySelector('button[data-testid="send-button"]');
    if (sendBtn && sendBtn.offsetHeight > 0 && !sendBtn.disabled && sendBtn.getAttribute('aria-disabled') !== 'true') {
        return false;
    }

    // Stop button visible → IS generating
    const stopSelectors = [
        'button[aria-label="Stop generating"]',
        '[data-testid="stop-button"]',
        'button[data-composer-stop]',
        '[data-composer-stop-icon]:not([hidden])',
    ];
    for (const sel of stopSelectors) {
        const el = document.querySelector(sel);
        if (el && el.offsetHeight > 0) return true;
    }

    return false;
}

// ──────────────────────────────────────────────────────────────────────────────
// Count assistant messages on page
// ──────────────────────────────────────────────────────────────────────────────
function countAssistantMsgs() {
    let n = document.querySelectorAll('[data-message-author-role="assistant"], li[data-message-role="assistant"]').length;
    if (n > 0) return n;
    n = document.querySelectorAll('article').length;
    if (n > 0) return n;
    return document.querySelectorAll('.markdown').length;
}

// ──────────────────────────────────────────────────────────────────────────────
// Extract the last assistant response as HTML
// ──────────────────────────────────────────────────────────────────────────────
function getLastAssistantText() {
    const asstNodes = document.querySelectorAll('[data-message-author-role="assistant"]');
    if (asstNodes.length > 0) {
        const last = asstNodes[asstNodes.length - 1];
        const mds = last.querySelectorAll('.markdown, [data-assistant-markdown]');
        if (mds.length > 0) return mds[mds.length - 1].innerHTML;
        return last.innerHTML;
    }

    const mdBlocks = document.querySelectorAll('.markdown');
    if (mdBlocks.length > 0) return mdBlocks[mdBlocks.length - 1].innerHTML;

    const articles = document.querySelectorAll('article');
    if (articles.length > 0) return articles[articles.length - 1].innerHTML;

    return "Error: Could not find ChatGPT response on page. DOM may have changed.";
}

// ──────────────────────────────────────────────────────────────────────────────
// Wait for ChatGPT to finish generating (event-driven, no busy polling)
// ──────────────────────────────────────────────────────────────────────────────
function waitForGenerationToFinish(prevMsgCount, timeoutMs = 180000) {
    return new Promise((resolve) => {
        showToast("⏳ Waiting for ChatGPT to respond...", "#6366f1");
        console.log("[ChatGPT Bridge] Waiting for generation...");

        // First wait up to 15s for generation to START
        let started = false;
        let startCheckId = null;
        let timeoutId = null;
        let observer = null;

        const cleanup = () => {
            if (observer) observer.disconnect();
            clearTimeout(timeoutId);
            clearInterval(startCheckId);
        };

        const checkDone = () => {
            const msgCount = countAssistantMsgs();
            if (!isGenerating() && msgCount > prevMsgCount) {
                console.log("[ChatGPT Bridge] Generation finished!");
                showToast("✅ Response complete. Extracting...", "#16a34a");
                cleanup();
                setTimeout(resolve, 800); // small delay for React to finish
            }
        };

        // MutationObserver watches for DOM changes
        observer = new MutationObserver(checkDone);
        observer.observe(document.body, { childList: true, subtree: true, attributes: true, characterData: true });

        // Timeout fallback
        timeoutId = setTimeout(() => {
            console.warn("[ChatGPT Bridge] Timeout! Extracting whatever is on screen.");
            showToast("⚠️ Timeout — extracting partial response.", "#b45309");
            cleanup();
            resolve();
        }, timeoutMs);

        // Immediate check
        checkDone();
    });
}

// ──────────────────────────────────────────────────────────────────────────────
// Main: process a task from the proxy
// ──────────────────────────────────────────────────────────────────────────────
async function processPrompt(taskId, prompt) {
    console.log("[ChatGPT Bridge] Processing task:", taskId.substring(0, 8), "| Prompt length:", prompt.length);
    showToast("📝 Injecting prompt into ChatGPT...", "#6366f1");

    try {
        const input = findInput();
        if (!input) {
            showToast("❌ Input not found! Open chatgpt.com first.", "#dc2626");
            console.error("[ChatGPT Bridge] No input element found.");
            return;
        }

        const prevMsgCount = countAssistantMsgs();
        console.log("[ChatGPT Bridge] Previous message count:", prevMsgCount);

        await injectText(input, prompt);

        // Verify injection worked
        const injectedContent = input.tagName === 'TEXTAREA' ? input.value : input.innerText;
        console.log("[ChatGPT Bridge] After injection, content length:", injectedContent.length);
        
        if (injectedContent.length < 10) {
            showToast("❌ Injection failed — text didn't appear in input box.", "#dc2626");
            console.error("[ChatGPT Bridge] Injection failed.");
            return;
        }

        showToast("📤 Sending to ChatGPT...", "#6366f1");

        const sendBtn = findSendBtn();
        if (!sendBtn) {
            showToast("❌ Send button not found!", "#dc2626");
            console.error("[ChatGPT Bridge] Send button not found.");
            return;
        }

        // Wait for the send button to be enabled
        for (let i = 0; i < 30; i++) {
            if (!sendBtn.disabled && sendBtn.getAttribute('aria-disabled') !== 'true') break;
            await sleep(200);
        }

        sendBtn.click();
        console.log("[ChatGPT Bridge] Send clicked.");
        showToast("💬 ChatGPT is thinking...", "#6366f1");

        await waitForGenerationToFinish(prevMsgCount);

        const answer = getLastAssistantText();
        console.log("[ChatGPT Bridge] Got answer:", answer.length, "chars");

        if (answer.length < 10) {
            showToast("❌ Response too short — extraction failed.", "#dc2626");
            return;
        }

        showToast("📡 Sending result back to Agent Fraud...", "#6366f1");

        await fetch(`${PROXY_URL}/submit`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ task_id: taskId, response: answer })
        });

        tasksProcessed++;
        showToast(`✅ Done! Task #${tasksProcessed} complete.`, "#16a34a");
        console.log("[ChatGPT Bridge] Task complete! Total:", tasksProcessed);

    } catch (err) {
        showToast("❌ Error: " + err.message, "#dc2626");
        console.error("[ChatGPT Bridge] Error:", err);
    } finally {
        isProcessing = false;
    }
}

// ──────────────────────────────────────────────────────────────────────────────
// Long polling loop
// ──────────────────────────────────────────────────────────────────────────────
async function startLongPolling() {
    console.log("[ChatGPT Bridge] Starting long polling loop...");
    while (true) {
        if (isProcessing) {
            await sleep(1000);
            continue;
        }
        try {
            const res = await fetch(`${PROXY_URL}/poll`);
            if (res.ok) {
                const data = await res.json();
                if (data.task_id && data.prompt) {
                    console.log("[ChatGPT Bridge] Task received:", data.task_id.substring(0, 8));
                    isProcessing = true;
                    await processPrompt(data.task_id, data.prompt);
                }
            } else {
                await sleep(2000);
            }
        } catch (_) {
            await sleep(3000);
        }
    }
}

startLongPolling();
