(() => {
  "use strict";
  const {t, html, msg} = window.MusashiI18n;

  window.MusashiPages ||= {};

  window.MusashiPages.records = ({state, helpers: h}) => {
    const records = state.records || [];
    const scans = state.scans || [];
    const active = h.workersActive(state);
    const actions = msg`<button class="button button-danger" data-action="clear-spool" ${!state.status || active ? html('disabled title="Stop all machine and destination workers before clearing the spool"') : ""}>Clear spool</button>
      <button class="button" data-action="refresh"><span aria-hidden="true">↻</span> Refresh</button>`;

    const recordRows = records.map(record => {
      const simulated = record.evidence_type === "simulated";
      const partial = ["error", "partial"].includes(record.values?.quality);
      return msg`<tr>
        <td><div class="device-name">${h.esc(record.machine_id || t("Unknown machine"))}</div><div class="device-meta">${h.esc(record.model || "—")}</div></td>
        <td><div>${h.esc(record.record_type || t("Unknown type"))}</div><div class="device-meta mono">${h.esc(record.source || "—")}</div></td>
        <td><time datetime="${h.esc(record.observed_at || "")}">${h.esc(h.date(record.observed_at))}</time></td>
        <td><span class="evidence-tag ${simulated ? "simulated" : ""}">${h.esc(record.evidence_type || "unknown")}</span></td>
        <td><span class="quality ${partial ? "partial" : ""}">${h.esc(record.values?.quality || "—")}</span></td>
        <td><code class="record-id" title="${h.esc(record.record_id || t("No record ID"))}">${h.esc(record.record_id?.slice(0, 8) || "—")}</code></td>
      </tr>`;
    }).join("");

    const scanRows = scans.map(scan => {
      const items = scan.items || [];
      const read = items.filter(item => item.outcome === "ok").length;
      const unsupported = items.filter(item => item.outcome === "unsupported").length;
      const failed = items.filter(item => item.outcome === "failed").length;
      const notRead = items.filter(item => !item.outcome).length;
      const complete = Boolean(scan.completed_at);
      const stateLabel = complete ? t("Complete") : t("Partial");
      const visibleItems = items.slice(0, 8);
      const itemMarkup = visibleItems.map(item => {
        const outcome = item.outcome || "not read";
        const stateClass = item.outcome === "failed" ? "failed"
          : item.outcome === "unsupported" ? "unsupported" : item.outcome ? "read" : "missing";
        return msg`<li class="records-scan-item ${stateClass}"><code>${h.esc(item.item_key || t("Unknown item"))}</code><span>${h.esc(outcome)}</span></li>`;
      }).join("");
      const moreItems = items.length > visibleItems.length
        ? msg`<li class="records-scan-more">and ${h.number(items.length - visibleItems.length)} more items</li>`
        : "";
      const coverage = items.length
        ? msg`<div class="records-scan-counts" role="group" aria-label="${h.esc(msg`${read} read, ${unsupported} unsupported, ${failed} failed, ${notRead} not read`)}">
            <span>${h.number(read)} read</span><span>${h.number(unsupported)} unsupported</span><span>${h.number(failed)} failed</span><span>${h.number(notRead)} not read</span>
          </div>
          <ul class="records-scan-items">${itemMarkup}${moreItems}</ul>`
        : html('<span class="records-no-items">No expected items recorded</span>');

      return msg`<tr>
        <td><div class="device-name">${h.esc(scan.machine_id || t("Unknown machine"))}</div><div class="device-meta mono">${h.esc(scan.group_name || scan.scan_id?.slice(0, 8) || t("Inventory"))}</div></td>
        <td><span class="badge ${complete ? "good" : "warning"}" aria-label="${stateLabel} inventory scan">${stateLabel}</span><div class="device-meta"><time datetime="${h.esc(scan.started_at || "")}">${h.esc(h.date(scan.started_at))}</time></div></td>
        <td>${coverage}${!complete ? html('<div class="records-scan-note">This scan is not marked complete.</div>') : ""}</td>
      </tr>`;
    }).join("");

    return msg`${h.pageHeading(t("RECENT ACTIVITY"), t("Recent data"), t("Showing up to 10 recent records and 10 scans from the spool."), actions)}
      ${active ? html('<div class="machine-lock-notice"><span aria-hidden="true">i</span><span>Stop all machine and destination workers before clearing the spool.</span></div>') : ""}
      <div class="records-layout">
        <section class="panel" aria-labelledby="records-title">
          <div class="panel-head">
            <div><h2 class="panel-title" id="records-title">Observation records</h2><div class="panel-subtitle">Stored in the spool · This is not a complete archive.</div></div>
            <span class="badge" aria-label="${h.number(records.length)} of 10 records">${h.number(records.length)} / 10</span>
          </div>
          <div class="table-scroll records-table-scroll" role="region" aria-label="Observation records table" tabindex="0">
            <table class="data-table records-table">
              <caption class="records-sr-only">Recent observation records stored in the local spool.</caption>
              <thead><tr><th scope="col">Machine</th><th scope="col">Type / source</th><th scope="col">Observed at</th><th scope="col">Evidence</th><th scope="col">Quality</th><th scope="col">Record ID</th></tr></thead>
              <tbody>${recordRows || html('<tr><td colspan="6" class="empty-row">No records yet</td></tr>')}</tbody>
            </table>
          </div>
        </section>
        <section class="panel" aria-labelledby="scans-title">
          <div class="panel-head">
            <div><h2 class="panel-title" id="scans-title">Inventory scans</h2><div class="panel-subtitle">Only scans with a completion time are marked complete; partial coverage remains visible.</div></div>
            <span class="badge" aria-label="${h.number(scans.length)} of 10 scans">${h.number(scans.length)} / 10</span>
          </div>
          <div class="table-scroll records-table-scroll" role="region" aria-label="Inventory scans table" tabindex="0">
            <table class="data-table records-table records-scan-table">
              <caption class="records-sr-only">Recent inventory scans with per-item outcomes.</caption>
              <thead><tr><th scope="col">Machine / scan</th><th scope="col">State / started</th><th scope="col">Item coverage</th></tr></thead>
              <tbody>${scanRows || html('<tr><td colspan="3" class="empty-row">No scans yet</td></tr>')}</tbody>
            </table>
          </div>
        </section>
      </div>`;
  };
})();
