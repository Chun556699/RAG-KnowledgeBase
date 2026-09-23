/**
 * RAG-KB 嵌入聊天挂件 —— 自包含 Vanilla JS + Shadow DOM，零外部依赖。
 *
 * 集成方式（任意网页一行即可）：
 *   <script src="https://<host>/embed/widget.js"
 *           data-key="ak_live_xxx"
 *           data-title="智能助手"
 *           data-color="#4f46e5"
 *           async></script>
 *
 * 可配置 data-* 属性：
 *   data-api       后端地址（默认取脚本所在源）
 *   data-key       API 密钥（必填，X-API-Key 头发送）
 *   data-kb        知识库 ID（默认 "default"，密钥绑定时自动以密钥为准）
 *   data-title     面板标题（默认 "智能问答助手"）
 *   data-color     主题色（默认 #4f46e5）
 *   data-position  右下角 right / 左下角 left（默认 right）
 *   data-stream    是否流式（默认 true）
 */
(function () {
  "use strict";

  var scriptEl = document.currentScript ||
    document.querySelector('script[data-key][src*="widget.js"]');
  var cfg = {};
  if (scriptEl) {
    for (var i = 0; i < scriptEl.attributes.length; i++) {
      var a = scriptEl.attributes[i];
      if (a.name.indexOf("data-") === 0) cfg[a.name.slice(5)] = a.value;
    }
  }

  var API = (cfg.api || (scriptEl ? new URL(scriptEl.src).origin : "")).replace(/\/$/, "");
  var KEY = cfg.key || "";
  var KB = cfg.kb || "default";
  var TITLE = cfg.title || "智能问答助手";
  var COLOR = cfg.color || "#4f46e5";
  var POS = cfg.position === "left" ? "left" : "right";
  var STREAM = cfg.stream !== "false";
  var SESSION_KEY = "ragkb_session_" + KB;

  if (!KEY) {
    console.error("[RAG-KB widget] 缺少 data-key（API 密钥），挂件未启动。");
    return;
  }

  var CSS = `
  :host { all: initial; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  .rkb-bubble {
    position: fixed; bottom: 24px; ${POS}: 24px; width: 56px; height: 56px;
    border-radius: 50%; background: ${COLOR}; border: none; cursor: pointer;
    display: flex; align-items: center; justify-content: center; z-index: 2147483000;
    box-shadow: 0 6px 24px rgba(0,0,0,.22); transition: transform .18s, box-shadow .18s;
  }
  .rkb-bubble:hover { transform: scale(1.07); box-shadow: 0 8px 30px rgba(0,0,0,.3); }
  .rkb-bubble svg { width: 26px; height: 26px; fill: #fff; }
  .rkb-panel {
    position: fixed; bottom: 92px; ${POS}: 24px; width: 380px; height: 560px;
    max-width: calc(100vw - 32px); max-height: calc(100vh - 120px);
    background: #fff; border-radius: 16px; overflow: hidden;
    display: flex; flex-direction: column; z-index: 2147483000;
    box-shadow: 0 12px 48px rgba(0,0,0,.22); border: 1px solid rgba(0,0,0,.06);
    opacity: 0; transform: translateY(16px) scale(.97); pointer-events: none;
    transition: opacity .2s, transform .2s;
  }
  .rkb-panel.open { opacity: 1; transform: none; pointer-events: auto; }
  .rkb-head {
    background: ${COLOR}; color: #fff; padding: 14px 16px;
    display: flex; align-items: center; justify-content: space-between; flex: none;
  }
  .rkb-head .t { font-size: 15px; font-weight: 600; }
  .rkb-head .sub { font-size: 11px; opacity: .85; margin-top: 2px; }
  .rkb-close { background: none; border: none; color: #fff; font-size: 20px; cursor: pointer; line-height: 1; padding: 4px; }
  .rkb-body { flex: 1; overflow-y: auto; padding: 14px; background: #f8fafc; }
  .rkb-msg { margin-bottom: 10px; display: flex; }
  .rkb-msg.user { justify-content: flex-end; }
  .rkb-b {
    max-width: 82%; padding: 9px 13px; border-radius: 14px; font-size: 13.5px;
    line-height: 1.55; white-space: pre-wrap; word-break: break-word;
  }
  .rkb-msg.user .rkb-b { background: ${COLOR}; color: #fff; border-bottom-right-radius: 4px; }
  .rkb-msg.bot .rkb-b { background: #fff; color: #1e293b; border: 1px solid #e2e8f0; border-bottom-left-radius: 4px; }
  .rkb-src { margin-top: 6px; font-size: 11px; color: #64748b; border-top: 1px dashed #e2e8f0; padding-top: 6px; }
  .rkb-src span { display: inline-block; background: #eef2ff; color: #4338ca; border-radius: 8px; padding: 1px 8px; margin: 2px 3px 0 0; }
  .rkb-typing { display: inline-flex; gap: 4px; padding: 4px 2px; }
  .rkb-typing i { width: 6px; height: 6px; border-radius: 50%; background: #94a3b8; animation: rkb-b 1.1s infinite; }
  .rkb-typing i:nth-child(2) { animation-delay: .15s; }
  .rkb-typing i:nth-child(3) { animation-delay: .3s; }
  @keyframes rkb-b { 0%,60%,100%{ transform: none; opacity:.5 } 30%{ transform: translateY(-4px); opacity:1 } }
  .rkb-foot { flex: none; padding: 10px; background: #fff; border-top: 1px solid #e2e8f0; display: flex; gap: 8px; }
  .rkb-input {
    flex: 1; border: 1px solid #e2e8f0; border-radius: 10px; padding: 9px 12px;
    font-size: 13.5px; outline: none; font-family: inherit; resize: none; height: 40px; max-height: 90px;
  }
  .rkb-input:focus { border-color: ${COLOR}; }
  .rkb-send {
    border: none; background: ${COLOR}; color: #fff; border-radius: 10px;
    padding: 0 16px; font-size: 13.5px; cursor: pointer; flex: none;
  }
  .rkb-send:disabled { opacity: .5; cursor: default; }
  .rkb-empty { text-align: center; color: #94a3b8; font-size: 12.5px; padding: 28px 18px; }
  @media (max-width: 480px) {
    .rkb-panel { bottom: 0; ${POS}: 0; width: 100vw; height: 78vh; max-height: none; border-radius: 16px 16px 0 0; }
  }
  `;

  var host = document.createElement("div");
  host.id = "ragkb-widget-host";
  var root = host.attachShadow({ mode: "open" });
  var style = document.createElement("style");
  style.textContent = CSS;
  root.appendChild(style);

  root.innerHTML += `
    <button class="rkb-bubble" aria-label="打开智能助手">
      <svg viewBox="0 0 24 24"><path d="M12 3C6.48 3 2 6.94 2 11.78c0 2.66 1.37 5.04 3.57 6.7L5 22l4.02-2.05c.95.2 1.94.3 2.98.3 5.52 0 10-3.94 10-8.47S17.52 3 12 3zm-4 9.5a1.5 1.5 0 110-3 1.5 1.5 0 010 3zm4 0a1.5 1.5 0 110-3 1.5 1.5 0 010 3zm4 0a1.5 1.5 0 110-3 1.5 1.5 0 010 3z"/></svg>
    </button>
    <div class="rkb-panel" role="dialog" aria-label="${TITLE}">
      <div class="rkb-head">
        <div><div class="t">${TITLE}</div><div class="sub">Powered by RAG-KnowledgeBase</div></div>
        <button class="rkb-close" aria-label="关闭">×</button>
      </div>
      <div class="rkb-body"><div class="rkb-empty">您好，我是${TITLE}，有什么可以帮您？</div></div>
      <div class="rkb-foot">
        <textarea class="rkb-input" rows="1" placeholder="输入问题，Enter 发送…"></textarea>
        <button class="rkb-send">发送</button>
      </div>
    </div>`;

  document.body.appendChild(host);

  var panel = root.querySelector(".rkb-panel");
  var body = root.querySelector(".rkb-body");
  var input = root.querySelector(".rkb-input");
  var sendBtn = root.querySelector(".rkb-send");
  var busy = false;

  root.querySelector(".rkb-bubble").addEventListener("click", function () {
    panel.classList.toggle("open");
    if (panel.classList.contains("open")) input.focus();
  });
  root.querySelector(".rkb-close").addEventListener("click", function () {
    panel.classList.remove("open");
  });

  function scrollBottom() { body.scrollTop = body.scrollHeight; }

  function clearEmpty() {
    var e = body.querySelector(".rkb-empty");
    if (e) e.remove();
  }

  function addMsg(role, text) {
    clearEmpty();
    var m = document.createElement("div");
    m.className = "rkb-msg " + role;
    var b = document.createElement("div");
    b.className = "rkb-b";
    b.textContent = text || "";
    m.appendChild(b);
    body.appendChild(m);
    scrollBottom();
    return b;
  }

  function addTyping() {
    var m = document.createElement("div");
    m.className = "rkb-msg bot";
    m.innerHTML = '<div class="rkb-b"><span class="rkb-typing"><i></i><i></i><i></i></span></div>';
    body.appendChild(m);
    scrollBottom();
    return m;
  }

  function addSources(b, sources) {
    if (!sources || !sources.length) return;
    var box = document.createElement("div");
    box.className = "rkb-src";
    box.appendChild(document.createTextNode("来源："));
    var seen = {};
    sources.forEach(function (s) {
      var name = s.filename || "文档";
      if (seen[name]) return;
      seen[name] = 1;
      var tag = document.createElement("span");
      tag.textContent = name;
      box.appendChild(tag);
    });
    b.appendChild(box);
    scrollBottom();
  }

  function sessionId() {
    try { return sessionStorage.getItem(SESSION_KEY) || ""; } catch (e) { return ""; }
  }
  function saveSession(id) {
    try { if (id) sessionStorage.setItem(SESSION_KEY, id); } catch (e) {}
  }

  function ask(q) {
    if (busy || !q) return;
    busy = true;
    sendBtn.disabled = true;
    addMsg("user", q);
    input.value = "";
    var typing = addTyping();
    var botB = null;
    var sources = [];

    function finish() {
      busy = false;
      sendBtn.disabled = false;
      input.focus();
    }
    function fail(msg) {
      if (!botB) { typing.remove(); botB = addMsg("bot", ""); }
      botB.textContent = msg;
      finish();
    }

    var payload = { question: q, kb: KB, top_k: 4 };
    var sid = sessionId();
    if (sid) payload.session_id = sid;

    var headers = { "Content-Type": "application/json", "X-API-Key": KEY };

    if (!STREAM) {
      fetch(API + "/api/v1/ask", { method: "POST", headers: headers, body: JSON.stringify(payload) })
        .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
        .then(function (res) {
          typing.remove();
          if (!res.ok) { fail(res.j.message || "服务暂不可用"); return; }
          saveSession(res.j.session_id);
          botB = addMsg("bot", res.j.answer || "");
          addSources(botB, res.j.sources);
          finish();
        })
        .catch(function () { fail("网络异常，请稍后再试"); });
      return;
    }

    fetch(API + "/api/v1/ask/stream", { method: "POST", headers: headers, body: JSON.stringify(payload) })
      .then(function (r) {
        if (!r.ok || !r.body) {
          return r.json().catch(function () { return {}; }).then(function (j) {
            typing.remove();
            fail(j.message || "服务暂不可用 (" + r.status + ")");
          });
        }
        var reader = r.body.getReader();
        var decoder = new TextDecoder();
        var buf = "";
        function pump() {
          return reader.read().then(function (res) {
            if (res.done) { finish(); return; }
            buf += decoder.decode(res.value, { stream: true });
            var idx;
            while ((idx = buf.indexOf("\n\n")) >= 0) {
              var line = buf.slice(0, idx).trim();
              buf = buf.slice(idx + 2);
              if (line.indexOf("data:") !== 0) continue;
              var ev;
              try { ev = JSON.parse(line.slice(5).trim()); } catch (e) { continue; }
              if (ev.type === "meta") {
                saveSession(ev.session_id);
                sources = ev.sources || [];
                typing.remove();
                botB = addMsg("bot", "");
              } else if (ev.type === "delta") {
                if (!botB) { typing.remove(); botB = addMsg("bot", ""); }
                botB.textContent += ev.content || "";
                scrollBottom();
              } else if (ev.type === "done") {
                if (botB) addSources(botB, sources);
              }
            }
            return pump();
          });
        }
        return pump();
      })
      .catch(function () { fail("网络异常，请稍后再试"); });
  }

  sendBtn.addEventListener("click", function () { ask(input.value.trim()); });
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      ask(input.value.trim());
    }
  });
})();
