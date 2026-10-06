(() => {
  "use strict";
  const {t, html, msg} = window.MusashiI18n;

  window.MusashiPages ||= {};

  const humanBytes = value => {
    if (!Number.isFinite(value) || value < 0) return "—";
    const units = ["B", "KiB", "MiB", "GiB", "TiB"];
    let amount = value, unit = 0;
    while (amount >= 1024 && unit < units.length - 1) { amount /= 1024; unit += 1; }
    const digits = unit === 0 ? (Number.isInteger(amount) ? 0 : 1) : amount >= 100 ? 0 : amount >= 10 ? 1 : 2;
    return msg`${new Intl.NumberFormat(window.MusashiI18n.locale, {maximumFractionDigits:digits}).format(amount)} ${units[unit]}`;
  };

  const growthSummary = samples => {
    if (samples.length < 2) return t("Collecting 60-second baseline");
    const latest = samples[samples.length - 1];
    const baseline = samples.slice(0, -1).reverse().find(sample => {
      const age = latest.at - sample.at;
      return age >= 60_000 && age <= 90_000;
    });
    if (!baseline) return t("Collecting 60-second baseline");
    const minutes = (latest.at - baseline.at) / 60_000;
    const formatRate = (delta, format) => {
      const rate = delta / minutes;
      const sign = rate > 0 ? "+" : rate < 0 ? "−" : "";
      return msg`${sign}${format(Math.abs(rate))}`;
    };
    const bytes = formatRate(latest.diskBytes - baseline.diskBytes, humanBytes);
    const records = formatRate(latest.records - baseline.records, value =>
      new Intl.NumberFormat(window.MusashiI18n.locale, {maximumFractionDigits:1}).format(value));
    const pending = formatRate(latest.pending - baseline.pending, value =>
      new Intl.NumberFormat(window.MusashiI18n.locale, {maximumFractionDigits:1}).format(value));
    return msg`Growth (~1 min): ${bytes}/min · ${records} records/min · pending ${pending}/min`;
  };

  window.MusashiPages.overview = ({state, helpers}) => {
    const {esc, number, date, ago, pageHeading, statusBadge, machineStatus,
      destinationStatus, emptyPanel, metric} = helpers;
    const status = state.status || {};
    const spool = status.spool || {};
    const machines = state.config?.machines || [];
    const destinations = state.config?.destinations || [];
    const running = Boolean(status.running);
    const fault = status.acquisition_fault || spool.fault;
    const actions = running
      ? html('<button class="button button-danger" type="button" data-action="stop">Stop acquisition</button>')
      : html('<button class="button button-primary" type="button" data-action="start">Start acquisition <span aria-hidden="true">→</span></button>');
    const pendingCount = Number(spool.pending || 0);
    const spoolStorage = humanBytes(Number(spool.disk_bytes || 0));
    const walStorage = humanBytes(Number(spool.wal_bytes || 0));
    const spoolGrowth = growthSummary(state.spoolSamples || []);
    const latestSuccess = machines
      .map(machine => machineStatus(state, machine).last_success)
      .filter(Boolean)
      .sort()
      .at(-1);

    const machineRows = machines.length
      ? machines.map(machine => {
        const live = machineStatus(state, machine);
        const endpoint = machine.model === "IV"
          ? msg`${machine.host}:${machine.port || 1024}`
          : machine.port;
        const seen = live.last_success ? ago(live.last_success) : t("No successful read yet");
        const health = live.error
          ? msg`<span class="badge danger">${esc(live.error)}</span>`
          : msg`<span class="mono">${number(live.skipped_polls || 0)} skipped polls</span>`;

        return msg`<tr>
          <td><div class="device-cell"><span class="device-avatar">${esc(machine.model)}</span><div>
            <div class="device-name">${esc(machine.id)}</div>
            <div class="device-meta">${machine.model === "III" ? t("Serial interface") : t("Network interface")}</div>
          </div></div></td>
          <td class="mono">${esc(endpoint || t("Not configured"))}</td>
          <td>${statusBadge(live)}</td>
          <td>${esc(seen)}</td>
          <td>${health}</td>
        </tr>`;
      }).join("")
      : html('<tr><td colspan="5" class="empty-row">No machines configured</td></tr>');

    const recentRecords = (state.records || []).slice(0, 5).map(record => {
      const simulated = record.evidence_type === "simulated";
      return msg`<div class="record-row" role="listitem">
        <i class="record-dot ${simulated ? "simulated" : ""}" aria-hidden="true"></i>
        <div>
          <div class="record-title">${esc(record.machine_id)} <span class="mono">${esc(record.source)}</span></div>
          <div class="record-meta">${esc(record.model)} · ${esc(record.record_type)} ·
            <span class="${simulated ? "quality partial" : "quality"}">${esc(record.evidence_type)}</span>
          </div>
        </div>
        <span class="record-time">${esc(ago(record.observed_at))}</span>
      </div>`;
    }).join("");

    const coverage = machines.length
      ? machines.map(machine => {
        const scan = (state.scans || []).find(item => item.machine_id === machine.id);
        const items = scan?.items || [];
        const done = items.filter(item => ["ok", "unsupported"].includes(item.outcome)).length;
        const percent = items.length ? Math.round(done / items.length * 100) : 0;
        const stateText = scan
          ? msg`${scan.completed_at ? t("Complete") : t("Partial")} · ${date(scan.started_at)} · ${number(done)} of ${number(items.length)} resolved`
          : t("No scan yet");

        return msg`<div class="coverage-item">
          <div class="coverage-row">
            <span class="coverage-label">${esc(machine.id)}</span>
            <div class="coverage-track" role="progressbar" aria-label="Resolved inventory items for ${esc(machine.id)}" aria-valuetext="${items.length ? msg`${done} of ${items.length} resolved` : t("No scan items")}" aria-valuenow="${percent}" aria-valuemin="0" aria-valuemax="100">
              <div class="coverage-fill" style="width:${percent}%"></div>
            </div>
            <span class="coverage-value">${items.length ? msg`${percent}%` : "—"}</span>
          </div>
          <div class="panel-subtitle coverage-meta">${esc(stateText)}</div>
        </div>`;
      }).join("")
      : emptyPanel(t("No coverage data"), t("Add a machine to see scan coverage."));

    return msg`${pageHeading(t("SYSTEM OVERVIEW"), t("System overview"), t("Current ingestion and delivery status."), actions)}
      <section class="status-strip" aria-label="Acquisition status">
        <div class="status-copy">
          <span class="status-icon ${fault ? "warn" : running ? "good" : ""}" aria-hidden="true">${fault ? "!" : running ? "↗" : "Ⅱ"}</span>
          <div>
            <div class="status-title">${fault ? t("System fault detected") : running ? t("Acquisition is running") : t("Acquisition is stopped")}</div>
            <div class="status-subtitle">${fault ? esc(fault) : running ? msg`Last successful read ${esc(ago(latestSuccess))}` : t("Configure a machine, then start acquisition when ready.")}</div>
          </div>
        </div>
        <div class="status-right">
          ${statusBadge({state: fault ? "fault" : running ? "running" : "stopped"})}
          <span class="badge">${state.health?.process === "ok" ? t("SERVICE ONLINE") : t("CHECK SERVICE")}</span>
        </div>
      </section>
      <div class="metric-grid">
        ${metric(t("Machines"), number(machines.length), t("configured"), msg`${number(machines.filter(machine => machineStatus(state, machine).worker_alive).length)} workers active`, "M")}
        ${metric(t("Destinations"), number(destinations.length), t("configured"), msg`${number(destinations.filter(item => destinationStatus(state, item).worker_alive).length)} delivery workers`, "↗")}
        ${metric(t("Pending delivery"), number(pendingCount), t("deliveries"), pendingCount ? msg`Oldest record ${ago(spool.oldest_pending_at)}` : t("No pending deliveries"), "…")}
        ${metric(t("Spool"), number(spool.records || 0), t("records"), msg`SQLite files ${spoolStorage} · WAL ${walStorage} · ${spoolGrowth}`, "▤")}
      </div>
      <div class="section-grid">
        <section class="panel">
          <div class="panel-head">
            <div><div class="panel-title">Configured machines</div><div class="panel-subtitle">Worker state and most recent read</div></div>
            <button class="text-link" type="button" data-nav="machines">View all <span aria-hidden="true">→</span></button>
          </div>
          <div class="table-scroll overview-table-scroll" role="region" aria-label="Configured machine status" tabindex="0"><table class="data-table overview-machine-table">
            <thead><tr><th scope="col">MACHINE</th><th scope="col">ENDPOINT</th><th scope="col">STATE</th><th scope="col">LAST SUCCESS</th><th scope="col">POLL HEALTH</th></tr></thead>
            <tbody>${machineRows}</tbody>
          </table></div>
        </section>
        <section class="panel">
          <div class="panel-head">
            <div><div class="panel-title">Inventory coverage</div><div class="panel-subtitle">Most recent scan by machine</div></div>
            <button class="text-link" type="button" data-nav="records">Details <span aria-hidden="true">→</span></button>
          </div>
          <div class="coverage-wrap">${coverage}</div>
        </section>
      </div>
      <section class="panel">
        <div class="panel-head">
          <div><div class="panel-title">Recent records</div><div class="panel-subtitle">Latest 5 records in the spool · simulated data is highlighted</div></div>
          <button class="text-link" type="button" data-nav="records">View recent data <span aria-hidden="true">→</span></button>
        </div>
        <div class="record-list" role="list" aria-label="Latest records">${recentRecords || html('<div class="panel-empty" role="listitem"><strong>No records yet</strong>Records will appear here after the collector stores data.</div>')}</div>
      </section>`;
  };
})();
