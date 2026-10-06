(() => {
  "use strict";
  const {t, html, msg} = window.MusashiI18n;

  const pageNames = {overview: "Overview", machines: "Machines", destinations: "Destinations", records: "Recent data", config: "Configuration"};
  const state = {csrfToken: "", authenticated: false, page: "overview", health: null, config: null, status: null, records: [], scans: [], spoolSamples: [], busy: false, edit: null, refreshTimer: null, machineFilter: "all", machineQuery: "", destinationFilter: "all", destinationQuery: "", confirmRefresh: null};
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const esc = value => String(value ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
  const number = value => Number.isFinite(Number(value)) ? new Intl.NumberFormat(window.MusashiI18n.locale, {maximumFractionDigits: 0}).format(Number(value)) : "—";
  const date = value => { if (!value) return "—"; const parsed = new Date(value); return Number.isNaN(parsed.valueOf()) ? "—" : new Intl.DateTimeFormat(window.MusashiI18n.locale, {dateStyle:"medium",timeStyle:"short"}).format(parsed); };
  const ago = value => { if (!value) return t("No data yet"); const seconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000)); if (!Number.isFinite(seconds)) return "—"; if (seconds < 60) return msg`${seconds} seconds ago`; if (seconds < 3600) return msg`${Math.floor(seconds / 60)} minutes ago`; if (seconds < 86400) return msg`${Math.floor(seconds / 3600)} hours ago`; return msg`${Math.floor(seconds / 86400)} days ago`; };
  const entries = value => Object.entries(value || {});
  let noticeVersion = 0;
  const setNotice = (message, kind = "", duration = 4500) => { const version = ++noticeVersion; const node = $("#notice"); node.textContent = message; node.className = msg`notice ${kind}`; node.hidden = !message; if (duration) window.setTimeout(() => { if (noticeVersion === version) node.hidden = true; }, duration); };
  async function syncSession() {
    let response;
    try { response = await fetch("/api/auth/session", {cache:"no-store", credentials:"same-origin"}); }
    catch { throw new Error(t("Could not reach the service. Check your network and try again.")); }
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(t("Could not check the operator session. Try again."));
    state.authenticated = body.authenticated === true;
    state.csrfToken = state.authenticated && typeof body.csrf_token === "string" ? body.csrf_token : "";
    return state.authenticated;
  }

  async function refreshSessionAfterForbidden() {
    try {
      if (!await syncSession()) clearSessionState({showLogin:true});
    } catch { /* Keep the current page state; the failed action is never replayed. */ }
  }

  const api = async (path, options = {}) => {
    const headers = new Headers(options.headers || {});
    const method = (options.method || "GET").toUpperCase();
    if (method !== "GET" && method !== "HEAD" && path !== "/api/auth/login" && state.csrfToken) headers.set("X-CSRF-Token", state.csrfToken);
    if (options.body !== undefined) headers.set("Content-Type", "application/json");
    let response;
    try { response = await fetch(path, {...options, method, headers, credentials:"same-origin", body: options.body === undefined ? undefined : JSON.stringify(options.body), cache:"no-store"}); }
    catch { const error = new Error(t("Could not reach the service. Check your network and try again.")); error.retryableLoginFailure = path === "/api/auth/login"; throw error; }
    const type = response.headers.get("content-type") || "";
    const body = type.includes("application/json") ? await response.json().catch(() => ({})) : {};
    if (response.status === 401) {
      if (path === "/api/auth/login") throw new Error(t("Invalid username or password."));
      clearSessionState({showLogin:true});
      throw new Error(t("Your session has expired. Sign in again."));
    }
    if (response.status === 403) {
      await refreshSessionAfterForbidden();
      throw new Error(t("This action was denied. Review your session and try again. The action was not repeated."));
    }
    if (!response.ok) {
      if (response.status === 422 && body.errors) throw new Error(Object.entries(body.errors).map(([key, message]) => msg`${key}: ${message}`).join(" · "));
      throw new Error(body.error || msg`Request failed (${response.status})`);
    }
    return body;
  };

  function clearSessionState({showLogin = false} = {}) {
    state.csrfToken = ""; state.authenticated = false;
    state.config = null; state.status = null; state.records = []; state.scans = []; state.spoolSamples = [];
    state.edit = null; state.confirmRefresh = null;
    if (state.refreshTimer) clearInterval(state.refreshTimer);
    state.refreshTimer = null;
    $("#machine-count").textContent = "0"; $("#destination-count").textContent = "0";
    $$("input[type='password']").forEach(input => { input.value = ""; });
    $("#edit-fields").replaceChildren();
    $("#page-content").replaceChildren();
    if ($("#edit-dialog").open) $("#edit-dialog").close();
    if ($("#confirm-dialog").open) $("#confirm-dialog").close();
    if (showLogin && !$("#login-dialog").open) $("#login-dialog").showModal();
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
      if (state.authenticated) {
        const [config, status, records, scans] = await Promise.all([
          api("/api/config"), api("/api/status"), api("/api/records"), api("/api/scans")
        ]);
        state.config = config; state.status = status; state.records = records.records || []; state.scans = scans.scans || [];
        const spool = status.spool || {};
        const sample = {at: Date.now(), diskBytes: Number(spool.disk_bytes), records: Number(spool.records), pending: Number(spool.pending)};
        if (Number.isFinite(sample.diskBytes) && Number.isFinite(sample.records) && Number.isFinite(sample.pending)) {
          state.spoolSamples = [...state.spoolSamples, sample]
            .filter(item => sample.at - item.at <= 120_000)
            .slice(-32);
        }
        $("#machine-count").textContent = number(config.machines?.length || 0);
        $("#destination-count").textContent = number(config.destinations?.length || 0);
        $("#connection-dot").className = msg`live-dot ${state.health.process === "ok" ? "online" : "offline"}`;
        $("#connection-label").textContent = state.health.process === "ok" ? t("Service online") : t("Service error");
        $("#last-updated").textContent = msg`Updated ${new Intl.DateTimeFormat(window.MusashiI18n.locale, {hour:"2-digit",minute:"2-digit",second:"2-digit"}).format(new Date())}`;
        $("#refresh-dot").classList.add("active");
        if (!quiet) setNotice(t("Data refreshed."), "", 1800);
        render();
      } else {
        $("#connection-dot").className = msg`live-dot ${state.health.process === "ok" ? "online" : "offline"}`;
        $("#connection-label").textContent = state.health.process === "ok" ? t("Service online") : t("Service error");
        $("#last-updated").textContent = t("Sign in to view system data");
      }
    } catch (error) {
      if (!quiet) setNotice(error.message, "error", 6500);
      if (state.authenticated) {
        if (state.page === "config") render();
        else renderError(error.message);
      }
    } finally { setBusy(false); }
  }

  function renderError(message) {
    const content = $("#page-content");
    content.innerHTML = msg`<div class="page-heading"><div><div class="kicker">CONNECTION ISSUE</div><h1>${esc(t(pageNames[state.page]))}</h1><p>This page could not load current service data.</p></div></div><section class="panel"><div class="panel-empty"><strong>Data unavailable</strong>${esc(message)}<div style="margin-top:15px"><button class="button button-primary" data-action="refresh">Try again</button></div></div></section>`;
  }

  function pageHeading(kicker, title, description, actions = "") {
    return msg`<div class="page-heading"><div><div class="kicker">${esc(kicker)}</div><h1>${esc(title)}</h1><p>${esc(description)}</p></div>${actions ? msg`<div class="heading-actions">${actions}</div>` : ""}</div>`;
  }

  function workersActive(current) {
    const machines = Object.values(current.status?.machines || {});
    const destinations = Object.values(current.status?.destinations || {});
    return [...machines, ...destinations].some(worker => worker.worker_alive);
  }

  function statusBadge(status = {}) {
    const stateName = status.state || (status.worker_alive ? "running" : "stopped");
    const labels = {running:t("Running"), starting:t("Starting"), stopped:t("Stopped"), fault:t("Fault")};
    const cls = stateName === "running" ? "good" : stateName === "fault" ? "danger" : stateName === "starting" ? "warning" : "";
    return msg`<span class="badge ${cls}"><i class="badge-dot"></i>${labels[stateName] || esc(stateName)}</span>`;
  }

  function metric(label, value, unit, foot, mark) {
    return msg`<article class="metric"><span class="metric-mark">${esc(mark)}</span><div class="metric-label">${esc(label)}</div><div class="metric-value">${esc(value)}<span class="metric-unit">${esc(unit)}</span></div><div class="metric-foot">${esc(foot)}</div></article>`;
  }

  function emptyPanel(title, detail, action = "") {
    return msg`<div class="panel-empty"><strong>${esc(title)}</strong>${esc(detail)}${action ? msg`<div style="margin-top:13px">${action}</div>` : ""}</div>`;
  }

  const pageHelpers = Object.freeze({
    esc, number, date, ago, pageHeading, statusBadge, metric, emptyPanel,
    workersActive, machineStatus, destinationStatus, machineState, destinationState,
  });

  function machineStatus(current, machine) { return current.status?.machines?.[machine.id] || {}; }
  function destinationStatus(current, destination) { return current.status?.destinations?.[destination.id] || {}; }

  function machineState(current, machine) {
    const live = machineStatus(current, machine);
    return live.state || (live.worker_alive ? "running" : "stopped");
  }

  function destinationState(current, destination) {
    const live = destinationStatus(current, destination);
    if (live.error) return "fault";
    return live.state || (live.worker_alive ? "running" : "stopped");
  }

  function render() {
    const page = window.MusashiPages?.[state.page];
    if (!page) {
      renderError(msg`The ${t(pageNames[state.page])} page is unavailable.`);
      return;
    }
    const active = document.activeElement;
    const focusTarget = active instanceof HTMLElement && active !== document.body
      ? {
          id: active.id,
          action: active.dataset.action,
          itemId: active.dataset.id,
          machineFilter: active.dataset.machineFilter,
          destinationFilter: active.dataset.destinationFilter,
          selectionStart: typeof active.selectionStart === "number" ? active.selectionStart : null,
          selectionEnd: typeof active.selectionEnd === "number" ? active.selectionEnd : null,
        }
      : null;
    const renderer = typeof page === "function" ? page : page.render;
    const markup = renderer({state, helpers: pageHelpers});
    $("#page-content").innerHTML = msg`<div class="page-view page-view--${state.page}">${markup}</div>`;
    if (focusTarget) {
      const selector = focusTarget.id ? msg`#${CSS.escape(focusTarget.id)}`
        : focusTarget.action ? msg`[data-action="${CSS.escape(focusTarget.action)}"]${focusTarget.itemId ? msg`[data-id="${CSS.escape(focusTarget.itemId)}"]` : ""}`
          : focusTarget.machineFilter ? msg`[data-machine-filter="${CSS.escape(focusTarget.machineFilter)}"]`
            : focusTarget.destinationFilter ? msg`[data-destination-filter="${CSS.escape(focusTarget.destinationFilter)}"]`
              : null;
      const replacement = selector ? $(selector, $("#page-content")) : null;
      if (replacement) {
        replacement.focus({preventScroll:true});
        if (focusTarget.selectionStart !== null && typeof replacement.setSelectionRange === "function") {
          replacement.setSelectionRange(focusTarget.selectionStart, focusTarget.selectionEnd);
        }
      }
    }
    $("#crumb-page").textContent = t(pageNames[state.page]);
    $$(".nav-link").forEach(link => link.classList.toggle("active", link.dataset.page === state.page));
    $("#operator-button").setAttribute("aria-label", t("Sign out of operator session"));
  }

  function field(name, label, value, {type="text", full=false, required=false, options=null, hint=""} = {}) {
    hint = [hint, t(window.MusashiConfigHelp?.[name])].filter(Boolean).join(" · ");
    const attr = msg`id="config-field-${esc(name)}" data-field="${esc(name)}" aria-describedby="config-hint-${esc(name)}"`;
    let control;
    if (options) control = msg`<select ${attr} ${required?"required":""}>${options.map(([key,text])=>msg`<option value="${esc(key)}" ${String(value)===String(key)?"selected":""}>${esc(text)}</option>`).join("")}</select>`;
    else control = msg`<input ${attr} type="${type}" value="${esc(value ?? "")}" ${required?"required":""} ${type === "number" ? 'min="0" step="any"' : ""} autocomplete="off">`;
    return msg`<div class="form-field ${full?"full":""}"><label for="config-field-${esc(name)}">${esc(label)}${required?" *":""}</label>${control}${hint?msg`<div id="config-hint-${esc(name)}" class="field-hint">${esc(hint)}</div>`:""}</div>`;
  }

  function openEdit(kind, item = null) {
    if (state.status?.running) { setNotice(t("Stop acquisition before editing configuration."), "warning"); return; }
    state.edit = {kind, itemId:item?.id || null, original:item?structuredClone(item):null};
    const isMachine = kind === "machine";
    const values = item || (isMachine ? {model:"III",poll_interval_seconds:1,inventory_interval_seconds:3600,channel_count:1,simulated:false} : {kind:"mqtt",port:1883,tls:false});
    $("#edit-title").textContent = msg`${item?t("Edit"):t("Add")} ${isMachine?t("machine"):t("destination")}`;
    $("#edit-kicker").textContent = isMachine ? t("MACHINE CONFIGURATION") : t("DESTINATION CONFIGURATION");
    const fields = [];
    fields.push(field("id",t("ID"),values.id,{required:true,full:true,hint:t("Use letters and numbers, for example iii-line-1.")}));
    if (isMachine) {
      fields.push(field("model",t("Model"),values.model,{required:true,options:[["III","Musashi III"],["IV","Musashi IV"]]}));
      fields.push(field("simulated",t("Data source"),values.simulated ?? false,{required:true,options:[["false",t("Physical device")],["true",t("Synthetic simulator")]],full:true,hint:t("Choose Synthetic simulator when the machine connects to a service under simulations/.")}));
      fields.push(field("poll_interval_seconds",t("Status poll interval (seconds)"),values.poll_interval_seconds ?? 1,{type:"number",required:true}));
      fields.push(field("inventory_interval_seconds",t("Inventory interval (seconds)"),values.inventory_interval_seconds ?? 3600,{type:"number",required:true,full:true}));
      if (values.model === "IV") {
        fields.push(field("host",t("IPv4 address"),values.host,{required:true,hint:t("Enter an IP address, not a hostname.")}));
        fields.push(field("port",t("Port"),values.port ?? 1024,{type:"number",required:true}));
        fields.push(field("channel_count",t("Channel count"),values.channel_count,{type:"number",required:true}));
        fields.push(field("recipe_count",t("Recipe count"),values.recipe_count,{type:"number",required:true}));
      } else {
        fields.push(field("port",t("Serial device"),values.port,{required:true,full:true,hint:t("Use /dev/serial/by-id/... for hardware, a local pseudo-terminal, or socket://musashi-iii:9000 in Docker dev.")}));
        fields.push(field("channel_count",t("Channel count"),values.channel_count,{type:"number",required:true,full:true}));
      }
    } else {
      fields.push(field("kind",t("Destination type"),values.kind,{required:true,options:[["mqtt","MQTT"],["postgres","PostgreSQL"],["influxdb","InfluxDB"]]}));
      if (values.kind === "mqtt") {
        fields.push(field("host",t("Broker host"),values.host,{required:true}));
        fields.push(field("port",t("Port"),values.port ?? 1883,{type:"number",required:true}));
        fields.push(field("topic",t("Topic"),values.topic,{required:true,full:true}));
      } else if (values.kind === "influxdb") {
        fields.push(field("url",t("InfluxDB URL"),values.url,{required:true,full:true}));
        fields.push(field("org",t("Organization"),values.org,{required:true}));
        fields.push(field("bucket",t("Bucket"),values.bucket,{required:true}));
      }
      const secretHint = item && values.secret_ref === "********" ? t("The existing secret is preserved. Enter a new path only when replacing it.") : t("Path to the secret file on the service host.");
      fields.push(field("secret_ref",t("Secret file path"),item?"":values.secret_ref,{required:!item,full:true,hint:secretHint}));
    }
    $("#edit-fields").innerHTML = fields.join("");
    $("#edit-error").textContent = "";
    $("#edit-dialog").showModal();
  }

  function formValues() {
    const values = {};
    $$("[data-field]", $("#edit-fields")).forEach(input => { if (input.value !== "") values[input.dataset.field] = input.type === "number" ? Number(input.value) : input.dataset.field === "simulated" ? input.value === "true" : input.value; });
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
      if (index < 0) { $("#edit-error").textContent = t("The original entry was not found. Reload the configuration and try again."); return; }
      list[index] = item;
    } else list.push(item);
    const payload = {...state.config, [listName]:list};
    try {
      const result = await api("/api/config", {method:"PUT",body:payload});
      state.config = result; $("#edit-dialog").close(); state.edit = null; await refresh({quiet:true}); setNotice(t("Configuration saved."));
    } catch(error) { $("#edit-error").textContent = error.message; }
  }

  function removeItem(kind, id) {
    if (state.status?.running) { setNotice(t("Stop acquisition before editing configuration."), "warning"); return; }
    const isMachine = kind === "machine", key = isMachine ? "machines" : "destinations";
    state.confirmRefresh = () => {
      $("#confirm-title").textContent = msg`Remove ${isMachine?t("machine"):t("destination")} ${id}`;
      $("#confirm-copy").textContent = isMachine ? t("Collection from this machine will stop after the next service start.") : t("Removing this destination stops its delivery lane. Previously delivered records cannot be recalled.");
    };
    state.confirmRefresh();
    const form = $("#confirm-form");
    form.onsubmit = async event => {
      event.preventDefault();
      const submitter = event.submitter;
      if (submitter?.value !== "confirm") { $("#confirm-dialog").close(); return; }
      try {
        const payload = {...state.config,[key]:state.config[key].filter(entry=>entry.id!==id)};
        state.config = await api("/api/config",{method:"PUT",body:payload});
        $("#confirm-dialog").close(); await refresh({quiet:true}); setNotice(t("Configuration removed."));
      } catch(error) { $("#confirm-dialog").close(); setNotice(error.message,"error",7000); }
    };
    $("#confirm-dialog").showModal();
  }

  function clearSpool() {
    if (workersActive(state)) { setNotice(t("Stop all machine and destination workers before clearing the spool."), "warning"); return; }
    const spool = state.status?.spool || {};
    state.confirmRefresh = () => {
      $("#confirm-title").textContent = t("Clear all spool data?");
      $("#confirm-copy").textContent = msg`This permanently deletes ${number(spool.records || 0)} local records and ${number(spool.pending || 0)} pending deliveries, plus all scan and fault history. Destination settings remain saved. Data already delivered to external destinations is not deleted.`;
    };
    state.confirmRefresh();
    const form = $("#confirm-form"), confirm = form.querySelector('[value="confirm"]');
    form.onsubmit = async event => {
      event.preventDefault();
      if (event.submitter?.value !== "confirm") { $("#confirm-dialog").close(); return; }
      confirm.disabled = true;
      try {
        const result = await api("/api/spool", {method:"DELETE"});
        $("#confirm-dialog").close();
        state.spoolSamples = [];
        await refresh({quiet:true});
        setNotice(result.storage_reclaimed ? t("Spool cleared.") : t("Spool data cleared, but SQLite could not reclaim the file space."), result.storage_reclaimed ? "" : "warning", 7000);
      } catch(error) { $("#confirm-dialog").close(); setNotice(error.message,"error",7000); }
      finally { confirm.disabled = false; }
    };
    $("#confirm-dialog").showModal();
  }

  async function control(action) {
    const label = action === "start" ? "Start acquisition" : "Stop acquisition";
    if (action === "start" && !(state.config?.machines || []).length) { setNotice(t("Add a machine before starting acquisition."), "warning"); location.hash = "#machines"; return; }
    $("#refresh-button").disabled = true;
    try { await api(msg`/api/control/${action}`,{method:"POST",body:{}}); await refresh({quiet:true}); setNotice(t(`${label} complete.`)); }
    catch(error) { setNotice(error.message,"error",7000); }
    finally { $("#refresh-button").disabled = false; }
  }

  document.addEventListener("click", event => {
    const destinationFilter = event.target.closest("[data-destination-filter]");
    if (destinationFilter) { state.destinationFilter = destinationFilter.dataset.destinationFilter; render(); return; }
    const filter = event.target.closest("[data-machine-filter]");
    if (filter) { state.machineFilter = filter.dataset.machineFilter; render(); return; }
    const target = event.target.closest("[data-action], [data-nav]");
    if (!target) return;
    if (target.dataset.nav) { state.page = target.dataset.nav; location.hash = msg`#${state.page}`; render(); return; }
    const {action,id} = target.dataset;
    if (action === "refresh") refresh();
    else if (action === "start" || action === "stop") control(action);
    else if (action === "add-machine") openEdit("machine");
    else if (action === "edit-machine") openEdit("machine",state.config.machines.find(item=>item.id===id));
    else if (action === "remove-machine") removeItem("machine",id);
    else if (action === "add-destination") openEdit("destination");
    else if (action === "edit-destination") openEdit("destination",state.config.destinations.find(item=>item.id===id));
    else if (action === "remove-destination") removeItem("destination",id);
    else if (action === "clear-spool") clearSpool();
  });

  document.addEventListener("input", event => {
    if (event.target.id === "machine-search") {
      state.machineQuery = event.target.value;
      const results = $("#machine-results");
      if (results) results.innerHTML = window.MusashiPages.machines.renderResults({state, helpers: pageHelpers}, state.config?.machines || []);
    } else if (event.target.id === "destination-search") {
      state.destinationQuery = event.target.value;
      const results = $("#destination-results");
      if (results) results.innerHTML = window.MusashiPages.destinations.renderResults({state, helpers: pageHelpers}, state.config?.destinations || []);
    }
  });

  $("#refresh-button").addEventListener("click",()=>refresh());
  $("#login-dialog").addEventListener("cancel",event=>{if(!state.authenticated)event.preventDefault();});
  $("#login-form").addEventListener("submit",async event=>{
    event.preventDefault();
    const username=$("#username-input").value.trim(), password=$("#password-input").value;
    const error=$("#login-error"), submit=$("#login-submit");
    $("#password-input").value=""; error.textContent=""; submit.disabled=true;
    submit.childNodes[0].textContent=t("Signing in")+" ";
    try {
      const result=await api("/api/auth/login",{method:"POST",body:{username,password}});
      state.authenticated=result.authenticated===true;
      state.csrfToken=typeof result.csrf_token==="string"?result.csrf_token:"";
      $("#login-dialog").close();
      await refresh({quiet:true});
      if (state.authenticated && state.config && !state.refreshTimer) state.refreshTimer=window.setInterval(()=>refresh({quiet:true}),8000);
    } catch (failure) {
      const retryable=failure.retryableLoginFailure===true;
      if (retryable) $("#password-input").value=password;
      submit.childNodes[0].textContent=retryable?t("Retry sign in")+" ":t("Sign in")+" ";
      error.textContent=failure.message || t("Sign-in failed. Check your connection and try again.");
      if (!$("#login-dialog").open) $("#login-dialog").showModal();
      $(retryable?"#password-input":"#username-input").focus();
    } finally { submit.disabled=false; }
  });
  $("#password-visibility").addEventListener("click",event=>{const input=$("#password-input");input.type=input.type==="password"?"text":"password";event.currentTarget.textContent=input.type==="password"?t("Show"):t("Hide");});
  $("#operator-button").addEventListener("click",async()=>{
    const button=$("#operator-button"); button.disabled=true;
    try {
      await api("/api/auth/logout",{method:"POST",body:{}});
      clearSessionState({showLogin:true});
      setNotice(t("You have signed out."));
    } catch(error) { setNotice(error.message,"error",7000); }
    finally { button.disabled=false; }
  });
  $("#edit-form").addEventListener("submit",saveEdit);
  $$(".close-dialog").forEach(button=>button.addEventListener("click",()=>$("#edit-dialog").close()));
  $("#edit-fields").addEventListener("change",event=>{
    if (event.target.dataset.field !== "model" && event.target.dataset.field !== "kind") return;
    const edit=state.edit, current={...(edit?.original||{}),...formValues(),[event.target.dataset.field]:event.target.value};
    if (edit) { const kind=edit.kind; edit.original=edit.original; openEdit(kind,current); $("#edit-fields [data-field='id']").value=current.id||""; }
  });

  function route() {
    const requested=location.hash.replace(/^#/,"").replace(/^config-[a-z]+$/, "config");state.page=Object.hasOwn(pageNames,requested)?requested:"overview";
    if(state.config || (state.authenticated && state.page === "config"))render();
  }
  window.addEventListener("musashi:languagechange", () => {
    if (state.config) render();
    $("#password-visibility").textContent = t($("#password-input").type === "password" ? "Show" : "Hide");
    $("#login-submit").childNodes[0].textContent = t($("#login-submit").disabled ? "Signing in" : "Sign in") + " ";
    if ($("#edit-dialog").open && state.edit) {
      const edit = state.edit, draft = formValues(), error = $("#edit-error").textContent;
      const inputs = $$("[data-field]", $("#edit-fields")).map(input => [input.dataset.field, input.value]);
      const focusedField = document.activeElement?.dataset.field;
      openEdit(edit.kind, {...(edit.original || {}), ...draft});
      state.edit = edit;
      inputs.forEach(([name, value]) => {
        const input = $(`[data-field="${CSS.escape(name)}"]`, $("#edit-fields"));
        if (input) input.value = value;
      });
      if (focusedField) $(`[data-field="${CSS.escape(focusedField)}"]`, $("#edit-fields"))?.focus();
      $("#edit-error").textContent = window.MusashiI18n.retranslate(error);
    }
    if ($("#confirm-dialog").open) state.confirmRefresh?.();
    ["#confirm-title", "#confirm-copy", "#login-error", "#notice", "#connection-label", "#last-updated"].forEach(selector => {
      const node = $(selector);
      node.textContent = window.MusashiI18n.retranslate(node.textContent);
    });
  });
  window.addEventListener("hashchange",route);
  $("#connection-address").textContent = msg`API · ${location.host || "same origin"}`;
  async function start() {
    try {
      if (await syncSession()) {
        await refresh({quiet:true});
        if (state.authenticated && state.config) state.refreshTimer=window.setInterval(()=>refresh({quiet:true}),8000);
      } else {
        await refresh({quiet:true});
        $("#login-dialog").showModal();
      }
    } catch(error) {
      await refresh({quiet:true});
      $("#login-dialog").showModal();
      $("#login-error").textContent=error.message;
    }
  }
  start();
  route();
})();
