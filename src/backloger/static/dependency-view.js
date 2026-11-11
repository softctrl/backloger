"use strict";
(function (global) {
  function create(onOpen) {
    const $ = (selector) => document.querySelector(selector);
    const node = (tag, className, text) => {
      const element = document.createElement(tag);
      if (className) element.className = className;
      if (text !== undefined) element.textContent = text;
      return element;
    };
    const reduced = () =>
      global.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    let cy = null,
      state = null,
      selected = null,
      signature = "";
    let forward = new Map(),
      reverse = new Map();
    function walk(map, id) {
      const seen = new Set(),
        queue = [id];
      for (let index = 0; index < queue.length; index++)
        for (const next of map.get(queue[index]) || [])
          if (!seen.has(next) && next !== id) {
            seen.add(next);
            queue.push(next);
          }
      return [...seen].sort();
    }
    function critical() {
      if (!cy || !state) return;
      cy.elements().removeClass("critical");
      if (!$("#graph-critical").checked) return;
      const path = state.analysis.critical_path.path;
      path.forEach((id) => cy.getElementById(id).addClass("critical"));
      for (let i = 1; i < path.length; i++)
        cy.getElementById(`edge:${path[i - 1]}:${path[i]}`).addClass(
          "critical",
        );
    }
    function reset() {
      selected = null;
      if (!cy) return;
      cy.elements()
        .removeClass("dimmed prerequisite affected focus-line")
        .unselect();
      $("#graph-select").value = "";
      $("#graph-detail").replaceChildren(
        node(
          "p",
          "graph-prompt",
          "Selecione uma atividade no grafo ou na lista para explorar seus pré-requisitos e impactos.",
        ),
      );
    }
    function focus(id) {
      if (!cy || !state) return;
      const item = state.work_items.find((i) => i.id === id);
      if (!item) return;
      selected = id;
      const before = walk(reverse, id),
        after = walk(forward, id),
        related = new Set([id, ...before, ...after]);
      cy.elements()
        .removeClass("dimmed prerequisite affected focus-line")
        .unselect();
      cy.nodes().forEach((n) => {
        if (!related.has(n.id())) n.addClass("dimmed");
        if (before.includes(n.id())) n.addClass("prerequisite");
        if (after.includes(n.id())) n.addClass("affected");
      });
      cy.edges().forEach((edge) =>
        edge.addClass(
          related.has(edge.source().id()) && related.has(edge.target().id())
            ? "focus-line"
            : "dimmed",
        ),
      );
      cy.getElementById(id).select();
      $("#graph-select").value = id;
      const heading = node("div", "graph-item-heading"),
        title = node("div", "");
      title.append(node("span", "eyebrow", id), node("h3", "", item.title));
      const open = node("button", "secondary", "Abrir atividade ↗");
      open.addEventListener("click", () => onOpen(item));
      heading.append(title, open);
      const columns = node("div", "graph-impact-columns");
      [
        ["Pré-requisitos no projeto", before],
        ["Atividades potencialmente afetadas", after],
      ].forEach(([label, ids]) => {
        const group = node("section", "graph-impact"),
          count = node("h4", "", `${label} · ${ids.length}`);
        group.append(count);
        if (!ids.length)
          group.append(node("p", "metric-note", "Nenhuma atividade."));
        ids.slice(0, 25).forEach((target) => {
          const dependency = state.work_items.find((i) => i.id === target);
          const button = node("button", "impact-item");
          button.append(
            node("span", "", target),
            node("span", "", dependency?.title || target),
          );
          button.addEventListener("click", () => onOpen(dependency));
          group.append(button);
        });
        if (ids.length > 25)
          group.append(
            node(
              "p",
              "metric-note",
              `Mais ${ids.length - 25} atividades; consulte a análise pela CLI para a lista completa.`,
            ),
          );
        columns.append(group);
      });
      $("#graph-detail").replaceChildren(heading, columns);
    }
    function layout() {
      if (!cy) return;
      cy.layout({
        name: $("#graph-layout").value,
        directed: true,
        padding: 45,
        spacingFactor: 1.35,
        avoidOverlap: true,
        animate: !reduced() && cy.nodes().length < 120,
        animationDuration: 350,
      }).run();
    }
    function update(next, items) {
      state = next;
      if (typeof global.cytoscape !== "function")
        throw new Error("Não foi possível carregar o visualizador de grafos");
      forward = new Map();
      reverse = new Map();
      state.analysis.edges.forEach((edge) => {
        if (!forward.has(edge.source)) forward.set(edge.source, []);
        if (!reverse.has(edge.target)) reverse.set(edge.target, []);
        forward.get(edge.source).push(edge.target);
        reverse.get(edge.target).push(edge.source);
      });
      const ids = new Set(items.map((i) => i.id));
      const categories = new Map(
        state.project.statuses.map((s) => [s.id, s.category]),
      );
      const elements = [
        ...items.map((item) => ({
          data: {
            id: item.id,
            label: `${item.id}\n${item.title.slice(0, 42)}`,
            category: categories.get(item.status),
            blocked: Boolean(state.analysis.blockers[item.id]?.length),
          },
        })),
        ...state.analysis.edges
          .filter((e) => ids.has(e.source) && ids.has(e.target))
          .map((e) => ({ data: { id: `edge:${e.source}:${e.target}`, ...e } })),
      ];
      const previousViewport = cy
        ? { zoom: cy.zoom(), pan: { ...cy.pan() } }
        : null;
      const nextSignature = elements
        .map((e) => e.data.id)
        .sort()
        .join("|");
      if (!cy) {
        cy = global.cytoscape({
          container: $("#graph-canvas"),
          elements,
          minZoom: 0.08,
          maxZoom: 3,
          layout: { name: "preset" },
          style: [
            {
              selector: "node",
              style: {
                label: "data(label)",
                shape: "roundrectangle",
                width: 180,
                height: 64,
                "font-family": "system-ui, sans-serif",
                "font-size": 10,
                "font-weight": 500,
                "text-valign": "center",
                "text-wrap": "wrap",
                "text-max-width": 160,
                "background-color": "#e7eddf",
                color: "#40533a",
                "border-width": 1.5,
                "border-color": "#bbcbb0",
                "overlay-opacity": 0,
              },
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
                width: 1.8,
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
              selector: ".critical",
              style: {
                "border-color": "#c64d25",
                "border-width": 3,
                "line-color": "#c64d25",
                "target-arrow-color": "#c64d25",
                width: 2.8,
              },
            },
            { selector: "node.critical", style: { width: 180 } },
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
            { selector: ".dimmed", style: { opacity: 0.2 } },
          ],
        });
        cy.on("tap", "node", (event) => focus(event.target.id()));
        cy.on("tap", (event) => {
          if (event.target === cy) reset();
        });
        cy.on(
          "mouseover",
          "node",
          () => ($("#graph-canvas").style.cursor = "pointer"),
        );
        cy.on(
          "mouseout",
          "node",
          () => ($("#graph-canvas").style.cursor = "grab"),
        );
      } else {
        cy.json({ elements });
        cy.resize();
      }
      if (signature !== nextSignature) {
        signature = nextSignature;
        layout();
      } else if (previousViewport) {
        cy.viewport(previousViewport);
      }
      const select = $("#graph-select");
      select.replaceChildren(
        new Option("Selecione uma atividade", ""),
        ...items.map((i) => new Option(`${i.id} · ${i.title}`, i.id)),
      );
      $("#graph-empty").hidden = Boolean(items.length);
      const path = state.analysis.critical_path;
      $("#graph-critical").disabled = path.duration === null;
      $("#critical-path").textContent =
        path.duration === null
          ? "Caminho crítico disponível quando todas as atividades tiverem estimativas na mesma unidade."
          : `Caminho crítico técnico: ${path.path.join(" → ")} · ${path.duration} ${path.unit}. ${state.analysis.critical_path_note}`;
      critical();
      if (selected && ids.has(selected)) focus(selected);
      else reset();
      return cy;
    }
    $("#graph-layout").addEventListener("change", layout);
    $("#graph-select").addEventListener("change", (event) =>
      event.target.value ? focus(event.target.value) : reset(),
    );
    $("#graph-critical").addEventListener("change", critical);
    $("#graph-reset").addEventListener("click", reset);
    $("#graph-fit").addEventListener("click", () => cy?.fit(undefined, 45));
    [
      ["#graph-zoom-in", 1.25],
      ["#graph-zoom-out", 0.8],
    ].forEach(([id, factor]) =>
      $(id).addEventListener("click", () => {
        if (cy)
          cy.zoom({
            level: Math.max(0.08, Math.min(3, cy.zoom() * factor)),
            renderedPosition: {
              x: $("#graph-canvas").clientWidth / 2,
              y: $("#graph-canvas").clientHeight / 2,
            },
          });
      }),
    );
    return { update };
  }
  global.BacklogGraph = { create };
})(globalThis);
