/* Local SVG charts. No external requests or HTML assembled from project data. */
"use strict";
(function (global) {
  const SVG = "http://www.w3.org/2000/svg";
  const palette = {
    pending: "#b8c5a6",
    active: "#d8a253",
    done: "#628d73",
    cancelled: "#ccd2cf",
  };
  const priorities = {
    critical: ["Crítica", "#c16651"],
    high: ["Alta", "#d5a454"],
    medium: ["Média", "#7d9c83"],
    low: ["Baixa", "#94acb4"],
  };
  const node = (tag, className, text) => {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  };
  const svg = (tag, attributes = {}, text) => {
    const element = document.createElementNS(SVG, tag);
    Object.entries(attributes).forEach(([key, value]) =>
      element.setAttribute(key, String(value)),
    );
    if (text !== undefined) element.textContent = text;
    return element;
  };
  const percent = (value, total) =>
    total ? Math.round((value / total) * 100) : 0;
  function categoryColor(category) {
    return palette[category] || palette.pending;
  }
  function icon(name) {
    const paths = {
      layers: ["M12 3 3 8l9 5 9-5-9-5Z", "m3 12 9 5 9-5", "m3 16 9 5 9-5"],
      clock: ["M12 8v4l3 2"],
      link: [
        "M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-2 2",
        "M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l2-2",
      ],
      trend: ["m3 17 6-6 4 4 8-10", "M15 5h6v6"],
      flag: ["M5 21V4", "M5 4c5-4 9 4 14 0v10c-5 4-9-4-14 0"],
      team: [
        "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2",
        "M22 21v-2a4 4 0 0 0-3-3.87",
        "M16 3.13a4 4 0 0 1 0 7.75",
      ],
    };
    const image = svg("svg", {
      viewBox: "0 0 24 24",
      fill: "none",
      stroke: "currentColor",
      "stroke-width": 1.65,
      "stroke-linecap": "round",
      "stroke-linejoin": "round",
      "aria-hidden": "true",
    });
    (paths[name] || paths.layers).forEach((d) =>
      image.append(svg("path", { d })),
    );
    if (name === "clock")
      image.prepend(svg("circle", { cx: 12, cy: 12, r: 9 }));
    if (name === "team") image.prepend(svg("circle", { cx: 9, cy: 7, r: 4 }));
    return image;
  }

  function donut(container, items, statuses, onSelect) {
    const total = items.length;
    const done = items.filter(
      (i) => statuses.find((s) => s.id === i.status)?.category === "done",
    ).length;
    const figure = node("div", "donut-figure");
    const image = svg("svg", {
      viewBox: "0 0 220 220",
      role: "img",
      "aria-label": `${done} de ${total} atividades concluídas`,
    });
    image.append(
      svg("circle", {
        cx: 110,
        cy: 110,
        r: 82,
        fill: "none",
        stroke: "#edf1e8",
        "stroke-width": 20,
      }),
    );
    const legend = node("div", "donut-legend");
    let offset = 0;
    statuses.forEach((status, index) => {
      const count = items.filter((i) => i.status === status.id).length;
      const color =
        status.category === "active" && index % 2 === 0
          ? "#83a1a6"
          : categoryColor(status.category);
      if (count) {
        const value = (count / total) * 100;
        const arc = svg("circle", {
          cx: 110,
          cy: 110,
          r: 82,
          fill: "none",
          stroke: color,
          "stroke-width": 20,
          pathLength: 100,
          "stroke-dasharray": `${Math.max(0, value - (count === total ? 0 : 0.8))} 100`,
          "stroke-dashoffset": -offset,
          transform: "rotate(-90 110 110)",
          class: "donut-arc",
        });
        arc.append(
          svg(
            "title",
            {},
            `${status.name}: ${count} (${percent(count, total)}%)`,
          ),
        );
        arc.addEventListener("click", () => onSelect(status.id));
        image.append(arc);
        offset += value;
      }
      const button = node("button", "legend-row");
      button.type = "button";
      button.disabled = !count;
      const label = node("span", "legend-label"),
        dot = node("i", "legend-dot");
      dot.style.backgroundColor = color;
      label.append(dot, node("span", "", status.name));
      button.append(
        label,
        node("strong", "", String(count)),
        node("small", "", `${percent(count, total)}%`),
      );
      button.setAttribute(
        "aria-label",
        `${status.name}: ${count} atividades. Abrir no Kanban`,
      );
      button.addEventListener("click", () => onSelect(status.id));
      legend.append(button);
    });
    image.append(
      svg(
        "text",
        { x: 110, y: 108, "text-anchor": "middle", class: "donut-value" },
        `${percent(done, total)}%`,
      ),
      svg(
        "text",
        { x: 110, y: 132, "text-anchor": "middle", class: "donut-caption" },
        total ? "concluído" : "sem atividades",
      ),
    );
    figure.append(
      image,
      node("p", "donut-total", `${done} de ${total} atividades entregues`),
    );
    container.replaceChildren(figure, legend);
  }

  function priority(container, items, onSelect) {
    const values = Object.keys(priorities).map((id) => ({
      id,
      count: items.filter((i) => i.priority === id).length,
    }));
    const max = Math.max(1, ...values.map((row) => row.count));
    container.replaceChildren(
      ...values.map(({ id, count }) => {
        const button = node("button", "priority-row");
        button.type = "button";
        button.disabled = !count;
        button.dataset.priority = id;
        const heading = node("div", "chart-row-heading"),
          label = node("span", ""),
          dot = node("i", "legend-dot");
        dot.style.backgroundColor = priorities[id][1];
        label.append(dot, node("span", "", priorities[id][0]));
        heading.append(label, node("strong", "", String(count)));
        const track = node("div", "chart-track"),
          fill = node("div", "chart-fill");
        fill.style.width = `${(count / max) * 100}%`;
        fill.style.backgroundColor = priorities[id][1];
        track.append(fill);
        button.append(heading, track);
        button.setAttribute(
          "aria-label",
          `${priorities[id][0]}: ${count} atividades. Abrir no Kanban`,
        );
        button.addEventListener("click", () => onSelect(id));
        return button;
      }),
    );
  }

  function owners(container, items, statuses, onSelect) {
    const categories = new Map(statuses.map((s) => [s.id, s.category]));
    const grouped = new Map();
    items.forEach((item) => {
      const key = item.owner || null;
      if (!grouped.has(key))
        grouped.set(key, {
          id: key,
          label: key || "Sem responsável",
          total: 0,
          done: 0,
          active: 0,
          pending: 0,
        });
      const row = grouped.get(key);
      row.total++;
      const category = categories.get(item.status);
      row[
        category === "done"
          ? "done"
          : category === "active"
            ? "active"
            : "pending"
      ]++;
    });
    const all = [...grouped.values()].sort(
      (a, b) => b.total - a.total || a.label.localeCompare(b.label, "pt-BR"),
    );
    const rows = all.slice(0, 6);
    if (all.length > 6) {
      const rest = {
        id: null,
        label: `Outros (${all.length - 6})`,
        total: 0,
        done: 0,
        active: 0,
        pending: 0,
      };
      all
        .slice(6)
        .forEach((row) =>
          ["total", "done", "active", "pending"].forEach(
            (k) => (rest[k] += row[k]),
          ),
        );
      rows.push(rest);
    }
    const max = Math.max(1, ...rows.map((row) => row.total));
    container.replaceChildren(
      ...rows.map((row) => {
        const button = node(row.id ? "button" : "div", "owner-row");
        if (row.id) {
          button.type = "button";
          button.addEventListener("click", () => onSelect(row.id));
        }
        const heading = node("div", "chart-row-heading");
        heading.append(
          node("span", "owner-name", row.label),
          node("strong", "", String(row.total)),
        );
        const track = node("div", "owner-track");
        track.style.width = `${(row.total / max) * 100}%`;
        ["done", "active", "pending"].forEach((category) => {
          const segment = node("span", `owner-segment ${category}`);
          segment.style.width = `${(row[category] / row.total) * 100}%`;
          track.append(segment);
        });
        button.append(heading, track);
        button.setAttribute(
          "aria-label",
          `${row.label}: ${row.total} atividades, ${row.done} concluídas, ${row.active} em andamento`,
        );
        return button;
      }),
    );
    if (!rows.length)
      container.append(
        node(
          "p",
          "empty",
          "As atividades aparecerão aqui quando forem cadastradas.",
        ),
      );
  }

  function activity(container, days) {
    const width = 700,
      height = 236,
      left = 30,
      right = 10,
      top = 18,
      bottom = 40,
      plotHeight = height - top - bottom;
    const maxValue = Math.max(
      1,
      ...days.flatMap((day) => [day.created, day.completed]),
    );
    const step = Math.max(1, Math.ceil(maxValue / 4)),
      ceiling = step * 4;
    const image = svg("svg", {
      viewBox: `0 0 ${width} ${height}`,
      role: "group",
      "aria-label":
        "Atividades criadas e concluídas por dia. Use as setas para explorar as datas.",
    });
    const tooltip = node("div", "chart-tooltip");
    tooltip.hidden = true;
    const format = (value, full = false) =>
      new Intl.DateTimeFormat(
        "pt-BR",
        full
          ? { day: "numeric", month: "long", timeZone: "UTC" }
          : { day: "2-digit", month: "2-digit", timeZone: "UTC" },
      ).format(new Date(value + "T00:00:00Z"));
    for (let i = 0; i <= 4; i++) {
      const y = top + plotHeight - (i / 4) * plotHeight;
      image.append(
        svg("line", {
          x1: left,
          y1: y,
          x2: width - right,
          y2: y,
          class: "chart-grid-line",
        }),
        svg(
          "text",
          { x: left - 8, y: y + 4, "text-anchor": "end", class: "chart-axis" },
          String(i * step),
        ),
      );
    }
    const stride = (width - left - right) / Math.max(1, days.length),
      barWidth = Math.min(15, stride * 0.3),
      groups = [];
    days.forEach((day, index) => {
      const x = left + index * stride + stride / 2;
      const label = `${format(day.date, true)}: ${day.created} criada(s), ${day.completed} concluída(s)`;
      const group = svg("g", {
        class: "activity-day",
        tabindex: index === 0 ? 0 : -1,
        role: "img",
        "aria-label": label,
      });
      group.append(
        svg("title", {}, label),
        svg("rect", {
          x: x - stride / 2,
          y: top,
          width: stride,
          height: plotHeight + 12,
          fill: "transparent",
          class: "day-hit",
        }),
      );
      ["created", "completed"].forEach((key, i) => {
        const barHeight = (day[key] / ceiling) * plotHeight;
        if (barHeight)
          group.append(
            svg("rect", {
              x: x + (i === 0 ? -barWidth - 1 : 1),
              y: top + plotHeight - barHeight,
              width: barWidth,
              height: barHeight,
              rx: 2,
              class: `activity-bar ${key}`,
            }),
          );
      });
      const show = () => {
        tooltip.textContent = label;
        tooltip.hidden = false;
      };
      group.addEventListener("pointerenter", show);
      group.addEventListener("focus", show);
      group.addEventListener("pointerleave", () => (tooltip.hidden = true));
      group.addEventListener("blur", () => (tooltip.hidden = true));
      group.addEventListener("keydown", (event) => {
        const direction =
          event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
        if (!direction) return;
        event.preventDefault();
        const next = groups[(index + direction + days.length) % days.length];
        group.setAttribute("tabindex", "-1");
        next.setAttribute("tabindex", "0");
        next.focus();
      });
      image.append(group);
      groups.push(group);
      if (
        index === 0 ||
        index === days.length - 1 ||
        index % Math.max(1, Math.ceil(days.length / 6)) === 0
      )
        image.append(
          svg(
            "text",
            { x, y: height - 12, "text-anchor": "middle", class: "chart-axis" },
            format(day.date),
          ),
        );
    });
    const details = node("details", "chart-data"),
      summary = node("summary", "", "Ver dados em tabela"),
      table = node("table"),
      head = node("thead"),
      headRow = node("tr");
    ["Data (UTC)", "Criadas", "Concluídas"].forEach((text) =>
      headRow.append(node("th", "", text)),
    );
    head.append(headRow);
    table.append(head);
    const body = node("tbody");
    days.forEach((day) => {
      const row = node("tr");
      [format(day.date), day.created, day.completed].forEach((value) =>
        row.append(node("td", "", String(value))),
      );
      body.append(row);
    });
    table.append(body);
    details.append(summary, table);
    container.replaceChildren(image, tooltip, details);
    if (!days.some((day) => day.created || day.completed)) {
      const empty = node("div", "activity-empty");
      empty.append(
        icon("trend"),
        node("strong", "", "O histórico começa com suas entregas"),
        node(
          "span",
          "",
          "Nenhuma criação ou conclusão registrada neste período.",
        ),
      );
      container.prepend(empty);
    }
  }
  function burndown(container, points) {
    const width = 700,
      height = 240,
      left = 30,
      right = 10,
      top = 18,
      bottom = 38,
      plotHeight = height - top - bottom;
    const maxValue = Math.max(
      1,
      ...points
        .flatMap((point) => [point.remaining, point.ideal])
        .filter(Number.isFinite),
    );
    const step = Math.max(1, Math.ceil(maxValue / 4)),
      ceiling = step * 4;
    const image = svg("svg", {
      viewBox: `0 0 ${width} ${height}`,
      role: "group",
      "aria-label":
        "Burndown de atividades restantes. Pontos indicam registros observados; datas desconhecidas ficam em aberto.",
    });
    const tooltip = node("div", "chart-tooltip");
    tooltip.hidden = true;
    const x = (index) =>
        left +
        (index / Math.max(1, points.length - 1)) * (width - left - right),
      y = (value) => top + plotHeight - (value / ceiling) * plotHeight;
    const format = (value) =>
      new Date(value + "T00:00:00Z").toLocaleDateString("pt-BR", {
        day: "2-digit",
        month: "2-digit",
        timeZone: "UTC",
      });
    for (let i = 0; i <= 4; i++)
      image.append(
        svg("line", {
          x1: left,
          y1: y(i * step),
          x2: width - right,
          y2: y(i * step),
          class: "chart-grid-line",
        }),
        svg(
          "text",
          {
            x: left - 8,
            y: y(i * step) + 4,
            "text-anchor": "end",
            class: "chart-axis",
          },
          String(i * step),
        ),
      );
    const drawSeries = (key, className) => {
      let previous = null;
      points.forEach((point, index) => {
        if (point[key] === null || point[key] === undefined) return;
        if (previous !== null)
          image.append(
            svg("line", {
              x1: x(previous),
              y1: y(points[previous][key]),
              x2: x(index),
              y2: y(point[key]),
              class: `burndown-line ${className} ${index - previous > 1 ? "unobserved" : ""}`,
            }),
          );
        previous = index;
      });
    };
    drawSeries("ideal", "ideal");
    drawSeries("remaining", "actual");
    const groups = [];
    points.forEach((point, index) => {
      if (
        index === 0 ||
        index === points.length - 1 ||
        index % Math.max(1, Math.ceil(points.length / 7)) === 0
      )
        image.append(
          svg(
            "text",
            {
              x: x(index),
              y: height - 10,
              "text-anchor": "middle",
              class: "chart-axis",
            },
            format(point.date),
          ),
        );
      if (point.remaining === null) return;
      const label = `${format(point.date)}: ${point.remaining} restantes em um escopo de ${point.total} atividades`;
      const group = svg("g", {
        class: "burndown-point",
        role: "img",
        tabindex: groups.length === 0 ? 0 : -1,
        "aria-label": label,
      });
      group.append(
        svg("title", {}, label),
        svg("circle", {
          cx: x(index),
          cy: y(point.remaining),
          r: 11,
          fill: "transparent",
          class: "burn-hit",
        }),
        svg("circle", {
          cx: x(index),
          cy: y(point.remaining),
          r: 4.5,
          class: "burn-marker",
        }),
      );
      const show = () => {
        tooltip.textContent = label;
        tooltip.hidden = false;
      };
      group.addEventListener("pointerenter", show);
      group.addEventListener("focus", show);
      group.addEventListener("pointerleave", () => (tooltip.hidden = true));
      group.addEventListener("blur", () => (tooltip.hidden = true));
      const position = groups.length;
      group.addEventListener("keydown", (event) => {
        const direction =
          event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
        if (!direction) return;
        event.preventDefault();
        group.setAttribute("tabindex", "-1");
        const next =
          groups[(position + direction + groups.length) % groups.length];
        next.setAttribute("tabindex", "0");
        next.focus();
      });
      groups.push(group);
      image.append(group);
    });
    const details = node("details", "chart-data"),
      table = node("table"),
      head = node("thead"),
      heading = node("tr");
    [
      "Data (UTC)",
      "Restantes observadas",
      "Escopo",
      "Referência ideal",
    ].forEach((text) => heading.append(node("th", "", text)));
    head.append(heading);
    table.append(head);
    const body = node("tbody");
    points.forEach((point) => {
      const row = node("tr");
      [
        format(point.date),
        point.remaining ?? "—",
        point.total ?? "—",
        point.ideal ?? "—",
      ].forEach((value) => row.append(node("td", "", String(value))));
      body.append(row);
    });
    table.append(body);
    details.append(node("summary", "", "Ver dados do burndown"), table);
    container.replaceChildren(image, tooltip, details);
    if (groups.length < 2)
      container.append(
        node(
          "p",
          "chart-hint",
          "O ponto atual é real. A curva ganhará histórico conforme os próximos registros forem feitos.",
        ),
      );
  }
  global.BacklogCharts = {
    donut,
    priority,
    owners,
    activity,
    burndown,
    icon,
    categoryColor,
  };
})(globalThis);
