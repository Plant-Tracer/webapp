// Verify billing UI privacy and truthful presentation of incomplete data.
// These tests exercise the actual DOM renderer with representative cache data.
// Spend tables show gross charges only; unknown metrics stay distinct from zero.
// Role changes must clear previously rendered private account information.
// Fetch is simulated only at the browser's HTTP boundary; Flask is covered
// separately by the real MinIO/DynamoDB browser integration test.
const { loadBilling, renderBilling } = require('admin_billing');

beforeEach(() => {
  document.body.innerHTML = '<section id="admin-billing" hidden><p id="billing-status"></p>'
    + '<p id="billing-scope"></p><nav id="billing-links"></nav><div id="billing-content"></div></section>';
  global.API_BASE = '/';
  fetch.resetMocks();
});

function payload() {
  const month = { start: '2026-09-01', end: '2026-10-01', estimated: false,
    total: { gross: '52.57', credits: '-50', net: '2.57' },
    services: [], lambda_usage: [], stack_gross: [] };
  return { state: 'ready', message: 'Updated daily', current_url: 'https://console.aws.amazon.com/',
    previous_url: 'https://console.aws.amazon.com/', dashboards_url: 'https://console.aws.amazon.com/',
    snapshot: { account_id: '123456789012', activity_region: 'us-east-1', collected_at: '2026-10-03T10:00:00Z',
      current: { ...month, start: '2026-10-01', end: '2026-10-04', estimated: true }, previous: month,
      snapshot_monthly_estimate: null, functions: [{ name: '<script>bad()</script>', stack: 'prod', component: 'Web',
        current: { invocations: 0, errors: null, duration_ms: 1500 }, previous: { invocations: 12, errors: 0, duration_ms: 3000 },
        snapshots: 1, snapshot_gb: '0.5' }] } };
}

test('renders gross charges only, periods, unknown totals and safely escaped function names', () => {
  const data = payload();
  data.snapshot.functions.push({ ...data.snapshot.functions[0], name: 'idle',
    current: { invocations: null, errors: null, duration_ms: null },
    previous: { invocations: null, errors: null, duration_ms: null } });
  renderBilling(data);
  const text = document.getElementById('billing-content').textContent;
  expect(text).toContain('$52.57');
  expect(text).not.toContain('-$50.00');
  expect(text).not.toContain('$2.57');
  const spendTables = [...document.querySelectorAll('#billing-content table')].slice(0, 7);
  spendTables.forEach((table) => {
    expect(table.querySelectorAll('thead th')).toHaveLength(2);
    table.querySelectorAll('tbody tr').forEach((row) => expect(row.children).toHaveLength(2));
  });
  expect(text).toContain('2026-10-01 – 2026-10-04 (estimated)');
  expect(text).toContain('No data');
  expect(text).toContain('0 (1 function: no data)');
  expect(text).toContain('Reported subtotal');
  expect(text).toContain('Unavailable');
  expect(text).toContain('<script>bad()</script>');
  expect(document.querySelector('script')).toBeNull();
  expect(document.querySelectorAll('#billing-links a')).toHaveLength(3);
});

test('fetches only for superadmins and clears private data after a role change', async () => {
  fetch.mockResponseOnce(JSON.stringify(payload()));
  await loadBilling('superadmin');
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(document.getElementById('admin-billing').hidden).toBe(false);
  await loadBilling('superauditor');
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(document.getElementById('admin-billing').hidden).toBe(true);
  expect(document.getElementById('billing-content').textContent).toBe('');
  expect(document.getElementById('billing-scope').textContent).toBe('');
});

test('unavailable and stale states retain useful links and never fabricate zeroes', async () => {
  const stale = payload();
  stale.state = 'stale';
  stale.message = 'Showing the last successful collection';
  renderBilling(stale);
  expect(document.getElementById('billing-status').className).toBe('admin-error');
  renderBilling({ ...stale, snapshot: null, state: 'unavailable' });
  expect(document.getElementById('billing-content').textContent).toBe('');
  expect(document.querySelectorAll('#billing-links a')).toHaveLength(3);
  fetch.mockRejectOnce(new Error('offline'));
  await loadBilling('superadmin');
  expect(document.getElementById('billing-status').textContent).toContain('No zero values');
  expect(document.getElementById('billing-status').className).toBe('admin-error');
  fetch.mockResponseOnce(JSON.stringify(payload()));
  await loadBilling('superadmin');
  expect(document.getElementById('billing-status').className).toBe('');
});

test('links only positive function errors to the matching UTC period and escaped log group', () => {
  const data = payload();
  const fn = data.snapshot.functions[0];
  fn.current.errors = 2;
  fn.previous.errors = 1;
  renderBilling(data);
  const links = [...document.querySelectorAll('#billing-content a')];
  expect(links).toHaveLength(2);
  links.forEach((link, index) => {
    expect(link.target).toBe('_blank');
    expect(link.rel).toBe('noopener noreferrer');
    const url = new URL(link.href);
    expect(url.origin).toBe('https://console.aws.amazon.com');
    expect(url.searchParams.get('region')).toBe('us-east-1');
    const detail = decodeURIComponent(url.hash.split('logs-insights:queryDetail=')[1]);
    const values = decodeURIComponent(detail.replace(/\*/g, '%'));
    expect(values).toContain("source~(~'/aws/lambda/<script>bad()</script>)");
    expect(values).toContain('(?i)(error|exception|timed out|timeout)');
    expect(values).toContain(index === 0 ? '2026-10-01T00:00:00.000Z' : '2026-09-01T00:00:00.000Z');
    expect(values).toContain(index === 0 ? '2026-10-03T09:59:59.999Z' : '2026-09-30T23:59:59.999Z');
  });
  fn.current.errors = 0;
  fn.previous.errors = null;
  renderBilling(data);
  expect(document.querySelectorAll('#billing-content a')).toHaveLength(0);
  expect(document.querySelector('script')).toBeNull();
});

test('keeps stack dates and elapsed days/hours/minutes in one cell without inventing missing dates', () => {
  const data = payload();
  const fn = data.snapshot.functions[0];
  fn.stack_lifetime = { started_at: '2026-09-01T01:02:00Z', stopped_at: '2026-09-03T04:07:59Z', status: 'DELETE_COMPLETE' };
  renderBilling(data);
  let rows = [...document.querySelectorAll('#billing-content table')][7].querySelectorAll('tbody tr');
  expect(rows[0].children).toHaveLength(6);
  expect(rows[0].children[0].textContent).toContain('Start: 2026-09-01 01:02');
  expect(rows[0].children[0].textContent).toContain('Stop: 2026-09-03 04:07');
  expect(rows[0].children[0].textContent).toContain('Elapsed: 2d 3h 5m');
  fn.stack_lifetime = { started_at: '2026-10-02T08:55:00Z', status: 'UPDATE_COMPLETE' };
  renderBilling(data);
  rows = [...document.querySelectorAll('#billing-content table')][7].querySelectorAll('tbody tr');
  expect(rows[0].children[0].textContent).toContain('Stop: Still present');
  expect(rows[0].children[0].textContent).toContain('Elapsed: 1d 1h 5m');
  fn.stack_lifetime.status = 'DELETE_COMPLETE';
  renderBilling(data);
  expect(document.getElementById('billing-content').textContent).toContain('Stop: Unknown');
  expect(document.getElementById('billing-content').textContent).toContain('Elapsed: Unavailable');
  delete fn.stack_lifetime;
  renderBilling(data);
  expect(document.getElementById('billing-content').textContent).toContain('Dates unavailable');
});
