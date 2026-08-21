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
});
