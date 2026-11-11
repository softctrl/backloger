"use strict";
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const el = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};
const priorityNames = {
  critical: "Crítica",
  high: "Alta",
  medium: "Média",
  low: "Baixa",
};
const pages = {
  kanban: [
    "Quadro do projeto",
    "Organize o trabalho. Conecte as entregas. Mantenha o foco.",
    "KANBAN",
  ],
  dashboard: [
    "Uma visão do todo",
    "O ritmo do projeto, com os dados que você já tem.",
    "DASHBOARD",
  ],
  graph: [
    "Cada entrega tem conexões",
    "Entenda pré-requisitos, bloqueios e o impacto de cada atividade.",
    "DEPENDÊNCIAS",
  ],
  table: [
    "O trabalho, em detalhe",
    "Todas as atividades em uma única visão.",
    "TABELA",
  ],
  roadmap: [
    "Do próximo passo à próxima entrega",
    "Acompanhe o progresso dos seus milestones.",
    "ROADMAP",
  ],
  document: [
    "O backlog, pronto para compartilhar",
    "Leia o documento gerado, consulte o Markdown e leve o relatório em PDF.",
    "DOCUMENTO DO PROJETO",
  ],
};
let state = null,
  currentView = Object.hasOwn(pages, location.hash.slice(1))
    ? location.hash.slice(1)
    : "dashboard",
  graph = null,
  editing = null,
  editRevision = null,
  busy = false,
  syncFailed = false,
  dragging = false,
  historyDays = 14,
  burndownDays = 14,
  lastMetricsDay = "",
  lastFullRefresh = 0,
  lastChangedItem = null,
  documentRevision = null,
  documentDay = null,
  documentLoading = false,
  pdfBusy = false,
  toastTimer = null;
const metricValues = new Map();
const graphView = BacklogGraph.create(openEditor);
function markChanged(id) {
  lastChangedItem = id;
  setTimeout(() => {
    if (lastChangedItem === id) {
      lastChangedItem = null;
      $$(".just-updated").forEach((card) =>
        card.classList.remove("just-updated"),
      );
    }
  }, 1800);
}
const filterIds = [
  "search",
  "filter-owner",
  "filter-status",
  "filter-priority",
  "filter-label",
  "filter-component",
  "filter-iteration",
  "filter-blocked",
];
const form = $("#item-form"),
  dialog = $("#editor");
function field(name) {
  return form.elements.namedItem(name);
}
function notice(text) {
  $("#notice").textContent = text;
  $("#notice").hidden = !text;
}
function toast(text) {
  clearTimeout(toastTimer);
  const target = $("#toast");
  target.replaceChildren(el("span", "toast-check", "✓"), el("span", "", text));
  target.hidden = false;
  toastTimer = setTimeout(() => {
    target.hidden = true;
  }, 4500);
}
function animateValue(target, previous, value) {
  target.textContent = String(value);
  if (
    previous === undefined ||
    previous === value ||
    !window.requestAnimationFrame ||
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
  )
    return;
  const start = performance.now();
  const frame = (at) => {
    const progress = Math.min(1, (at - start) / 450);
    target.textContent = String(
      Math.round(
        previous + (value - previous) * (1 - Math.pow(1 - progress, 3)),
      ),
    );
    if (progress < 1 && target.isConnected) requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
}
function endDrag() {
  dragging = false;
  document.body.classList.remove("is-dragging");
  $$(".drag-over,.dragging").forEach((node) =>
    node.classList.remove("drag-over", "dragging"),
  );
}
function drillDown(filter, value) {
  $("#filter-" + filter).value = value;
  setView("kanban");
  $("#page-title").focus({ preventScroll: true });
}
async function api(path, options = {}, revision = state?.revision) {
  const headers = {
    "X-Backloger-Token": $("meta[name=backloger-token]").content,
    ...(options.headers || {}),
  };
  if (options.body) headers["Content-Type"] = "application/json";
  if (options.method && options.method !== "GET")
    headers["If-Match"] = `"${revision}"`;
  const response = await fetch(path, {
    ...options,
    headers,
    credentials: "same-origin",
  });
  if (response.status === 304) return null;
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      data.message ||
        (typeof data.detail === "string"
          ? data.detail
          : JSON.stringify(data.detail || data.error)),
    );
  return data;
}
async function refresh(force = false) {
  if (busy || dragging) return;
  const today = new Date().toISOString().slice(0, 10);
  force =
    force || today !== lastMetricsDay || Date.now() - lastFullRefresh > 60000;
  try {
    const fresh = await api("/api/v1/state", {
      headers:
        state && !force ? { "If-None-Match": `"${state.revision}"` } : {},
    });
    if (fresh) {
      if (dialog.open && state && state.revision !== fresh.revision) {
        $("#editor-conflict").textContent =
          "O projeto mudou enquanto você editava. Seus campos foram preservados. Feche e reabra a atividade para revisar a versão atual antes de salvar.";
        $("#editor-conflict").hidden = false;
      }
      state = fresh;
      lastMetricsDay = today;
      lastFullRefresh = Date.now();
      render();
    }
    $("#sync-status").textContent = "Sincronizado com o projeto";
    $(".connection").classList.remove("sync-error");
    if (syncFailed) notice("");
    syncFailed = false;
  } catch (error) {
    syncFailed = true;
    $("#sync-status").textContent = "Sincronização pendente";
    $(".connection").classList.add("sync-error");
    notice(error.message);
  }
}
function fillSelect(selector, values, label) {
  const select = typeof selector === "string" ? $(selector) : selector;
  const current = select.value;
  select.replaceChildren(
    new Option(label, ""),
    ...values.map(([value, text]) => new Option(text, value)),
  );
  select.value = values.some(([value]) => value === current) ? current : "";
}
function filters() {
  return Object.fromEntries(
    filterIds.map((id) => [
      id,
      $("#" + id).type === "checkbox"
        ? String($("#" + id).checked)
        : $("#" + id).value,
    ]),
  );
}
function visibleItems() {
  const f = filters(),
    q = f.search.toLocaleLowerCase();
  return state.work_items.filter(
    (i) =>
      (!q || `${i.id} ${i.title}`.toLocaleLowerCase().includes(q)) &&
      (!f["filter-owner"] || i.owner === f["filter-owner"]) &&
      (!f["filter-status"] || i.status === f["filter-status"]) &&
      (!f["filter-priority"] || i.priority === f["filter-priority"]) &&
      (!f["filter-label"] || i.labels.includes(f["filter-label"])) &&
      (!f["filter-component"] || i.component === f["filter-component"]) &&
      (!f["filter-iteration"] || i.iteration_id === f["filter-iteration"]) &&
      (f["filter-blocked"] !== "true" || state.analysis.blockers[i.id]?.length),
  );
}
function render() {
  const distinct = (key) =>
    [...new Set(state.work_items.map((i) => i[key]).filter(Boolean))]
      .sort()
      .map((s) => [s, s]);
  fillSelect("#filter-owner", distinct("owner"), "Responsáveis");
  fillSelect(
    "#filter-status",
    state.project.statuses.map((s) => [s.id, s.name]),
    "Estados",
  );
  fillSelect("#filter-component", distinct("component"), "Componentes");
  fillSelect(
    "#filter-label",
    [...new Set(state.work_items.flatMap((i) => i.labels))]
      .sort()
      .map((s) => [s, s]),
    "Etiquetas",
  );
  fillSelect(
    "#filter-iteration",
    state.iterations.map((i) => [i.id, i.name]),
    "Iterações",
  );
  fillSelect(
    "#saved-views",
    state.views.map((v) => [v.id, v.name]),
    "Visões salvas",
  );
  $("#storage-label").textContent =
    state.storage === "split" ? "Um arquivo por atividade" : "Arquivo único";
  const active = state.project.statuses
    .filter((s) => s.category === "active")
    .reduce((n, s) => n + state.metrics.by_status[s.id], 0);
  const metrics = [
    [
      "Total de atividades",
      state.metrics.total,
      "Escopo completo do projeto",
      "layers",
    ],
    ["Em andamento", active, "Trabalho nas fases ativas", "clock"],
    [
      "Atividades bloqueadas",
      state.metrics.blocked,
      "Pré-requisitos pendentes",
      "link",
    ],
    [
      "Concluídas na semana",
      state.metrics.throughput_7d,
      "Registradas pelo Backloger",
      "trend",
    ],
  ];
  $("#metrics").replaceChildren(
    ...metrics.map(([title, value, note, symbol]) => {
      const card = el("article", "metric");
      const number = el("div", "metric-value", String(value));
      animateValue(number, metricValues.get(title), value);
      metricValues.set(title, value);
      const symbolNode = el("span", "metric-symbol");
      symbolNode.append(BacklogCharts.icon(symbol));
      card.append(
        el("div", "metric-title", title),
        number,
        el("div", "metric-note", note),
        symbolNode,
      );
      return card;
    }),
  );
  $$("[data-icon]").forEach((element) =>
    element.replaceChildren(BacklogCharts.icon(element.dataset.icon)),
  );
  renderView();
}
function itemCard(item) {
  const card = el("button", "card");
  card.type = "button";
  card.dataset.id = item.id;
  if (item.id === lastChangedItem) card.classList.add("just-updated");
  card.draggable = !state.read_only;
  const top = el("div", "card-top");
  top.append(el("span", "", item.id), el("span", "card-type", item.type));
  const tags = el("div", "tags");
  item.labels.slice(0, 4).forEach((t) => tags.append(el("span", "tag", t)));
  const bottom = el("div", "card-bottom");
  bottom.append(
    el("span", `priority ${item.priority}`, priorityNames[item.priority]),
    el("span", "", item.owner || "Sem responsável"),
  );
  const historyBadge = el(
    "span",
    "card-history",
    String(item.history?.length || 0),
  );
  historyBadge.prepend(BacklogCharts.icon("clock"));
  historyBadge.title = `Histórico: ${item.history?.length || 0} registros`;
  historyBadge.setAttribute("aria-label", historyBadge.title);
  bottom.append(historyBadge);
  card.append(top, el("div", "card-title", item.title), tags);
  const blockers = state.analysis.blockers[item.id] || [];
  if (blockers.length)
    card.append(
      el(
        "span",
        "blocked-badge",
        `⌁ ${blockers.length} pré-requisito(s) pendente(s)`,
      ),
    );
  card.append(bottom);
  card.addEventListener("click", () => openEditor(item));
  card.addEventListener("dragstart", (event) => {
    dragging = true;
    card.classList.add("dragging");
    document.body.classList.add("is-dragging");
    event.dataTransfer.setData("text/plain", item.id);
    event.dataTransfer.effectAllowed = "move";
  });
  card.addEventListener("dragend", endDrag);
  return card;
}
function renderBoard(items) {
  const board = $("#board");
  board.style.setProperty("--columns", String(state.project.statuses.length));
  board.replaceChildren(
    ...state.project.statuses.map((status) => {
      const column = el("div", "column");
      column.dataset.status = status.id;
      const heading = el("div", "column-heading");
      heading.dataset.category = status.category;
      const matching = items.filter((i) => i.status === status.id);
      heading.append(
        el("span", "status-dot"),
        el("span", "", status.name),
        el("small", "", String(matching.length)),
      );
      if (status.wip_limit)
        heading.append(
          el(
            "span",
            "wip",
            `WIP ${state.metrics.by_status[status.id]}/${status.wip_limit}`,
          ),
        );
      column.append(heading, ...matching.map(itemCard));
      if (!matching.length)
        column.append(el("div", "empty", "Nenhuma atividade nesta fase."));
      if (!state.read_only) {
        const add = el("button", "column-add", "＋ Adicionar atividade");
        add.addEventListener("click", () => openEditor(null, status.id));
        column.append(add);
      }
      column.addEventListener("dragover", (event) => {
        if (!state.read_only) {
          event.preventDefault();
          column.classList.add("drag-over");
        }
      });
      column.addEventListener("dragleave", () =>
        column.classList.remove("drag-over"),
      );
      column.addEventListener("drop", async (event) => {
        event.preventDefault();
        column.classList.remove("drag-over");
        endDrag();
        if (state.read_only) return;
        const item = state.work_items.find(
          (i) => i.id === event.dataTransfer.getData("text/plain"),
        );
        if (!item || item.status === status.id) return;
        busy = true;
        try {
          await api(`/api/v1/items/${item.id}`, {
            method: "PATCH",
            body: JSON.stringify({
              expected_version: item.version,
              status: status.id,
            }),
          });
          markChanged(item.id);
          toast(`${item.id} movida para ${status.name}`);
        } catch (error) {
          notice(error.message);
        } finally {
          busy = false;
          await refresh(true);
        }
      });
      return column;
    }),
  );
}
function renderDashboard(items) {
  BacklogCharts.donut(
    $("#completion-chart"),
    items,
    state.project.statuses,
    (id) => drillDown("status", id),
  );
  BacklogCharts.priority($("#priority-chart"), items, (id) =>
    drillDown("priority", id),
  );
  BacklogCharts.owners(
    $("#owners-chart"),
    items,
    state.project.statuses,
    (id) => drillDown("owner", id),
  );
  renderActivity();
  renderBurndown();
  $("#status-bars").replaceChildren(
    ...state.project.statuses.map((status) => {
      const row = el("div", "bar-row"),
        label = el("div", "bar-label"),
        track = el("div", "bar-track"),
        fill = el("div", "bar-fill");
      const count = items.filter((i) => i.status === status.id).length;
      label.append(el("span", "", status.name), el("span", "", String(count)));
      fill.style.width = `${items.length ? (count / items.length) * 100 : 0}%`;
      fill.style.backgroundColor = BacklogCharts.categoryColor(status.category);
      track.append(fill);
      row.append(label, track);
      return row;
    }),
  );
  const ready = items.filter((i) => state.analysis.ready.includes(i.id));
  $("#ready-items").replaceChildren(
    ...ready.slice(0, 10).map((i) => {
      const button = el("button", "ready-item");
      button.append(el("span", "", i.id), el("strong", "", i.title));
      button.addEventListener("click", () => openEditor(i));
      return button;
    }),
  );
  if (!ready.length)
    $("#ready-items").append(
      el("p", "empty", "Nenhuma atividade pronta com os filtros atuais."),
    );
  $("#ready-items").append(
    el(
      "p",
      "metric-note",
      `${state.metrics.overdue} atividade(s) vencida(s) no projeto.`,
    ),
  );
}
function renderActivity() {
  const days = state.history?.days?.slice(-historyDays) || [];
  const created = days.reduce((sum, day) => sum + day.created, 0),
    completed = days.reduce((sum, day) => sum + day.completed, 0);
  const summary = $("#activity-summary");
  summary.replaceChildren();
  [
    [created, "criadas", "created"],
    [completed, "conclusões", "completed"],
  ].forEach(([value, label, kind]) => {
    const part = el("span", `activity-total ${kind}`);
    part.append(
      el("i", ""),
      el("strong", "", String(value)),
      el("span", "", label),
    );
    summary.append(part);
  });
  BacklogCharts.activity($("#activity-chart"), days);
  $("#activity-note").textContent =
    state.history?.note ||
    "O histórico será exibido quando houver eventos registrados pelo Backloger.";
}
function renderBurndown() {
  const scopes = state.burndown?.scopes || [];
  const select = $("#burndown-scope"),
    selected = select.value || "project";
  select.replaceChildren(
    ...scopes.map(
      (scope) =>
        new Option(
          scope.id === "project" ? "Projeto completo" : scope.name,
          scope.id,
        ),
    ),
  );
  select.value = scopes.some((scope) => scope.id === selected)
    ? selected
    : "project";
  const scope = scopes.find((scope) => scope.id === select.value);
  const points = scope?.points.slice(-burndownDays) || [];
  BacklogCharts.burndown($("#burndown-chart"), points);
  const latest = points.filter((point) => point.remaining !== null).at(-1);
  $("#burndown-remaining").textContent = latest
    ? String(latest.remaining)
    : "—";
  const date = (value) =>
    new Date(value + "T00:00:00Z").toLocaleDateString("pt-BR", {
      timeZone: "UTC",
    });
  $("#burndown-baseline").textContent = scope?.baseline_date
    ? `Referência a partir de ${date(scope.baseline_date)} · Prazo: ${date(scope.due_date)}`
    : "Selecione uma iteração com início e prazo para comparar com a referência ideal.";
  $("#burndown-note").textContent =
    state.burndown?.note ||
    "O histórico será construído a partir dos próximos registros do projeto.";
}
function renderTable(items) {
  $("#item-table").replaceChildren(
    ...items.map((item) => {
      const row = el("tr");
      [
        item.id,
        item.title,
        item.type,
        state.project.statuses.find((s) => s.id === item.status).name,
        priorityNames[item.priority],
        item.owner || "—",
        item.due_date || "—",
      ].forEach((value, index) => {
        const td = el("td");
        if (index === 1) {
          const button = el("button", "", value);
          button.addEventListener("click", () => openEditor(item));
          td.append(button);
        } else td.textContent = value;
        row.append(td);
      });
      return row;
    }),
  );
  if (!items.length) {
    const row = el("tr"),
      td = el("td", "empty", "Nenhuma atividade encontrada.");
    td.colSpan = 7;
    row.append(td);
    $("#item-table").append(row);
  }
}
function renderRoadmap(items) {
  const milestones = [
    ...state.milestones,
    { id: null, name: "Sem milestone", due_date: null },
  ];
  $("#roadmap").replaceChildren(
    ...milestones.map((m) => {
      const matching = items.filter((i) => i.milestone_id === m.id),
        card = el("article", "panel milestone-panel");
      const done = matching.filter(
        (i) =>
          state.project.statuses.find((s) => s.id === i.status).category ===
          "done",
      ).length;
      const percentage = matching.length
        ? Math.round((done / matching.length) * 100)
        : 0;
      const progress = el("div", "milestone-progress-track"),
        fill = el("div", "milestone-progress-fill");
      fill.style.width = `${percentage}%`;
      progress.append(fill);
      progress.setAttribute("role", "progressbar");
      progress.setAttribute("aria-label", `Progresso de ${m.name}`);
      progress.setAttribute("aria-valuenow", String(percentage));
      progress.setAttribute("aria-valuemin", "0");
      progress.setAttribute("aria-valuemax", "100");
      card.append(
        el("p", "eyebrow", m.id || "PRÓXIMAS ENTREGAS"),
        el("h2", "", m.name),
        el(
          "p",
          "metric-note",
          m.due_date ? `Prazo: ${m.due_date}` : "Sem prazo definido",
        ),
        el(
          "p",
          "milestone-progress",
          `${done} de ${matching.length} atividades concluídas`,
        ),
        el("strong", "milestone-percentage", `${percentage}%`),
        progress,
        ...matching.map(itemCard),
      );
      if (!matching.length)
        card.append(el("p", "empty", "Nenhuma atividade neste milestone."));
      return card;
    }),
  );
}
function renderGraph(items) {
  try {
    graph = graphView.update(state, items);
  } catch (error) {
    notice(error.message);
  }
}
async function renderDocument() {
  const today = new Date().toISOString().slice(0, 10);
  if (
    documentLoading ||
    (documentRevision === state.revision && documentDay === today)
  )
    return;
  documentLoading = true;
  $("#refresh-document").disabled = true;
  $("#document-info").textContent = "Gerando relatório gerencial…";
  let received = false;
  try {
    const data = await api("/api/v1/document");
    $("#document-source").textContent = data.markdown;
    $("#document-info").textContent =
      `${data.item_count} atividades · Relatório gerencial atualizado com os dados do projeto`;
    $("#document-frame").src =
      `/document?revision=${encodeURIComponent(data.revision)}&day=${today}`;
    documentRevision = data.revision;
    documentDay = today;
    received = true;
  } catch (error) {
    $("#document-info").textContent =
      "Falha ao gerar relatório. Use Atualizar relatório para tentar novamente.";
    notice(error.message);
  } finally {
    documentLoading = false;
    $("#refresh-document").disabled = false;
    if (
      received &&
      state &&
      documentRevision !== state.revision &&
      currentView === "document"
    )
      setTimeout(renderDocument, 250);
  }
}
async function downloadPDF() {
  if (pdfBusy || !state) return;
  pdfBusy = true;
  $(".export-menu").open = false;
  const buttons = $$("[data-export-pdf]");
  buttons.forEach((button) => {
    button.disabled = true;
    button.classList.add("is-loading");
  });
  toast("Gerando o PDF do backlog…");
  try {
    const response = await fetch("/api/v1/export/pdf", {
      credentials: "same-origin",
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.message || "Não foi possível gerar o PDF.");
    }
    const file = await response.blob(),
      url = URL.createObjectURL(file);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${state.project.key}-BACKLOG.pdf`;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
    toast("PDF pronto. O download foi iniciado.");
  } catch (error) {
    notice(error.message);
  } finally {
    pdfBusy = false;
    buttons.forEach((button) => {
      button.disabled = false;
      button.classList.remove("is-loading");
    });
  }
}
function renderView() {
  if (!state) return;
  const items = visibleItems();
  filterIds.forEach((id) =>
    $("#" + id).classList.toggle(
      "filter-active",
      $("#" + id).type === "checkbox"
        ? $("#" + id).checked
        : Boolean($("#" + id).value),
    ),
  );
  $("#item-count").textContent =
    currentView === "document"
      ? `${state.work_items.length} atividades no documento`
      : `${items.length} de ${state.work_items.length} atividades`;
  ({
    kanban: renderBoard,
    dashboard: renderDashboard,
    table: renderTable,
    graph: renderGraph,
    roadmap: renderRoadmap,
    document: renderDocument,
  })[currentView](items);
}
function setView(view) {
  if (!Object.hasOwn(pages, view)) return;
  currentView = view;
  history.replaceState(null, "", `#${view}`);
  $(".toolbar").hidden = view === "document";
  $$("[data-view]").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === view);
    if (button.dataset.view === view)
      button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  $$(".view-panel").forEach(
    (panel) => (panel.hidden = panel.id !== `${view}-view`),
  );
  $("#page-title").textContent = pages[view][0];
  $("#page-subtitle").textContent = pages[view][1];
  $("#view-label").textContent = pages[view][2];
  renderView();
}
function addCriterion(criterion = null) {
  const row = el("div", "criterion");
  row.dataset.original = JSON.stringify(
    criterion || {
      id: `AC-${crypto.randomUUID().slice(0, 8)}`,
      text: "",
      done: false,
    },
  );
  const done = el("input");
  done.type = "checkbox";
  done.checked = criterion?.done || false;
  done.setAttribute("aria-label", "Critério concluído");
  const text = el("input");
  text.type = "text";
  text.required = true;
  text.maxLength = 2000;
  text.value = criterion?.text || "";
  text.setAttribute("aria-label", "Texto do critério");
  const remove = el("button", "", "×");
  remove.type = "button";
  remove.setAttribute("aria-label", "Remover critério");
  remove.addEventListener("click", () => row.remove());
  row.append(done, text, remove);
  $("#criteria-list").append(row);
}
function renderItemHistory(item) {
  const entries = item?.history || [];
  $("#history-count").textContent = `${entries.length} registro(s)`;
  const kinds = {
    created: "Criação",
    updated: "Alteração",
    comment: "Nota",
    restored: "Restauração",
  };
  $("#item-history-list").replaceChildren(
    ...[...entries].reverse().map((entry) => {
      const row = el("li", "history-entry"),
        meta = el("div", "history-meta"),
        time = el("time");
      time.dateTime = entry.at;
      time.textContent = new Date(entry.at).toLocaleString("pt-BR");
      meta.append(
        el("strong", "", kinds[entry.kind] || "Registro"),
        time,
        el("span", "", `v${entry.version}`),
      );
      row.append(meta, el("p", "", entry.text));
      return row;
    }),
  );
  if (!entries.length)
    $("#item-history-list").append(
      el(
        "li",
        "history-empty",
        "As próximas alterações e notas aparecerão aqui.",
      ),
    );
}
function openEditor(item = null, status = null) {
  if (!state) return;
  editing = item;
  editRevision = state.revision;
  form.reset();
  renderItemHistory(item);
  $("#editor-conflict").hidden = true;
  $("#editor-id").textContent = item
    ? `${item.id} · VERSÃO ${item.version}`
    : "NOVA ATIVIDADE";
  $("#editor-title").textContent = item
    ? "Detalhes da atividade"
    : "Dê forma ao próximo passo";
  field("status").replaceChildren(
    ...state.project.statuses.map((s) => new Option(s.name, s.id)),
  );
  fillSelect(
    field("milestone_id"),
    state.milestones.map((m) => [m.id, m.name]),
    "Sem milestone",
  );
  fillSelect(
    field("iteration_id"),
    state.iterations.map((m) => [m.id, m.name]),
    "Sem iteração",
  );
  [
    "title",
    "description",
    "type",
    "priority",
    "owner",
    "component",
    "due_date",
    "milestone_id",
    "iteration_id",
  ].forEach(
    (key) =>
      (field(key).value =
        item?.[key] ??
        (key === "type" ? "task" : key === "priority" ? "medium" : "")),
  );
  field("status").value =
    item?.status ||
    status ||
    state.project.statuses.find((s) => s.category === "pending").id;
  field("labels").value = item?.labels.join(", ") || "";
  field("blocked_by").value =
    item?.dependencies
      .filter((d) => d.relation === "blocked_by")
      .map((d) => d.target_id)
      .join(", ") || "";
  field("estimate_value").value = item?.estimate?.value ?? "";
  field("estimate_unit").value = item?.estimate?.unit || "hours";
  $("#criteria-list").replaceChildren();
  (item?.acceptance_criteria || []).forEach(addCriterion);
  $$("input,select,textarea", form).forEach(
    (input) => (input.disabled = state.read_only),
  );
  $("#save-item").hidden = state.read_only;
  $("#add-criterion").hidden = state.read_only;
  $$(".criterion button", form).forEach(
    (button) => (button.disabled = state.read_only),
  );
  dialog.showModal();
}
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (state.read_only || busy) return;
  const data = Object.fromEntries(
    ["title", "description", "type", "priority", "status"].map((k) => [
      k,
      field(k).value,
    ]),
  );
  ["owner", "component", "due_date", "milestone_id", "iteration_id"].forEach(
    (k) => (data[k] = field(k).value || null),
  );
  data.labels = field("labels")
    .value.split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  data.history_note = field("history_note").value.trim() || null;
  const previous = editing?.dependencies || [];
  data.dependencies = [
    ...previous.filter((d) => d.relation !== "blocked_by"),
    ...field("blocked_by")
      .value.split(",")
      .map((s) => s.trim())
      .filter(Boolean)
      .map(
        (id) =>
          previous.find(
            (d) => d.target_id === id && d.relation === "blocked_by",
          ) || { target_id: id, relation: "blocked_by" },
      ),
  ];
  data.estimate =
    field("estimate_value").value === ""
      ? null
      : {
          ...(editing?.estimate || {}),
          unit: field("estimate_unit").value,
          value: Number(field("estimate_value").value),
        };
  data.acceptance_criteria = $$(".criterion", form).map((row) => ({
    ...JSON.parse(row.dataset.original),
    text: $("input[type=text]", row).value,
    done: $("input[type=checkbox]", row).checked,
  }));
  if (editing) data.expected_version = editing.version;
  busy = true;
  $("#save-item").disabled = true;
  $("#save-item").classList.add("is-loading");
  $("#save-item").textContent = "Salvando…";
  try {
    const saved = await api(
      editing ? `/api/v1/items/${editing.id}` : "/api/v1/items",
      { method: editing ? "PATCH" : "POST", body: JSON.stringify(data) },
      editRevision,
    );
    dialog.close();
    markChanged(saved.item?.id || editing?.id);
    toast(
      editing
        ? "Atividade atualizada com sucesso"
        : "Atividade criada com sucesso",
    );
    notice("");
  } catch (error) {
    $("#editor-conflict").textContent = error.message;
    $("#editor-conflict").hidden = false;
  } finally {
    busy = false;
    $("#save-item").disabled = false;
    $("#save-item").classList.remove("is-loading");
    $("#save-item").textContent = "Salvar atividade";
    await refresh(true);
  }
});
$$("[data-view]").forEach((button) =>
  button.addEventListener("click", () => setView(button.dataset.view)),
);
$("#new-item").addEventListener("click", () => openEditor());
$("#close-editor").addEventListener("click", () => dialog.close());
$("#cancel-editor").addEventListener("click", () => dialog.close());
$("#add-criterion").addEventListener("click", () => addCriterion());
$$("[data-history-days]").forEach((button) =>
  button.addEventListener("click", () => {
    historyDays = Number(button.dataset.historyDays);
    $$("[data-history-days]").forEach((node) => {
      const active = node === button;
      node.classList.toggle("selected", active);
      node.setAttribute("aria-pressed", String(active));
    });
    if (state) renderActivity();
  }),
);
$("#burndown-scope").addEventListener("change", () => {
  if (state) renderBurndown();
});
$("#burndown-range").addEventListener("change", (event) => {
  burndownDays = Number(event.target.value);
  if (state) renderBurndown();
});
$$("[data-document-mode]").forEach((button) =>
  button.addEventListener("click", () => {
    const source = button.dataset.documentMode === "source";
    $("#document-preview").hidden = source;
    $("#document-source-panel").hidden = !source;
    $$("[data-document-mode]").forEach((node) => {
      const active = node === button;
      node.classList.toggle("selected", active);
      node.setAttribute("aria-pressed", String(active));
    });
  }),
);
$$("[data-export-pdf]").forEach((button) =>
  button.addEventListener("click", downloadPDF),
);
$("#refresh-document").addEventListener("click", () => {
  documentRevision = null;
  renderDocument();
});
$("#copy-markdown").addEventListener("click", async () => {
  try {
    if (!navigator.clipboard)
      throw new Error(
        "Seu navegador não permite copiar automaticamente. Selecione o texto na aba Markdown.",
      );
    await navigator.clipboard.writeText($("#document-source").textContent);
    toast("Markdown copiado");
  } catch (error) {
    notice(error.message);
  }
});
document.addEventListener("click", (event) => {
  const menu = $(".export-menu");
  if (menu.open && !menu.contains(event.target)) menu.open = false;
});
filterIds.forEach((id) =>
  $("#" + id).addEventListener(
    id === "search" ? "input" : "change",
    renderView,
  ),
);
$("#clear-filters").addEventListener("click", () => {
  filterIds.forEach((id) => {
    const input = $("#" + id);
    if (input.type === "checkbox") input.checked = false;
    else input.value = "";
  });
  renderView();
});
$("#save-view").addEventListener("click", async () => {
  const name = window.prompt("Nome da visualização:");
  if (!name?.trim()) return;
  try {
    const id = `view-${crypto.randomUUID().slice(0, 12)}`;
    await api(`/api/v1/views/${id}`, {
      method: "PUT",
      body: JSON.stringify({ id, name: name.trim(), filters: filters() }),
    });
    await refresh(true);
    toast("Visualização salva");
  } catch (error) {
    notice(error.message);
  }
});
$("#saved-views").addEventListener("change", (event) => {
  const view = state.views.find((v) => v.id === event.target.value);
  if (!view) return;
  filterIds.forEach((id) => {
    const input = $("#" + id);
    if (input.type === "checkbox") input.checked = view.filters[id] === "true";
    else input.value = view.filters[id] || "";
  });
  renderView();
});
setView(currentView);
refresh(true);
setInterval(() => refresh(), 3000);
