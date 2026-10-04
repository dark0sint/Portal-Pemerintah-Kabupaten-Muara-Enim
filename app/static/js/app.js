(function () {
  "use strict";
  var root = document.documentElement, body = document.body;
  var store = {
    get: function (k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set: function (k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
  };

  /* ---------- Aksesibilitas ---------- */
  var sizes = ["fsm", "", "fs1", "fs2", "fs3"];
  var si = parseInt(store.get("fs") || "1", 10);
  function applySize() {
    sizes.forEach(function (c) { if (c) root.classList.remove(c); });
    if (sizes[si]) root.classList.add(sizes[si]);
    store.set("fs", si);
  }
  applySize();
  function toggle(cls, key, btn) {
    var on = body.classList.toggle(cls);
    store.set(key, on ? "1" : "0");
    if (btn) btn.setAttribute("aria-pressed", on);
  }
  [["dys", "dys", "a-dys"], ["hc", "hc", "a-hc"], ["rtl-align", "al", "a-align"]].forEach(function (x) {
    var b = document.getElementById(x[2]);
    if (store.get(x[1]) === "1") { body.classList.add(x[0]); if (b) b.setAttribute("aria-pressed", "true"); }
    if (b) b.addEventListener("click", function () { toggle(x[0], x[1], b); });
  });
  function on(id, fn) { var e = document.getElementById(id); if (e) e.addEventListener("click", fn); }
  on("a-plus", function () { si = Math.min(si + 1, sizes.length - 1); applySize(); });
  on("a-min", function () { si = Math.max(si - 1, 0); applySize(); });
  on("a-reset", function () {
    si = 1; applySize();
    ["dys", "hc", "rtl-align"].forEach(function (c) { body.classList.remove(c); });
    ["dys", "hc", "al"].forEach(function (k) { store.set(k, "0"); });
    ["a-dys", "a-hc", "a-align"].forEach(function (i) { var b = document.getElementById(i); if (b) b.setAttribute("aria-pressed", "false"); });
  });

  /* Pembaca suara (Web Speech API, bahasa Indonesia) */
  var tts = window.speechSynthesis;
  var bRead = document.getElementById("a-read");
  if (!tts && bRead) { bRead.disabled = true; bRead.title = "Peramban Anda tidak mendukung pembaca suara"; }
  on("a-read", function () {
    if (!tts) return;
    tts.cancel();
    var sel = String(window.getSelection() || "").trim();
    var text = sel || (document.querySelector("main") || body).innerText;
    var parts = text.replace(/\s+/g, " ").match(/[^.!?]{1,220}[.!?]?/g) || [];
    parts.forEach(function (p) {
      var u = new SpeechSynthesisUtterance(p);
      u.lang = "id-ID"; u.rate = 0.95;
      tts.speak(u);
    });
  });
  on("a-stop", function () { if (tts) tts.cancel(); });

  /* ---------- Menu mobile ---------- */
  var mb = document.getElementById("menu-btn"), nav = document.getElementById("nav");
  if (mb && nav) mb.addEventListener("click", function () {
    var o = nav.classList.toggle("open");
    mb.setAttribute("aria-expanded", o);
  });

  /* ---------- Chatbot ---------- */
  var cb = document.getElementById("chat-btn"), cp = document.getElementById("chat");
  if (cb && cp) {
    var log = document.getElementById("chat-log"), form = document.getElementById("chat-form"), inp = document.getElementById("chat-in");
    var csrf = document.querySelector('meta[name="csrf"]').content;
    function add(t, who, link) {
      var d = document.createElement("div");
      d.className = "msg " + who; d.textContent = t;
      if (link) { var a = document.createElement("a"); a.href = link; a.textContent = " Buka halaman"; d.appendChild(a); }
      log.appendChild(d); log.scrollTop = log.scrollHeight;
    }
    cb.addEventListener("click", function () {
      var o = cp.classList.toggle("open");
      cb.setAttribute("aria-expanded", o);
      if (o) { if (!log.children.length) add("Halo! Saya asisten portal. Tanyakan tentang layanan, pengaduan, JDIH, atau data.", "bot"); inp.focus(); }
    });
    document.getElementById("chat-x").addEventListener("click", function () { cp.classList.remove("open"); cb.setAttribute("aria-expanded", "false"); cb.focus(); });
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var t = inp.value.trim(); if (!t) return;
      add(t, "me"); inp.value = "";
      fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf }, body: JSON.stringify({ q: t }) })
        .then(function (r) { return r.json(); })
        .then(function (j) { add(j.a || j.error || "Terjadi kesalahan.", "bot", j.link); })
        .catch(function () { add("Koneksi bermasalah. Coba lagi.", "bot"); });
    });
  }

  /* ---------- Grafik batang SVG (Satu Data) ---------- */
  var ch = document.getElementById("chart");
  if (ch && ch.dataset.rows) {
    var data = JSON.parse(ch.dataset.rows), unit = ch.dataset.unit || "";
    var NS = "http://www.w3.org/2000/svg", W = 760, H = 340, m = { l: 56, r: 14, t: 16, b: 70 };
    var max = Math.max.apply(null, data.map(function (d) { return d[1]; }).concat([1]));
    var bw = (W - m.l - m.r) / Math.max(data.length, 1);
    function el(n, a, t) { var e = document.createElementNS(NS, n); for (var k in a) e.setAttribute(k, a[k]); if (t != null) e.textContent = t; return e; }
    ch.setAttribute("viewBox", "0 0 " + W + " " + H);
    for (var g = 0; g <= 4; g++) {
      var y = m.t + (H - m.t - m.b) * (1 - g / 4);
      ch.appendChild(el("line", { x1: m.l, x2: W - m.r, y1: y, y2: y, stroke: "#9aa9a4", "stroke-width": 0.6 }));
      ch.appendChild(el("text", { x: m.l - 6, y: y + 4, "text-anchor": "end", "font-size": 11 }, Math.round(max * g / 4).toLocaleString("id-ID")));
    }
    data.forEach(function (d, i) {
      var h = (H - m.t - m.b) * d[1] / max, x = m.l + i * bw + bw * 0.15;
      ch.appendChild(el("rect", { "class": "bar", x: x, y: H - m.b - h, width: bw * 0.7, height: h }));
      ch.appendChild(el("text", { x: x + bw * 0.35, y: H - m.b - h - 5, "text-anchor": "middle", "font-size": 11, "font-weight": 600 }, d[1].toLocaleString("id-ID")));
      var lab = String(d[0]); if (lab.length > 14) lab = lab.slice(0, 13) + "…";
      var t = el("text", { x: x + bw * 0.35, y: H - m.b + 16, "text-anchor": data.length > 6 ? "end" : "middle", "font-size": 11 }, lab);
      if (data.length > 6) t.setAttribute("transform", "rotate(-35 " + (x + bw * 0.35) + " " + (H - m.b + 16) + ")");
      ch.appendChild(t);
    });
    ch.appendChild(el("text", { x: 4, y: 12, "font-size": 11 }, unit));
  }

  /* ---------- Konfirmasi hapus ---------- */
  document.querySelectorAll("form[data-confirm]").forEach(function (f) {
    f.addEventListener("submit", function (e) { if (!confirm(f.dataset.confirm)) e.preventDefault(); });
  });
})();
