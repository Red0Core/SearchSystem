const HISTORY_LIMIT = 10;
let lastResponse = null;
let history = [];

function $(id) {
  return document.getElementById(id);
}

function setStatusSearching(q) {
  const el = $("status");
  el.classList.remove("text-red-600");
  el.textContent = `Поиск: "${q}"...`;
}

function renderStatus(data) {
  const el = $("status");
  el.classList.remove("text-red-600");
  const parts = [];
  if (data?.query) {
    parts.push(`Запрос: "${data.query}"`);
  }
  if (data?.classification) {
    parts.push(`Тип: ${data.classification}`);
  }
  if (typeof data?.took_ms === "number") {
    parts.push(`ES: ${data.took_ms.toFixed(2)} ms`);
  }
  if (typeof data?.eta_ms === "number") {
    parts.push(`Всего: ${data.eta_ms.toFixed(2)} ms`);
  }
  el.textContent = parts.join(" | ") || "Готово.";
}

function renderError(err) {
  const el = $("status");
  el.classList.add("text-red-600");
  el.textContent = `Ошибка запроса: ${err?.message || err}`;
  $("results-body").innerHTML = "";
  $("results-count").textContent = "";
}

function clearError() {
  $("status").classList.remove("text-red-600");
}

function renderResults(results) {
  const tbody = $("results-body");
  const countEl = $("results-count");
  tbody.innerHTML = "";

  if (!Array.isArray(results) || results.length === 0) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 4;
    td.className = "px-3 py-4 text-center text-xs text-slate-400";
    td.textContent = "Ничего не найдено.";
    tr.appendChild(td);
    tbody.appendChild(tr);
    countEl.textContent = "";
    return;
  }

  countEl.textContent = `${results.length} результатов`;

  for (const hit of results) {
    const tr = document.createElement("tr");
    tr.className = "hover:bg-slate-50";

    const manufacturer = document.createElement("td");
    manufacturer.className = "px-3 py-2 font-semibold text-slate-800 whitespace-nowrap";
    manufacturer.textContent = hit.manufacturer || "";

    const code = document.createElement("td");
    code.className = "px-3 py-2 font-mono text-xs text-slate-700 whitespace-nowrap";
    code.textContent = hit.product_code || "";

    const title = document.createElement("td");
    title.className = "px-3 py-2 text-slate-700";
    title.textContent = hit.title || "";

    const score = document.createElement("td");
    score.className = "px-3 py-2 text-right text-xs text-slate-500";
    score.textContent = typeof hit.score === "number" ? hit.score.toFixed(2) : "";

    tr.appendChild(manufacturer);
    tr.appendChild(code);
    tr.appendChild(title);
    tr.appendChild(score);
    tbody.appendChild(tr);
  }
}

function updateHistory(query) {
  history = [query, ...history.filter((item) => item !== query)].slice(0, HISTORY_LIMIT);
  renderHistory();
}

function renderHistory() {
  const container = $("history");
  container.innerHTML = "";

  if (history.length === 0) {
    const p = document.createElement("p");
    p.className = "text-slate-400";
    p.textContent = "История пока пуста.";
    container.appendChild(p);
    return;
  }

  const list = document.createElement("div");
  list.className = "flex flex-wrap gap-2";

  for (const q of history) {
    const btn = document.createElement("button");
    btn.className =
      "px-2 py-1 rounded-full border border-slate-200 text-[11px] text-slate-700 bg-slate-50 hover:bg-slate-100";
    btn.textContent = q;
    btn.addEventListener("click", () => {
      $("search-input").value = q;
      performSearch();
    });
    list.appendChild(btn);
  }

  container.appendChild(list);
}

async function performSearch() {
  const input = $("search-input");
  const q = input.value.trim();
  if (!q) {
    return;
  }

  setStatusSearching(q);
  clearError();

  try {
    const resp = await fetch(`/search?q=${encodeURIComponent(q)}`);
    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}`);
    }
    const data = await resp.json();
    lastResponse = data;
    updateHistory(q);
    renderStatus(data);
    renderResults(data.results || []);
  } catch (err) {
    renderError(err);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const btn = $("search-button");
  const input = $("search-input");

  btn.addEventListener("click", () => performSearch());
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      performSearch();
    }
  });
});
