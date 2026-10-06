(() => {
  "use strict";
  const {t, html, msg} = window.MusashiI18n;
  const descriptions = {
    version: "Configuration format version. This release supports version 1 only.",
    revision: "Configuration revision. Increases automatically on save to prevent overwriting changes made by another operator.",
    auto_start: "Automatic acquisition on startup. This release supports false only; select Start acquisition manually.",
    machines: "Machines to collect data from. Supports up to 8 machines. Configure each machine below.",
    destinations: "Delivery targets. Each destination has its own delivery queue.",
    id: "Reference name. Must be nonempty and unique within its group. Links records and status to this entry. Use a recognizable name, such as line-1.",
    model: "Machine model. III uses a serial connection; IV uses an IPv4 network connection.",
    simulated: "Set true to label records as simulated. Connect to a running simulator separately. Set false for a physical device; this setting does not establish hardware verification.",
    poll_interval_seconds: "Time between status reads, in seconds. Default: 1. Minimum: 1. Shorter intervals increase communication load.",
    inventory_interval_seconds: "Time between channel/recipe inventory reads, in seconds. Default: 3600. Minimum: 60. Larger inventories take longer to read.",
    host: "Connection address. IV requires an IPv4 address, such as 192.168.1.20. MQTT accepts a broker hostname or IP address.",
    port: "III: serial path such as /dev/serial/by-id/... or simulator URL socket://musashi-iii:9000. IV: 1024, 1025, or 1026 (default: 1024). MQTT: broker port, defaulting to 1883, or 8883 with TLS.",
    channel_count: "Number of channels to read during inventory. Use a count supported by evidence from the device. III: 1–100. IV: 1–400. This count is configured manually.",
    recipe_count: "Number of recipes to read during IV inventory. Requires a count supported by device evidence, from 1 to 100.",
    kind: "Destination type: mqtt, postgres, or influxdb. Choose the system that will receive the records.",
    topic: "MQTT topic for delivery using QoS 1. Large records are split into chunks; receivers must reassemble them using record_id and index.",
    tls: "Enable TLS encryption for MQTT. Default: false. Use the matching broker port and certificate settings.",
    ca_file: "Path to a CA certificate file on the service host for MQTT certificate verification. Uses system CAs when omitted.",
    secret_ref: "Path to a UTF-8 secret file readable by the service. MQTT: JSON containing username/password. PostgreSQL: DSN. InfluxDB: token. Existing values and paths are hidden in the UI. Leave the edit field blank to preserve the existing reference.",
    url: "InfluxDB URL including http:// or https:// and the port, for example http://influxdb:8086.",
    org: "InfluxDB organization name. The token must have permission to access it.",
    bucket: "InfluxDB bucket name. The service checks for the bucket and creates it if missing; the token needs the appropriate permissions.",
    max_payload_bytes: "Maximum delivery payload size, in bytes. MQTT: 1024–262144, default 262144; messages are split into chunks. InfluxDB: minimum and default 8388608; larger payloads fail delivery.",
    connect_timeout_seconds: "PostgreSQL connection timeout, in seconds. Default: 10.",
    timeout_ms: "InfluxDB request timeout, in milliseconds. Default: 10000 (10 seconds).",
    verify_ssl: "Verify the InfluxDB HTTPS certificate. Default: true.",
  };
  window.MusashiConfigHelp = Object.freeze(descriptions);
  window.MusashiPages ||= {};
  // Reference entries describe supported software settings, independent of live config.
  // Keep defaults and limits aligned with config/store.py, destinations/factory.py,
  // and __main__.py when those contracts change.
  const parameter = (name, type, requirement, fallback, example, detail = descriptions[name]) => ({name, type, requirement, fallback, example, detail});
  const sections = [
    {id:"system", title:"Configuration file", intro:"The service stores config.json in MUSASHI_DATA_DIR. These fields describe the whole configuration document.", fields:[
      parameter("version", "integer", "Required", "No default; use 1", "1"),
      parameter("revision", "integer", "Managed by service", "0 for a new configuration", "3", "The API returns the saved revision. Include that revision when updating configuration through the API. A successful save increments it; a stale revision is rejected."),
      parameter("auto_start", "boolean", "Optional", "false", "false"),
      parameter("machines", "array", "Required", "[] for a new configuration", "[]"),
      parameter("destinations", "array", "Required", "[] for a new configuration", "[]"),
    ]},
    {id:"machines", title:"Shared machine parameters", intro:"Each entry in machines uses these parameters. IDs must be unique within the machine list.", fields:[
      parameter("id", "string", "Required", "No default", '"line-1"'),
      parameter("model", "string", "Required", "No default", '"III" or "IV"'),
      parameter("simulated", "boolean", "Optional", "false", "true"),
      parameter("poll_interval_seconds", "number · seconds", "Optional", "1", "2"),
      parameter("inventory_interval_seconds", "number · seconds", "Optional", "3600", "3600"),
    ]},
    {id:"iii", title:"Musashi III", intro:"Serial connection settings for model III. Set inventory counts using evidence from your device.", fields:[
      parameter("port", "string", "Required", "No default", '"/dev/serial/by-id/your-device"', "Serial device path, local pseudo-terminal, or simulator socket URL such as socket://musashi-iii:9000. Each III machine needs a unique serial endpoint."),
      parameter("channel_count", "integer", "Required", "No default", "1", "Number of channels included in inventory reads. Allowed range: 1–100. Use a count supported by device evidence; the service does not discover this count automatically."),
    ]},
    {id:"iv", title:"Musashi IV", intro:"Network connection settings for model IV. Each host and port pair must be unique.", fields:[
      parameter("host", "string · IPv4", "Required", "No default", '"192.168.1.20"', "IPv4 address of the IV device. Hostnames and IPv6 addresses are not accepted. Obtain the address from the device network settings."),
      parameter("port", "integer", "Optional", "1024", "1024", "IV network port. Only 1024, 1025, and 1026 are accepted. Select the port configured on the device."),
      parameter("channel_count", "integer", "Required", "No default", "1", "Number of channels included in inventory reads. Allowed range: 1–400. Use a count supported by evidence from the device."),
      parameter("recipe_count", "integer", "Required", "No default", "1"),
    ]},
    {id:"destinations", title:"Shared destination parameters", intro:"Each entry in destinations uses these parameters. IDs must be unique within the destination list.", fields:[
      parameter("id", "string", "Required", "No default", '"plant-mqtt"'),
      parameter("kind", "string", "Required", "No default", '"mqtt", "postgres", or "influxdb"'),
      parameter("secret_ref", "string · file path", "Required", "No default", '"/run/secrets/mqtt_credentials"'),
    ]},
    {id:"mqtt", title:"MQTT", intro:"Parameters for kind mqtt. Ask your broker administrator for the host, topic, port, and credentials.", fields:[
      parameter("host", "string", "Required", "No default", '"mqtt.example.com"', "Broker hostname or IP address. This is the canonical host field for MQTT configuration."),
      parameter("port", "integer", "Optional", "1883; 8883 with TLS", "8883", "Port used to connect to the broker. Match the broker listener. The configuration validator does not enforce a port range; connection errors are reported when delivery starts."),
      parameter("topic", "string", "Required", "No default", '"factory/musashi"'),
      parameter("tls", "boolean", "Optional", "false", "true"),
      parameter("ca_file", "string · file path", "Optional", "System CA certificates", '"/run/secrets/broker_ca.pem"'),
      parameter("max_payload_bytes", "integer · bytes", "Optional", "262144", "65536", "Maximum size of each MQTT envelope. Accepted range: 1024–262144 bytes. Records are split into Base64 JSON chunks when needed. Receivers reassemble them using record_id, index, and count."),
    ]},
    {id:"postgres", title:"PostgreSQL", intro:"Parameters for kind postgres. The connection DSN belongs in the secret file referenced by secret_ref.", fields:[
      parameter("connect_timeout_seconds", "integer · seconds", "Optional", "10", "10"),
    ]},
    {id:"influxdb", title:"InfluxDB", intro:"Parameters for kind influxdb. Obtain the URL, organization, bucket, and token from your InfluxDB administrator.", fields:[
      parameter("url", "string · URL", "Required", "No default", '"https://influx.example.com"'),
      parameter("org", "string", "Required", "No default", '"factory"'),
      parameter("bucket", "string", "Required", "No default", '"musashi"'),
      parameter("timeout_ms", "integer · milliseconds", "Optional", "10000", "10000"),
      parameter("verify_ssl", "boolean", "Optional", "true", "true"),
      parameter("max_payload_bytes", "integer · bytes", "Optional", "8388608", "8388608", "Maximum size of an InfluxDB line. Must be at least 8388608 bytes to preserve accepted records. A record larger than the configured limit fails delivery and remains pending."),
    ]},
    {id:"environment", title:"Startup environment", intro:"Set these variables in the service process environment or Compose environment. Restart the service after changing them; they are not config.json fields.", fields:[
      parameter("MUSASHI_DATA_DIR", "string · directory path", "Optional", "./data", '"/var/lib/musashi"', "Directory holding config.json and spool.sqlite3. The service creates it if needed and requires permission to write there."),
      parameter("MUSASHI_BIND", "string · bind address", "Optional", "127.0.0.1", '"0.0.0.0"', "Address on which the management HTTP server listens. Loopback is the default. Configure trusted browser origins when accessing it through another address."),
      parameter("MUSASHI_PORT", "integer · TCP port", "Optional", "8080", "8080", "Port for the management HTTP server. Must be usable by the host and available to the service."),
      parameter("MUSASHI_PUBLIC_ORIGIN", "string · HTTPS origin", "Optional", "Not set", '"https://musashi.example.com"', "Trusted browser origin behind a TLS proxy. Must be an HTTPS origin with no path, credentials, query, or fragment. When omitted, the trusted default is http://127.0.0.1:<MUSASHI_PORT>."),
      parameter("MUSASHI_ALLOWED_ORIGINS", "string · comma-separated origins", "Optional", "Empty list", '"http://192.168.1.10:8080"', "Additional trusted browser origins, separated by commas. Use exact origins without paths. HTTP supports localhost, private IPs, or Tailscale IPs. The wildcard * is accepted only on its own and permits any matching browser origin and host."),
      parameter("OPERATOR_USERNAME", "string", "Optional", "admin", '"operator"', "Shared operator account name used to sign in to the console. It must not be empty."),
      parameter("OPERATOR_PASSWORD", "string · secret", "Optional", "00000000", '"your-operator-password"', "Shared operator password. It must not be empty. Set your own value in the service environment before deployment; this is separate from destination secret files."),
    ]},
  ];
  const examples = [
    ["Musashi III", {id:"line-iii", model:"III", port:"/dev/serial/by-id/your-device", channel_count:1}],
    ["Musashi IV", {id:"line-iv", model:"IV", host:"192.168.1.20", port:1024, channel_count:1, recipe_count:1}],
    ["MQTT", {id:"plant-mqtt", kind:"mqtt", host:"mqtt.example.com", topic:"factory/musashi", tls:true, secret_ref:"/run/secrets/mqtt_credentials"}],
    ["PostgreSQL", {id:"plant-postgres", kind:"postgres", secret_ref:"/run/secrets/postgres_dsn"}],
    ["InfluxDB", {id:"plant-influx", kind:"influxdb", url:"https://influx.example.com", org:"factory", bucket:"musashi", secret_ref:"/run/secrets/influx_token"}],
  ];
  window.MusashiPages.config = ({helpers: h}) => {
    const text = value => h.esc(t(value));
    const reference = section => msg`<section id="config-${section.id}" class="config-section"><header class="config-section-heading"><h2>${text(section.title)}</h2><p>${text(section.intro)}</p></header><div class="config-reference-list">${section.fields.map(field => msg`<article class="config-parameter"><header><h3><code>${h.esc(field.name)}</code></h3><span class="config-requirement ${field.requirement === "Required" ? "is-required" : ""}">${text(field.requirement)}</span></header><p class="config-description">${text(field.detail)}</p><dl class="config-parameter-meta"><div><dt>Type</dt><dd>${text(field.type)}</dd></div><div><dt>Default</dt><dd><code>${text(field.fallback)}</code></dd></div><div><dt>Example</dt><dd><code>${h.esc(field.example)}</code></dd></div></dl></article>`).join("")}</div></section>`;
    return msg`${h.pageHeading(t("PARAMETER REFERENCE"), t("Configuration reference"), t("Documentation for every supported configuration parameter, including defaults, constraints, and examples."))}
      <div class="config-doc-intro"><div><strong>Where to configure</strong><p>Set machine and destination values on their respective pages. Stop all workers before saving, then start acquisition on Overview. Environment variables take effect after a service restart.</p></div><nav aria-label="Configuration tools"><a href="#machines">Machines ↗</a><a href="#destinations">Destinations ↗</a></nav></div>
      <div class="config-layout"><aside class="config-contents"><nav aria-label="Configuration sections"><span class="config-nav-label">ON THIS PAGE</span>${sections.map(section => msg`<a href="#config-${section.id}">${text(section.title)}</a>`).join("")}<a href="#config-secrets">Secret file formats</a><a href="#config-examples">Configuration examples</a></nav></aside><div class="config-main">${sections.map(reference).join("")}
      <section id="config-secrets" class="config-section"><header class="config-section-heading"><h2>Secret file formats</h2><p>Keep destination credentials in UTF-8 files readable by the service. Use secret_ref to point to the file on the service host or inside its container.</p></header><div class="config-secret-formats"><article><h3>MQTT</h3><p>JSON object with username and password strings.</p><pre><code>${h.esc('{"username":"your-user","password":"your-password"}')}</code></pre></article><article><h3>PostgreSQL</h3><p>Connection DSN containing host, database, user, and credentials.</p><pre><code>${h.esc("postgresql://your-user:your-password@postgres:5432/musashi")}</code></pre></article><article><h3>InfluxDB</h3><p>Token text only.</p><pre><code>your-influx-token</code></pre></article></div><p class="config-doc-note">Inline password, token, secret, and dsn values in a destination are rejected. The API hides secret references; an unchanged redacted reference preserves the existing secret file path.</p></section>
      <section id="config-examples" class="config-section"><header class="config-section-heading"><h2>Configuration examples</h2><p>Illustrative values only. Replace addresses, paths, and inventory counts with values supported by your installation. These examples do not establish hardware verification.</p></header><div class="config-example"><h3>Document structure</h3><pre><code>${h.esc(JSON.stringify({version:1,revision:0,auto_start:false,machines:[],destinations:[]},null,2))}</code></pre><p>Add machine objects to machines and destination objects to destinations. Optional parameters use the defaults documented above when omitted.</p></div>${examples.map(([title,value]) => msg`<div class="config-example"><h3>${h.esc(title)}</h3><pre><code>${h.esc(JSON.stringify(value,null,2))}</code></pre></div>`).join("")}</section></div></div>`;
  };
})();
