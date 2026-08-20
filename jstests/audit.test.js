const { build_audit_table } = require('audit');

function auditDocument() {
  document.body.innerHTML = '<p id="message"></p><input id="audit-search"><table id="audit"></table>';
}

function auditRows() {
  return Array.from(document.querySelectorAll('#audit tbody tr'))
    .map((row) => Array.from(row.cells).map((cell) => cell.textContent));
}

async function settleAudit() {
  await new Promise(process.nextTick);
  await new Promise(process.nextTick);
}

function loadLogs(logs) {
  fetch.mockResponseOnce(JSON.stringify({ error: false, logs }));
  build_audit_table();
  return settleAudit();
}

describe('audit log page', () => {
  beforeEach(() => {
    auditDocument();
    fetch.resetMocks();
    sessionStorage.clear();
    global.API_BASE = '/';
    global.api_key = 'audit-test-key';
    global.course_view_id = null;
    global.user_default_course_id = 'BIO-1';
    global.course_choices = [{ course_id: 'BIO-1', course_name: 'Biology' }];
  });

  test('posts the API key and active course, then renders headers and rows', async () => {
    await loadLogs([{ action: 'Movie uploaded', user: 'Ada', count: 2 }]);

    expect(fetch).toHaveBeenCalledWith('/api/get-logs', expect.objectContaining({
      method: 'POST',
      body: expect.any(FormData),
    }));
    const formData = fetch.mock.calls[0][1].body;
    expect(formData.get('api_key')).toBe('audit-test-key');
    expect(formData.get('course_id')).toBe('BIO-1');
    expect(Array.from(document.querySelectorAll('#audit th')).map((cell) => cell.textContent))
      .toEqual(['action', 'user', 'count']);
    expect(auditRows()).toEqual([['Movie uploaded', 'Ada', '2']]);
  });

  test('shows the empty-log state', async () => {
    await loadLogs([]);

    expect(document.querySelector('#audit').textContent).toContain('No logs available');
  });

  test('shows an API-reported error', async () => {
    fetch.mockResponseOnce(JSON.stringify({ error: true, message: 'Not authorized' }));
    build_audit_table();
    await settleAudit();

    expect(document.getElementById('message').textContent).toBe('error: Not authorized');
  });

  test('shows a fetch failure', async () => {
    const consoleError = jest.spyOn(console, 'error').mockImplementation(() => {});
    fetch.mockRejectOnce(new Error('offline'));
    build_audit_table();
    await settleAudit();

    expect(document.getElementById('message').textContent).toBe('error: Failed to load audit logs');
    consoleError.mockRestore();
  });

  test('filters rows across all log fields', async () => {
    await loadLogs([
      { action: 'Movie uploaded', user: 'Ada', count: 2 },
      { action: 'Movie traced', user: 'Bert', count: 5 },
    ]);

    const search = document.getElementById('audit-search');
    search.value = 'bert';
    search.dispatchEvent(new Event('input'));

    expect(auditRows()).toEqual([['Movie traced', 'Bert', '5']]);
  });

  test('sorts numeric and text values in both directions, keeping missing values last', async () => {
    await loadLogs([
      { action: 'Zulu', count: 20 },
      { action: 'alpha', count: 3 },
      { action: null, count: null },
    ]);

    document.querySelector('#audit th:nth-child(2)').click();
    expect(auditRows().map((row) => row[1])).toEqual(['3', '20', '']);
    document.querySelector('#audit th:nth-child(2)').click();
    expect(auditRows().map((row) => row[1])).toEqual(['20', '3', '']);
    document.querySelector('#audit th:first-child').click();
    expect(auditRows().map((row) => row[0])).toEqual(['alpha', 'Zulu', '']);
  });
});
