/* BridgeNote 웹 배포판 — 화면 동작.
   - 판단(검사 · 안내 문장 · 정렬 · 찾기 · 점검)은 모두 서버(/api, logic.py)가 해요.
   - 기록(상대 카드 · 보관함)은 이 브라우저의 localStorage 에만 덧붙여 저장해요. 수정 · 삭제 기능은 없어요.
   - 사용자가 쓴 글은 textContent 로만 화면에 넣어요 (HTML 로 해석하지 않게). */
"use strict";

const STORE_KEY = "bridgenote.web.v1";
const $ = (id) => document.getElementById(id);
let CFG = null;              // 서버가 준 선택지 · 문장
let DB = { contacts: [], phrases: [] };
let lastTranslation = null;  // { source, language, contact_id }

// ---------------------------------------------------------------- 저장 (이 브라우저에만)
function loadStore() {
  try { const v = JSON.parse(localStorage.getItem(STORE_KEY)); return v && Array.isArray(v.contacts) ? v : null; }
  catch { return null; }
}
function saveStore() {
  try { localStorage.setItem(STORE_KEY, JSON.stringify(DB)); return true; } catch { return false; }
}

// ---------------------------------------------------------------- 도우미
async function api(path, body) {
  try {
    const res = await fetch(path, body === undefined ? {} : {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    return await res.json();
  } catch {
    return { error: "서버와 연결이 끊겼어요. 인터넷을 확인하고 다시 해 보세요" };
  }
}
function el(tag, props = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "text") n.textContent = v; else if (k === "class") n.className = v; else n.setAttribute(k, v);
  }
  for (const k of kids) if (k) n.append(k);
  return n;
}
function show(boxId, kind, text) {
  const box = $(boxId); box.replaceChildren();
  if (text) box.append(el("div", { class: `msg ${kind}`, role: kind === "error" ? "alert" : "status", text }));
}
const labelOf = (opts, code) => (opts.find(([c]) => c === code) || [null, "—"])[1];
const contactById = (id) => DB.contacts.find((c) => c.id === id) || null;

function radios(boxId, name, opts, preselect) {
  const box = $(boxId); box.replaceChildren();
  opts.forEach(([code, text], i) => {
    const input = el("input", { type: "radio", name, value: code });
    if (preselect && i === 0) input.checked = true;
    box.append(el("label", {}, input, document.createTextNode(text)));
  });
}
const picked = (name) => (document.querySelector(`input[name="${name}"]:checked`) || {}).value || null;
function clearRadios(name) { document.querySelectorAll(`input[name="${name}"]`).forEach((r) => (r.checked = false)); }

/** 상대 고르기 + (상대가 없을 때만) 언어 고르기 */
function whoPicker(boxId, prefix) {
  const box = $(boxId); box.replaceChildren();
  const sel = el("select", { id: `${prefix}-contact` });
  sel.append(el("option", { value: "", text: "상대 없이 쓰기" }));
  [...DB.contacts].reverse().forEach((c) => sel.append(el("option", {
    value: c.id,
    text: [c.name, labelOf(CFG.options.relations, c.relation), labelOf(CFG.options.languages, c.language),
      labelOf(CFG.options.formalities, c.formality)].join(" · "),
  })));
  const langBox = el("div", { class: "field" }, el("span", { class: "lab", text: "언어" }),
    el("div", { id: `${prefix}-language`, class: "radios" }));
  box.append(el("label", {}, document.createTextNode("상대"), sel), langBox);
  radios(`${prefix}-language`, `${prefix}-language`, CFG.options.languages, false);
  const sync = () => { langBox.hidden = !!sel.value; };
  sel.addEventListener("change", sync); sync();
}
function who(prefix) {
  const contact = contactById($(`${prefix}-contact`).value);
  return { contact, language: contact ? null : picked(`${prefix}-language`) };
}
function refreshWhoPickers() { ["t", "r", "p", "e"].forEach((p) => whoPicker(`${p}-who`, p)); }

async function busy(btn, work) {
  btn.disabled = true;
  try { await work(); } finally { btn.disabled = false; }
}

// ---------------------------------------------------------------- F1 상대방 카드
function renderContacts() {
  show("c-empty", "info", DB.contacts.length ? "" : CFG.messages.noContacts);
  const box = $("c-list"); box.replaceChildren();
  if (!DB.contacts.length) return;
  const tbody = el("tbody");
  [...DB.contacts].reverse().forEach((c) => tbody.append(el("tr", {},
    el("td", { text: c.name || "—" }), el("td", { text: labelOf(CFG.options.relations, c.relation) }),
    el("td", { text: labelOf(CFG.options.languages, c.language) }), el("td", { text: labelOf(CFG.options.formalities, c.formality) }))));
  box.append(el("div", { class: "table-wrap" }, el("table", {},
    el("thead", {}, el("tr", {}, ...["이름", "관계", "언어", "격식"].map((h) => el("th", { text: h })))), tbody)));
}
async function saveContact() {
  const r = await api("/api/contact", {
    name: $("c-name").value, relation: picked("c-relation"), language: picked("c-language"),
    formality: picked("c-formality"), contacts: DB.contacts,
  });
  if (r.error) return show("c-msg", "error", r.error);   // 실패하면 쓴 내용은 그대로
  DB.contacts.push(r.contact);
  if (!saveStore()) return show("c-msg", "error", "이 브라우저에 저장하지 못했어요. 시크릿 창이면 일반 창으로 열어 주세요");
  $("c-name").value = ""; ["c-relation", "c-language", "c-formality"].forEach(clearRadios);
  show("c-msg", "ok", "저장했어요!");
  renderContacts(); refreshWhoPickers(); renderSearchContacts(); runSearch();
}

// ---------------------------------------------------------------- F2 AI 번역 · 다듬기
function showLeft(left) {
  if (typeof left === "number") $("t-left").textContent = `오늘 남은 AI 번역: ${left}번 (하루 ${CFG.aiLimit}번)`;
}
async function translate() {
  const { contact, language } = who("t");
  show("t-saved", "", "");
  const r = await api("/api/translate", { source: $("t-source").value, contact, language });
  showLeft(r.aiLeft);
  if (r.error) return show("t-msg", "error", r.error);
  show("t-msg", "", "");
  lastTranslation = { source: r.source, language: r.language, contact_id: r.contact_id };
  $("t-result").value = r.result; $("t-out").hidden = false;
  show("t-verbose", "warn", r.verbose ? CFG.messages.tooVerbose : "");
}
let verboseTimer = null;
function recheckVerbose() {
  clearTimeout(verboseTimer);
  verboseTimer = setTimeout(async () => {
    if (!lastTranslation) return;
    const r = await api("/api/verbose", { source: lastTranslation.source, result: $("t-result").value });
    show("t-verbose", "warn", r.verbose ? CFG.messages.tooVerbose : "");
  }, 400);
}
async function saveTranslation() {
  if (!lastTranslation) return;
  const r = await api("/api/phrase", {
    text: $("t-result").value, contact: contactById(lastTranslation.contact_id),
    language: lastTranslation.language, situation: picked("t-situation"),
    source_ko: lastTranslation.source, phrases: DB.phrases,
  });
  if (r.error) return show("t-saved", "error", r.error);
  DB.phrases.push(r.phrase); saveStore();
  show("t-saved", "ok", "보관함에 저장했어요!"); runSearch();
}

// ---------------------------------------------------------------- F3 검수 요청문
async function makeRequest() {
  const { contact, language } = who("r");
  const r = await api("/api/request", { source: $("r-source").value, situation: picked("r-situation"), contact, language });
  if (r.error) { $("r-out").hidden = true; return show("r-msg", "error", r.error); }
  show("r-msg", "", ""); $("r-text").textContent = r.text; $("r-out").hidden = false; $("r-copied").textContent = "";
}
async function copyRequest() {
  try { await navigator.clipboard.writeText($("r-text").textContent); $("r-copied").textContent = "복사했어요!"; }
  catch { $("r-copied").textContent = "복사하지 못했어요. 글을 직접 드래그해서 복사해 주세요"; }
}

// ---------------------------------------------------------------- F4 보관함
function renderSearchContacts() {
  const sel = $("q-contact"); const keep = sel.value; sel.replaceChildren(el("option", { value: "", text: "전체" }));
  [...DB.contacts].reverse().forEach((c) => sel.append(el("option", { value: c.id, text: c.name })));
  sel.value = keep;
}
let searchTimer = null;
function runSearch() {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(async () => {
    const r = await api("/api/search", { phrases: DB.phrases, contacts: DB.contacts, word: $("q-word").value, contact_id: $("q-contact").value });
    const box = $("p-list"); box.replaceChildren();
    if (r.error) return box.append(el("div", { class: "msg error", text: r.error }));
    if (!r.total) return box.append(el("div", { class: "msg info", text: CFG.messages.noPhrases }));
    if (!r.phrases.length) return box.append(el("div", { class: "msg info", text: CFG.messages.noResults }));
    const tbody = el("tbody");
    r.phrases.forEach((p) => tbody.append(el("tr", {},
      el("td", { text: p.date || "—" }), el("td", { text: p.text }), el("td", { text: p.contact_name }),
      el("td", { text: labelOf(CFG.options.languages, p.language) }), el("td", { text: labelOf(CFG.options.situations, p.situation) }))));
    box.append(el("div", { class: "table-wrap" }, el("table", {},
      el("thead", {}, el("tr", {}, ...["날짜", "문장", "상대", "언어", "상황"].map((h) => el("th", { text: h })))), tbody)));
  }, 200);
}
async function savePhrase() {
  const { contact, language } = who("p");
  const r = await api("/api/phrase", {
    text: $("p-text").value, contact, language, situation: picked("p-situation"),
    source_ko: $("p-source").value, phrases: DB.phrases,
  });
  if (r.error) return show("p-msg", "error", r.error);
  DB.phrases.push(r.phrase); saveStore();
  $("p-text").value = ""; $("p-source").value = "";
  show("p-msg", "ok", "저장했어요!"); runSearch();
}

// ---------------------------------------------------------------- F5 보내기 전 점검
async function runCheck() {
  const { contact, language } = who("e");
  const r = await api("/api/check", { subject: $("e-subject").value, body: $("e-body").value, contact, language });
  const box = $("e-msg"); box.replaceChildren();
  const add = (kind, text) => box.append(el("div", { class: `msg ${kind}`, text }));
  if (r.error) return add("error", r.error);
  if (r.missing && r.missing.length) add("error", "빠진 항목: " + r.missing.join(" · "));
  if (r.casual && r.casual.length) add("warn", "상사 · 거래처에게 피할 표현: " + r.casual.join(", "));
  if (r.note) add("info", r.note);
  if (r.ready) add("ok", CFG.messages.ready);
}

// ---------------------------------------------------------------- 시작
function tabs() {
  document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll(".tabs button").forEach((x) => x.classList.toggle("on", x === b));
    document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("on", p.id === b.dataset.tab));
  }));
}
async function start() {
  tabs();
  CFG = await api("/api/seed");
  if (CFG.error || !CFG.options) {
    document.querySelector(".tabs").after(el("div", { class: "msg error", text: "서버에 연결하지 못했어요. 잠시 뒤 새로고침해 주세요" }));
    return;
  }
  DB = loadStore() || { contacts: CFG.contacts, phrases: CFG.phrases };
  saveStore();
  $("ai-limit").textContent = CFG.aiLimit;
  radios("c-relation", "c-relation", CFG.options.relations, false);
  radios("c-language", "c-language", CFG.options.languages, false);
  radios("c-formality", "c-formality", CFG.options.formalities, false);
  radios("t-situation", "t-situation", CFG.options.situations, true);
  radios("r-situation", "r-situation", CFG.options.situations, true);
  radios("p-situation", "p-situation", CFG.options.situations, false);   // PRD F4 기준 6: 미리 고르지 않음
  refreshWhoPickers(); renderContacts(); renderSearchContacts(); runSearch();
  showLeft(CFG.aiLeft);
  if (!CFG.aiReady) $("t-left").textContent = "지금은 AI 키가 없어서 번역할 수 없어요. 검수 요청문 탭을 써 보세요.";
  $("p-box").open = !DB.phrases.length;

  $("c-save").addEventListener("click", (e) => busy(e.target, saveContact));
  $("t-go").addEventListener("click", (e) => busy(e.target, translate));
  $("t-result").addEventListener("input", recheckVerbose);
  $("t-save").addEventListener("click", (e) => busy(e.target, saveTranslation));
  $("r-go").addEventListener("click", (e) => busy(e.target, makeRequest));
  $("r-copy").addEventListener("click", copyRequest);
  $("p-save").addEventListener("click", (e) => busy(e.target, savePhrase));
  $("q-word").addEventListener("input", runSearch);
  $("q-contact").addEventListener("change", runSearch);
  $("e-go").addEventListener("click", (e) => busy(e.target, runCheck));
}
start();
