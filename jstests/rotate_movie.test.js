/**
 * @jest-environment jsdom
 */

const { rotate_movie } = require('planttracer');

describe('rotate_movie', () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <a id="rotate_movie_link" href="javascript:;">Rotate</a>
      <span id="rotate_status"></span>
      <img id="image-preview">
      <a id="process_movie_link"></a>`;
    global.api_key = 'test-api-key';
    global.API_BASE = '/';
    window.movie_id = 'movie-123';
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  test('disables rotation until the save completes and ignores duplicate clicks', async () => {
    let completeRequest;
    global.fetch = jest.fn(() => new Promise((resolve) => {
      completeRequest = resolve;
    }));

    const rotation = rotate_movie();
    rotate_movie();

    const link = document.querySelector('#rotate_movie_link');
    expect(link.classList.contains('rotate-pending')).toBe(true);
    expect(link.getAttribute('aria-disabled')).toBe('true');
    expect(global.fetch).toHaveBeenCalledTimes(1);
    expect(document.querySelector('#image-preview').style.transform).toBe('rotate(90deg)');

    completeRequest({ json: async () => ({ error: false }) });
    await rotation;

    expect(link.classList.contains('rotate-pending')).toBe(false);
    expect(link.hasAttribute('aria-disabled')).toBe(false);
    expect(document.querySelector('#rotate_status').textContent).toContain('(Rotation saved)');

    global.fetch.mockResolvedValueOnce({ json: async () => ({ error: false }) });
    await rotate_movie();

    expect(global.fetch).toHaveBeenCalledTimes(2);
    expect(document.querySelector('#image-preview').style.transform).toBe('rotate(180deg)');
  });

  test('re-enables rotation after a failed save so the user can retry', async () => {
    jest.spyOn(global.console, 'error').mockImplementation(() => {});
    global.fetch = jest.fn().mockResolvedValueOnce({ json: async () => ({ error: false }) });
    await rotate_movie();
    const preview = document.querySelector('#image-preview');
    const persistedTransform = preview.style.transform;

    global.fetch.mockRejectedValueOnce(new Error('offline'));
    await rotate_movie();

    const link = document.querySelector('#rotate_movie_link');
    expect(link.classList.contains('rotate-pending')).toBe(false);
    expect(link.hasAttribute('aria-disabled')).toBe(false);
    expect(preview.style.transform).toBe(persistedTransform);
    expect(document.querySelector('#rotate_status').textContent).toContain('Network error');

    global.fetch.mockResolvedValueOnce({ json: async () => ({ error: false }) });
    await rotate_movie();
    expect(preview.style.transform).not.toBe(persistedTransform);
  });

  test('restores the persisted preview when the backend rejects a rotation', async () => {
    global.fetch = jest.fn().mockResolvedValueOnce({ json: async () => ({ error: false }) });
    await rotate_movie();
    const preview = document.querySelector('#image-preview');
    const persistedTransform = preview.style.transform;

    global.fetch.mockResolvedValueOnce({
      json: async () => ({ error: true, message: 'save rejected' }),
    });
    await rotate_movie();

    expect(preview.style.transform).toBe(persistedTransform);
    expect(document.querySelector('#rotate_status').textContent).toContain('save rejected');
  });
});
