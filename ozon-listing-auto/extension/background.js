// extension/background.js
chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type !== "capture") return;
  chrome.storage.sync.get(["backendUrl", "token", "keyword"], async (c) => {
    if (!c.backendUrl || !c.token) return;
    try {
      await fetch(c.backendUrl.replace(/\/$/, "") + "/import/offers" + (c.keyword ? `?keyword=${encodeURIComponent(c.keyword)}` : ""),
        { method: "POST", headers: { "Content-Type": "application/json", "X-Import-Token": c.token }, body: JSON.stringify(msg.payload) });
    } catch (e) {}
  });
});
