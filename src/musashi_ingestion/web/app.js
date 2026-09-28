(() => {
  "use strict";

  const pageNames = {overview: "ภาพรวม", machines: "เครื่องจักร", destinations: "ปลายทาง", records: "ข้อมูลล่าสุด"};
  const state = {token: "", page: "overview", health: null, config: null, status: null, records: [], scans: [], busy: false, edit: null, refreshTimer: null};
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const esc = value => String(value ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
  const number = value => Number.isFinite(Number(value)) ? new Intl.NumberFormat("th-TH", {maximumFractionDigits: 0}).format(Number(value)) : "—";
  const date = value => { if (!value) return "—"; const parsed = new Date(value); return Number.isNaN(parsed.valueOf()) ? "—" : new Intl.DateTimeFormat("th-TH", {dateStyle:"medium",timeStyle:"short"}).format(parsed); };
  const ago = value => { if (!value) return "ยังไม่มีข้อมูล"; const seconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000)); if (!Number.isFinite(seconds)) return "—"; if (seconds < 60) return `${seconds} วินาทีก่อน`; if (seconds < 3600) return `${Math.floor(seconds / 60)} นาที ก่อน`; if (seconds < 86400) return `${Math.floor(seconds / 3600)} ชั่วโมงก่อน`; return `${Math.floor(seconds / 86400)} วันก่อน`; };
  const entries = value => Object.entries(value || {});
  const setNotice = (message, kind = "", duration = 4500) => { const node = $("#notice"); node.textContent = message; node.className = `notice ${kind}`; node.hidden = !message; if (duration) window.setTimeout(() => { if (node.textContent === message) node.hidden = true; }, duration); };
  const api = async (path, options = {}) => {
    const headers = new Headers(options.headers || {});
    if (state.token) headers.set("Authorization", `Bearer ${state.token}`);
    if (options.body !== undefined) headers.set("Content-Type", "application/json");
    let response;
    try { response = await fetch(path, {...options, headers, body: options.body === undefined ? undefined : JSON.stringify(options.body), cache:"no-store"}); }
    catch { throw new Error("เชื่อมต่อ service ไม่ได้ ตรวจ network แล้วลองใหม่"); }
    const type = response.headers.get("content-type") || "";
    const body = type.includes("application/json") ? await response.json().catch(() => ({})) : {};
    if (response.status === 401) { forgetToken(); throw new Error("operator token ไม่ถูกต้องหรือหมดอายุ"); }
    if (!response.ok) {
      if (response.status === 422 && body.errors) throw new Error(Object.entries(body.errors).map(([key, message]) => `${key}: ${message}`).join(" · "));
      throw new Error(body.error || `Request failed (${response.status})`);
    }
    return body;
  };

  function forgetToken() {
    state.token = "";
    if (!$("#token-dialog").open) $("#token-dialog").showModal();
  }

  function setBusy(value) {
    state.busy = value;
    $("#refresh-dot").classList.toggle("busy", value);
    $("#refresh-button").disabled = value;
  }

  async function refresh({quiet = false} = {}) {
    if (state.busy) return;
    setBusy(true);
    try {
      state.health = await api("/health");
      if (state.token) {
        const [config, status, records, scans] = await Promise.all([
          api("/api/config"), api("/api/status"), api("/api/records"), api("/api/scans")
        ]);
        state.config = config; state.status = status; state.records = records.records || []; state.scans = scans.scans || [];
        $("#machine-count").textContent = number(config.machines?.length || 0);
        $("#destination-count").textContent = number(config.destinations?.length || 0);
        $("#connection-dot").className = `live-dot ${state.health.process === "ok" ? "online" : "offline"}`;
        $("#connection-label").textContent = state.health.process === "ok" ? "Service พร้อมใช้งาน" : "Service มีปัญหา";
        $("#last-updated").textContent = `อัปเดต ${new Intl.DateTimeFormat("th-TH", {hour:"2-digit",minute:"2-digit",second:"2-digit"}).format(new Date())}`;
        $("#refresh-dot").classList.add("active");
        if (!quiet) setNotice("อัปเดตข้อมูลแล้ว", "", 1800);
        render();
      } else {
        $("#connection-dot").className = `live-dot ${state.health.process === "ok" ? "online" : "offline"}`;
        $("#connection-label").textContent = state.health.process === "ok" ? "Service พร้อมใช้งาน" : "Service มีปัญหา";
        $("#last-updated").textContent = "ต้องยืนยัน operator token";
      }
    } catch (error) {
      if (!quiet) setNotice(error.message, "error", 6500);
      if (state.token) renderError(error.message);
    } finally { setBusy(false); }
  }

  function renderError(message) {
    const content = $("#page-content");
    content.innerHTML = `<div class="page-heading"><div><div class="kicker">CONNECTION ISSUE</div><h1>${esc(pageNames[state.page])}</h1><p>หน้าไม่สามารถอ่านข้อมูลปัจจุบันจาก service ได้</p></div></div><section class="panel"><div class="panel-empty"><strong>ยังโหลดข้อมูลไม่ได้</strong>${esc(message)}<div style="margin-top:15px"><button class="button button-primary" data-action="refresh">ลองอีกครั้ง</button></div></div></section>`;
  }

  function pageHeading(kicker, title, description, actions = "") {
    return `<div class="page-heading"><div><div class="kicker">${esc(kicker)}</div><h1>${esc(title)}</h1><p>${esc(description)}</p></div>${actions ? `<div class="heading-actions">${actions}</div>` : ""}</div>`;
  }

  function statusBadge(status = {}) {
    const stateName = status.state || (status.worker_alive ? "running" : "stopped");
    const labels = {running:"กำลังทำงาน", starting:"กำลังเริ่ม", stopped:"หยุดอยู่", fault:"มีข้อผิดพลาด"};
    const cls = stateName === "running" ? "good" : stateName === "fault" ? "danger" : stateName === "starting" ? "warning" : "";
    return `<span class="badge ${cls}"><i class="badge-dot"></i>${labels[stateName] || esc(stateName)}</span>`;
  }

  function metric(label, value, unit, foot, mark) {
    return `<article class="metric"><span class="metric-mark">${esc(mark)}</span><div class="metric-label">${esc(label)}</div><div class="metric-value">${esc(value)}<span class="metric-unit">${esc(unit)}</span></div><div class="metric-foot">${esc(foot)}</div></article>`;
  }

  function machineStatus(machine) { return state.status?.machines?.[machine.id] || {}; }
  function destinationStatus(destination) { return state.status?.destinations?.[destination.id] || {}; }

  function machineRow(machine) {
    const live = machineStatus(machine);
    const endpoint = machine.model === "IV" ? `${machine.host}:${machine.port || 1024}` : machine.port;
    const seen = live.last_success ? ago(live.last_success) : "ยังไม่สำเร็จ";
    return `<tr><td><div class="device-cell"><span class="device-avatar">${esc(machine.model)}</span><div><div class="device-name">${esc(machine.id)}</div><div class="device-meta">${machine.model === "II" ? "Serial interface" : "Network interface"}</div></div></div></td><td class="mono">${esc(endpoint)}</td><td>${statusBadge(live)}</td><td>${esc(seen)}</td><td>${live.error ? `<span class="badge danger">${esc(live.error)}</span>` : `<span class="mono">${number(live.skipped_polls || 0)} skipped</span>`}</td></tr>`;
  }

  function machineCard(machine) {
    const live = machineStatus(machine);
    const endpoint = machine.model === "IV" ? `${machine.host}:${machine.port || 1024}` : machine.port;
    return `<article class="entity-card"><div class="entity-head"><div class="entity-identity"><span class="device-avatar">${esc(machine.model)}</span><div><h3>${esc(machine.id)}</h3><p>${machine.model === "II" ? "Musashi Super ΣCM II" : "Musashi Super ΣCM IV"}</p></div></div><div class="entity-actions"><button class="small-button" data-action="edit-machine" data-id="${esc(machine.id)}">แก้ไข</button><button class="small-button danger" data-action="remove-machine" data-id="${esc(machine.id)}">ลบ</button></div></div><div class="entity-detail-grid"><div><div class="detail-label">ENDPOINT</div><div class="detail-value mono">${esc(endpoint)}</div></div><div><div class="detail-label">POLL INTERVAL</div><div class="detail-value">${esc(machine.poll_interval_seconds ?? 1)} วินาที</div></div><div><div class="detail-label">LAST SUCCESS</div><div class="detail-value">${esc(ago(live.last_success))}</div></div><div><div class="detail-label">POLL LAG / SKIPPED</div><div class="detail-value">${number(live.poll_lag_seconds || 0)} วิ · ${number(live.skipped_polls || 0)} รอบ</div></div></div><div class="entity-foot"><span>${live.error ? `<span class="quality error">${esc(live.error)}</span>` : `Inventory · ทุก ${esc(machine.inventory_interval_seconds ?? 3600)} วินาที`}</span>${statusBadge(live)}</div></article>`;
  }

  function destinationCard(destination) {
    const live = destinationStatus(destination);
    const target = destination.kind === "mqtt" ? `${destination.host || "Broker"} · ${destination.topic || "—"}` : destination.kind === "influxdb" ? `${destination.org || "Org"} / ${destination.bucket || "Bucket"}` : "PostgreSQL service";
    return `<article class="entity-card"><div class="entity-head"><div class="entity-identity"><span class="device-avatar">${esc(destination.kind.slice(0,2).toUpperCase())}</span><div><h3>${esc(destination.id)}</h3><p>${esc(destination.kind.toUpperCase())}</p></div></div><div class="entity-actions"><button class="small-button" data-action="edit-destination" data-id="${esc(destination.id)}">แก้ไข</button><button class="small-button danger" data-action="remove-destination" data-id="${esc(destination.id)}">ลบ</button></div></div><div class="entity-detail-grid"><div class="full"><div class="detail-label">TARGET</div><div class="detail-value">${esc(target)}</div></div><div><div class="detail-label">PENDING</div><div class="detail-value">${number(live.pending_count || 0)} records</div></div><div><div class="detail-label">OLDEST PENDING</div><div class="detail-value">${esc(ago(live.oldest_pending_at))}</div></div></div><div class="entity-foot"><span>${live.error ? `<span class="quality error">${esc(live.error)}</span>` : `ส่งล่าสุด · ${esc(ago(live.last_success))}`}</span>${statusBadge(live)}</div></article>`;
  }

  function emptyPanel(title, detail, action = "") {
    return `<div class="panel-empty"><strong>${esc(title)}</strong>${esc(detail)}${action ? `<div style="margin-top:13px">${action}</div>` : ""}</div>`;
  }

  function renderOverview() {
    const status = state.status || {}, spool = status.spool || {}, machines = state.config?.machines || [], destinations = state.config?.destinations || [];
    const running = Boolean(status.running), fault = status.acquisition_fault || spool.fault;
    const actions = running ? `<button class="button button-danger" data-action="stop">หยุด acquisition</button>` : `<button class="button button-primary" data-action="start">เริ่ม acquisition <span aria-hidden="true">→</span></button>`;
    const pendingCount = Number(spool.pending || 0);
    const latestSuccess = machines.map(m => machineStatus(m).last_success).filter(Boolean).sort().at(-1);
    const machineRows = machines.length ? machines.map(machineRow).join("") : `<tr><td colspan="5" class="empty-row">ยังไม่มีเครื่องจักรที่ตั้งค่าไว้</td></tr>`;
    const latest = state.records.slice(0,5).map(record => `<div class="record-row"><i class="record-dot ${record.evidence_type === "simulated" ? "simulated" : ""}"></i><div><div class="record-title">${esc(record.machine_id)} <span class="mono">${esc(record.source)}</span></div><div class="record-meta">${esc(record.model)} · ${esc(record.record_type)} · <span class="${record.evidence_type === "simulated" ? "quality partial" : "quality"}">${esc(record.evidence_type)}</span></div></div><span class="record-time">${esc(ago(record.observed_at))}</span></div>`).join("");
    return `${pageHeading("SYSTEM OVERVIEW", "ภาพรวมระบบ", "สถานะ ingestion และปลายทางของข้อมูลในขณะนี้", actions)}
      <section class="status-strip"><div class="status-copy"><span class="status-icon ${fault ? "warn" : running ? "good" : ""}">${fault ? "!" : running ? "↗" : "Ⅱ"}</span><div><div class="status-title">${fault ? "ระบบพบข้อผิดพลาด" : running ? "Acquisition ทำงานอยู่" : "Acquisition หยุดอยู่"}</div><div class="status-subtitle">${fault ? esc(fault) : running ? `สำเร็จล่าสุด ${esc(ago(latestSuccess))}` : "ตั้งค่าเครื่องจักรแล้วเริ่มอ่านข้อมูลได้เมื่อพร้อม"}</div></div></div><div class="status-right">${statusBadge({state:fault ? "fault" : running ? "running" : "stopped"})}<span class="badge">${state.health?.process === "ok" ? "SERVICE ONLINE" : "CHECK SERVICE"}</span></div></section>
      <div class="metric-grid">${metric("เครื่องจักร", number(machines.length), "เครื่อง", `${number(machines.filter(m => machineStatus(m).worker_alive).length)} workers active`, "M")}${metric("ปลายทาง", number(destinations.length), "แห่ง", `${number(destinations.filter(d => destinationStatus(d).worker_alive).length)} delivery workers`, "↗")}${metric("รายการรอส่ง", number(pendingCount), "records", pendingCount ? `เก่าสุด ${ago(spool.oldest_pending_at)}` : "ทุก lane ไม่มีรายการค้าง", "…")}${metric("ข้อมูลใน spool", number(spool.records || 0), "records", `Disk ${number(spool.disk_bytes || 0)} bytes · WAL ${number(spool.wal_bytes || 0)} bytes`, "▤")}</div>
      <div class="section-grid"><section class="panel"><div class="panel-head"><div><div class="panel-title">เครื่องจักรที่ตั้งค่า</div><div class="panel-subtitle">สถานะ worker และการอ่านล่าสุด</div></div><button class="text-link" data-nav="machines">ดูทั้งหมด →</button></div><div class="table-scroll"><table class="data-table"><thead><tr><th>MACHINE</th><th>ENDPOINT</th><th>STATE</th><th>LAST SUCCESS</th><th>HEALTH</th></tr></thead><tbody>${machineRows}</tbody></table></div></section>
      <section class="panel"><div class="panel-head"><div><div class="panel-title">Inventory coverage</div><div class="panel-subtitle">ภาพรวม scan ล่าสุด</div></div><button class="text-link" data-nav="records">รายละเอียด →</button></div><div class="coverage-wrap">${machines.length ? machines.map(machine => {const scans=state.scans.filter(scan=>scan.machine_id===machine.id);const scan=scans[0];const items=scan?.items||[];const done=items.filter(item=>["ok","unsupported"].includes(item.outcome)).length;const pct=items.length?Math.round(done/items.length*100):0;return `<div class="coverage-row"><span class="coverage-label">${esc(machine.id)}</span><div class="coverage-track" role="progressbar" aria-label="Inventory ${esc(machine.id)}" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100"><div class="coverage-fill" style="width:${pct}%"></div></div><span class="coverage-value">${items.length?`${pct}%`:"—"}</span></div><div class="panel-subtitle" style="margin:-6px 0 11px 111px">${scan?`${scan.completed_at?"Complete":"Partial"} · ${date(scan.started_at)}`:"ยังไม่มี scan"}</div>`}).join("") : emptyPanel("ยังไม่มีข้อมูล coverage", "เพิ่มเครื่องจักรเพื่อเริ่มแสดงผล scan")}</div></section></div>
      <section class="panel"><div class="panel-head"><div><div class="panel-title">ข้อมูลล่าสุด</div><div class="panel-subtitle">5 รายการล่าสุดใน spool · ข้อมูล simulated แสดงสีเหลือง</div></div><button class="text-link" data-nav="records">เปิดข้อมูลทั้งหมด →</button></div><div class="record-list">${latest || `<div class="panel-empty"><strong>ยังไม่มี records</strong>เมื่อ collector บันทึกข้อมูลแล้ว รายการจะแสดงที่นี่</div>`}</div></section>`;
  }

  function renderMachines() {
    const machines = state.config?.machines || [], running = Boolean(state.status?.running);
    const action = `<button class="button button-primary" data-action="add-machine" ${running ? "disabled title=\"หยุด acquisition ก่อนแก้ configuration\"" : ""}>＋ เพิ่มเครื่องจักร</button>`;
    return `${pageHeading("DEVICE MANAGEMENT", "เครื่องจักร", "จัดการเครื่อง Musashi II และ IV ที่ระบบจะอ่านข้อมูล", action)}${running?`<div class="notice warning" style="position:static;transform:none;max-width:none;margin-bottom:14px">หยุด acquisition ก่อนเพิ่ม แก้ไข หรือลบ configuration</div>`:""}<div class="toolbar"><span class="toolbar-note">${number(machines.length)} เครื่องที่บันทึกไว้ · สถานะอัปเดตอัตโนมัติ</span></div><div class="machine-cards">${machines.length?machines.map(machineCard).join(""):emptyPanel("ยังไม่มีเครื่องจักร", "เพิ่มเครื่องแรกเพื่อเริ่มตั้งค่าการเก็บข้อมูล", `<button class="button button-primary" data-action="add-machine">เพิ่มเครื่องจักร</button>`)}</div>`;
  }

  function renderDestinations() {
    const destinations = state.config?.destinations || [], running = Boolean(state.status?.running), spool = state.status?.spool || {};
    const action = `<button class="button button-primary" data-action="add-destination" ${running ? "disabled title=\"หยุด acquisition ก่อนแก้ configuration\"" : ""}>＋ เพิ่มปลายทาง</button>`;
    return `${pageHeading("DELIVERY TARGETS", "ปลายทาง", "แยกสถานะการส่งของ MQTT, PostgreSQL และ InfluxDB", action)}${running?`<div class="notice warning" style="position:static;transform:none;max-width:none;margin-bottom:14px">หยุด acquisition ก่อนเพิ่ม แก้ไข หรือลบ configuration</div>`:""}<section class="status-strip"><div class="status-copy"><span class="status-icon">↗</span><div><div class="status-title">ประวัติที่เก็บอยู่ใน spool</div><div class="status-subtitle">ปลายทางใหม่ส่งย้อนหลังได้ถึงรายการที่ยัง retained เท่านั้น</div></div></div><div class="status-right"><span class="badge">เริ่มเก็บตั้งแต่ ${esc(date(spool.oldest_retained_at))}</span><span class="badge">ถูก prune ${number(spool.pruned_record_count || 0)}</span></div></section><div class="toolbar"><span class="toolbar-note">${number(destinations.length)} destinations · แต่ละ lane ส่งแยกจากกัน</span></div><div class="destination-cards">${destinations.length?destinations.map(destinationCard).join(""):emptyPanel("ยังไม่มีปลายทาง", "เก็บข้อมูลลง spool ได้โดยไม่ต้องมีปลายทาง เลือกเพิ่มเมื่อพร้อมส่ง", `<button class="button button-primary" data-action="add-destination">เพิ่มปลายทาง</button>`)}</div>`;
  }

  function renderRecords() {
    const records = state.records || [], scans = state.scans || [];
    const recordRows = records.map(record => `<tr><td><div class="device-name">${esc(record.machine_id)}</div><div class="device-meta">${esc(record.model)}</div></td><td>${esc(record.record_type)}<div class="device-meta mono">${esc(record.source)}</div></td><td>${esc(date(record.observed_at))}</td><td><span class="evidence-tag ${record.evidence_type === "simulated" ? "simulated" : ""}">${esc(record.evidence_type || "unknown")}</span></td><td><span class="quality ${record.values?.quality === "error" || record.values?.quality === "partial" ? "partial" : ""}">${esc(record.values?.quality || "—")}</span></td><td class="mono">${esc(record.record_id?.slice(0,8) || "—")}</td></tr>`).join("");
    const scanRows = scans.map(scan => {const items=scan.items||[];return `<tr><td><div class="device-name">${esc(scan.machine_id)}</div><div class="device-meta mono">${esc(scan.group_name || scan.scan_id?.slice(0,8))}</div></td><td>${scan.completed_at?`<span class="badge good">Complete</span>`:`<span class="badge warning">Partial</span>`}<div class="device-meta">${esc(date(scan.started_at))}</div></td><td><div class="scan-items">${items.map(item=>`<span class="scan-item ${item.outcome === "failed" ? "failed" : item.outcome === "unsupported" ? "unsupported" : item.outcome ? "" : "missing"}" title="${esc(item.outcome || "missing")}">${esc(item.item_key)} · ${esc(item.outcome || "missing")}</span>`).join("") || "—"}</div></td></tr>`}).join("");
    return `${pageHeading("RECENT ACTIVITY", "ข้อมูลล่าสุด", "แสดงไม่เกิน 10 records และ 10 scans ล่าสุดจาก spool", `<button class="button" data-action="refresh">↻ รีเฟรช</button>`)}<div class="records-layout"><section class="panel"><div class="panel-head"><div><div class="panel-title">Observation records</div><div class="panel-subtitle">ข้อมูลเก็บใน spool · ไม่ใช่ archive ทั้งหมด</div></div><span class="badge">${number(records.length)} / 10</span></div><div class="table-scroll"><table class="data-table"><thead><tr><th>MACHINE</th><th>TYPE / SOURCE</th><th>OBSERVED AT</th><th>EVIDENCE</th><th>QUALITY</th><th>RECORD ID</th></tr></thead><tbody>${recordRows||`<tr><td colspan="6" class="empty-row">ยังไม่มี records</td></tr>`}</tbody></table></div></section><section class="panel"><div class="panel-head"><div><div class="panel-title">Inventory scans</div><div class="panel-subtitle">รายการที่ขาดจะไม่แสดงว่า scan complete</div></div><span class="badge">${number(scans.length)} / 10</span></div><div class="table-scroll"><table class="data-table"><thead><tr><th>MACHINE / SCAN</th><th>STATE / STARTED</th><th>ITEM COVERAGE</th></tr></thead><tbody>${scanRows||`<tr><td colspan="3" class="empty-row">ยังไม่มี scans</td></tr>`}</tbody></table></div></section></div>`;
  }

  function render() {
    const pages = {overview:renderOverview, machines:renderMachines, destinations:renderDestinations, records:renderRecords};
    $("#page-content").innerHTML = pages[state.page]();
    $("#crumb-page").textContent = pageNames[state.page];
    $$(".nav-link").forEach(link => link.classList.toggle("active", link.dataset.page === state.page));
    $("#operator-button").setAttribute("aria-label", "ออกจาก operator session");
  }

  function field(name, label, value, {type="text", full=false, required=false, options=null, hint=""} = {}) {
    const attr = `data-field="${esc(name)}"`;
    let control;
    if (options) control = `<select ${attr} ${required?"required":""}>${options.map(([key,text])=>`<option value="${esc(key)}" ${String(value)===String(key)?"selected":""}>${esc(text)}</option>`).join("")}</select>`;
    else control = `<input ${attr} type="${type}" value="${esc(value ?? "")}" ${required?"required":""} ${type === "number" ? 'min="0" step="any"' : ""} autocomplete="off">`;
    return `<div class="form-field ${full?"full":""}"><label>${esc(label)}${required?" *":""}</label>${control}${hint?`<div class="field-hint">${esc(hint)}</div>`:""}</div>`;
  }

  function openEdit(kind, item = null) {
    if (state.status?.running) { setNotice("หยุด acquisition ก่อนแก้ configuration", "warning"); return; }
    state.edit = {kind, itemId:item?.id || null, original:item?structuredClone(item):null};
    const isMachine = kind === "machine";
    const values = item || (isMachine ? {model:"II",poll_interval_seconds:1,inventory_interval_seconds:3600,channel_count:1} : {kind:"mqtt",port:1883,tls:false});
    $("#edit-title").textContent = `${item?"แก้ไข":"เพิ่ม"}${isMachine?"เครื่องจักร":"ปลายทาง"}`;
    $("#edit-kicker").textContent = isMachine ? "MACHINE CONFIGURATION" : "DESTINATION CONFIGURATION";
    const fields = [];
    fields.push(field("id","ID",values.id,{required:true,full:true,hint:"ใช้ตัวอักษรและตัวเลข เช่น ii-line-1"}));
    if (isMachine) {
      fields.push(field("model","รุ่น",values.model,{required:true,options:[["II","Musashi II"],["IV","Musashi IV"]]}));
      fields.push(field("poll_interval_seconds","รอบอ่านสถานะ (วินาที)",values.poll_interval_seconds ?? 1,{type:"number",required:true}));
      fields.push(field("inventory_interval_seconds","รอบ inventory (วินาที)",values.inventory_interval_seconds ?? 3600,{type:"number",required:true,full:true}));
      if (values.model === "IV") {
        fields.push(field("host","IPv4 address",values.host,{required:true,hint:"ระบุ IP โดยตรง ไม่ใช้ hostname"}));
        fields.push(field("port","Port",values.port ?? 1024,{type:"number",required:true}));
        fields.push(field("channel_count","จำนวน channels",values.channel_count,{type:"number",required:true}));
        fields.push(field("recipe_count","จำนวน recipes",values.recipe_count,{type:"number",required:true}));
      } else {
        fields.push(field("port","Serial device",values.port,{required:true,full:true,hint:"ต้องเป็น /dev/serial/by-id/..."}));
        fields.push(field("channel_count","จำนวน channels",values.channel_count,{type:"number",required:true,full:true}));
      }
    } else {
      fields.push(field("kind","ประเภทปลายทาง",values.kind,{required:true,options:[["mqtt","MQTT"],["postgres","PostgreSQL"],["influxdb","InfluxDB"]]}));
      if (values.kind === "mqtt") {
        fields.push(field("host","Broker host",values.host,{required:true}));
        fields.push(field("port","Port",values.port ?? 1883,{type:"number",required:true}));
        fields.push(field("topic","Topic",values.topic,{required:true,full:true}));
      } else if (values.kind === "influxdb") {
        fields.push(field("url","InfluxDB URL",values.url,{required:true,full:true}));
        fields.push(field("org","Organization",values.org,{required:true}));
        fields.push(field("bucket","Bucket",values.bucket,{required:true}));
      }
      const secretHint = item && values.secret_ref === "********" ? "เก็บ secret เดิมไว้ · ใส่ path ใหม่เมื่อมีการเปลี่ยน secret" : "path ของ secret file บนเครื่องที่รัน service";
      fields.push(field("secret_ref","Secret file path",item?"":values.secret_ref,{required:!item,full:true,hint:secretHint}));
    }
    $("#edit-fields").innerHTML = fields.join("");
    $("#edit-error").textContent = "";
    $("#edit-dialog").showModal();
  }

  function formValues() {
    const values = {};
    $$("[data-field]", $("#edit-fields")).forEach(input => { if (input.value !== "") values[input.dataset.field] = input.type === "number" ? Number(input.value) : input.value; });
    return values;
  }

  async function saveEdit(event) {
    event.preventDefault();
    const edit = state.edit;
    if (!edit) return;
    const values = formValues();
    const isMachine = edit.kind === "machine";
    const listName = isMachine ? "machines" : "destinations";
    let item = {...(edit.original || {}), ...values};
    if (edit.original?.secret_ref === "********" && !values.secret_ref) item.secret_ref = "********";
    const list = [...(state.config?.[listName] || [])];
    if (edit.itemId) {
      const index = list.findIndex(entry => entry.id === edit.itemId);
      if (index < 0) { $("#edit-error").textContent = "ไม่พบรายการเดิม โหลด config ใหม่ก่อน"; return; }
      list[index] = item;
    } else list.push(item);
    const payload = {...state.config, [listName]:list};
    try {
      const result = await api("/api/config", {method:"PUT",body:payload});
      state.config = result; $("#edit-dialog").close(); state.edit = null; await refresh({quiet:true}); setNotice("บันทึก configuration แล้ว");
    } catch(error) { $("#edit-error").textContent = error.message; }
  }

  function removeItem(kind, id) {
    if (state.status?.running) { setNotice("หยุด acquisition ก่อนแก้ configuration", "warning"); return; }
    const isMachine = kind === "machine", key = isMachine ? "machines" : "destinations";
    $("#confirm-title").textContent = `ลบ${isMachine?"เครื่องจักร":"ปลายทาง"} ${id}`;
    $("#confirm-copy").textContent = isMachine ? "การลบจะหยุดการเก็บข้อมูลจากเครื่องนี้เมื่อเริ่มระบบครั้งถัดไป" : "การลบปลายทางจะหยุดสร้าง delivery lane ให้ปลายทางนี้ ข้อมูลที่ส่งแล้วจะไม่ถูกย้อนกลับ";
    const form = $("#confirm-form");
    form.onsubmit = async event => {
      event.preventDefault();
      const submitter = event.submitter;
      if (submitter?.value !== "confirm") { $("#confirm-dialog").close(); return; }
      try {
        const payload = {...state.config,[key]:state.config[key].filter(entry=>entry.id!==id)};
        state.config = await api("/api/config",{method:"PUT",body:payload});
        $("#confirm-dialog").close(); await refresh({quiet:true}); setNotice("ลบ configuration แล้ว");
      } catch(error) { $("#confirm-dialog").close(); setNotice(error.message,"error",7000); }
    };
    $("#confirm-dialog").showModal();
  }

  async function control(action) {
    const label = action === "start" ? "เริ่ม acquisition" : "หยุด acquisition";
    if (action === "start" && !(state.config?.machines || []).length) { setNotice("เพิ่มเครื่องจักรก่อนเริ่ม acquisition", "warning"); location.hash = "#machines"; return; }
    $("#refresh-button").disabled = true;
    try { await api(`/api/control/${action}`,{method:"POST",body:{}}); await refresh({quiet:true}); setNotice(`${label} แล้ว`); }
    catch(error) { setNotice(error.message,"error",7000); }
    finally { $("#refresh-button").disabled = false; }
  }

  document.addEventListener("click", event => {
    const target = event.target.closest("[data-action], [data-nav]");
    if (!target) return;
    if (target.dataset.nav) { state.page = target.dataset.nav; location.hash = `#${state.page}`; render(); return; }
    const {action,id} = target.dataset;
    if (action === "refresh") refresh();
    else if (action === "start" || action === "stop") control(action);
    else if (action === "add-machine") openEdit("machine");
    else if (action === "edit-machine") openEdit("machine",state.config.machines.find(item=>item.id===id));
    else if (action === "remove-machine") removeItem("machine",id);
    else if (action === "add-destination") openEdit("destination");
    else if (action === "edit-destination") openEdit("destination",state.config.destinations.find(item=>item.id===id));
    else if (action === "remove-destination") removeItem("destination",id);
  });

  $("#refresh-button").addEventListener("click",()=>refresh());
  $("#token-form").addEventListener("submit",async event=>{
    event.preventDefault(); const input=$("#token-input"); state.token=input.value; input.value=""; $("#token-error").textContent=""; $("#token-dialog").close();
    await refresh({quiet:true});
    if (!state.config) { state.token=""; if (!$("#token-dialog").open) $("#token-dialog").showModal(); $("#token-error").textContent="ยืนยันตัวตนไม่สำเร็จ ตรวจ token แล้วลองอีกครั้ง"; }
    else if (!state.refreshTimer) state.refreshTimer=window.setInterval(()=>refresh({quiet:true}),8000);
  });
  $("#token-visibility").addEventListener("click",event=>{const input=$("#token-input");input.type=input.type==="password"?"text":"password";event.currentTarget.textContent=input.type==="password"?"แสดง":"ซ่อน";});
  $("#operator-button").addEventListener("click",()=>{state.token="";state.config=null;state.status=null;state.records=[];state.scans=[];if(state.refreshTimer)clearInterval(state.refreshTimer);state.refreshTimer=null;renderError("ออกจาก operator session แล้ว");$("#token-dialog").showModal();});
  $("#edit-form").addEventListener("submit",saveEdit);
  $$(".close-dialog").forEach(button=>button.addEventListener("click",()=>$("#edit-dialog").close()));
  $("#edit-fields").addEventListener("change",event=>{
    if (event.target.dataset.field !== "model" && event.target.dataset.field !== "kind") return;
    const edit=state.edit, current={...(edit?.original||{}),...formValues(),[event.target.dataset.field]:event.target.value};
    if (edit) { const kind=edit.kind; edit.original=edit.original; openEdit(kind,current); $("#edit-fields [data-field='id']").value=current.id||""; }
  });

  function route() {
    const requested=location.hash.replace(/^#/,"");state.page=Object.hasOwn(pageNames,requested)?requested:"overview";
    if(state.config)render();
  }
  window.addEventListener("hashchange",route);
  $("#connection-address").textContent = `API · ${location.host || "same origin"}`;
  refresh({quiet:true});
  window.setTimeout(()=>{if(!state.token&&!$("#token-dialog").open)$("#token-dialog").showModal();},240);
  route();
})();
