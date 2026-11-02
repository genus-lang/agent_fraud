// background.js

let polling = true;

// Keep service worker alive and log status
console.log("ChatGPT Proxy Extension started.");

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === 'HEARTBEAT') {
        sendResponse({status: 'alive'});
    }
});
