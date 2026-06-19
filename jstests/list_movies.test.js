/**
 * @jest-environment jsdom
 */

const { $ } = require('utils');
const fs = require('fs');
const path = require('path');

const module = require('planttracer');
const list_movies_data = module.list_movies_data;
const play_clicked = module.play_clicked;
const hide_clicked = module.hide_clicked;
const dtInstances = module.dtInstances;

global.Audio = function() {
  this.play = jest.fn();
};

// Load global data from globals.json
let globalData;
beforeAll(() => {
  const jsonPath = path.join(__dirname, 'constants.json');
  globalData = JSON.parse(fs.readFileSync(jsonPath, 'utf8'));
});

describe('list_movies_data', () => {
  let mockElements;

  beforeEach(() => {
    jest.clearAllMocks();
    // Assign global variables from globalData
    global.user_id = parseInt(globalData.user_id, 10);
    global.admin = globalData.admin === 'true';
    global.demo_mode = globalData.demo_mode === 'false';
    global.PLAY_LABEL = globalData.PLAY_LABEL;
    global.PLAY_TRACKED_LABEL = globalData.PLAY_TRACKED_LABEL;
    global.UNPUBLISH_BUTTON = globalData.UNPUBLISH_BUTTON;
    global.PUBLISH_BUTTON = globalData.PUBLISH_BUTTON;
    global.DELETE_BUTTON = globalData.DELETE_BUTTON;
    global.UNDELETE_BUTTON = globalData.UNDELETE_BUTTON;
    global.TABLE_HEAD = globalData.TABLE_HEAD;
    global.user_primary_course_id = parseInt(globalData.user_primary_course_id, 10);

    // Mock DataTables so planttracer.js can call $.fn.DataTable() without a real browser
    const mockDtInstance = {
      destroy: jest.fn(),
      row: jest.fn(),
    };
    $.fn.DataTable = jest.fn(() => mockDtInstance);
    $.fn.DataTable.isDataTable = jest.fn(() => false);

    // Mock document.querySelector to return mock elements with innerHTML setter
    mockElements = {};
    document.querySelector = jest.fn((selector) => {
      if (!mockElements[selector]) {
        mockElements[selector] = { innerHTML: '', style: {} };
      }
      return mockElements[selector];
    });

    // Mock document.querySelectorAll (kept for safety; no longer called by movies code)
    document.querySelectorAll = jest.fn(() => []);
  });

  test('should create the correct HTML for published movies', () => {
    const movies = [
      {
        movie_id: 1,
        user_id: 1,
        published: 1,
        title: 'Movie Title',
        description: 'Description',
        width: 1280,
        height: 720,
        total_bytes: 2000000,
        fps: '30',
        total_frames: 3600,
        date_uploaded: 1627689600,
        deleted: 0,
        orig_movie: false,
      }
    ];

    list_movies_data(movies);
    expect(document.querySelector).toHaveBeenCalledTimes(4);

    // Check that the published movies div was populated
    const publishedHtml = mockElements['#your-published-movies'].innerHTML;
    expect(publishedHtml).toContain("pure-table");
    expect(publishedHtml).toContain("Movie Title");
  });

  test('should show traced movie download and retrace warning when present', () => {
    const movies = [
      {
        movie_id: 1,
        user_id: 1,
        published: 1,
        title: 'Movie Title',
        description: 'Description',
        width: 1280,
        height: 720,
        total_bytes: 2000000,
        fps: '30',
        total_frames: 3600,
        date_uploaded: 1627689600,
        deleted: 0,
        orig_movie: false,
        movie_traced_url: 'https://example.com/traced.mp4?x=1&y=2',
        needs_retracing: 1,
      }
    ];

    list_movies_data(movies);

    const publishedHtml = mockElements['#your-published-movies'].innerHTML;
    expect(publishedHtml).toContain('download traced');
    expect(publishedHtml).toContain("class='play traced-movie-download'");
    expect(publishedHtml).toContain('https://example.com/traced.mp4?x=1&amp;y=2');
    expect(publishedHtml).toContain('marker moved; movie requires retracing');
  });

  test('should handle an empty list of movies gracefully', () => {
    const movies = [];

    list_movies_data(movies);
    expect(document.querySelector).toHaveBeenCalledTimes(4);

    // Check that empty movies show the right message
    const publishedHtml = mockElements['#your-published-movies'].innerHTML;
    expect(publishedHtml).toContain("No movies");
    expect(publishedHtml).toContain('<a href="/upload">Click here to upload a movie</a>');
  });

  test('should correctly classify and display course movies', () => {
    const movies = [
      {
        movie_id: 1,
        user_id: 2,
        course_id: 1,
        published: 0,
        deleted: 0,
        orig_movie: false,
      },
      {
        movie_id: 2,
        user_id: 3,
        course_id: 2,
        published: 0,
        deleted: 0,
        orig_movie: false,
      }
    ];

    list_movies_data(movies);
    expect(document.querySelector).toHaveBeenCalledTimes(4);

    // Check that course movies are shown in the right section
    const courseHtml = mockElements['#course-movies'].innerHTML;
    expect(courseHtml).toContain('pure-table');
  });

  test('should display a link to upload movies for non-demo users', () => {
    const movies = [];
    global.demo_mode = false;
    list_movies_data(movies);
    expect(document.querySelector).toHaveBeenCalledTimes(4);

    const publishedHtml = mockElements['#your-published-movies'].innerHTML;
    expect(publishedHtml).toContain('No movies');
    expect(publishedHtml).toContain('<a href="/upload">Click here to upload a movie</a>');
  });

  test('should not display upload link for demo users', () => {
    const movies = [];

    global.demo_mode = true;

    list_movies_data(movies);
    expect(document.querySelector).toHaveBeenCalledTimes(4);

    const publishedHtml = mockElements['#your-published-movies'].innerHTML;
    expect(publishedHtml).not.toContain('Click here to upload a movie');
  });

  // DataTables initialisation tests

  test('should initialise DataTables when movies are present', () => {
    const movies = [
      {
        movie_id: 1,
        user_id: 1,
        published: 1,
        title: 'Movie Title',
        description: 'Description',
        date_uploaded: 1627689600,
        deleted: 0,
        orig_movie: false,
      }
    ];

    list_movies_data(movies);
    // DataTable() should have been called at least once (for the published table)
    expect($.fn.DataTable).toHaveBeenCalled();
    // The DataTables config should disable sorting on column 5 (status and action)
    const dtConfig = $.fn.DataTable.mock.calls[0][0];
    expect(dtConfig.columnDefs).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ orderable: false, targets: 5 })
      ])
    );
    // Default sort should be column 1 (uploaded), descending
    expect(dtConfig.order).toEqual([[1, 'desc']]);
  });

  test('should not initialise DataTables when the movie list is empty', () => {
    list_movies_data([]);
    expect($.fn.DataTable).not.toHaveBeenCalled();
  });

  test('should store DataTables instance in dtInstances keyed by divSelector', () => {
    const movies = [
      {
        movie_id: 1,
        user_id: 1,
        published: 1,
        title: 'Movie Title',
        description: 'Description',
        date_uploaded: 1627689600,
        deleted: 0,
        orig_movie: false,
      }
    ];

    list_movies_data(movies);
    expect(dtInstances['#your-published-movies']).toBeDefined();
  });

  // Action Button Tests

  test('should display a publish button for unpublished movies (admin)', () => {
    global.admin = true; // Set admin privileges

    const movies = [
      {
        movie_id: 1,
        user_id: 1,
        published: 0,
        deleted: 0,
        title: 'Unpublished Movie',
        date_uploaded: 1627689600,
        width: 1280,
        height: 720,
        total_bytes: 2000000,
        fps: '30',
        total_frames: 3600,
        orig_movie: false,
      }
    ];

    list_movies_data(movies);

    const unpublishedHtml = mockElements['#your-unpublished-movies'].innerHTML;
    expect(unpublishedHtml).toContain('Status: Not published');
  });

  test('should display an unpublish button for published movies', () => {
    const movies = [
      {
        movie_id: 1,
        user_id: 1,
        published: 1,
        deleted: 0,
        title: 'Published Movie',
        date_uploaded: 1627689600,
        width: 1280,
        height: 720,
        total_bytes: 2000000,
        fps: '30',
        total_frames: 3600,
        orig_movie: false,
      }
    ];

    list_movies_data(movies);

    const publishedHtml = mockElements['#your-published-movies'].innerHTML;
    expect(publishedHtml).toContain('Status: <b>Published</b>');
  });
});

describe('play_clicked', () => {
  let mockChildApi;
  let mockRow;
  let mockDtInstance;

  beforeEach(() => {
    jest.clearAllMocks();
    global.api_key = 'test-api-key';
    global.LAMBDA_API_BASE = 'https://lambda.example.com/';

    // Build a minimal DataTables child-row mock
    mockChildApi = { show: jest.fn() };
    mockRow = {
      child: jest.fn(() => mockChildApi),
    };
    mockDtInstance = {
      destroy: jest.fn(),
      row: jest.fn(() => mockRow),
    };

    // Pre-populate dtInstances so play_clicked can find the table
    dtInstances['#your-published-movies'] = mockDtInstance;

    // Minimal closest() on the button element
    document.querySelector = jest.fn(() => null);
  });

  afterEach(() => {
    delete dtInstances['#your-published-movies'];
  });

  test('returns early when LAMBDA_API_BASE is not set', () => {
    global.LAMBDA_API_BASE = '';
    const btn = {
      getAttribute: jest.fn((attr) => {
        if (attr === 'x-movie_id') return '1';
        if (attr === 'x-rowid') return 'row1';
        if (attr === 'x-div-selector') return '#your-published-movies';
        return null;
      }),
      closest: jest.fn(() => null),
    };
    play_clicked(btn);
    expect(mockDtInstance.row).not.toHaveBeenCalled();
  });

  test('returns early when dtInstances entry is missing', () => {
    delete dtInstances['#your-published-movies'];
    const btn = {
      getAttribute: jest.fn((attr) => {
        if (attr === 'x-movie_id') return '1';
        if (attr === 'x-rowid') return 'row1';
        if (attr === 'x-div-selector') return '#your-published-movies';
        return null;
      }),
      closest: jest.fn(() => null),
    };
    play_clicked(btn);
    expect(mockDtInstance.row).not.toHaveBeenCalled();
  });

  test('shows loading child row and fetches movie data on success', async () => {
    const mockTr = document.createElement('tr');
    const btn = {
      getAttribute: jest.fn((attr) => {
        if (attr === 'x-movie_id') return '42';
        if (attr === 'x-rowid') return 'row42';
        if (attr === 'x-div-selector') return '#your-published-movies';
        return null;
      }),
      closest: jest.fn(() => mockTr),
    };

    global.fetch = jest.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ url: 'https://s3.example.com/movie.mp4' }),
      })
    );

    play_clicked(btn);

    // Loading child row shown immediately (synchronously)
    expect(mockDtInstance.row).toHaveBeenCalledWith(mockTr);
    expect(mockRow.child).toHaveBeenCalledWith(expect.stringContaining('Loading'));
    expect(mockChildApi.show).toHaveBeenCalled();

    // Allow the fetch chain to resolve
    await new Promise((r) => setTimeout(r, 0));

    // Video child row shown after fetch resolves
    expect(mockRow.child).toHaveBeenCalledWith(expect.stringContaining('video'));
  });

  test('shows error child row when fetch returns non-ok response', async () => {
    const mockTr = document.createElement('tr');
    const btn = {
      getAttribute: jest.fn((attr) => {
        if (attr === 'x-movie_id') return '42';
        if (attr === 'x-rowid') return 'row42';
        if (attr === 'x-div-selector') return '#your-published-movies';
        return null;
      }),
      closest: jest.fn(() => mockTr),
    };

    global.fetch = jest.fn(() =>
      Promise.resolve({
        ok: false,
        status: 403,
        json: () => Promise.resolve({ message: 'Forbidden' }),
      })
    );

    play_clicked(btn);
    await new Promise((r) => setTimeout(r, 0));

    expect(mockRow.child).toHaveBeenLastCalledWith(expect.stringContaining('error'));
  });

  test('shows error child row when fetch rejects', async () => {
    const mockTr = document.createElement('tr');
    const btn = {
      getAttribute: jest.fn((attr) => {
        if (attr === 'x-movie_id') return '42';
        if (attr === 'x-rowid') return 'row42';
        if (attr === 'x-div-selector') return '#your-published-movies';
        return null;
      }),
      closest: jest.fn(() => mockTr),
    };

    global.fetch = jest.fn(() => Promise.reject(new Error('Network error')));

    play_clicked(btn);
    await new Promise((r) => setTimeout(r, 0));

    expect(mockRow.child).toHaveBeenLastCalledWith(expect.stringContaining('error'));
  });
});

describe('hide_clicked', () => {
  let mockChildApi;
  let mockRow;
  let mockDtInstance;

  beforeEach(() => {
    jest.clearAllMocks();

    mockChildApi = { show: jest.fn() };
    mockRow = { child: jest.fn(() => mockChildApi) };
    mockDtInstance = {
      destroy: jest.fn(),
      row: jest.fn(() => mockRow),
    };
    dtInstances['#your-published-movies'] = mockDtInstance;
  });

  afterEach(() => {
    delete dtInstances['#your-published-movies'];
  });

  test('pauses video and collapses child row', () => {
    // Insert a fake video element into the document
    const video = document.createElement('video');
    video.id = 'video-row99';
    video.pause = jest.fn();
    document.body.appendChild(video);

    const parentTr = document.createElement('tr');
    const childTr = document.createElement('tr');
    parentTr.appendChild(childTr); // childTr.previousElementSibling === parentTr siblings...
    // DOM: parentTr → childTr as siblings inside a tbody
    const tbody = document.createElement('tbody');
    tbody.appendChild(parentTr);
    tbody.appendChild(childTr);

    const btn = {
      getAttribute: jest.fn((attr) => {
        if (attr === 'x-rowid') return 'row99';
        if (attr === 'x-div-selector') return '#your-published-movies';
        return null;
      }),
      closest: jest.fn(() => childTr),
    };

    hide_clicked(btn);

    expect(video.pause).toHaveBeenCalled();
    expect(mockDtInstance.row).toHaveBeenCalledWith(parentTr);
    expect(mockRow.child).toHaveBeenCalledWith(false);

    document.body.removeChild(video);
  });

  test('handles missing video element gracefully', () => {
    const parentTr = document.createElement('tr');
    const childTr = document.createElement('tr');
    const tbody = document.createElement('tbody');
    tbody.appendChild(parentTr);
    tbody.appendChild(childTr);

    const btn = {
      getAttribute: jest.fn((attr) => {
        if (attr === 'x-rowid') return 'nonexistent';
        if (attr === 'x-div-selector') return '#your-published-movies';
        return null;
      }),
      closest: jest.fn(() => childTr),
    };

    expect(() => hide_clicked(btn)).not.toThrow();
    expect(mockDtInstance.row).toHaveBeenCalledWith(parentTr);
  });

  test('handles missing dtInstances entry gracefully', () => {
    delete dtInstances['#your-published-movies'];
    const btn = {
      getAttribute: jest.fn((attr) => {
        if (attr === 'x-rowid') return 'row99';
        if (attr === 'x-div-selector') return '#your-published-movies';
        return null;
      }),
      closest: jest.fn(() => null),
    };
    expect(() => hide_clicked(btn)).not.toThrow();
  });
});
