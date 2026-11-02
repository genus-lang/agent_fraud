// popup.js

const PROXY_URL = "http://127.0.0.1:5000";
let chatGptTabId = null;
let taskCount = 0;

// ──────────────────────────────────────────────────────────────────────────────
// DOM helpers
// ──────────────────────────────────────────────────────────────────────────────
const dotTab   = document.getElementById("dot-tab");
const valTab   = document.getElementById("val-tab");
const cardTab  = document.getElementById("card-tab");

const dotProxy  = document.getElementById("dot-proxy");
const valProxy  = document.getElementById("val-proxy");
const cardProxy = document.getElementById("card-proxy");

const btnOpen   = document.getElementById("btn-open");
const btnFocus  = document.getElementById("btn-focus");
const logBox    = document.getElementById("log-box");
const taskCountEl = document.getElementById("task-count");

function setDot(dotEl, valEl, cardEl, state, text) {
    dotEl.className = "dot " + (state === "ok" ? "green" : state === "err" ? "red" : "amber");
    valEl.className = "status-value " + (state === "ok" ? "connected" : state === "err" ? "disconnected" : "checking");
    valEl.textContent = text;
    cardEl.className = "status-card " + (state === "ok" ? "connected" : state === "err" ? "disconnected" : "");
}

function log(msg, type = "info") {
    const line = document.createElement("div");
    line.className = "log-line " + type;
    const now = new Date();
    const ts = `${now.getHours().toString().padStart(2,'0')}:${now.getMinutes().toString().padStart(2,'0')}:${now.getSeconds().toString().padStart(2,'0')}`;
    line.textContent = `[${ts}] ${msg}`;
    logBox.appendChild(line);
    logBox.scrollTop = logBox.scrollHeight;
}

// ──────────────────────────────────────────────────────────────────────────────
// Check ChatGPT tab
// ──────────────────────────────────────────────────────────────────────────────
async function checkChatGptTab() {
    return new Promise((resolve) => {
        chrome.tabs.query({ url: "*://chatgpt.com/*" }, (tabs) => {
            if (tabs && tabs.length > 0) {
                chatGptTabId = tabs[0].id;
                setDot(dotTab, valTab, cardTab, "ok", "Connected ✓");
                btnOpen.style.display = "none";
                btnFocus.style.display = "block";
                log("ChatGPT tab found (tab #" + chatGptTabId + ")", "ok");
                resolve(true);
            } else {
                chatGptTabId = null;
                setDot(dotTab, valTab, cardTab, "err", "No tab open");
                btnOpen.style.display = "block";
                btnFocus.style.display = "none";
                log("No ChatGPT tab detected.", "warn");
                resolve(false);
            }
        });
    });
}

// ──────────────────────────────────────────────────────────────────────────────
// Check Proxy Server
// ──────────────────────────────────────────────────────────────────────────────
async function checkProxyServer() {
    try {
        const res = await fetch(`${PROXY_URL}/health`, { signal: AbortSignal.timeout(2000) });
        if (res.ok) {
            const data = await res.json();
            // Check tasks processed counter from server (if available)
            if (data.tasks_processed !== undefined) {
                taskCount = data.tasks_processed;
                taskCountEl.textContent = taskCount;
            }
            setDot(dotProxy, valProxy, cardProxy, "ok", "Online on :5000 ✓");
            log("Proxy server is online.", "ok");
            return true;
        }
    } catch (e) {
        // fall through
    }
    setDot(dotProxy, valProxy, cardProxy, "err", "Offline — start chatgpt_proxy.py");
    log("Proxy server not reachable on port 5000.", "warn");
    return false;
}

// ──────────────────────────────────────────────────────────────────────────────
// Button handlers
// ──────────────────────────────────────────────────────────────────────────────
btnOpen.addEventListener("click", () => {
    chrome.tabs.create({ url: "https://chatgpt.com", active: true }, (tab) => {
        chatGptTabId = tab.id;
        log("Opening ChatGPT tab…", "info");
        // Re-check after a brief delay to update the status
        setTimeout(checkAll, 2500);
    });
});

btnFocus.addEventListener("click", () => {
    if (chatGptTabId !== null) {
        chrome.tabs.update(chatGptTabId, { active: true });
        chrome.tabs.get(chatGptTabId, (tab) => {
            chrome.windows.update(tab.windowId, { focused: true });
        });
        log("Focused ChatGPT tab.", "info");
    }
});

const btnReset = document.getElementById("btn-reset");
btnReset.addEventListener("click", async () => {
    // 1. Reset proxy queue
    try {
        await fetch(`${PROXY_URL}/reset`, { method: "POST" });
        log("Proxy queue cleared.", "ok");
    } catch (e) {
        log("Could not reach proxy to reset.", "warn");
    }
    // 2. Reset isProcessing flag in content script
    if (chatGptTabId !== null) {
        chrome.tabs.sendMessage(chatGptTabId, { type: "RESET" }, () => {
            log("Content script state reset.", "ok");
        });
    }
    log("✅ Reset complete — ready for a new investigation.", "ok");
});

// ──────────────────────────────────────────────────────────────────────────────
// Task count — communicate with content script via runtime messaging
// ──────────────────────────────────────────────────────────────────────────────
function getTaskCount() {
    if (chatGptTabId !== null) {
        chrome.tabs.sendMessage(chatGptTabId, { type: "GET_TASK_COUNT" }, (response) => {
            if (chrome.runtime.lastError) return; // tab not ready yet
            if (response && response.count !== undefined) {
                taskCountEl.textContent = response.count;
            }
        });
    }
}

// ──────────────────────────────────────────────────────────────────────────────
// Run all checks
// ──────────────────────────────────────────────────────────────────────────────
async function checkAll() {
    await checkChatGptTab();
    await checkProxyServer();
    getTaskCount();
}

// Run on popup open
checkAll();

// Refresh every 5 seconds while popup is open
setInterval(checkAll, 5000);
