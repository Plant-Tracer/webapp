/**
 * @jest-environment jsdom
 */

const { waitForUploadProcessing } = require('planttracer');

describe('upload processing status', () => {
  beforeEach(() => {
    document.body.innerHTML = '<div id="upload_message"></div>';
    global.API_BASE = '/';
    global.api_key = 'api-key';
    global.course_choices = [];
    global.course_view_id = null;
    global.user_default_course_id = '';
    fetch.resetMocks();
  });

  afterEach(() => {
    jest.useRealTimers();
    jest.restoreAllMocks();
  });

  test('distinguishes completed S3 upload from server-side processing', async () => {
    fetch.mockResponseOnce(JSON.stringify({
      error: false,
      metadata: { status: 'ready', resized_at: 1700000000 },
    }));

    await waitForUploadProcessing('movie-123');

    expect(document.querySelector('#upload_message').textContent).toContain(
      'Upload complete. Processing the movie usually takes 1–3 minutes.'
    );
    const requestBody = fetch.mock.calls[0][1].body;
    expect(requestBody.get('movie_id')).toBe('movie-123');
  });

  test('polls until server-side processing is ready', async () => {
    jest.useFakeTimers();
    fetch
      .mockResponseOnce(JSON.stringify({
        error: false,
        metadata: { status: 'processing', resized_at: null },
      }))
      .mockResponseOnce(JSON.stringify({
        error: false,
        metadata: { status: 'ready', resized_at: 1700000000 },
      }));

    const processing = waitForUploadProcessing('movie-123');
    await jest.advanceTimersByTimeAsync(1000);

    await expect(processing).resolves.toMatchObject({ status: 'ready' });
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  test('reports when storage succeeds but processing times out', async () => {
    jest.useFakeTimers();
    const now = jest.spyOn(Date, 'now')
      .mockReturnValueOnce(0)
      .mockReturnValueOnce(0)
      .mockReturnValueOnce(0)
      .mockReturnValue(300000);
    fetch.mockResponse(JSON.stringify({
      error: false,
      metadata: { status: 'processing', resized_at: null },
    }));

    const processing = waitForUploadProcessing('movie-123');
    const rejection = expect(processing).rejects.toMatchObject({
      name: 'UploadProcessingTimeoutError',
      message: expect.stringContaining('movie processing did not finish within 5 minutes'),
    });
    await jest.advanceTimersByTimeAsync(1000);

    await rejection;
    expect(fetch).toHaveBeenCalledTimes(1);
    now.mockRestore();
  });

  test('surfaces a metadata status error without continuing to poll', async () => {
    fetch.mockResponseOnce(JSON.stringify({
      error: true,
      message: 'Movie upload record is unavailable.',
    }), { status: 503 });

    await expect(waitForUploadProcessing('movie-123'))
      .rejects.toThrow('Movie upload record is unavailable.');
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});
