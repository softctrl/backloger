"use strict";
(function (global) {
  function positions(ids, edges, direction = "LR") {
    const children = new Map(ids.map((id) => [id, []]));
    const parents = new Map(ids.map((id) => [id, []]));
    edges.forEach(({ source, target }) => {
      if (children.has(source) && children.has(target)) {
        children.get(source).push(target);
        parents.get(target).push(source);
      }
    });
    const seen = new Set(),
      result = new Map();
    let offsetX = 0,
      offsetY = 0,
      rowHeight = 0;
    for (const seed of [...ids].sort()) {
      if (seen.has(seed)) continue;
      const component = [seed];
      seen.add(seed);
      for (let i = 0; i < component.length; i++) {
        for (const next of [
          ...children.get(component[i]),
          ...parents.get(component[i]),
        ]) {
          if (!seen.has(next)) {
            seen.add(next);
            component.push(next);
          }
        }
      }
      const degree = new Map(
        component.map((id) => [id, parents.get(id).length]),
      );
      const queue = component.filter((id) => degree.get(id) === 0).sort();
      const rank = new Map(component.map((id) => [id, 0]));
      for (let i = 0; i < queue.length; i++) {
        for (const next of children.get(queue[i])) {
          rank.set(next, Math.max(rank.get(next), rank.get(queue[i]) + 1));
          degree.set(next, degree.get(next) - 1);
          if (degree.get(next) === 0) queue.push(next);
        }
      }
      const levels = [];
      for (const id of component) {
        const level = rank.get(id);
        while (levels.length <= level) levels.push([]);
        levels[level].push(id);
      }
      levels.forEach((level) => level.sort());
      const order = new Map();
      const index = () =>
        levels.forEach((level) => level.forEach((id, i) => order.set(id, i)));
      index();
      // Two barycentric sweeps reduce crossings without force simulations.
      for (let pass = 0; pass < 2; pass++) {
        for (const [sequence, neighbors] of [
          [levels, parents],
          [[...levels].reverse(), children],
        ]) {
          for (const level of sequence) {
            const center = (id) => {
              const links = neighbors.get(id);
              return links.length
                ? links.reduce((sum, next) => sum + order.get(next), 0) /
                    links.length
                : order.get(id);
            };
            level.sort((a, b) => center(a) - center(b) || a.localeCompare(b));
            level.forEach((id, i) => order.set(id, i));
          }
        }
      }
      const rows = Math.max(...levels.map((level) => level.length), 1);
      const width = direction === "LR" ? levels.length * 265 : rows * 235;
      const height = direction === "LR" ? rows * 105 : levels.length * 125;
      if (offsetX && offsetX + width > 1600) {
        offsetY += rowHeight + 90;
        offsetX = 0;
        rowHeight = 0;
      }
      levels.forEach((level, column) =>
        level.forEach((id, row) => {
          result.set(
            id,
            direction === "LR"
              ? { x: offsetX + 115 + column * 265, y: offsetY + 60 + row * 105 }
              : {
                  x: offsetX + 115 + row * 235,
                  y: offsetY + 60 + column * 125,
                },
          );
        }),
      );
      offsetX += width + 90;
      rowHeight = Math.max(rowHeight, height);
    }
    return result;
  }
  global.BacklogGraphLayout = { positions };
})(globalThis);
