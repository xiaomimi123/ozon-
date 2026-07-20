// extension/options.js
const F = ["backendUrl", "token", "matchSubstr", "keyword"];
chrome.storage.sync.get(F, (c) => F.forEach((k) => (document.getElementById(k).value = c[k] || "")));
document.getElementById("save").onclick = () => {
  const o = {}; F.forEach((k) => (o[k] = document.getElementById(k).value));
  chrome.storage.sync.set(o, () => (document.getElementById("msg").textContent = "已保存"));
};
