"use strict";
(function (global) {
  const UNITS = { hours: "horas", days: "dias", points: "pontos" };
  const LOCAL_LIMIT = 180;
  function create(onOpen, onNotice = () => {}) {
    const $ = (selector) => document.querySelector(selector);
    const node = (tag, className, text) => {
      const element = document.createElement(tag);
      if (className) element.className = className;
      if (text !== undefined) element.textContent = text;
      return element;
    };
    const fold = (value) =>
      String(value)
        .normalize("NFD")
        .replace(/\p{Diacritic}/gu, "")
        .toLowerCase();
    let cy = null,
      state = null,
      filtered = [],
      selected = null,
      signature = "",
      expanded = false;
    let forward = new Map(),
      reverse = new Map(),
      byId = new Map(),
      source = [],
      exportBusy = false;
    let previousFocus = null,
      previousViewport = null;
    const scope = () => $("#graph-scope").value;
    const schedule = () =>
      state?.analysis.critical_paths?.[scope()] || {
        ...state?.analysis.critical_path,
        method:
          state?.analysis.critical_path.duration === null
            ? "structure"
            : "estimate",
        nodes: state?.analysis.critical_path.path || [],
        edges: [],
      };
    function walk(map, id) {
      const seen = new Set(),
        queue = [id];
      for (let i = 0; i < queue.length; i++)
        for (const next of map.get(queue[i]) || []) {
          if (!seen.has(next) && next !== id) {
            seen.add(next);
            queue.push(next);
          }
        }
      return [...seen].sort();
    }
    function critical() {
      if (!cy || !state) return;
      cy.elements().removeClass("critical");
      if (!$("#graph-critical").checked) return;
      const data = schedule();
      (data.nodes || data.path).forEach((id) =>
        cy.getElementById(id).addClass("critical"),
      );
      const edges = data.edges?.length
        ? data.edges
        : data.path
            .slice(1)
            .map((id, i) => ({ source: data.path[i], target: id }));
      edges.forEach((edge) =>
        cy
          .getElementById(`edge:${edge.source}:${edge.target}`)
          .addClass("critical"),
      );
    }
    function detail() {
      cy?.elements()
        .removeClass("dimmed prerequisite affected focus-line")
        .unselect();
      const item = byId.get(selected);
      if (!item) {
        $("#graph-detail").replaceChildren(
          node(
            "p",
            "graph-prompt",
            "Selecione uma atividade para explorar seus pré-requisitos e impactos.",
          ),
        );
        return;
      }
      const before = walk(reverse, selected),
        after = walk(forward, selected);
      const prerequisites = new Set(before),
        affected = new Set(after),
        related = new Set([selected, ...before, ...after]);
      cy.nodes().forEach((n) => {
        if (!related.has(n.id())) n.addClass("dimmed");
        if (prerequisites.has(n.id())) n.addClass("prerequisite");
        if (affected.has(n.id())) n.addClass("affected");
      });
      cy.edges().forEach((edge) =>
        edge.addClass(
          related.has(edge.source().id()) && related.has(edge.target().id())
            ? "focus-line"
            : "dimmed",
        ),
      );
      cy.getElementById(selected).select();
      const heading = node("div", "graph-item-heading"),
        title = node("div", "");
      title.append(
        node("span", "eyebrow", selected),
        node("h3", "", item.title),
      );
      const open = node("button", "secondary", "Abrir atividade ↗");
      open.addEventListener("click", async () => {
        if (expanded) await toggleFullscreen();
        onOpen(item);
      });
      heading.append(title, open);
      const timing = schedule().timings?.[selected],
        summary = node("p", "metric-note");
      summary.textContent =
        timing && schedule().method === "estimate"
          ? `Início técnico mais cedo: ${timing.start.toLocaleString("pt-BR")} · Folga: ${timing.slack.toLocaleString("pt-BR")} ${UNITS[schedule().unit]}. Não são datas de calendário.`
          : "A análise estrutural não atribui duração ou datas à atividade.";
      const columns = node("div", "graph-impact-columns");
      for (const [label, ids] of [
        ["Pré-requisitos no projeto", before],
        ["Atividades potencialmente afetadas", after],
      ]) {
        const group = node("section", "graph-impact");
        group.append(node("h4", "", `${label} · ${ids.length}`));
        if (!ids.length)
          group.append(node("p", "metric-note", "Nenhuma atividade."));
        const list = node("div", "impact-list");
        let shown = 0;
        const more = node("button", "text-button", "Mostrar mais");
        const append = () => {
          for (const id of ids.slice(shown, shown + 30)) {
            const button = node("button", "impact-item");
            button.append(
              node("span", "", id),
              node("span", "", byId.get(id)?.title || id),
            );
            button.addEventListener("click", () => focus(id));
            list.append(button);
          }
          shown = Math.min(ids.length, shown + 30);
          more.hidden = shown >= ids.length;
          more.textContent = `Mostrar mais (${ids.length - shown} restantes)`;
        };
        more.addEventListener("click", append);
        append();
        group.append(list, more);
        columns.append(group);
      }
      $("#graph-detail").replaceChildren(heading, summary, columns);
    }
    function selectOptions() {
      const search = fold($("#graph-search").value);
      const matches = source.filter((item) =>
        fold(`${item.id} ${item.title}`).includes(search),
      );
      const choices = matches.slice(0, 150);
      if (
        selected &&
        !choices.some((item) => item.id === selected) &&
        byId.has(selected)
      )
        choices.unshift(byId.get(selected));
      $("#graph-select").replaceChildren(
        new Option(
          matches.length > 150
            ? `${matches.length} resultados; refine a busca`
            : "Selecione uma atividade",
          "",
        ),
        ...choices.map(
          (item) => new Option(`${item.id} · ${item.title}`, item.id),
        ),
      );
      $("#graph-select").value = selected || "";
      return matches;
    }
    function visible() {
      const sourceIds = new Set(source.map((item) => item.id));
      const seeds = filtered.filter((item) => sourceIds.has(item.id));
      const seedIds = new Set(seeds.map((item) => item.id));
      const mode = $("#graph-mode").value;
      const local =
        ["neighbors", "prerequisites", "impacts"].includes(mode) ||
        (mode === "auto" && seeds.length > 120);
      let ids = new Set(seeds.map((item) => item.id)),
        truncated = false;
      if (mode === "critical")
        ids = new Set(schedule().nodes || schedule().path);
      else if (mode === "missing")
        ids = new Set(schedule().missing_estimates || []);
      else if (local && (seeds.length || selected)) {
        const anchor = sourceIds.has(selected)
          ? selected
          : state.analysis.bottlenecks.find((row) => ids.has(row.id))?.id ||
            seeds[0].id;
        let related =
          mode === "prerequisites"
            ? walk(reverse, anchor)
            : mode === "impacts"
              ? walk(forward, anchor)
              : [
                  ...(reverse.get(anchor) || []),
                  ...(forward.get(anchor) || []),
                ];
        related = related.filter((id) => sourceIds.has(id));
        truncated = related.length >= LOCAL_LIMIT;
        ids = new Set([anchor, ...related.slice(0, LOCAL_LIMIT - 1)]);
      }
      const items = source.filter((item) => ids.has(item.id));
      const added = items.filter((item) => !seedIds.has(item.id)).length;
      $("#graph-context-note").textContent =
        local && (seeds.length || selected)
          ? `Visão local: ${items.length} de ${source.length} atividades. ${truncated ? "Recorte limitado a 180 nós. " : ""}Use a busca para trocar a atividade ou Panorama completo para ampliar o escopo.${added ? ` ${added} itens de contexto estão fora dos filtros gerais.` : ""}`
          : mode === "critical"
            ? "Rotas calculadas no escopo inteiro; os filtros gerais não cortam o caminho."
            : mode === "missing"
              ? "Atividades sem estimativa no escopo inteiro. Abra uma atividade para completar a estimativa; os filtros gerais não cortam esta lista."
              : "Arraste para mover, use zoom e selecione uma atividade. A busca também encontra itens fora dos filtros gerais.";
      return items;
    }
    function layout() {
      if (!cy) return;
      if ($("#graph-layout").value === "breadthfirst") {
        const positions = global.BacklogGraphLayout.positions(
          cy.nodes().map((n) => n.id()),
          cy
            .edges()
            .map((e) => ({ source: e.source().id(), target: e.target().id() })),
          $("#graph-direction").value,
        );
        cy.nodes().positions((n) => positions.get(n.id()));
        cy.fit(undefined, 45);
      } else
        cy.layout({
          name: $("#graph-layout").value,
          padding: 45,
          animate: false,
          avoidOverlap: true,
        }).run();
    }
    function render() {
      if (!state) return;
      const categories = new Map(
        state.project.statuses.map((status) => [status.id, status.category]),
      );
      source = state.work_items.filter(
        (item) =>
          scope() === "project" ||
          !["done", "cancelled"].includes(categories.get(item.status)),
      );
      if (selected && !source.some((item) => item.id === selected))
        selected = null;
      const items = visible(),
        ids = new Set(items.map((item) => item.id));
      const edges = state.analysis.edges.filter(
        (edge) => ids.has(edge.source) && ids.has(edge.target),
      );
      const compact =
        $("#graph-labels").value === "ids" ||
        ($("#graph-labels").value === "auto" && items.length > 80);
      const elements = [
        ...items.map((item) => ({
          data: {
            id: item.id,
            label: compact ? item.id : `${item.id}\n${item.title.slice(0, 64)}`,
            category: categories.get(item.status),
            compact,
            blocked: Boolean(state.analysis.blockers[item.id]?.length),
          },
        })),
        ...edges.map((edge) => ({
          data: { id: `edge:${edge.source}:${edge.target}`, ...edge },
        })),
      ];
      const viewport = cy ? { zoom: cy.zoom(), pan: { ...cy.pan() } } : null;
      const next =
        `${scope()}|${$("#graph-mode").value}|${compact}|` +
        elements
          .map((e) => e.data.id)
          .sort()
          .join("|");
      if (!cy) {
        cy = global.cytoscape({
          container: $("#graph-canvas"),
          elements,
          minZoom: 0.015,
          maxZoom: 4,
          pixelRatio: 1,
          hideEdgesOnViewport: true,
          layout: { name: "preset" },
          style: [
            {
              selector: "node",
              style: {
                label: "data(label)",
                shape: "roundrectangle",
                width: 200,
                height: 72,
                "font-family": "system-ui, sans-serif",
                "font-size": 11,
                "text-valign": "center",
                "text-wrap": "wrap",
                "text-max-width": 180,
                "min-zoomed-font-size": 6,
                "background-color": "#e7eddf",
                color: "#40533a",
                "border-width": 1.5,
                "border-color": "#bbcbb0",
                "overlay-opacity": 0,
              },
            },
            {
              selector: "node[?compact]",
              style: { width: 140, height: 42, "font-weight": 600 },
            },
            {
              selector: 'node[category = "active"]',
              style: {
                "background-color": "#fbefd9",
                "border-color": "#d4a565",
                color: "#856025",
              },
            },
            {
              selector: 'node[category = "done"]',
              style: {
                "background-color": "#e1eee4",
                "border-color": "#7eaa8b",
                color: "#3e6a4b",
              },
            },
            {
              selector: 'node[category = "cancelled"]',
              style: {
                "background-color": "#f0f1ef",
                "border-color": "#cbd0c8",
                color: "#91988c",
              },
            },
            { selector: "node[?blocked]", style: { "border-style": "dashed" } },
            {
              selector: "edge",
              style: {
                width: 1.6,
                "target-arrow-shape": "triangle",
                "line-color": "#bdc9b5",
                "target-arrow-color": "#bdc9b5",
                "curve-style": "bezier",
                "arrow-scale": 0.9,
                "overlay-opacity": 0,
              },
            },
            {
              selector: "node.prerequisite",
              style: { "border-color": "#6c9ba3", "border-width": 3 },
            },
            {
              selector: "node.affected",
              style: { "border-color": "#d29568", "border-width": 3 },
            },
            {
              selector: "edge.focus-line",
              style: {
                "line-color": "#98ab89",
                "target-arrow-color": "#98ab89",
                width: 2.5,
              },
            },
            {
              selector: "node.critical",
              style: { "border-color": "#c64d25", "border-width": 3 },
            },
            {
              selector: "edge.critical",
              style: {
                "line-color": "#c64d25",
                "target-arrow-color": "#c64d25",
                width: 3,
              },
            },
            {
              selector: "node:selected",
              style: {
                "background-color": "#263f32",
                color: "#fff",
                "border-color": "#263f32",
                "border-style": "solid",
                "border-width": 3,
              },
            },
            { selector: ".dimmed", style: { opacity: 0.17 } },
          ],
        });
        cy.on("tap", "node", (event) => focus(event.target.id()));
        cy.on("tap", (event) => {
          if (event.target === cy) reset();
        });
      } else {
        cy.json({ elements });
        cy.resize();
      }
      if (signature !== next) {
        signature = next;
        layout();
      } else if (viewport) cy.viewport(viewport);
      selectOptions();
      $("#graph-empty").hidden = Boolean(items.length);
      if (!exportBusy)
        [$("#graph-export-svg"), $("#graph-export-pdf")].forEach(
          (button) => (button.disabled = !items.length),
        );
      $("#graph-stats").textContent =
        `${items.length} / ${source.length} atividades · ${edges.length} relações`;
      const path = schedule();
      $("#graph-missing").hidden = !path.missing_estimates?.length;
      $("#graph-missing").textContent =
        `Completar estimativas (${path.missing_estimates?.length || 0})`;
      $("#graph-critical").disabled = !path.path.length;
      $("#graph-show-critical").disabled = !path.path.length;
      $("#graph-critical-label").textContent =
        path.method === "estimate"
          ? "Caminho crítico"
          : "Cadeia de precedência";
      $("#critical-path").textContent =
        path.method === "estimate"
          ? `${path.duration.toLocaleString("pt-BR")} ${UNITS[path.unit]} · ${path.nodes.length} atividades em rotas sem folga. Estimativa técnica, sem previsão de calendário.`
          : path.path.length
            ? `${path.length || path.path.length} atividades na maior cadeia. ${path.reason || ""} Não é uma previsão de duração.`
            : path.reason || "Nenhuma atividade neste escopo.";
      detail();
      critical();
      return cy;
    }
    function focus(id) {
      if (!byId.has(id)) return;
      const item = byId.get(id);
      const status = state.project.statuses.find(
        (value) => value.id === item.status,
      );
      if (
        scope() === "remaining" &&
        ["done", "cancelled"].includes(status?.category)
      )
        $("#graph-scope").value = "project";
      if (
        !filtered.some((value) => value.id === id) ||
        ($("#graph-mode").value === "critical" &&
          !(schedule().nodes || schedule().path).includes(id)) ||
        ($("#graph-mode").value === "missing" &&
          !(schedule().missing_estimates || []).includes(id))
      )
        $("#graph-mode").value = "neighbors";
      selected = id;
      render();
      const target = cy.getElementById(id);
      if (target.length) cy.center(target);
    }
    function reset() {
      selected = null;
      $("#graph-search").value = "";
      render();
    }
    function update(next, items) {
      state = next;
      filtered = items;
      byId = new Map(state.work_items.map((item) => [item.id, item]));
      forward = new Map();
      reverse = new Map();
      state.analysis.edges.forEach(({ source: a, target: b }) => {
        if (!forward.has(a)) forward.set(a, []);
        if (!reverse.has(b)) reverse.set(b, []);
        forward.get(a).push(b);
        reverse.get(b).push(a);
      });
      if (typeof global.cytoscape !== "function")
        throw new Error("Não foi possível carregar o visualizador de grafos");
      return render();
    }
    function resize() {
      const run = () => {
        cy?.resize();
        if (expanded) cy?.fit(undefined, 45);
        else if (previousViewport) cy?.viewport(previousViewport);
      };
      (global.requestAnimationFrame || ((callback) => setTimeout(callback, 0)))(
        run,
      );
    }
    function setExpanded(value) {
      expanded = value;
      $("#graph-panel").classList.toggle("graph-expanded", value);
      document.body.classList.toggle("graph-is-expanded", value);
      $("#graph-fullscreen").setAttribute("aria-pressed", String(value));
      $("#graph-fullscreen").textContent = value
        ? "↙ Sair da tela inteira"
        : "⛶ Tela inteira";
      if (value) {
        $("#graph-panel").setAttribute("role", "dialog");
        $("#graph-panel").setAttribute("aria-modal", "true");
      } else {
        $("#graph-panel").removeAttribute("role");
        $("#graph-panel").removeAttribute("aria-modal");
        previousFocus?.focus();
      }
      resize();
    }
    async function toggleFullscreen() {
      if (expanded) {
        if (document.fullscreenElement) {
          try {
            await document.exitFullscreen();
          } catch (_) {
            setExpanded(false);
          }
        } else setExpanded(false);
        return;
      }
      previousFocus = document.activeElement;
      previousViewport = cy ? { zoom: cy.zoom(), pan: { ...cy.pan() } } : null;
      setExpanded(true);
      try {
        await $("#graph-panel").requestFullscreen?.();
      } catch (_) {
        /* CSS expansion remains available. */
      }
      $("#graph-fullscreen").focus();
    }
    async function exportGraph(format) {
      if (exportBusy || !cy?.nodes().length) return;
      exportBusy = true;
      const buttons = [$("#graph-export-pdf"), $("#graph-export-svg")];
      buttons.forEach((button) => (button.disabled = true));
      const trigger = $(`#graph-export-${format}`),
        original = trigger.textContent;
      trigger.textContent = "Gerando…";
      try {
        const positions = {};
        cy.nodes().forEach((n) => {
          const point = n.position();
          positions[n.id()] = {
            x: Math.round(point.x * 100) / 100,
            y: Math.round(point.y * 100) / 100,
            width: Math.round(n.width()),
            height: Math.round(n.height()),
          };
        });
        const response = await fetch(`/api/v1/graph/export/${format}`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Backloger-Token": $('meta[name="backloger-token"]').content,
            "If-Match": `"${state.revision}"`,
          },
          body: JSON.stringify({
            positions,
            scope: scope(),
            highlight_critical: $("#graph-critical").checked,
          }),
        });
        if (!response.ok) {
          const error = await response.json();
          throw new Error(
            error.message || error.detail || "Falha ao exportar o grafo",
          );
        }
        const url = URL.createObjectURL(await response.blob()),
          link = node("a", "");
        link.href = url;
        link.download = `${state.project.key}-DEPENDENCIAS.${format}`;
        document.body.append(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 30000);
        onNotice(`Grafo ${format.toUpperCase()} pronto para download.`);
      } catch (error) {
        onNotice(error.message);
      } finally {
        exportBusy = false;
        trigger.textContent = original;
        buttons.forEach((button) => (button.disabled = !cy.nodes().length));
      }
    }
    ["#graph-mode", "#graph-scope", "#graph-labels"].forEach((id) =>
      $(id).addEventListener("change", render),
    );
    ["#graph-layout", "#graph-direction"].forEach((id) =>
      $(id).addEventListener("change", layout),
    );
    $("#graph-select").addEventListener("change", (event) =>
      event.target.value ? focus(event.target.value) : reset(),
    );
    $("#graph-search").addEventListener("input", selectOptions);
    $("#graph-search").addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        const matches = selectOptions();
        if (matches.length) focus(matches[0].id);
      }
    });
    $("#graph-critical").addEventListener("change", critical);
    $("#graph-missing").addEventListener("click", () => {
      $("#graph-mode").value = "missing";
      render();
    });
    $("#graph-show-critical").addEventListener("click", () => {
      $("#graph-critical").checked = true;
      $("#graph-mode").value = "critical";
      render();
    });
    $("#graph-reset").addEventListener("click", reset);
    $("#graph-fit").addEventListener("click", () => cy?.fit(undefined, 45));
    $("#graph-fullscreen").addEventListener("click", toggleFullscreen);
    document.addEventListener("fullscreenchange", () => {
      if (!document.fullscreenElement) setExpanded(false);
    });
    document.addEventListener("keydown", (event) => {
      if (!expanded || document.querySelector("dialog[open]")) return;
      if (event.key === "Escape" && !document.fullscreenElement) {
        event.preventDefault();
        setExpanded(false);
      }
      if (event.key === "Tab") {
        const options = [
          ...$("#graph-panel").querySelectorAll(
            "button:not([disabled]), input, select",
          ),
        ].filter((element) => !element.hidden);
        const first = options[0],
          last = options[options.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    });
    $("#graph-export-pdf").addEventListener("click", () => exportGraph("pdf"));
    $("#graph-export-svg").addEventListener("click", () => exportGraph("svg"));
    for (const [id, factor] of [
      ["#graph-zoom-in", 1.25],
      ["#graph-zoom-out", 0.8],
    ])
      $(id).addEventListener("click", () => {
        if (cy)
          cy.zoom({
            level: Math.max(0.015, Math.min(4, cy.zoom() * factor)),
            renderedPosition: {
              x: $("#graph-canvas").clientWidth / 2,
              y: $("#graph-canvas").clientHeight / 2,
            },
          });
      });
    return { update };
  }
  global.BacklogGraph = { create };
})(globalThis);
