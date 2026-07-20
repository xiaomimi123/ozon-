// extension/interceptor.js —— 主世界: hook fetch/XHR, 命中搜索接口→postMessage 出去
(function () {
  const MATCH = (document.currentScript && document.currentScript.dataset.match || "search").split(",");
  const hit = (url) => MATCH.some((m) => url.includes(m));
  const post = (data) => { try { window.postMessage({ __ozonCollector: true, payload: data }, "*"); } catch (e) {} };
  const of = window.fetch;
  window.fetch = async function (...args) {
    const res = await of.apply(this, args);
    try { const u = (args[0] && args[0].url) || String(args[0]); if (hit(u)) res.clone().json().then(post).catch(() => {}); } catch (e) {}
    return res;
  };
  const oo = XMLHttpRequest.prototype.open, os = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (m, u) { this.__ozUrl = u; return oo.apply(this, arguments); };
  XMLHttpRequest.prototype.send = function () {
    this.addEventListener("load", function () {
      try { if (this.__ozUrl && hit(this.__ozUrl)) post(JSON.parse(this.responseText)); } catch (e) {}
    });
    return os.apply(this, arguments);
  };
})();
