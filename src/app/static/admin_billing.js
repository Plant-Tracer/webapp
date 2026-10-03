// Render the private daily AWS summary on the dedicated Billing page.
// Authorization is enforced by the API before any cached account data is read.
// This module never queries AWS directly or refreshes paid billing data.
// Period labels and timestamps come from the cache, including stale snapshots.
// Null metrics mean unavailable samples, while numeric zero remains a real zero.
// All data is inserted as text; only server-generated AWS console links are used.

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
    values.forEach((text) => element("td", text, row));
  });
}

function chargeRows(month, field) {
  return month[field].map((row) => [row.name, money(row.gross), money(row.credits), money(row.net)]);
}

function subtotal(values, divisor) {
  const known = values.filter((value) => value !== null && value !== undefined);
  if (!known.length) return "No data";
  const missing = values.length - known.length;
  return metric(known.reduce((sum, value) => sum + value, 0), divisor)
    + (missing ? ` (${missing} ${missing === 1 ? "function" : "functions"}: no data)` : "");
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
  table(content, "AWS spend (USD)", ["UTC period (end exclusive)", "Charges", "Credits / refunds", "Net"],
    [snapshot.current, snapshot.previous].map((month) => [
      `${month.start} – ${month.end}${month.estimated ? " (estimated)" : ""}`,
      money(month.total.gross), money(month.total.credits), money(month.total.net),
    ]));
  [snapshot.current, snapshot.previous].forEach((month) => {
    const details = element("details", undefined, content);
    element("summary", `${month.start.slice(0, 7)} spend breakdown`, details);
    const headings = ["Category", "Charges", "Credits / refunds", "Net"];
    table(details, "By service", headings, chargeRows(month, "services"));
    table(details, "Lambda charge types", headings, chargeRows(month, "lambda_usage"));
    table(details, "By billing stack tag", headings, chargeRows(month, "stack_gross"));
    element("p", "Unallocated / shared includes costs without an active stack billing tag. "
      + "Account credits may be unallocated. Function activity is not a cost allocation.", details);
  });
  ["current", "previous"].forEach((period) => {
    const rows = snapshot.functions.map((fn) => [fn.stack, fn.name, fn.component,
      metric(fn[period].invocations), metric(fn[period].errors), metric(fn[period].duration_ms, 1000)]);
    rows.push(["Reported subtotal", "", "",
      ...["invocations", "errors", "duration_ms"].map((field) => subtotal(
        snapshot.functions.map((fn) => fn[period][field]), field === "duration_ms" ? 1000 : 1,
      ))]);
    table(content, `${snapshot[period].start.slice(0, 7)} function activity${period === "current" ? " (to collection time)" : ""}`,
      ["Stack", "Function", "Component", "Invocations", "Errors", "Execution seconds"], rows);
  });
  element("p", "Web functions serve pages, static files and Flask APIs. Resize functions serve "
    + "resize APIs and video/tracing work. No data means AWS returned no samples; reported subtotals "
    + "identify functions with missing data. Activity covers existing functions across all their versions.", content);
  const snapshots = snapshot.functions.reduce((sum, fn) => sum + fn.snapshots, 0);
  element("p", `${snapshots} retained SnapStart snapshots. Estimated 30-day caching run rate: `
    + `${money(snapshot.snapshot_monthly_estimate)} using the observed cache rate, excluding restores.`, content);
  table(content, "Retained SnapStart snapshots", ["Stack", "Function", "Snapshots", "Cached GB"],
    snapshot.functions.filter((fn) => fn.snapshots).map((fn) => [
      fn.stack, fn.name, String(fn.snapshots), metric(fn.snapshot_gb),
    ]));
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
