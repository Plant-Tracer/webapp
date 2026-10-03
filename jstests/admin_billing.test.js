// Verify billing UI privacy and truthful presentation of incomplete data.
// These tests exercise the actual DOM renderer with representative cache data.
// Monetary credits and unknown metrics must remain visibly distinct from zero.
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

test('renders credits, periods, unknown totals and safely escaped function names', () => {
  const data = payload();
  data.snapshot.functions.push({ ...data.snapshot.functions[0], name: 'idle',
    current: { invocations: null, errors: null, duration_ms: null },
    previous: { invocations: null, errors: null, duration_ms: null } });
  renderBilling(data);
  const text = document.getElementById('billing-content').textContent;
  expect(text).toContain('$52.57');
  expect(text).toContain('-$50.00');
  expect(text).toContain('$2.57');
  expect(text).toContain('2026-10-01 – 2026-10-04 (estimated)');
  expect(text).toContain('No data');
  expect(text).toContain('0 (1 functions: no data)');
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
  expect(document.getElementById('billing-status').className).toBe('error');
  renderBilling({ ...stale, snapshot: null, state: 'unavailable' });
  expect(document.getElementById('billing-content').textContent).toBe('');
  expect(document.querySelectorAll('#billing-links a')).toHaveLength(3);
  fetch.mockRejectOnce(new Error('offline'));
  await loadBilling('superadmin');
  expect(document.getElementById('billing-status').textContent).toContain('No zero values');
});
