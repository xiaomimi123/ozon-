// extension/content.js —— 隔离世界: 注入主世界脚本, 转发 payload 给 background
(async () => {
  const { matchSubstr } = await chrome.storage.sync.get(["matchSubstr"]);
  const s = document.createElement("script");
  s.src = chrome.runtime.getURL("interceptor.js");
  s.dataset.match = matchSubstr || "search,offer";
  (document.head || document.documentElement).appendChild(s);
  window.addEventListener("message", (e) => {
    if (e.source === window && e.data && e.data.__ozonCollector) {
      chrome.runtime.sendMessage({ type: "capture", payload: e.data.payload });
    }
  });
})();
