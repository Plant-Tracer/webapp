/**
 * Jest unit tests for checkLambdaStatus()
 *
 * Target lines in planttracer.js:
 *   176 – if (!r.ok) return false;
 *   178 – return data && data.status === 'ok';
 *
*/

const { checkLambdaStatus } = require('planttracer');

// ---------------------------------------------------------------------------
// 2. Helper – build a minimal fetch Response mock
// ---------------------------------------------------------------------------
function makeFetchMock({ ok, jsonData, jsonThrows = false }) {
  return jest.fn().mockResolvedValue({
    ok,
    json: jsonThrows
      ? jest.fn().mockRejectedValue(new Error('invalid json'))
      : jest.fn().mockResolvedValue(jsonData),
  });
}

// ---------------------------------------------------------------------------
// 3. Tests
// ---------------------------------------------------------------------------
describe('checkLambdaStatus()', () => {

  afterEach(() => {
    jest.restoreAllMocks();
  });

  // --- r.ok is false → must return false ----------------

  describe('HTTP error response (r.ok === false)', () => {

    test('returns false when the server responds with HTTP 500', async () => {
      global.fetch = makeFetchMock({ ok: false, jsonData: null });

      const result = await checkLambdaStatus();

      expect(result).toBe(false);
    });

    test('returns false when the server responds with HTTP 404', async () => {
      global.fetch = makeFetchMock({ ok: false, jsonData: { status: 'ok' } });
      // Even if the body would say "ok", a non-ok HTTP status must short-circuit

      const result = await checkLambdaStatus();

      expect(result).toBe(false);
    });

    test('does NOT call r.json() when r.ok is false', async () => {
      const jsonSpy = jest.fn();
      global.fetch = jest.fn().mockResolvedValue({ ok: false, json: jsonSpy });

      await checkLambdaStatus();

      expect(jsonSpy).not.toHaveBeenCalled();
    });

  });

  // evaluate data && data.status === 'ok' -----------

  describe('JSON body evaluation (r.ok === true)', () => {

    test('returns true when data.status is "ok"', async () => {
      global.fetch = makeFetchMock({ ok: true, jsonData: { status: 'ok' } });

      const result = await checkLambdaStatus();

      expect(result).toBe(true);
    });

    test('returns false when data.status is a non-"ok" string', async () => {
      global.fetch = makeFetchMock({ ok: true, jsonData: { status: 'error' } });

      const result = await checkLambdaStatus();

      expect(result).toBe(false);
    });

    test('returns false when data.status is missing', async () => {
      global.fetch = makeFetchMock({ ok: true, jsonData: {} });

      const result = await checkLambdaStatus();

      expect(result).toBe(false);
    });

    test('returns false when the JSON body is null', async () => {
      global.fetch = makeFetchMock({ ok: true, jsonData: null });

      const result = await checkLambdaStatus();

      // null && ... → false (the `data &&` guard on line 178)
      expect(result).toBe(false);
    });

    test('returns false when the JSON body is undefined', async () => {
      global.fetch = makeFetchMock({ ok: true, jsonData: undefined });

      const result = await checkLambdaStatus();

      expect(result).toBe(false);
    });

  });

  // --- catch branch: fetch itself rejects (network error) ----------------

  describe('catch block – fetch throws', () => {

    test('returns false when fetch rejects (network failure)', async () => {
      global.fetch = jest.fn().mockRejectedValue(new Error('Network error'));

      const result = await checkLambdaStatus();

      expect(result).toBe(false);
    });

    test('returns false when r.json() throws (malformed response)', async () => {
      global.fetch = makeFetchMock({ ok: true, jsonData: null, jsonThrows: true });

      const result = await checkLambdaStatus();

      expect(result).toBe(false);
    });

  });

});
