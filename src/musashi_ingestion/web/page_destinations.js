(() => {
  "use strict";

  window.MusashiPages ||= {};

  function destinationCard(destination, context) {
    const {state, helpers: h} = context;
    const live = h.destinationStatus(state, destination);
    const kind = destination.kind || "unknown";
    const names = {mqtt: "MQTT broker", postgres: "PostgreSQL", influxdb: "InfluxDB"};
    const marks = {mqtt: "MQ", postgres: "PG", influxdb: "IF"};
    const target = kind === "mqtt"
      ? `${destination.host || "Broker host"}:${destination.port || (destination.tls ? 8883 : 1883)}`
      : kind === "influxdb" ? destination.url || "InfluxDB URL not configured"
        : "Connection details stored in a protected secret file";
    const targetMeta = kind === "mqtt"
      ? `Topic · ${destination.topic || "Not configured"}`
      : kind === "influxdb" ? `${destination.org || "Organization not configured"} · ${destination.bucket || "Bucket not configured"}`
        : "Credentials are kept outside the configuration response";
    const pending = Number(live.pending_count || 0);
    const message = live.error
      ? "Delivery needs attention · see error details"
      : pending ? `${h.number(pending)} pending · oldest ${h.ago(live.oldest_pending_at)}`
        : live.last_success ? `Last delivered · ${h.ago(live.last_success)}` : "No successful delivery recorded";
    const locked = Boolean(state.status?.running);
    const currentState = h.destinationState(state, destination);

    return `<article class="destination-card" data-destination-state="${h.esc(currentState)}">
      <div class="destination-card-head">
        <div class="destination-kind-mark" aria-hidden="true">${marks[kind] || "↗"}</div>
        <div class="destination-identity"><p>${h.esc(names[kind] || kind)}</p><h2>${h.esc(destination.id)}</h2></div>
        <div class="destination-actions">
          <button class="small-button" data-action="edit-destination" data-id="${h.esc(destination.id)}" ${locked ? 'disabled title="Stop acquisition before editing configuration"' : ""}>Edit</button>
          <button class="small-button danger" data-action="remove-destination" data-id="${h.esc(destination.id)}" ${locked ? 'disabled title="Stop acquisition before editing configuration"' : ""}>Remove</button>
        </div>
      </div>
      <div class="destination-target">
        <span class="detail-label">DELIVERY TARGET</span>
        <strong class="mono">${h.esc(target)}</strong>
        <span>${h.esc(targetMeta)}</span>
      </div>
      <div class="destination-health ${live.error ? "has-error" : ""}">
        ${h.statusBadge({...live, state: currentState})}<span>${h.esc(message)}</span>
      </div>
      ${live.error ? `<div class="destination-error" role="alert">${h.esc(live.error)}</div>` : ""}
      <div class="destination-stats">
        <div><span>Pending records</span><strong>${h.number(pending)}</strong></div>
        <div><span>Oldest pending</span><strong>${pending ? h.esc(h.ago(live.oldest_pending_at)) : "Queue clear"}</strong></div>
      </div>
    </article>`;
  }

  function renderResults(context, destinations) {
    const {state, helpers: h} = context;
    const query = state.destinationQuery.trim().toLocaleLowerCase();
    const filtered = destinations.filter(destination => {
      const currentState = h.destinationState(state, destination);
      const pending = Number(h.destinationStatus(state, destination).pending_count || 0) > 0;
      const matchesFilter = state.destinationFilter === "all"
        || (state.destinationFilter === "running" && ["running", "starting"].includes(currentState))
        || (state.destinationFilter === "fault" && currentState === "fault")
        || (state.destinationFilter === "pending" && pending)
        || (state.destinationFilter === "stopped" && currentState === "stopped");
      const searchable = [destination.id, destination.kind, destination.host, destination.port,
        destination.topic, destination.url, destination.org, destination.bucket]
        .filter(Boolean).join(" ").toLocaleLowerCase();
      return matchesFilter && searchable.includes(query);
    });

    if (!filtered.length) {
      return '<div class="destination-no-results"><strong>No matching destinations</strong><span>Try another search or delivery filter.</span></div>';
    }
    return filtered.map(destination => destinationCard(destination, context)).join("");
  }

  window.MusashiPages.destinations = {
    render({state, helpers: h}) {
      const destinations = state.config?.destinations || [];
      const running = Boolean(state.status?.running);
      const spool = state.status?.spool || {};
      const states = destinations.map(destination => h.destinationState(state, destination));
      const active = states.filter(value => ["running", "starting"].includes(value)).length;
      const faults = states.filter(value => value === "fault").length;
      const stopped = destinations.length - active - faults;
      const pendingRecords = Number(spool.pending || 0);
      const pendingLanes = destinations.filter(destination => Number(h.destinationStatus(state, destination).pending_count || 0) > 0).length;
      const action = `<button class="button button-primary" data-action="add-destination" ${running ? 'disabled title="Stop acquisition before editing configuration"' : ""}>Add destination <span aria-hidden="true">＋</span></button>`;
      const filterButton = (key, label, count) => `<button type="button" class="destination-filter ${state.destinationFilter === key ? "active" : ""}" data-destination-filter="${key}" aria-pressed="${state.destinationFilter === key}">${label}<span>${h.number(count)}</span></button>`;
      const results = destinations.length
        ? `<div id="destination-results" class="destination-cards" aria-live="polite" aria-relevant="additions text">${renderResults({state, helpers: h}, destinations)}</div>`
        : `<div class="destination-empty"><span class="destination-empty-mark" aria-hidden="true">↗</span><h2>No delivery targets yet</h2><p>Collected records stay in the local spool until a destination is configured.</p>${action}</div>`;

      return `${h.pageHeading("DELIVERY TARGETS", "Destinations", "Monitor delivery lanes, queued records, and endpoint health.", action)}
        ${running ? '<div class="machine-lock-notice"><span aria-hidden="true">i</span><span>Acquisition is running. Stop it before changing destination configuration.</span></div>' : ""}
        <section class="destination-summary" aria-label="Destination delivery summary">
          <div><span class="machine-summary-label">Configured</span><strong>${h.number(destinations.length)}</strong></div>
          <div><span class="machine-summary-label">Active workers</span><strong class="summary-good">${h.number(active)}</strong></div>
          <div><span class="machine-summary-label">Pending records</span><strong>${h.number(pendingRecords)}</strong></div>
          <div><span class="machine-summary-label">Needs attention</span><strong class="summary-danger">${h.number(faults)}</strong></div>
        </section>
        <section class="destination-retention">
          <div class="retention-mark" aria-hidden="true">↗</div>
          <div class="retention-copy"><strong>Retained spool data</strong><span>Delivered records are removed; new destinations can backfill only data still in the spool.</span></div>
          <div class="retention-values">
            <div><span>Oldest retained</span><strong>${h.esc(h.date(spool.oldest_retained_at))}</strong></div>
            <div><span>Pruned records</span><strong>${h.number(spool.pruned_record_count || 0)}</strong></div>
          </div>
        </section>
        <section class="destination-browser" aria-label="Destination list">
          <div class="destination-browser-head">
            <div><h2>Delivery lanes</h2><p>${h.number(pendingLanes)} ${pendingLanes === 1 ? "lane has" : "lanes have"} queued records</p></div>
            <label class="destination-search"><span aria-hidden="true">⌕</span><input id="destination-search" type="search" value="${h.esc(state.destinationQuery)}" placeholder="Search destinations" aria-label="Search destinations"></label>
          </div>
          <div class="destination-filter-row" role="group" aria-label="Filter destinations">
            ${filterButton("all", "All", destinations.length)}
            ${filterButton("running", "Active", active)}
            ${filterButton("fault", "Needs attention", faults)}
            ${filterButton("pending", "With pending", pendingLanes)}
            ${filterButton("stopped", "Stopped", stopped)}
          </div>
        </section>
        ${results}`;
    },
    renderResults,
  };
})();
