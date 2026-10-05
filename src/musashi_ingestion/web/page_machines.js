(() => {
  "use strict";

  window.MusashiPages ||= {};

  function machineCard(machine, context) {
    const {state, helpers: h} = context;
    const live = h.machineStatus(state, machine);
    const endpoint = machine.model === "IV"
      ? `${machine.host}:${machine.port || 1024}`
      : machine.port;
    const currentState = h.machineState(state, machine);
    const locked = Boolean(state.status?.running);
    const name = machine.model === "III" ? "Musashi Super ΣCM III" : "Musashi Super ΣCM IV";
    const lastRead = live.error
      ? "Attention required"
      : live.last_success ? `Last read ${h.ago(live.last_success)}` : "Waiting for first read";

    return `<article class="machine-card" data-machine-state="${h.esc(currentState)}">
      <div class="machine-card-top">
        <span class="machine-model" aria-hidden="true">Σ${h.esc(machine.model)}</span>
        <div class="machine-card-title"><h2>${h.esc(machine.id)}</h2><p>${name}</p></div>
      <div class="machine-card-actions">
          <button class="small-button" data-action="edit-machine" data-id="${h.esc(machine.id)}" aria-label="Edit machine ${h.esc(machine.id)}" ${locked ? 'disabled title="Stop acquisition before editing configuration"' : ""}>Edit</button>
          <button class="small-button danger" data-action="remove-machine" data-id="${h.esc(machine.id)}" aria-label="Remove machine ${h.esc(machine.id)}" ${locked ? 'disabled title="Stop acquisition before removing a machine"' : ""}>Remove</button>
        </div>
      </div>
      <div class="machine-state-line">${h.statusBadge(live)}<span>${lastRead}</span></div>
      ${live.error ? `<div class="machine-error" role="status">${h.esc(live.error)}</div>` : ""}
      <div class="machine-endpoint">
        <span class="detail-label">${machine.model === "IV" ? "NETWORK ENDPOINT" : "SERIAL DEVICE"}</span>
        <strong class="mono">${h.esc(endpoint || "Not configured")}</strong>
      </div>
      <dl class="machine-specs">
        <div><dt>Poll interval</dt><dd>${h.esc(machine.poll_interval_seconds ?? 1)} sec</dd></div>
        <div><dt>Inventory scan</dt><dd>Every ${h.esc(machine.inventory_interval_seconds ?? 3600)} sec</dd></div>
        <div><dt>Poll lag</dt><dd>${h.number(live.poll_lag_seconds || 0)} sec</dd></div>
        <div><dt>Skipped polls</dt><dd>${h.number(live.skipped_polls || 0)}</dd></div>
      </dl>
    </article>`;
  }

  function renderResults(context, machines) {
    const {state, helpers: h} = context;
    const query = state.machineQuery.trim().toLocaleLowerCase();
    const filtered = machines.filter(machine => {
      const currentState = h.machineState(state, machine);
      const matchesFilter = state.machineFilter === "all"
        || (state.machineFilter === "running" && ["running", "starting"].includes(currentState))
        || currentState === state.machineFilter;
      const endpoint = machine.model === "IV"
        ? `${machine.host}:${machine.port || 1024}`
        : machine.port;
      return matchesFilter && `${machine.id} ${machine.model} ${endpoint} ${currentState}`.toLocaleLowerCase().includes(query);
    });

    if (!filtered.length) {
      return '<div class="machine-no-results"><strong>No matching machines</strong><span>Try another search or status filter.</span></div>';
    }
    return filtered.map(machine => machineCard(machine, context)).join("");
  }

  window.MusashiPages.machines = {
    render({state, helpers: h}) {
      const machines = state.config?.machines || [];
      const running = Boolean(state.status?.running);
      const states = machines.map(machine => h.machineState(state, machine));
      const active = states.filter(value => ["running", "starting"].includes(value)).length;
      const faults = states.filter(value => value === "fault").length;
      const stopped = machines.length - active - faults;
      const action = `<button class="button button-primary" data-action="add-machine" ${running ? 'disabled title="Stop acquisition before editing machine configuration"' : ""}>Add machine <span aria-hidden="true">＋</span></button>`;
      const filterButton = (key, label, count) => `<button type="button" class="machine-filter ${state.machineFilter === key ? "active" : ""}" data-machine-filter="${key}" aria-pressed="${state.machineFilter === key}">${label}<span>${h.number(count)}</span></button>`;
      const results = machines.length
        ? `<div id="machine-results" class="machine-cards">${renderResults({state, helpers: h}, machines)}</div>`
        : `<div class="machine-empty"><span class="machine-empty-mark" aria-hidden="true">Σ</span><h2>No machines configured</h2><p>Add a Musashi III or IV device to begin setting up collection.</p>${action}</div>`;

      return `${h.pageHeading("DEVICE MANAGEMENT", "Machines", "Monitor device health and manage collection endpoints.", action)}
        ${running ? '<div class="machine-lock-notice"><span aria-hidden="true">i</span><span>Acquisition is running. Stop it before changing machine configuration.</span></div>' : ""}
        <section class="machine-summary" aria-label="Machine status summary">
          <div><span class="machine-summary-label">Configured</span><strong>${h.number(machines.length)}</strong></div>
          <div><span class="machine-summary-label">Active</span><strong class="summary-good">${h.number(active)}</strong></div>
          <div><span class="machine-summary-label">Needs attention</span><strong class="summary-danger">${h.number(faults)}</strong></div>
          <div><span class="machine-summary-label">Stopped</span><strong>${h.number(stopped)}</strong></div>
        </section>
        <section class="machine-browser" aria-labelledby="machine-list-heading">
          <div class="machine-browser-head">
            <div><h2 id="machine-list-heading">All machines</h2><p>Status updates automatically</p></div>
            <label class="machine-search"><span aria-hidden="true">⌕</span><input id="machine-search" type="search" value="${h.esc(state.machineQuery)}" placeholder="Search name, model, endpoint, or status" aria-label="Search machines by name, model, endpoint, or status"></label>
          </div>
          <div class="machine-filter-row" role="group" aria-label="Filter machines">
            ${filterButton("all", "All", machines.length)}
            ${filterButton("running", "Active", active)}
            ${filterButton("fault", "Needs attention", faults)}
            ${filterButton("stopped", "Stopped", stopped)}
          </div>
        </section>
        ${results}`;
    },
    renderResults,
  };
})();
