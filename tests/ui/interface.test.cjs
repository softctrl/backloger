const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const { JSDOM } = require(process.env.BACKLOGER_JSDOM || "jsdom");
const cytoscapeSource = fs.readFileSync(
  "src/backloger/static/vendor/cytoscape.min.js",
  "utf8",
);
const fixture = JSON.parse(
  fs.readFileSync(
    process.env.BACKLOGER_UI_FIXTURE || ".cache/ui-fixture.json",
    "utf8",
  ),
);

async function harness(t, readOnly = false, withSprints = false) {
  const dom = new JSDOM(readOnly ? fixture.readonly_html : fixture.html, {
    url: "http://localhost/",
    runScripts: "outside-only",
  });
  const w = dom.window,
    d = w.document;
  let data = structuredClone(
      withSprints ? fixture.sprint_state : fixture.state,
    ),
    revision = 0;
  data.read_only = readOnly;
  const downloads = [],
    requests = [];
  w.matchMedia = () => ({ matches: true });
  w.structuredClone = (value) => w.JSON.parse(w.JSON.stringify(value));
  w.setInterval = () => 0;
  w.HTMLDialogElement.prototype.showModal = function () {
    this.open = true;
  };
  w.HTMLDialogElement.prototype.close = function () {
    this.open = false;
  };
  w.HTMLAnchorElement.prototype.click = function () {
    downloads.push({ href: this.href, name: this.download });
  };
  w.URL.createObjectURL = () => "blob:backloger-test";
  w.URL.revokeObjectURL = () => {};
  vm.runInContext(cytoscapeSource, dom.getInternalVMContext());
  const cytoscape = w.cytoscape;
  w.cytoscape = (options) => {
    options.container = undefined;
    options.headless = true;
    options.styleEnabled = true;
    return cytoscape(options);
  };
  w.fetch = async (path, options = {}) => {
    requests.push({ path, options });
    const result = (value, status = 200) => ({
      ok: status < 400,
      status,
      json: async () => structuredClone(value),
    });
    if (path === "/api/v1/state") {
      if (options.headers?.["If-None-Match"] === `"${data.revision}"`)
        return result(null, 304);
      return result(data);
    }
    if (path === "/api/v1/document")
      return result({
        markdown: fixture.markdown,
        revision: data.revision,
        item_count: data.work_items.length,
      });
    if (
      path === "/api/v1/export/pdf" ||
      path.startsWith("/api/v1/graph/export/")
    )
      return {
        ok: true,
        status: 200,
        blob: async () =>
          new w.Blob(["%PDF-test"], { type: "application/pdf" }),
      };
    if (options.method) {
      if (readOnly) return result({ message: "Somente leitura" }, 403);
      if (options.headers["If-Match"] !== `"${data.revision}"`)
        return result({ message: "Os dados mudaram; recarregue" }, 409);
      const payload = JSON.parse(options.body);
      if (path.startsWith("/api/v1/iterations")) {
        const id =
          options.method === "POST" ? "SPR-003" : path.split("/").at(-1);
        let iteration = data.iterations.find((value) => value.id === id);
        if (!iteration) {
          iteration = { id };
          data.iterations.push(iteration);
        }
        Object.assign(iteration, payload);
        data.revision = `revision-${++revision}`;
        updateSprintSummaries();
        return result({ iteration, revision: data.revision });
      }
      let item;
      if (options.method === "POST") {
        item = { ...payload, id: "SYS-006", version: 1, extensions: {} };
        data.work_items.push(item);
      } else if (options.method === "PATCH") {
        item = data.work_items.find((i) => path.endsWith(i.id));
        assert.equal(payload.expected_version, item.version);
        Object.assign(item, payload, { version: item.version + 1 });
      } else if (options.method === "PUT") data.views.push(payload);
      data.revision = `revision-${++revision}`;
      data.metrics.total = data.work_items.length;
      for (const status of data.project.statuses)
        data.metrics.by_status[status.id] = data.work_items.filter(
          (i) => i.status === status.id,
        ).length;
      updateSprintSummaries();
      return result({ item, revision: data.revision });
    }
    throw new Error("Unexpected request " + path);
  };
  function updateSprintSummaries() {
    const template = data.sprint_overview.unassigned;
    const build = (iteration) => {
      const items = data.work_items.filter(
        (item) => (item.iteration_id || null) === (iteration?.id || null),
      );
      const counts = Object.fromEntries(
        ["pending", "active", "done", "cancelled"].map((category) => [
          category,
          items.filter(
            (item) =>
              data.project.statuses.find((status) => status.id === item.status)
                .category === category,
          ).length,
        ]),
      );
      return {
        ...template,
        ...iteration,
        ...counts,
        phase: iteration
          ? data.sprint_overview.iterations.find((i) => i.id === iteration.id)
              ?.phase || "undated"
          : "unplanned",
        total: items.length,
        remaining: counts.pending + counts.active,
        blocked: 0,
        overdue: 0,
        open_estimates: {},
        progress:
          items.length - counts.cancelled
            ? (100 * counts.done) / (items.length - counts.cancelled)
            : null,
      };
    };
    data.sprint_overview.iterations = data.iterations.map((iteration) =>
      build(iteration),
    );
    data.sprint_overview.unassigned = build(null);
  }
  [
    "charts.js",
    "graph-layout.js",
    "dependency-view.js",
    "sprint-view.js",
    "app.js",
  ].forEach((name) =>
    vm.runInContext(
      fs.readFileSync("src/backloger/static/" + name, "utf8"),
      dom.getInternalVMContext(),
    ),
  );
  t.after(() => {
    w.eval("graph")?.destroy();
    dom.window.close();
  });
  const tick = () => new Promise((resolve) => setTimeout(resolve, 15));
  await tick();
  return {
    w,
    d,
    data,
    requests,
    downloads,
    syncSprints: updateSprintSummaries,
    tick,
    view: (name) => d.querySelector(`[data-view="${name}"]`).click(),
    field: (name) => d.querySelector(`[name="${name}"]`),
    submit: () =>
      d
        .querySelector("#item-form")
        .dispatchEvent(
          new w.Event("submit", { bubbles: true, cancelable: true }),
        ),
    change: (selector) =>
      d
        .querySelector(selector)
        .dispatchEvent(new w.Event("change", { bubbles: true })),
  };
}

test("dashboard charts reflect actual data and drill down into the Kanban", async (t) => {
  const h = await harness(t),
    { d } = h;
  assert.equal(d.querySelector("#dashboard-view").hidden, false);
  assert.equal(d.querySelectorAll("#completion-chart .donut-arc").length, 2);
  assert.match(
    d.querySelector("#completion-chart svg").getAttribute("aria-label"),
    /1 de 5/,
  );
  assert.equal(d.querySelectorAll("#priority-chart .priority-row").length, 4);
  assert.equal(d.querySelectorAll("#owners-chart .owner-row").length, 4);
  d.querySelector('.legend-row[aria-label^="Concluído"]').click();
  assert.equal(d.querySelector("#filter-status").value, "done");
  assert.equal(d.querySelectorAll("#board .card").length, 1);
  assert.match(d.querySelector("#board").textContent, /Contrato da API/);
  d.querySelector("#clear-filters").click();
  h.view("dashboard");
  d.querySelector('[data-priority="critical"]').click();
  assert.equal(d.querySelector("#filter-priority").value, "critical");
  assert.equal(d.querySelectorAll("#board .card").length, 1);
  d.querySelector("#clear-filters").click();
  h.view("dashboard");
  d.querySelector('.owner-row[aria-label^="backend"]').click();
  assert.equal(d.querySelectorAll("#board .card").length, 2);
});

test("burndown keeps missing dates open and shows the observed remainder", async (t) => {
  const h = await harness(t);
  assert.equal(h.d.querySelector("#burndown-remaining").textContent, "4");
  assert.equal(
    h.d.querySelectorAll("#burndown-chart .burndown-point").length,
    1,
  );
  assert.equal(h.d.querySelectorAll("#burndown-chart tbody tr").length, 14);
  assert.match(h.d.querySelector("#burndown-chart tbody tr").textContent, /—/);
  h.d.querySelector("#burndown-range").value = "30";
  h.change("#burndown-range");
  assert.equal(h.d.querySelectorAll("#burndown-chart tbody tr").length, 30);
  const points = h.data.burndown.scopes[0].points;
  points[points.length - 2].remaining = 5;
  points[points.length - 2].total = 5;
  h.data.revision = "burn-update";
  await h.w.refresh(true);
  assert.equal(
    h.d.querySelectorAll("#burndown-chart .burndown-line.actual").length,
    1,
  );
});

test("activity chart switches ranges and exposes accessible real counts", async (t) => {
  const { d } = await harness(t);
  assert.equal(d.querySelectorAll("#activity-chart .activity-day").length, 14);
  assert.match(
    d.querySelector("#activity-summary").textContent,
    /5criadas1conclusões/,
  );
  d.querySelector('[data-history-days="7"]').click();
  assert.equal(d.querySelectorAll("#activity-chart .activity-day").length, 7);
  d.querySelector('[data-history-days="30"]').click();
  assert.equal(d.querySelectorAll("#activity-chart .activity-day").length, 30);
  assert.equal(d.querySelectorAll("#activity-chart tbody tr").length, 30);
  assert.equal(d.querySelectorAll('#activity-chart [tabindex="0"]').length, 1);
  assert.equal(
    d.querySelectorAll("#activity-chart .activity-bar.completed").length,
    1,
  );
  const row = d.querySelector("#activity-chart .activity-day");
  row.focus();
  assert.equal(d.querySelector("#activity-chart .chart-tooltip").hidden, false);
});

test("empty historical data stays explicit and charts tolerate an empty filtered backlog", async (t) => {
  const h = await harness(t);
  h.data.history.days.forEach((day) => {
    day.created = 0;
    day.completed = 0;
  });
  h.data.revision = "without-history";
  await h.w.refresh(true);
  assert.match(
    h.d.querySelector(".activity-empty").textContent,
    /Nenhuma criação ou conclusão/,
  );
  const input = h.d.querySelector("#search");
  input.value = "no such work item";
  input.dispatchEvent(new h.w.Event("input"));
  assert.match(
    h.d.querySelector(".donut-caption").textContent,
    /sem atividades/,
  );
  assert.equal(h.d.querySelectorAll(".donut-arc").length, 0);
  assert.match(
    h.d.querySelector("#owners-chart").textContent,
    /aparecerão aqui/,
  );
});

test("graph focuses prerequisites and impacts, highlights critical path and preserves viewport", async (t) => {
  const h = await harness(t);
  h.view("graph");
  h.d.querySelector("#graph-scope").value = "project";
  h.change("#graph-scope");
  const graph = h.w.eval("graph");
  assert.ok(graph, h.d.querySelector("#notice").textContent);
  assert.equal(graph.nodes().length, 5);
  assert.equal(graph.edges().length, 3);
  h.d.querySelector("#graph-select").value = "SYS-001";
  h.change("#graph-select");
  assert.equal(graph.nodes(".prerequisite").length, 1);
  assert.equal(graph.nodes(".affected").length, 2);
  assert.match(
    h.d.querySelector("#graph-detail").textContent,
    /Pré-requisitos no projeto · 1/,
  );
  h.d.querySelector("#graph-critical").checked = true;
  h.change("#graph-critical");
  assert.equal(graph.nodes(".critical").length, 4);
  h.w.eval("graph.pan({x:47,y:29})");
  h.data.work_items[0].title = "Mudança externa";
  h.data.revision = "external";
  await h.w.refresh(true);
  assert.deepEqual({ ...graph.pan() }, { x: 47, y: 29 });
  assert.match(
    h.d.querySelector("#graph-detail").textContent,
    /Mudança externa/,
  );
  h.d.querySelector("#graph-reset").click();
  assert.equal(graph.nodes(".dimmed").length, 0);
  h.d.querySelector("#graph-layout").value = "circle";
  h.change("#graph-layout");
  assert.ok(Number.isFinite(graph.nodes()[0].position().x));
});

test("editor preserves concurrent edits and gives a success toast without interpreting HTML", async (t) => {
  const h = await harness(t);
  h.view("kanban");
  assert.equal(h.d.querySelectorAll("#board img").length, 0);
  h.d.querySelector("#new-item").click();
  h.field("title").value = "Nova entrega";
  h.submit();
  await h.tick();
  assert.equal(h.d.querySelector("#editor").open, false);
  assert.match(h.d.querySelector("#toast").textContent, /criada com sucesso/);
  h.d.querySelector('.card[data-id="SYS-001"]').click();
  h.field("title").value = "Minha edição";
  h.data.work_items[0].title = "Edição externa";
  h.data.revision = "external-unchanged-version";
  h.submit();
  await h.tick();
  assert.equal(h.field("title").value, "Minha edição");
  assert.equal(h.d.querySelector("#editor").open, true);
  assert.equal(h.d.querySelector("#editor-conflict").hidden, false);
  assert.equal(h.data.work_items[0].title, "Edição externa");
});

test("card history shows dated entries and submits a new progress note", async (t) => {
  const h = await harness(t);
  h.view("kanban");
  h.d.querySelector('.card[data-id="SYS-001"]').click();
  assert.equal(
    h.d.querySelectorAll("#item-history-list .history-entry").length,
    2,
  );
  assert.match(
    h.d.querySelector("#item-history-list").textContent,
    /Dependências/,
  );
  h.field("history_note").value = "Revisão concluída sem perder o contexto";
  h.submit();
  await h.tick();
  const request = h.requests.findLast(
    (request) => request.options.method === "PATCH",
  );
  assert.equal(
    JSON.parse(request.options.body).history_note,
    "Revisão concluída sem perder o contexto",
  );
});

test("document shows the generated Markdown, isolated preview and PDF download", async (t) => {
  const h = await harness(t);
  h.view("document");
  await h.tick();
  assert.equal(
    h.d.querySelector("#document-source").textContent,
    fixture.markdown,
  );
  assert.equal(
    h.d.querySelector("#document-frame").getAttribute("sandbox"),
    "",
  );
  assert.match(
    h.d.querySelector("#document-frame").src,
    /\/document\?revision=/,
  );
  assert.match(fixture.markdown, /Resumo executivo/);
  assert.match(fixture.markdown, /Detalhamento das atividades/);
  assert.match(fixture.markdown, /```mermaid/);
  const priorRequests = h.requests.filter(
    (request) => request.path === "/api/v1/document",
  ).length;
  h.d.querySelector("#refresh-document").click();
  await h.tick();
  assert.equal(
    h.requests.filter((request) => request.path === "/api/v1/document").length,
    priorRequests + 1,
  );
  assert.equal(h.d.querySelector("#refresh-document").disabled, false);
  h.d.querySelector('[data-document-mode="source"]').click();
  assert.equal(h.d.querySelector("#document-source-panel").hidden, false);
  assert.equal(h.d.querySelector("#document-preview").hidden, true);
  h.d.querySelector("#document-view [data-export-pdf]").click();
  await h.tick();
  assert.equal(h.downloads[0].name, "SYS-BACKLOG.pdf");
  assert.match(h.d.querySelector("#toast").textContent, /PDF pronto/);
});

test("read-only mode permits reading/export but offers no edit or drag mutation", async (t) => {
  const h = await harness(t, true);
  h.view("kanban");
  assert.equal(h.d.querySelector("#new-item").disabled, true);
  assert.ok(
    [...h.d.querySelectorAll("#board .card")].every((card) => !card.draggable),
  );
  h.d.querySelector("#board .card").click();
  assert.equal(h.d.querySelector("#save-item").hidden, true);
  assert.ok(
    [...h.d.querySelectorAll("#item-form input")].every(
      (input) => input.disabled,
    ),
  );
  h.d.querySelector("#close-editor").click();
  h.view("document");
  await h.tick();
  h.d.querySelector("#document-view [data-export-pdf]").click();
  await h.tick();
  assert.equal(h.downloads.length, 1);
  assert.ok(
    h.requests.every(
      (request) => !request.options.method || request.options.method === "GET",
    ),
  );
});

test("graph distinguishes structural chains from estimated critical paths and helps complete estimates", async (t) => {
  const h = await harness(t);
  for (const [scope, data] of Object.entries(h.data.analysis.critical_paths)) {
    data.method = "structure";
    data.duration = null;
    data.missing_estimates = h.data.work_items
      .filter((item) => scope === "project" || item.status !== "done")
      .map((item) => item.id);
    data.reason = `${data.missing_estimates.length} atividades sem estimativa neste escopo.`;
  }
  h.data.work_items.forEach((item) => (item.estimate = null));
  h.data.revision = "missing-estimates";
  await h.w.refresh(true);
  h.view("graph");
  const graph = h.w.eval("graph");
  assert.equal(graph.nodes().length, 4);
  assert.equal(graph.getElementById("SYS-002").length, 0);
  assert.match(
    h.d.querySelector("#graph-critical-label").textContent,
    /Cadeia de precedência/,
  );
  assert.equal(h.d.querySelector("#graph-critical").disabled, false);
  h.d.querySelector("#graph-show-critical").click();
  assert.equal(graph.nodes(".critical").length, 3);
  assert.match(
    h.d.querySelector("#critical-path").textContent,
    /Não é uma previsão de duração/,
  );
  h.d.querySelector("#graph-missing").click();
  assert.equal(h.d.querySelector("#graph-mode").value, "missing");
  assert.equal(graph.nodes().length, 4);
  h.data.analysis.critical_paths.remaining.missing_estimates = ["SYS-003"];
  h.data.revision = "one-missing-estimate";
  await h.w.refresh(true);
  assert.equal(graph.nodes().length, 1);
  assert.equal(graph.nodes()[0].id(), "SYS-003");
  h.d.querySelector("#graph-select").value = "SYS-001";
  h.change("#graph-select");
  assert.equal(h.d.querySelector("#graph-mode").value, "neighbors");
  assert.equal(graph.getElementById("SYS-001").length, 1);
});

test("graph fullscreen falls back to an expanded accessible panel and Escape restores focus", async (t) => {
  const h = await harness(t);
  h.view("graph");
  const panel = h.d.querySelector("#graph-panel"),
    button = h.d.querySelector("#graph-fullscreen");
  panel.requestFullscreen = async () => {
    throw new Error("Fullscreen unavailable");
  };
  button.focus();
  button.click();
  await h.tick();
  assert.equal(panel.classList.contains("graph-expanded"), true);
  assert.equal(panel.getAttribute("aria-modal"), "true");
  assert.equal(button.getAttribute("aria-pressed"), "true");
  h.d.dispatchEvent(
    new h.w.KeyboardEvent("keydown", { key: "Escape", bubbles: true }),
  );
  await h.tick();
  assert.equal(panel.classList.contains("graph-expanded"), false);
  assert.equal(h.d.body.classList.contains("graph-is-expanded"), false);
  assert.equal(h.d.activeElement, button);
  h.d.querySelector("#graph-select").value = "SYS-001";
  h.change("#graph-select");
  button.click();
  await h.tick();
  h.d.querySelector("#graph-detail button").click();
  await h.tick();
  assert.equal(panel.classList.contains("graph-expanded"), false);
  assert.equal(h.d.querySelector("#editor").open, true);
});

test("graph exports the visible geometry in read-only mode without changing cards", async (t) => {
  const h = await harness(t, true);
  h.view("graph");
  h.d.querySelector("#graph-critical").checked = true;
  h.change("#graph-critical");
  const original = structuredClone(h.data.work_items);
  h.d.querySelector("#graph-export-pdf").click();
  await h.tick();
  const request = h.requests.findLast(
    (request) => request.path === "/api/v1/graph/export/pdf",
  );
  assert.equal(request.options.headers["If-Match"], `"${h.data.revision}"`);
  assert.equal(request.options.headers["X-Backloger-Token"], "test-token");
  const payload = JSON.parse(request.options.body);
  assert.equal(Object.keys(payload.positions).length, 4);
  assert.equal(payload.scope, "remaining");
  assert.equal(payload.highlight_critical, true);
  assert.equal(payload.positions["SYS-001"].width, 200);
  assert.ok(Number.isFinite(payload.positions["SYS-001"].x));
  assert.equal(h.downloads[0].name, "SYS-DEPENDENCIAS.pdf");
  h.d.querySelector("#graph-export-svg").click();
  await h.tick();
  assert.equal(h.downloads[1].name, "SYS-DEPENDENCIAS.svg");
  assert.deepEqual(h.data.work_items, original);
});

test("large graphs start with a bounded neighborhood and can locate nodes outside the initial crop", async (t) => {
  const h = await harness(t);
  const template = h.data.work_items[4];
  for (let i = 6; i <= 205; i++) {
    const id = `SYS-${String(i).padStart(3, "0")}`;
    h.data.work_items.push({
      ...structuredClone(template),
      id,
      title: `Entrega ${i}`,
      status: "todo",
      dependencies: [{ target_id: "SYS-001", relation: "blocked_by" }],
    });
    h.data.analysis.edges.push({ source: "SYS-001", target: id });
  }
  h.data.analysis.bottlenecks = [{ id: "SYS-001", affected: 202 }];
  h.data.revision = "large-project";
  await h.w.refresh(true);
  h.view("graph");
  const graph = h.w.eval("graph");
  assert.ok(graph.nodes().length <= 180);
  assert.match(
    h.d.querySelector("#graph-context-note").textContent,
    /limitado a 180/,
  );
  const input = h.d.querySelector("#graph-search");
  input.value = "SYS-205";
  input.dispatchEvent(new h.w.Event("input"));
  input.dispatchEvent(
    new h.w.KeyboardEvent("keydown", { key: "Enter", bubbles: true }),
  );
  assert.equal(graph.getElementById("SYS-205").length, 1);
  assert.equal(graph.nodes().length, 2);
  h.d.querySelector("#graph-mode").value = "overview";
  h.change("#graph-mode");
  assert.equal(graph.nodes().length, 204);
  assert.ok(
    graph
      .nodes()
      .every(
        (node) =>
          Number.isFinite(node.position().x) &&
          Number.isFinite(node.position().y),
      ),
  );
});

test("hierarchical layout follows longest precedence ranks even when shortcuts exist", async (t) => {
  const h = await harness(t);
  const positions = h.w.eval(
    'BacklogGraphLayout.positions(["A","B","C","D","E"], [{source:"A",target:"D"},{source:"A",target:"B"},{source:"B",target:"C"},{source:"C",target:"D"}], "LR")',
  );
  assert.ok(positions.get("D").x > positions.get("C").x);
  assert.ok(positions.get("C").x > positions.get("B").x);
  assert.ok(positions.get("B").x > positions.get("A").x);
  assert.notDeepEqual(positions.get("E"), positions.get("A"));
});

test("sprint view selects current period and keeps complete totals while filtering cards", async (t) => {
  const h = await harness(t, false, true);
  h.d.querySelector("#filter-iteration").value = "SPR-002";
  h.change("#filter-iteration");
  h.view("sprints");
  assert.equal(h.d.querySelector("#sprint-select").value, "SPR-001");
  assert.equal(h.d.querySelectorAll("#sprint-board .card").length, 3);
  assert.match(
    h.d.querySelector("#sprint-progress-label").textContent,
    /33,3%.*1 de 3/,
  );
  assert.equal(h.d.querySelector("#metrics").hidden, true);
  assert.equal(h.d.querySelector("#filter-iteration").hidden, true);
  h.d.querySelector("#filter-owner").value = "backend";
  h.change("#filter-owner");
  assert.equal(h.d.querySelectorAll("#sprint-board .card").length, 2);
  assert.match(
    h.d.querySelector("#sprint-progress-label").textContent,
    /1 de 3/,
  );
  assert.match(
    h.d.querySelector("#sprint-scope-note").textContent,
    /3 atividades.*2 com os filtros/,
  );
  h.d.querySelector("#sprint-select").value = "SPR-002";
  h.change("#sprint-select");
  assert.match(
    h.d.querySelector("#sprint-progress-label").textContent,
    /Sem atividades aplicáveis/,
  );
  assert.equal(h.d.querySelectorAll("#sprint-board .card").length, 0);
});

test("sprint creation validates dates and renders names as text", async (t) => {
  const h = await harness(t);
  h.view("sprints");
  assert.equal(h.d.querySelector("#sprint-onboarding").hidden, false);
  h.d.querySelector("#sprint-create").click();
  const form = h.d.querySelector("#sprint-form");
  form.elements.namedItem("name").value = 'Sprint <img src=x onerror="bad()">';
  form.elements.namedItem("start_date").value = "2026-11-20";
  form.elements.namedItem("due_date").value = "2026-11-01";
  form.dispatchEvent(
    new h.w.Event("submit", { bubbles: true, cancelable: true }),
  );
  assert.match(
    h.d.querySelector("#sprint-editor-error").textContent,
    /posterior ao início/,
  );
  assert.equal(
    h.requests.some((r) => r.path === "/api/v1/iterations"),
    false,
  );
  form.elements.namedItem("due_date").value = "2026-11-30";
  form.dispatchEvent(
    new h.w.Event("submit", { bubbles: true, cancelable: true }),
  );
  await h.tick();
  assert.equal(h.d.querySelector("#sprint-editor").open, false);
  assert.equal(h.d.querySelector("#sprint-select").value, "SPR-003");
  assert.match(h.d.querySelector("#sprint-name").textContent, /Sprint <img/);
  assert.equal(h.d.querySelector("#sprint-name img"), null);
});

test("sprint editor preserves input on a concurrent project edit", async (t) => {
  const h = await harness(t, false, true);
  h.view("sprints");
  h.d.querySelector("#sprint-edit").click();
  const form = h.d.querySelector("#sprint-form");
  form.elements.namedItem("name").value = "Minha revisão ainda aberta";
  h.data.iterations[0].name = "Mudança externa";
  h.data.revision = "sprint-changed-externally";
  h.syncSprints();
  await h.w.refresh(true);
  assert.match(
    h.d.querySelector("#sprint-editor-error").textContent,
    /projeto mudou/,
  );
  form.dispatchEvent(
    new h.w.Event("submit", { bubbles: true, cancelable: true }),
  );
  await h.tick();
  assert.equal(h.d.querySelector("#sprint-editor").open, true);
  assert.equal(
    form.elements.namedItem("name").value,
    "Minha revisão ainda aberta",
  );
  assert.equal(h.data.iterations[0].name, "Mudança externa");
});

test("sprint planning assigns an existing card and new cards inherit the selected sprint", async (t) => {
  const h = await harness(t, false, true);
  h.view("sprints");
  h.d.querySelector("#sprint-add").click();
  const search = h.d.querySelector("#sprint-backlog-search");
  search.value = "SYS-004";
  search.dispatchEvent(new h.w.Event("input"));
  h.d.querySelector('[aria-label="Adicionar SYS-004 à sprint"]').click();
  await h.tick();
  assert.equal(
    h.data.work_items.find((i) => i.id === "SYS-004").iteration_id,
    "SPR-001",
  );
  assert.equal(h.d.querySelectorAll("#sprint-board .card").length, 4);
  assert.match(
    h.d.querySelector("#sprint-progress-label").textContent,
    /25%.*1 de 4/,
  );
  h.d.querySelector("#sprint-planner-close").click();
  h.d.querySelector("#sprint-new").click();
  assert.equal(h.field("iteration_id").value, "SPR-001");
});

test("read-only sprint view exposes cards but disables planning actions", async (t) => {
  const h = await harness(t, true, true);
  h.view("sprints");
  for (const id of ["sprint-create", "sprint-edit", "sprint-add", "sprint-new"])
    assert.equal(h.d.getElementById(id).disabled, true);
  h.d.querySelector("#sprint-board .card").click();
  assert.equal(h.d.querySelector("#editor").open, true);
  assert.equal(h.field("iteration_id").disabled, true);
  assert.ok(h.requests.every((r) => !r.options.method));
});

test("external sprint assignment updates the view and lets users inspect the other sprint", async (t) => {
  const h = await harness(t, false, true);
  h.view("sprints");
  h.data.work_items.find((i) => i.id === "SYS-003").iteration_id = "SPR-002";
  h.data.revision = "external-sprint-assignment";
  h.syncSprints();
  await h.w.refresh(true);
  assert.equal(h.d.querySelectorAll("#sprint-board .card").length, 2);
  h.d.querySelector("#sprint-select").value = "SPR-002";
  h.change("#sprint-select");
  assert.equal(h.d.querySelectorAll("#sprint-board .card").length, 1);
  assert.equal(h.d.querySelector("#sprint-board .card").dataset.id, "SYS-003");
});

test("large sprint lists paginate while search can find cards beyond the initial page", async (t) => {
  const h = await harness(t, false, true);
  for (let n = 6; n <= 205; n++)
    h.data.work_items.push({
      ...structuredClone(h.data.work_items[0]),
      id: `SYS-${String(n).padStart(3, "0")}`,
      title: `Entrega ${n}`,
      iteration_id: "SPR-001",
    });
  h.syncSprints();
  h.data.revision = "large-sprint";
  await h.w.refresh(true);
  h.view("sprints");
  assert.equal(
    h.d.querySelectorAll('#sprint-board [data-category="pending"] .card')
      .length,
    24,
  );
  h.d
    .querySelector('#sprint-board [data-category="pending"] .sprint-more')
    .click();
  assert.equal(
    h.d.querySelectorAll('#sprint-board [data-category="pending"] .card')
      .length,
    48,
  );
  h.d.querySelector("#search").value = "SYS-205";
  h.d.querySelector("#search").dispatchEvent(new h.w.Event("input"));
  assert.equal(h.d.querySelectorAll("#sprint-board .card").length, 1);
  assert.equal(h.d.querySelector("#sprint-board .card").dataset.id, "SYS-205");
  assert.match(
    h.d.querySelector("#sprint-scope-note").textContent,
    /203 atividades/,
  );
});
