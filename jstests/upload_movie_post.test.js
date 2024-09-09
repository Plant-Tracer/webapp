/**
 * @jest-environment jsdom
 */

const $ = require('jquery');
global.$ = $;

const module  = require('../static/planttracer.js') 
const upload_movie_post = module.upload_movie_post

global.Audio = function() {
  this.play = jest.fn();
};

jest.mock('../static/planttracer.js', () => ({
  computeSHA256: jest.fn(),
  first_frame_url: jest.fn(),
  check_upload_metadata: jest.fn(),
}));

const API_BASE = '${process.env.API_BASE}';
const UPLOAD_TIMEOUT_SECONDS = 30;

describe('upload_movie_post', () => {
  let mockMovieFile;
  let mockSHA256;
  let mockPresignedPost;

  beforeEach(() => {
    // Reset mock function calls
    jest.clearAllMocks();

    // Mock movie file
    mockMovieFile = {
      fileSize: 1000,
    };

    // Mock SHA256 function
    mockSHA256 = 'mock_sha256_hash';
    require('../static/planttracer.js').computeSHA256.mockResolvedValue(mockSHA256);

    // Mock presigned post response
    mockPresignedPost = {
      fields: {
        key: 'test_key',
        policy: 'test_policy',
      },
      url: 'https://upload.example.com',
    };
  });

  it('should upload a movie and update the DOM on success', async () => {
    // Mock successful movie ID response
    global.fetch = jest.fn()
      .mockResolvedValueOnce({
        json: async () => ({
          movie_id: '1234',
          presigned_post: mockPresignedPost,
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
      });

    // Mock DOM elements
    document.body.innerHTML = `
      <div id="upload_message"></div>
      <input id="movie-title">
      <input id="movie-description">
      <input id="movie-file">
      <div id="uploaded_movie_title"></div>
      <div id="movie_id"></div>
      <img id="image-preview">
      <div id="upload-preview"></div>
      <form id="upload-form"></form>
      <a id="track_movie_link"></a>
    `;

    // Mock first frame URL
    require('../static/planttracer.js').first_frame_url.mockReturnValue('mock_first_frame_url');


    // Assertions
    expect(global.fetch).toHaveBeenCalledTimes(2);
    expect(global.fetch).toHaveBeenNthCalledWith(1, `${process.env.API_BASE}api/new-movie`, expect.any(Object));
    expect(global.fetch).toHaveBeenNthCalledWith(2, mockPresignedPost.url, expect.any(Object));

    expect(document.getElementById('upload_message').textContent).toBe('Movie uploaded.');
    expect(document.getElementById('uploaded_movie_title').textContent).toBe('Test Movie');
    expect(document.getElementById('movie_id').textContent).toBe('1234');
    expect(document.getElementById('image-preview').src).toBe('mock_first_frame_url');
    expect(document.getElementById('upload-preview').style.display).toBe('');
    expect(document.getElementById('upload-form').style.display).toBe('none');
    expect(require('../static/planttracer.js').check_upload_metadata).toHaveBeenCalled();
  });

  it('should handle errors when fetching upload URL', async () => {
    // Mock error response
    global.fetch = jest.fn().mockResolvedValueOnce({
      json: async () => ({
        error: true,
        message: 'Test Error',
      }),
    });

    // Mock DOM element
    document.body.innerHTML = `<div id="message"></div>`;


    // Assertions
    expect(global.fetch).toHaveBeenCalledTimes(1);
    expect(document.getElementById('message').innerHTML).toBe('Error getting upload URL: Test Error');
  });

  it('should handle upload timeouts', async () => {
    // Mock successful movie ID response
    global.fetch = jest.fn()
      .mockResolvedValueOnce({
        json: async () => ({
          movie_id: '1234',
          presigned_post: mockPresignedPost,
        }),
      })
      .mockRejectedValueOnce(new Error('Timeout Error'));

    // Mock DOM element
    document.body.innerHTML = `<div id="upload_message"></div>`;

    // Assertions
    expect(global.fetch).toHaveBeenCalledTimes(2);
    expect(document.getElementById('upload_message').innerHTML).toBe(`Timeout uploading movie -- timeout is currently ${UPLOAD_TIMEOUT_SECONDS} seconds`);
  });

  it('should handle non-OK responses from the upload request', async () => {
    // Mock successful movie ID response
    global.fetch = jest.fn()
      .mockResolvedValueOnce({
        json: async () => ({
          movie_id: '1234',
          presigned_post: mockPresignedPost,
        }),
      })
      .mockResolvedValueOnce({
        ok: false,
        status: 400,
        statusText: 'Bad Request',
      });

    // Mock DOM element
    document.body.innerHTML = `<div id="upload_message"></div>`;


    // Assertions
    expect(global.fetch).toHaveBeenCalledTimes(2);
    expect(document.getElementById('upload_message').innerHTML).toBe('Error uploading movie status=400 Bad Request');
  });
});
