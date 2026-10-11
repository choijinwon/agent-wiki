const API_ORIGIN = window.location.protocol === "file:" ? "http://127.0.0.1:8090" : "";
const STATIC_SITE = [".github.io", ".netlify.app"].some((domain) => window.location.hostname.endsWith(domain));
const STORAGE_KEY = "orbit-knowledge-documents-v1";
const state = { busy: false, documents: [], connected: false, staticMode: STATIC_SITE };
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

function readBrowserDocuments() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
  } catch (_) {
    return state.documents || [];
  }
}

function writeBrowserDocuments(documents) {
  state.documents = documents;
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(documents)); } catch (_) { /* file previews may block storage */ }
}

function browserSearch(query, limit = 5) {
  const terms = [...new Set((query.toLowerCase().match(/[0-9a-z_가-힣]{2,}/g) || []))];
  return readBrowserDocuments()
    .map((document) => {
      const haystack = `${document.title} ${document.content}`.toLowerCase();
      const hits = terms.filter((term) => haystack.includes(term)).length;
      return { document, score: terms.length ? hits / terms.length : 0 };
    })
    .filter((item) => item.score > 0)
    .sort((left, right) => right.score - left.score)
    .slice(0, limit);
}

async function browserApi(path, options = {}) {
  const method = options.method || "GET";
  const body = options.body ? JSON.parse(options.body) : {};
  const documents = readBrowserDocuments();
  if (path === "/api/health") {
    return { status: "ok", static: true, llm: false, stats: { documents: documents.length, chunks: documents.reduce((sum, item) => sum + item.chunk_count, 0) } };
  }
  if (path === "/api/documents" && method === "GET") return { documents };
  if (path === "/api/documents" && method === "POST") {
    if (!body.title?.trim() || !body.content?.trim()) throw new Error("문서 제목과 내용을 입력해 주세요.");
    const identity = `web-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
    const document = { id: identity, title: body.title.trim(), source: body.source?.trim() || "browser", content: body.content.trim(), chunk_count: Math.max(1, Math.ceil(body.content.length / 900)), created_at: new Date().toISOString() };
    writeBrowserDocuments([document, ...documents]);
    return { document };
  }
  if (path.startsWith("/api/documents/") && method === "DELETE") {
    const id = decodeURIComponent(path.slice("/api/documents/".length));
    writeBrowserDocuments(documents.filter((item) => item.id !== id));
    return { deleted: id };
  }
  if (path === "/api/chat" && method === "POST") {
    const started = performance.now();
    if (/(문서|자료).*(목록|리스트)|무슨 문서|어떤 자료/.test(body.question)) {
      return { answer: documents.length ? `등록된 문서입니다:\n${documents.map((item) => `- ${item.title} (${item.source})`).join("\n")}` : "등록된 문서가 없습니다.", mode: "tool", citations: [], latency_ms: Math.round(performance.now() - started) };
    }
    const matches = browserSearch(body.question, body.top_k || 5);
    if (!matches.length) return { answer: "관련 근거를 지식 베이스에서 찾지 못했습니다. 문서를 추가하거나 질문을 더 구체적으로 입력해 주세요.", mode: "no_context", citations: [], latency_ms: Math.round(performance.now() - started) };
    const citations = matches.map(({ document, score }, index) => ({ index: index + 1, document_id: document.id, chunk_id: `${document.id}:0`, title: document.title, source: document.source, score, excerpt: document.content.replace(/\s+/g, " ").slice(0, 240) }));
    const answer = `검색된 문서에서 다음 근거를 확인했습니다:\n${citations.map((item) => `\n[${item.index}] ${item.excerpt}${item.excerpt.length >= 240 ? "…" : ""}`).join("")}\n\n서버의 LLM을 연결하면 위 근거를 바탕으로 자연어 답변을 합성할 수 있습니다.`;
    return { answer, mode: "extractive", citations, latency_ms: Math.round(performance.now() - started) };
  }
  throw new Error("지원하지 않는 요청입니다.");
}

async function api(path, options = {}) {
  if (STATIC_SITE) return browserApi(path, options);
  try {
    const response = await fetch(`${API_ORIGIN}${path}`, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "요청을 처리하지 못했습니다.");
    return payload;
  } catch (error) {
    if (window.location.protocol === "file:") {
      state.staticMode = true;
      return browserApi(path, options);
    }
    throw error;
  }
}

function escapeHtml(value = "") {
  return String(value).replace(/[&<>'"]/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  })[char]);
}

function toast(message, type = "success") {
  const element = $("#toast");
  element.querySelector("span").textContent = type === "error" ? "!" : "✓";
  element.querySelector("p").textContent = message;
  element.classList.toggle("error", type === "error");
  element.classList.add("visible");
  clearTimeout(element.timer);
  element.timer = setTimeout(() => element.classList.remove("visible"), 2800);
}

function switchView(name) {
  $$(".nav-item").forEach((button) => button.classList.toggle("active", button.dataset.view === name));
  $$(".view").forEach((view) => view.classList.toggle("active", view.id === `${name}-view`));
  $("#page-title").textContent = name === "chat" ? "지식 에이전트" : "지식 문서";
  if (name === "documents") loadDocuments();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function resetChat() {
  $("#messages").innerHTML = "";
  $("#suggestions").hidden = false;
  $("#chat-intro").classList.remove("hidden");
  $("#question").value = "";
  switchView("chat");
  $("#question").focus();
}

function addMessage(role, payload) {
  const box = document.createElement("article");
  box.className = `message ${role}`;
  if (role === "user") {
    box.textContent = payload;
  } else {
    const avatar = document.createElement("span");
    avatar.className = "agent-avatar";
    avatar.textContent = "✦";
    const content = document.createElement("div");
    content.className = "agent-content";
    if (payload.loading) {
      box.classList.add("typing");
      content.innerHTML = '<span class="typing-dots"><i></i><i></i><i></i></span>문서를 검색하고 근거를 검토하고 있습니다';
    } else {
      const modeLabel = payload.mode === "llm" ? "LLM SYNTHESIS" : payload.mode === "tool" ? "AGENT TOOL" : payload.mode === "error" ? "ERROR" : "GROUNDED SEARCH";
      content.innerHTML = `<div class="agent-label"><span>ORBIT ANSWER</span><b>${modeLabel}</b></div><p class="answer"></p>`;
      content.querySelector(".answer").textContent = payload.answer;

      if (payload.citations?.length) {
        const citations = document.createElement("div");
        citations.className = "citations";
        payload.citations.slice(0, 5).forEach((citation) => {
          const item = document.createElement("div");
          item.className = "citation";
          item.innerHTML = `<div class="citation-head"><span class="citation-index">${citation.index}</span><strong>${escapeHtml(citation.title)}</strong><em>${escapeHtml(citation.source)}</em></div><p>${escapeHtml(citation.excerpt)}</p>`;
          citations.append(item);
        });
        content.append(citations);
      }

      const meta = document.createElement("div");
      meta.className = "message-meta";
      meta.innerHTML = `<span class="trace">질문 분석 <i></i> 문서 검색 <i></i> 답변 생성</span><span>${payload.latency_ms || 0}ms · 출처 ${payload.citations?.length || 0}개</span>`;
      content.append(meta);
    }
    box.append(avatar, content);
  }
  $("#messages").append(box);
  box.scrollIntoView({ behavior: "smooth", block: "nearest" });
  return box;
}

async function ask(question) {
  question = question.trim();
  if (!question || state.busy) return;
  if (!state.connected) {
    toast("먼저 make knowledge-agent-run으로 서버를 실행해 주세요.", "error");
    return;
  }
  state.busy = true;
  $("#chat-intro").classList.add("hidden");
  $("#suggestions").hidden = true;
  $("#chat-form button").disabled = true;
  addMessage("user", question);
  const loading = addMessage("agent", { loading: true });
  try {
    const result = await api("/api/chat", { method: "POST", body: JSON.stringify({ question, top_k: 5 }) });
    loading.remove();
    addMessage("agent", result);
  } catch (error) {
    loading.remove();
    addMessage("agent", { answer: error.message, mode: "error", citations: [], latency_ms: 0 });
  } finally {
    state.busy = false;
    $("#chat-form button").disabled = false;
    $("#question").focus();
  }
}

function setConnection(connected, llm = false, staticMode = false) {
  state.connected = connected;
  state.staticMode = staticMode;
  $("#llm-chip span").textContent = connected ? (staticMode ? "브라우저 데모" : llm ? "LLM 연결됨" : "로컬 검색 모드") : "서버 연결 필요";
  $("#llm-chip").classList.toggle("offline", !connected);
  $(".status-line b").textContent = connected ? "ONLINE" : "OFFLINE";
  $(".status-line").classList.toggle("offline", !connected);
}

async function loadStatus() {
  try {
    const data = await api("/api/health");
    setConnection(true, data.llm, Boolean(data.static));
    $("#system-stats").textContent = `${data.stats.documents}개 문서 · ${data.stats.chunks}개 청크`;
    $("#nav-document-count").textContent = data.stats.documents;
    $("#context-count").textContent = `${data.stats.documents}개 문서 연결됨`;
    $("#document-count").textContent = data.stats.documents;
    $("#chunk-count").textContent = data.stats.chunks;
    $("#engine-mode").textContent = data.static ? "WEB" : data.llm ? "LLM" : "LOCAL";
  } catch (_) {
    setConnection(false);
    $("#system-stats").textContent = "서버를 실행해 연결하세요";
  }
}

async function loadDocuments() {
  if (!state.connected) {
    state.documents = [];
    renderDocuments();
    return;
  }
  try {
    const data = await api("/api/documents");
    state.documents = data.documents;
    renderDocuments();
  } catch (error) {
    toast(error.message, "error");
  }
}

function renderDocuments() {
  const query = $("#document-search").value.trim().toLowerCase();
  const filtered = state.documents.filter((item) => `${item.title} ${item.source}`.toLowerCase().includes(query));
  const list = $("#document-list");
  list.innerHTML = "";
  $("#library-count").textContent = `${state.documents.length}개의 문서`;
  $("#empty-documents").classList.toggle("visible", state.documents.length === 0 && !query);
  $("#empty-search").classList.toggle("visible", state.documents.length > 0 && filtered.length === 0);
  filtered.forEach((item) => list.append(documentCard(item)));
}

function documentCard(item) {
  const card = document.createElement("article");
  card.className = "document-card";
  card.innerHTML = `<div class="document-card-head"><span class="doc-icon">▤</span><button class="delete-doc" aria-label="${escapeHtml(item.title)} 삭제" title="삭제">×</button></div><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.source)}</p><div class="doc-footer"><span>${new Date(item.created_at).toLocaleDateString("ko-KR")}</span><b>${item.chunk_count} CHUNKS</b></div>`;
  card.querySelector(".delete-doc").addEventListener("click", async () => {
    if (!confirm(`'${item.title}' 문서를 삭제할까요?`)) return;
    try {
      await api(`/api/documents/${encodeURIComponent(item.id)}`, { method: "DELETE" });
      toast("문서를 삭제했습니다.");
      await Promise.all([loadDocuments(), loadStatus()]);
    } catch (error) {
      toast(error.message, "error");
    }
  });
  return card;
}

async function readFile(file) {
  if (!file) return;
  if (file.size > 5_000_000) {
    toast("파일은 5MB 이하여야 합니다.", "error");
    return;
  }
  const content = await file.text();
  $("#document-content").value = content;
  $("#character-count").textContent = content.length.toLocaleString("ko-KR");
  $("#file-label").textContent = file.name;
  if (!$("#document-title").value) $("#document-title").value = file.name.replace(/\.[^.]+$/, "");
  if (!$("#document-source").value) $("#document-source").value = file.name;
}

function openUpload() {
  if (!state.connected) {
    toast("문서를 추가하려면 먼저 서버를 실행해 주세요.", "error");
    return;
  }
  $("#upload-dialog").showModal();
  $("#document-title").focus();
}

$$('.nav-item').forEach((button) => button.addEventListener('click', () => switchView(button.dataset.view)));
$$('#suggestions button').forEach((button) => button.addEventListener('click', () => ask(button.dataset.prompt)));
$("#new-chat").addEventListener("click", resetChat);
$(".icon-button").addEventListener("click", () => toast("문서를 등록한 뒤 자연어로 질문해 보세요."));
$("#document-search").addEventListener("input", renderDocuments);

$("#chat-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const input = $("#question");
  const question = input.value;
  input.value = "";
  input.style.height = "auto";
  ask(question);
});
$("#question").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    $("#chat-form").requestSubmit();
  }
});
$("#question").addEventListener("input", (event) => {
  event.target.style.height = "auto";
  event.target.style.height = `${Math.min(event.target.scrollHeight, 140)}px`;
});
document.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
    event.preventDefault();
    resetChat();
  }
});

const dialog = $("#upload-dialog");
$("#open-upload").addEventListener("click", openUpload);
$("#empty-upload").addEventListener("click", openUpload);
$("#close-upload").addEventListener("click", () => dialog.close());
$("#cancel-upload").addEventListener("click", () => dialog.close());
$("#document-file").addEventListener("change", (event) => readFile(event.target.files[0]));
$("#document-content").addEventListener("input", (event) => {
  $("#character-count").textContent = event.target.value.length.toLocaleString("ko-KR");
});

const dropZone = $("#drop-zone");
["dragenter", "dragover"].forEach((name) => dropZone.addEventListener(name, (event) => {
  event.preventDefault();
  dropZone.classList.add("dragover");
}));
["dragleave", "drop"].forEach((name) => dropZone.addEventListener(name, (event) => {
  event.preventDefault();
  dropZone.classList.remove("dragover");
}));
dropZone.addEventListener("drop", (event) => readFile(event.dataTransfer.files[0]));

$("#upload-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const submit = $("#submit-document");
  submit.disabled = true;
  submit.textContent = "인덱싱 중…";
  try {
    await api("/api/documents", {
      method: "POST",
      body: JSON.stringify({
        title: $("#document-title").value,
        source: $("#document-source").value || "manual",
        content: $("#document-content").value,
      }),
    });
    event.target.reset();
    $("#file-label").textContent = "파일을 끌어놓거나 클릭해 선택하세요";
    $("#character-count").textContent = "0";
    dialog.close();
    toast("문서를 분석하고 검색 인덱스를 만들었습니다.");
    await Promise.all([loadDocuments(), loadStatus()]);
  } catch (error) {
    toast(error.message, "error");
  } finally {
    submit.disabled = false;
    submit.innerHTML = "<span>✦</span> 인덱싱 시작";
  }
});

loadStatus().then(loadDocuments);
