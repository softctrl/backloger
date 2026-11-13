"use strict";
(function (global) {
  const priorities = {
    critical: "Crítica",
    high: "Alta",
    medium: "Média",
    low: "Baixa",
  };
  const units = { hours: "horas", days: "dias", points: "pontos" };
  const phases = {
    current: "No período",
    upcoming: "Planejada",
    past: "Período encerrado",
    undated: "Período incompleto",
    unplanned: "Sem sprint",
  };
  const $ = (selector) => document.querySelector(selector);
  const node = (tag, className, text) => {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  };
  const date = (value) =>
    value
      ? new Date(value + "T00:00:00Z").toLocaleDateString("pt-BR", {
          timeZone: "UTC",
        })
      : "Não definido";
  const fold = (value) =>
    String(value)
      .normalize("NFD")
      .replace(/\p{Diacritic}/gu, "")
      .toLowerCase();

  function create({ api, refresh, openItem, toast, notice }) {
    let state = null,
      filtered = [],
      selected = null,
      initialized = false,
      saving = false;
    let limits = {},
      editId = null,
      editRevision = null,
      planningId = null;
    const editor = $("#sprint-editor"),
      form = $("#sprint-form"),
      planner = $("#sprint-planner");
    const field = (name) => form.elements.namedItem(name);
    const summaries = () => state?.sprint_overview?.iterations || [];
    const summary = () =>
      summaries().find((value) => value.id === selected) ||
      state.sprint_overview.unassigned;
    const error = (selector, text = "") => {
      $(selector).textContent = text;
      $(selector).hidden = !text;
    };
    function choose() {
      const values = summaries();
      return (
        [...values]
          .filter((i) => i.phase === "current")
          .sort((a, b) =>
            (b.start_date || "").localeCompare(a.start_date || ""),
          )[0]?.id ||
        [...values]
          .filter((i) => i.phase === "upcoming")
          .sort((a, b) => a.start_date.localeCompare(b.start_date))[0]?.id ||
        [...values].sort((a, b) =>
          (b.due_date || b.start_date || "").localeCompare(
            a.due_date || a.start_date || "",
          ),
        )[0]?.id ||
        null
      );
    }
    function card(item) {
      const status = state.project.statuses.find(
        (value) => value.id === item.status,
      );
      const button = node("button", "card sprint-card");
      button.type = "button";
      button.dataset.id = item.id;
      const top = node("div", "card-top");
      top.append(
        node("span", "", item.id),
        node("span", "card-type", status.name),
      );
      const bottom = node("div", "card-bottom");
      bottom.append(
        node("span", `priority ${item.priority}`, priorities[item.priority]),
        node("span", "", item.owner || "Sem responsável"),
      );
      button.append(top, node("div", "card-title", item.title), bottom);
      const blockers = state.analysis.blocker_counts[item.id] || 0;
      if (blockers)
        button.append(
          node("span", "blocked-badge", `${blockers} bloqueador(es)`),
        );
      if (item.due_date)
        button.append(
          node("span", "sprint-card-due", `Prazo: ${date(item.due_date)}`),
        );
      button.addEventListener("click", () => openItem(item));
      return button;
    }
    function renderBoard() {
      const all = state.work_items.filter(
        (item) => (item.iteration_id || null) === selected,
      );
      const ids = new Set(all.map((item) => item.id));
      const items = filtered.filter((item) => ids.has(item.id));
      const ranks = { critical: 0, high: 1, medium: 2, low: 3 };
      items.sort(
        (a, b) =>
          ranks[a.priority] - ranks[b.priority] ||
          (a.due_date || "9999").localeCompare(b.due_date || "9999") ||
          a.id.localeCompare(b.id),
      );
      const categories = new Map(
        state.project.statuses.map((status) => [status.id, status.category]),
      );
      $("#item-count").textContent =
        `${items.length} de ${all.length} atividades neste escopo`;
      $("#sprint-scope-note").textContent =
        `Resumo: ${all.length} atividades no escopo completo. Lista: ${items.length} com os filtros atuais. Abra um card para atualizar o estado ou a sprint.`;
      $("#sprint-board").replaceChildren(
        ...[
          ["pending", "A fazer"],
          ["active", "Em andamento"],
          ["done", "Concluídas"],
        ].map(([category, name]) => {
          const column = node("section", "sprint-column");
          column.dataset.category = category;
          const matches = items.filter(
            (item) => categories.get(item.status) === category,
          );
          const total = all.filter(
            (item) => categories.get(item.status) === category,
          ).length;
          const heading = node("div", "sprint-column-heading");
          heading.append(
            node("h3", "", name),
            node("span", "", `${matches.length} / ${total}`),
          );
          column.append(
            heading,
            ...matches.slice(0, limits[category] || 24).map(card),
          );
          if (!matches.length)
            column.append(
              node("p", "empty", "Nenhuma atividade com os filtros atuais."),
            );
          if (matches.length > (limits[category] || 24)) {
            const more = node(
              "button",
              "secondary sprint-more",
              `Mostrar mais (${matches.length - (limits[category] || 24)} restantes)`,
            );
            more.addEventListener("click", () => {
              limits[category] = (limits[category] || 24) + 24;
              renderBoard();
              $("#sprint-board")
                .querySelector(`[data-category="${category}"] .sprint-more`)
                ?.focus();
            });
            column.append(more);
          }
          return column;
        }),
      );
      const cancelled = items.filter(
        (item) => categories.get(item.status) === "cancelled",
      );
      $("#sprint-cancelled").hidden = !all.some(
        (item) => categories.get(item.status) === "cancelled",
      );
      $("#sprint-cancelled-label").textContent =
        `Canceladas · ${cancelled.length} com os filtros atuais`;
      $("#sprint-cancelled-list").replaceChildren(...cancelled.map(card));
    }
    function render() {
      if (!state?.sprint_overview) return;
      if (
        !initialized ||
        (selected && !summaries().some((i) => i.id === selected))
      ) {
        selected = choose();
        initialized = true;
        limits = {};
      }
      $("#sprint-select").replaceChildren(
        new Option(
          `Sem sprint (${state.sprint_overview.unassigned.total})`,
          "",
        ),
        ...summaries().map(
          (i) => new Option(`${i.name} · ${i.remaining} restantes`, i.id),
        ),
      );
      $("#sprint-select").value = selected || "";
      const value = summary();
      $("#sprint-name").textContent = value.name;
      $("#sprint-phase").textContent = phases[value.phase];
      $("#sprint-period").textContent = selected
        ? `${date(value.start_date)} → ${date(value.due_date)}`
        : "Trabalho do backlog que ainda não foi incluído em uma sprint.";
      $("#sprint-onboarding").hidden = summaries().length > 0;
      ["#sprint-create", "#sprint-new"].forEach(
        (id) => ($(id).disabled = state.read_only || saving),
      );
      $("#sprint-edit").disabled = !selected || state.read_only || saving;
      $("#sprint-add").disabled = !selected || state.read_only || saving;
      $("#sprint-new").textContent = selected
        ? "＋ Nova atividade na sprint"
        : "＋ Nova atividade no backlog";
      $("#sprint-summary").replaceChildren(
        ...[
          ["A fazer", value.pending],
          ["Em andamento", value.active],
          ["Concluídas", value.done],
          ["Restantes", value.remaining],
          ["Bloqueadas", value.blocked],
        ].map(([label, count]) => {
          const metric = node("div", "sprint-metric");
          metric.append(
            node("strong", "", String(count)),
            node("span", "", label),
          );
          return metric;
        }),
      );
      $("#sprint-progress").value = value.progress || 0;
      $("#sprint-progress-label").textContent =
        value.progress === null
          ? "Sem atividades aplicáveis"
          : `${value.progress.toLocaleString("pt-BR")}% concluído · ${value.done} de ${value.total - value.cancelled}`;
      $("#sprint-progress").setAttribute(
        "aria-valuetext",
        $("#sprint-progress-label").textContent,
      );
      const estimates = Object.entries(value.open_estimates)
        .map(
          ([unit, amount]) =>
            `${amount.toLocaleString("pt-BR")} ${units[unit]}`,
        )
        .join(" · ");
      $("#sprint-attention").textContent =
        `${value.cancelled} canceladas fora do cálculo de conclusão · ${value.overdue} atividades com prazo vencido. Bloqueios podem vir de fora da sprint.${value.phase === "past" && value.remaining ? ` Período encerrado com ${value.remaining} atividades restantes.` : ""}${estimates ? ` Estimativas dos itens abertos: ${estimates}.` : ""}`;
      $("#sprint-burndown-panel").hidden = !selected;
      if (selected) {
        const scope = state.burndown.scopes.find(
          (scope) => scope.id === `iteration:${selected}`,
        );
        BacklogCharts.burndown($("#sprint-burndown"), scope?.points || []);
        $("#sprint-burndown-note").textContent =
          `${state.burndown.note} ${scope?.baseline_date ? `Referência inicial observada em ${date(scope.baseline_date)}.` : "Sem linha de base observada no período; não há referência ideal."}`;
      }
      renderBoard();
      if (editor.open && editRevision !== state.revision)
        error(
          "#sprint-editor-error",
          "O projeto mudou. Seus campos foram preservados. Feche e reabra o planejamento para revisar antes de salvar.",
        );
      if (planner.open && !saving) renderPlanner();
    }
    function openForm(edit) {
      if (!state || state.read_only) return;
      const iteration = edit
        ? state.iterations.find((i) => i.id === selected)
        : null;
      if (edit && !iteration) return;
      editId = iteration?.id || null;
      editRevision = state.revision;
      form.reset();
      error("#sprint-editor-error");
      $("#sprint-editor-title").textContent = edit
        ? "Editar sprint"
        : "Criar sprint";
      field("name").value = iteration?.name || "";
      field("start_date").value = iteration?.start_date || "";
      field("due_date").value = iteration?.due_date || "";
      field("due_date").min = field("start_date").value;
      editor.showModal();
    }
    function renderPlanner() {
      if (!state.iterations.some((i) => i.id === planningId)) {
        planner.close();
        notice("A sprint não está mais disponível. Reabra o planejamento.");
        return;
      }
      const query = fold($("#sprint-backlog-search").value);
      const candidates = state.work_items.filter(
        (i) => !i.iteration_id && fold(`${i.id} ${i.title}`).includes(query),
      );
      $("#sprint-planner-count").textContent =
        `${candidates.length} atividades encontradas. Exibindo até 50; refine a busca por ID ou título.`;
      $("#sprint-backlog-list").replaceChildren(
        ...candidates.slice(0, 50).map((item) => {
          const row = node("div", "sprint-candidate"),
            title = node("div", "");
          title.append(node("strong", "", item.id), node("p", "", item.title));
          const add = node("button", "secondary", "Adicionar");
          add.setAttribute("aria-label", `Adicionar ${item.id} à sprint`);
          add.disabled = saving || state.read_only;
          add.addEventListener("click", () => assign(item.id));
          row.append(title, add);
          return row;
        }),
      );
    }
    async function assign(id) {
      if (saving || state.read_only) return;
      const item = state.work_items.find((i) => i.id === id);
      if (!item || item.iteration_id) {
        error(
          "#sprint-planner-error",
          "A atividade mudou de sprint. Atualize a seleção.",
        );
        return;
      }
      saving = true;
      error("#sprint-planner-error");
      renderPlanner();
      try {
        await api(
          `/api/v1/items/${id}`,
          {
            method: "PATCH",
            body: JSON.stringify({
              expected_version: item.version,
              iteration_id: planningId,
            }),
          },
          state.revision,
        );
        await refresh(true);
        toast(`${id} adicionada à sprint`);
        $("#sprint-backlog-search").focus();
      } catch (failure) {
        error("#sprint-planner-error", failure.message);
        await refresh(true);
      } finally {
        saving = false;
        renderPlanner();
        render();
      }
    }
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (saving || state.read_only) return;
      const data = {
        name: field("name").value.trim(),
        start_date: field("start_date").value || null,
        due_date: field("due_date").value || null,
      };
      if (!data.name) {
        error("#sprint-editor-error", "Informe o nome da sprint.");
        return;
      }
      if (data.start_date && data.due_date && data.due_date < data.start_date) {
        error(
          "#sprint-editor-error",
          "O fim da sprint deve ser igual ou posterior ao início.",
        );
        return;
      }
      saving = true;
      $("#sprint-save").disabled = true;
      error("#sprint-editor-error");
      try {
        const result = await api(
          editId ? `/api/v1/iterations/${editId}` : "/api/v1/iterations",
          { method: editId ? "PUT" : "POST", body: JSON.stringify(data) },
          editRevision,
        );
        selected = result.iteration.id;
        initialized = true;
        limits = {};
        editor.close();
        await refresh(true);
        toast("Sprint salva");
      } catch (failure) {
        error("#sprint-editor-error", failure.message);
      } finally {
        saving = false;
        $("#sprint-save").disabled = false;
        render();
      }
    });
    $("#sprint-select").addEventListener("change", (event) => {
      selected = event.target.value || null;
      initialized = true;
      limits = {};
      render();
    });
    $("#sprint-create").addEventListener("click", () => openForm(false));
    $("#sprint-edit").addEventListener("click", () => openForm(true));
    ["#sprint-close", "#sprint-cancel"].forEach((id) =>
      $(id).addEventListener("click", () => editor.close()),
    );
    field("start_date").addEventListener(
      "change",
      () => (field("due_date").min = field("start_date").value),
    );
    $("#sprint-add").addEventListener("click", () => {
      if (!selected || state.read_only) return;
      planningId = selected;
      $("#sprint-backlog-search").value = "";
      error("#sprint-planner-error");
      renderPlanner();
      planner.showModal();
    });
    $("#sprint-planner-close").addEventListener("click", () => planner.close());
    $("#sprint-backlog-search").addEventListener("input", renderPlanner);
    $("#sprint-new").addEventListener("click", () => openItem());
    return {
      update(next, items) {
        state = next;
        filtered = items;
        render();
      },
      selectedId: () => selected,
    };
  }
  global.BacklogSprints = { create };
})(globalThis);
