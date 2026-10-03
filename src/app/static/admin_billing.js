// Render the private daily AWS summary on the dedicated Billing page.
// Authorization is enforced by the API before any cached account data is read.
// This module never queries AWS directly or refreshes paid billing data.
// Period labels and timestamps come from the cache, including stale snapshots.
// Null metrics mean unavailable samples, while numeric zero remains a real zero.
// Data is inserted as text; error links encode the function, region and period.

function element(tag, text, parent) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (parent) parent.append(node);
  return node;
}

function money(value) {
  return value === null || value === undefined ? "Unavailable" : new Intl.NumberFormat(
    "en-US", { style: "currency", currency: "USD", maximumFractionDigits: 4 },
  ).format(Number(value));
}

function metric(value, divisor = 1) {
  return value === null || value === undefined ? "No data" : (Number(value) / divisor).toLocaleString(
    "en-US", { maximumFractionDigits: 2 },
  );
}

function encodeConsole(value) {
  return encodeURIComponent(value).replace(/[!'()*~]/g, (char) => `%${char.charCodeAt(0).toString(16)}`);
}

function errorLink(fn, period, snapshot) {
  const count = fn[period].errors;
  if (!(count > 0)) return metric(count);
  const month = snapshot[period];
  const start = `${month.start}T00:00:00.000Z`;
  const end = new Date(Math.min(Date.parse(`${month.end}T00:00:00Z`),
    Date.parse(snapshot.collected_at)) - 1).toISOString();
  const query = 'fields @timestamp, @message, @logStream, @requestId\n'
    + '| filter @message like /(?i)(error|exception|timed out|timeout)/\n'
    + '| sort @timestamp desc\n| limit 200';
  // CloudWatch serializes queryDetail with JSURL strings inside its encoded fragment.
  const string = (value) => `'${encodeConsole(value).replace(/%/g, '*')}`;
  const detail = `~(start~${string(start)}~end~${string(end)}~timeType~'ABSOLUTE~tz~'UTC`
    + `~editorString~${string(query)}~source~(~${string(`/aws/lambda/${fn.name}`)}))`;
  const link = element('a', metric(count));
  link.href = `https://console.aws.amazon.com/cloudwatch/home?region=${encodeConsole(fn.region || snapshot.activity_region)}`
    + `#logs-insights:queryDetail=${detail}`;
  link.target = '_blank';
  link.rel = 'noopener noreferrer';
  link.setAttribute('aria-label', `${metric(count)} errors: view ${fn.name} logs for ${month.start.slice(0, 7)}`);
  return link;
}

function table(parent, caption, headings, rows) {
  const wrapper = element("div", undefined, parent);
  wrapper.className = "admin-table-scroll";
  const grid = element("table", undefined, wrapper);
  grid.className = "pure-table pure-table-striped";
  element("caption", caption, grid);
  const header = element("tr", undefined, element("thead", undefined, grid));
  headings.forEach((text) => { element("th", text, header).scope = "col"; });
  const body = element("tbody", undefined, grid);
  rows.forEach((values) => {
    const row = element("tr", undefined, body);
    values.forEach((text) => {
      const cell = element("td", undefined, row);
      if (text instanceof Node) cell.append(text);
      else cell.textContent = text;
    });
  });
}

function chargeRows(month, field) {
  return month[field].map((row) => [row.display_name || row.name, money(row.gross)]);
}

function subtotal(values, divisor) {
  const known = values.filter((value) => value !== null && value !== undefined);
  if (!known.length) return "No data";
  const missing = values.length - known.length;
  return metric(known.reduce((sum, value) => sum + value, 0), divisor)
    + (missing ? ` (${missing} ${missing === 1 ? "function" : "functions"}: no data)` : "");
}

function storagePoints(storage, bucketName) {
  const buckets = storage.buckets.filter((b) => !bucketName || b.name === bucketName);
  const days = new Map();
  buckets.forEach((bucket) => bucket.days.forEach((sample) => {
    if (!days.has(sample.day)) days.set(sample.day, { day: sample.day, size_bytes: null, objects: null, reporting: 0, object_reporting: 0 });
    const point = days.get(sample.day);
    if (sample.size_bytes !== null) {
      point.size_bytes = (point.size_bytes ?? 0) + sample.size_bytes;
      point.reporting += 1;
    }
    if (sample.objects !== null) {
      point.objects = (point.objects ?? 0) + sample.objects;
      point.object_reporting += 1;
    }
  }));
  return [...days.values()].sort((a, b) => a.day.localeCompare(b.day));
}

function storageChart(parent, points) {
  const svgNode = (tag, attrs, text, container) => {
    const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
    Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
    if (text !== undefined) node.textContent = text;
    container.append(node);
    return node;
  };
  const known = points.filter((p) => p.size_bytes !== null);
  if (!known.length) { element('p', 'No storage measurements available for this selection.', parent); return; }
  const svg = svgNode('svg', { viewBox: '0 0 900 260', role: 'img',
    'aria-label': 'Daily S3 storage in GB; gaps indicate missing reports. Exact values follow in the daily data table.',
    width: '100%' }, undefined, parent);
  const maximum = Math.max(...known.map((p) => p.size_bytes / 1e9), 0.001);
  const first = Date.parse(points[0].day);
  const span = Math.max(86400000, Date.parse(points.at(-1).day) - first);
  const x = (p) => 70 + (Date.parse(p.day) - first) / span * 800;
  const y = (p) => 215 - p.size_bytes / 1e9 / maximum * 185;
  [0, 0.5, 1].forEach((fraction) => {
    const position = 215 - 185 * fraction;
    svgNode('line', { x1: 70, x2: 870, y1: position, y2: position, stroke: '#ddd' }, undefined, svg);
    svgNode('text', { x: 60, y: position + 4, 'text-anchor': 'end', 'font-size': 12 },
      (maximum * fraction).toLocaleString('en-US', { maximumFractionDigits: 3 }), svg);
  });
  svgNode('text', { x: 20, y: 18, 'font-size': 13 }, 'GB', svg);
  svgNode('text', { x: 70, y: 245, 'font-size': 12 }, points[0].day, svg);
  svgNode('text', { x: 870, y: 245, 'text-anchor': 'end', 'font-size': 12 }, points.at(-1).day, svg);
  let previous = null;
  points.forEach((point) => {
    if (point.size_bytes === null) { previous = null; return; }
    if (previous && previous.reporting === point.reporting && Date.parse(point.day) - Date.parse(previous.day) === 86400000) {
      svgNode('line', { x1: x(previous), y1: y(previous), x2: x(point), y2: y(point), stroke: '#176c98', 'stroke-width': 2 }, undefined, svg);
    }
    const dot = svgNode('circle', { cx: x(point), cy: y(point), r: 3, fill: '#176c98' }, undefined, svg);
    svgNode('title', {}, `${point.day}: ${metric(point.size_bytes, 1e9)} GB; ${point.reporting} buckets reporting`, dot);
    previous = point;
  });
}

function renderStorage(parent, snapshot) {
  element('h3', 'S3 storage and objects', parent);
  const storage = snapshot.storage;
  if (!storage) { element('p', 'Storage data unavailable until the collector refreshes.', parent); return; }
  element('p', `Daily measurements: ${storage.start} – ${storage.end} UTC (end exclusive). `
    + 'Current general-purpose buckets across all regions; deleted buckets and directory buckets are excluded. '
    + 'GB = 1 billion bytes. Includes versions, metadata and incomplete multipart uploads; object counts also include delete markers. '
    + 'Shared buckets are not divided by stack. Missing measurements are not zero.', parent);
  table(parent, 'Latest reported S3 measurements', ['Bucket', 'Region', 'Storage (GB)', 'Objects', 'Measured (UTC)'],
    storage.buckets.map((bucket) => {
      const latest = [...bucket.days].reverse().find((d) => d.size_bytes !== null || d.objects !== null);
      const stale = latest && Date.parse(snapshot.collected_at) - Date.parse(latest.day) > 3 * 86400000;
      return [bucket.name, bucket.region, metric(latest?.size_bytes, 1e9), metric(latest?.objects),
        latest ? `${latest.day}${stale ? ' (stale)' : ''}` : 'No data'];
    }));
  const label = element('label', 'Storage history: ', parent);
  const select = element('select', undefined, label);
  select.setAttribute('aria-label', 'Storage history bucket');
  const all = element('option', 'All buckets (reported subtotal)', select);
  all.value = '';
  storage.buckets.forEach((bucket) => { const option = element('option', bucket.name, select); option.value = bucket.name; });
  const graph = element('div', undefined, parent);
  const update = () => {
    graph.replaceChildren();
    const points = storagePoints(storage, select.value);
    const latest = [...points].reverse().find((p) => p.size_bytes !== null);
    element('p', latest ? `Reported storage: ${metric(latest.size_bytes, 1e9)} GB on ${latest.day}; `
      + `${latest.reporting} of ${select.value ? 1 : storage.buckets.length} buckets reported size that day. `
      + `Objects: ${metric(latest.objects)} (${latest.object_reporting} buckets reporting).` : 'No data', graph);
    element('p', 'The subtotal includes only measurements reported on each date; coverage can change. '
      + 'The line breaks when the reporting count changes or no sizes are reported. Hover over points or expand daily data for values.', graph);
    storageChart(graph, points);
    const details = element('details', undefined, graph);
    element('summary', 'Daily storage data', details);
    table(details, 'Daily S3 measurements (UTC)', ['Date', 'Storage (GB)', 'Objects', 'Buckets reporting size'],
      points.map((p) => [p.day, metric(p.size_bytes, 1e9), metric(p.objects), String(p.reporting)]));
  };
  select.addEventListener('change', update);
  update();
}

function stackCell(fn, collectedAt) {
  const cell = element('div');
  element('strong', fn.stack, cell);
  const life = fn.stack_lifetime;
  if (!life) {
    element('div', 'Dates unavailable', cell);
    return cell;
  }
  const stamp = (value) => new Date(value).toISOString().slice(0, 16).replace('T', ' ');
  element('div', `Start: ${stamp(life.started_at)}`, cell);
  const deleted = life.status === 'DELETE_COMPLETE';
  element('div', `Stop: ${life.stopped_at ? stamp(life.stopped_at) : (deleted ? 'Unknown' : 'Still present')}`, cell);
  const end = life.stopped_at || (deleted ? null : collectedAt);
  const minutes = end ? Math.floor((Date.parse(end) - Date.parse(life.started_at)) / 60000) : NaN;
  const elapsed = Number.isFinite(minutes) && minutes >= 0
    ? `${Math.floor(minutes / 1440)}d ${Math.floor((minutes % 1440) / 60)}h ${minutes % 60}m` : 'Unavailable';
  element('div', `Elapsed: ${elapsed}`, cell);
  return cell;
}

function renderBilling(payload) {
  const status = document.getElementById("billing-status");
  status.textContent = payload.message;
  status.className = payload.state === "ready" ? "" : "admin-error";
  const links = document.getElementById("billing-links");
  links.replaceChildren();
  [
    ["Current month in Cost Explorer", payload.current_url],
    ["Previous month in Cost Explorer", payload.previous_url],
    ["AWS billing dashboards", payload.dashboards_url],
  ].forEach(([label, url]) => {
    const link = element("a", label, links);
    link.href = url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    links.append(document.createTextNode(" · "));
  });
  element("span", "AWS login required.", links);
  const content = document.getElementById("billing-content");
  const scope = document.getElementById("billing-scope");
  content.replaceChildren();
  scope.textContent = "";
  if (!payload.snapshot) return;
  const snapshot = payload.snapshot;
  scope.textContent = `Account ${snapshot.account_id}: spend covers all regions and services. `
    + `Function activity covers ${snapshot.activity_region}. Updated ${snapshot.collected_at} (UTC).`;
  table(content, "AWS spend (USD)", ["UTC period (end exclusive)", "Charges"],
    [snapshot.current, snapshot.previous].map((month) => [
      `${month.start} – ${month.end}${month.estimated ? " (estimated)" : ""}`,
      money(month.total.gross),
    ]));
  [snapshot.current, snapshot.previous].forEach((month) => {
    const details = element("details", undefined, content);
    element("summary", `${month.start.slice(0, 7)} spend breakdown`, details);
    const headings = ["Category", "Charges"];
    table(details, "By service", headings, chargeRows(month, "services"));
    table(details, "Lambda charge types", headings, chargeRows(month, "lambda_usage"));
    table(details, "By billing stack tag", headings, chargeRows(month, "stack_gross"));
    element("p", "Unallocated / shared includes costs without an active stack billing tag. "
      + "Account credits may be unallocated. Function activity is not a cost allocation.", details);
  });
  ["current", "previous"].forEach((period) => {
    const rows = snapshot.functions.map((fn) => [stackCell(fn, snapshot.collected_at), fn.name, fn.component,
      metric(fn[period].invocations), errorLink(fn, period, snapshot), metric(fn[period].duration_ms, 1000)]);
    rows.push(["Reported subtotal", "", "",
      ...["invocations", "errors", "duration_ms"].map((field) => subtotal(
        snapshot.functions.map((fn) => fn[period][field]), field === "duration_ms" ? 1000 : 1,
      ))]);
    table(content, `${snapshot[period].start.slice(0, 7)} function activity${period === "current" ? " (to collection time)" : ""}`,
      ["Stack / lifetime (UTC)", "Function", "Component", "Invocations", "Errors", "Execution seconds"], rows);
  });
  element("p", "Web functions serve pages, static files and Flask APIs. Resize functions serve "
    + "resize APIs and video/tracing work. No data means AWS returned no samples; reported subtotals "
    + "identify functions with missing data. Activity covers existing functions across all their versions.", content);
  element('p', 'Stack elapsed time runs from creation to deletion, or to collection time if still present. '
    + 'It is not Lambda execution time; retained functions can outlive their stack. '
    + 'Dates unavailable means AWS no longer exposes that stack record, or its identity is missing.', content);
  element("p", "Positive error counts open CloudWatch logs for that function and period (AWS login required). "
    + "Matching log messages can differ from failed-invocation counts. Older logs may have expired; "
    + "Logs Insights queries incur AWS scan charges.", content);
  const snapshots = snapshot.functions.reduce((sum, fn) => sum + fn.snapshots, 0);
  element("p", `${snapshots} retained SnapStart snapshots. Estimated 30-day caching run rate: `
    + `${money(snapshot.snapshot_monthly_estimate)} using the observed cache rate, excluding restores.`, content);
  table(content, "Retained SnapStart snapshots", ["Stack", "Function", "Snapshots", "Cached GB"],
    snapshot.functions.filter((fn) => fn.snapshots).map((fn) => [
      fn.stack, fn.name, String(fn.snapshots), metric(fn.snapshot_gb),
    ]));
  renderStorage(content, snapshot);
}

async function loadBilling(role) {
  const panel = document.getElementById("admin-billing");
  if (!panel) return;
  panel.hidden = role !== "superadmin";
  document.getElementById("billing-content").replaceChildren();
  document.getElementById("billing-scope").textContent = "";
  document.getElementById("billing-links").replaceChildren();
  if (panel.hidden) return;
  const status = document.getElementById("billing-status");
  status.className = "";
  status.textContent = "Loading cached summary...";
  try {
    const response = await fetch(`${API_BASE}api/admin/billing`, { credentials: "same-origin", cache: "no-store" });
    if (!response.ok) throw new Error("Billing summary unavailable.");
    renderBilling(await response.json());
  } catch (_error) {
    status.className = "admin-error";
    status.textContent = "Billing summary unavailable. No zero values have been assumed.";
  }
}

export { loadBilling, renderBilling };

if (document.getElementById("billing-page")) {
  loadBilling(super_role);
}
