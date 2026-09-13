/**
 * @jest-environment jsdom
 */
const { webcrypto } = require('crypto');
const { rotate_movie, preview_upload_movie, upload_movie } = require('planttracer');

describe('rotation before upload', () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <form id="upload-movie-form">
        <input id="movie-title" value="Plant movie">
        <input id="movie-description" value="Landscape plant">
        <input id="movie-file" type="file">
        <input id="movie-rotation" value="0">
        <button id="upload-button"></button>
        <div id="upload-orientation"><video id="upload-source-preview"></video></div>
      </form>
      <div id="upload_message"></div><div id="message"></div>`;
    Object.defineProperty(document.querySelector('#movie-file'), 'files', {
      value: [{ size: 4, arrayBuffer: async () => new Uint8Array([1, 2, 3, 4]).buffer }],
      configurable: true,
    });
    Object.defineProperty(global.crypto, 'subtle', { value: webcrypto.subtle, configurable: true });
    global.api_key = 'test-api-key';
    global.API_BASE = '/';
    global.LAMBDA_API_BASE = '';
    global.MAX_FILE_UPLOAD = 100;
    fetch.resetMocks();
  });

  test('cycles locally through all orientations without changing a stored movie', () => {
    for (const rotation of [90, 180, 270, 0]) {
      rotate_movie();
      expect(document.querySelector('#movie-rotation').value).toBe(String(rotation));
      expect(document.querySelector('#upload-source-preview').style.transform).toBe(`rotate(${rotation}deg)`);
    }
    expect(fetch).not.toHaveBeenCalled();
  });

  test('includes the chosen orientation when requesting an upload', async () => {
    rotate_movie();
    rotate_movie();
    fetch.mockResponseOnce(JSON.stringify({ error: true, message: 'Upload unavailable' }));
    await upload_movie();
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0][0]).toBe('/api/new-movie');
    expect(fetch.mock.calls[0][1].body.get('rotation')).toBe('180');
    expect(document.querySelector('#message').textContent).toContain('Upload unavailable');
  });

  test('changing files resets orientation and releases the previous local preview', () => {
    URL.createObjectURL = jest.fn().mockReturnValueOnce('blob:first').mockReturnValueOnce('blob:second');
    URL.revokeObjectURL = jest.fn();
    preview_upload_movie();
    rotate_movie();
    preview_upload_movie();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:first');
    expect(document.querySelector('#movie-rotation').value).toBe('0');
    expect(document.querySelector('#upload-source-preview').style.transform).toBe('');
    expect(document.querySelector('#upload-source-preview').src).toBe('blob:second');
  });
});
