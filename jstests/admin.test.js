const {
  loadAdminSummary,
  state,
} = require('admin');

function adminDocument() {
  document.body.innerHTML = `
    <p id="admin-status"></p>
    <span id="admin-course-count"></span>
    <span id="admin-user-count"></span>
    <span id="admin-movie-count"></span>
    <label><input id="admin-verbose-details" type="checkbox"></label>
    <table data-resizable-table>
      <thead><tr>
        <th><button class="admin-sort" data-table="courses" data-key="course_name">
          Name <span class="admin-sort-indicator"></span>
        </button></th>
      </tr></thead>
      <tbody id="admin-course-rows"></tbody>
    </table>
    <table data-resizable-table>
      <thead><tr>
        <th><button class="admin-sort" data-table="users" data-key="user_name">
          Name <span class="admin-sort-indicator"></span>
        </button></th>
      </tr></thead>
      <tbody id="admin-user-rows"></tbody>
    </table>
    <table data-resizable-table>
      <thead><tr>
        <th><button class="admin-sort" data-table="movies" data-key="title">
          Title <span class="admin-sort-indicator"></span>
        </button></th>
      </tr></thead>
      <tbody id="admin-movie-rows"></tbody>
    </table>`;
}

function payload() {
  return {
    viewer: { user_name: 'Root Reader', super_role: 'superauditor' },
    counts: { courses: 2, users: 1, movies: 1 },
    courses: {
      items: [
        {
          course_id: 'BIO-1', course_key: 'grow-beans', course_name: 'Biology', admin_count: 1,
          enrollment_count: 7, max_enrollment: 10, created_at: 1700000000,
          last_movie_activity_at: null,
        },
        {
          course_id: 'CHEM-2', course_key: 'grow-salts', course_name: 'Chemistry', admin_count: 1,
          enrollment_count: 4, max_enrollment: 10, created_at: null,
          last_movie_activity_at: null,
        },
      ],
      restart_marker: null,
    },
    users: {
      items: [{
        user_id: 'user-1', user_name: 'Ada', email: 'ada@example.test', default_course_id: 'BIO-1',
        super_role: 'none', created_at: 1700000000, last_movie_activity_at: null,
        courses: [
          { course_id: 'BIO-1', is_admin: true },
          { course_id: 'CHEM-2', is_admin: false },
        ],
      }],
      restart_marker: null,
    },
    movies: {
      items: [{
        movie_id: 'movie-1', title: 'Bean Growth', course_id: 'BIO-1', user_id: 'user-1',
        owner_name: 'Ada', state: 'published', status: 'ready', created_at: 1700000000,
        uploaded_at: 1700000100, last_activity_at: 1700000200, total_frames: 121,
        total_bytes: 2500000, fpm: '60', has_traced_movie: true,
        description: 'Daily bean measurement', fps: '30', width: 640, height: 480,
        rotation: 0, trim_start_frame: 0, trim_end_frame: 120, needs_retracing: false,
        research_use: 1, credit_by_name: 'Ada', attribution_name: 'Ada Lovelace',
      }],
      restart_marker: null,
    },
  };
}

describe('admin summary rendering', () => {
  beforeEach(() => {
    adminDocument();
    global.API_BASE = '/';
    fetch.resetMocks();
    state.courses = [];
    state.users = [];
    state.movies = [];
    state.viewerRole = 'none';
    state.sort.courses = { key: 'course_name', direction: 1 };
    state.sort.users = { key: 'user_name', direction: 1 };
    state.sort.movies = { key: 'title', direction: 1 };
  });

  test('renders enrollment, named memberships, and movies', async () => {
    fetch.mockResponseOnce(JSON.stringify(payload()));

    await loadAdminSummary();

    const key = document.querySelector('.admin-course-key');
    const keyToggle = document.querySelector('.admin-key-toggle');
    expect(key.textContent).toBe('••••••••');
    expect(document.getElementById('admin-course-rows').textContent).not.toContain('grow-beans');
    expect(keyToggle.querySelector('.admin-eye-slash')).not.toBeNull();
    keyToggle.click();
    expect(key.textContent).toBe('grow-beans');
    expect(keyToggle.querySelector('.admin-eye-slash')).toBeNull();
    expect(keyToggle.getAttribute('aria-label')).toBe('Hide course key for Biology');
    keyToggle.click();
    expect(key.textContent).toBe('••••••••');
    expect(keyToggle.querySelector('.admin-eye-slash')).not.toBeNull();
    expect(document.getElementById('admin-course-rows').textContent).toContain('7 / 10');
    const userRow = document.getElementById('admin-user-rows');
    expect(userRow.textContent).toContain('Biology, Chemistry');
    expect(userRow.querySelector('strong').textContent).toBe('Biology');
    const movieRow = document.querySelector('#admin-movie-rows tr');
    expect(movieRow.textContent).toContain('Bean Growth');
    expect(movieRow.textContent).toContain('121 frames · 2 min elapsed · 2.5 MB');
    expect(movieRow.querySelector('.admin-actions-toggle').textContent).toBe('⋮');
    expect(movieRow.querySelector('.admin-actions-menu').textContent).toContain('Play');
    expect(movieRow.querySelector('.admin-actions-menu').textContent).toContain('Download traced');
    expect(movieRow.querySelector('.admin-actions-menu').textContent).not.toContain('Analyze');
    expect(document.querySelectorAll('.admin-resize-handle')).toHaveLength(3);
    const courseLink = document.querySelector('#admin-course-rows a');
    expect(courseLink.href).toContain('/list?course_id=BIO-1');
    expect(courseLink.target).toBe('_blank');
  });

  test('loads every table page and globally sorts movies', async () => {
    const initial = payload();
    initial.courses.items[0].course_name = 'Zoology';
    initial.courses.restart_marker = 'course-token';
    initial.users.items[0].user_name = 'Zoe';
    initial.users.restart_marker = 'user-token';
    initial.movies.items[0].title = 'Zinnia Growth';
    initial.movies.restart_marker = 'movie-token';
    const nextItems = {
      courses: {
        ...payload(),
        courses: {
          items: [{ ...payload().courses.items[0], course_id: 'BIO-2' }],
          restart_marker: null,
        },
      },
      users: {
        ...payload(),
        users: {
          items: [{ ...payload().users.items[0], user_id: 'user-2' }],
          restart_marker: null,
        },
      },
      movies: {
        ...payload(),
        movies: {
          items: [{ ...payload().movies.items[0], movie_id: 'movie-2' }],
          restart_marker: null,
        },
      },
    };
    fetch.mockImplementation(async (url) => {
      const section = new URL(url, 'https://example.test').searchParams.get('section');
      return {
        ok: true,
        status: 200,
        json: async () => (section === 'all' ? initial : nextItems[section]),
      };
    });

    await loadAdminSummary();

    expect(fetch.mock.calls.map((call) => call[0])).toEqual(expect.arrayContaining([
      expect.stringContaining('section=courses&course_marker=course-token'),
      expect.stringContaining('section=users&user_marker=user-token'),
      expect.stringContaining('section=movies&movie_marker=movie-token'),
    ]));
    expect(document.querySelector('#admin-course-rows tr').textContent).toContain('Biology');
    expect(document.querySelector('#admin-user-rows tr').textContent).toContain('Ada');
    expect(document.querySelector('#admin-movie-rows tr').textContent).toContain('Bean Growth');
    document.querySelector('[data-table="movies"]').click();
    expect(document.querySelector('#admin-movie-rows tr').textContent).toContain('Zinnia Growth');
    expect(document.querySelector('[data-table="movies"]').closest('th').getAttribute('aria-sort'))
      .toBe('descending');
  });

  test('renders supplied data without HTML interpretation', async () => {
    const untrusted = payload();
    untrusted.movies.items[0].title = '<script>bad()</script>';
    fetch.mockResponseOnce(JSON.stringify(untrusted));

    await loadAdminSummary();

    expect(document.querySelector('#admin-movie-rows script')).toBeNull();
    expect(document.getElementById('admin-movie-rows').textContent).toContain('<script>bad()</script>');
  });

  test('marks pending uploads red and suppresses unusable actions', async () => {
    const adminPayload = payload();
    adminPayload.viewer.super_role = 'superadmin';
    adminPayload.movies.items[0].uploaded_at = null;
    fetch.mockResponseOnce(JSON.stringify(adminPayload));

    await loadAdminSummary();

    const movieRow = document.querySelector('#admin-movie-rows tr');
    expect(movieRow.classList.contains('admin-upload-pending')).toBe(true);
    expect(movieRow.title).toContain('upload has not completed');
    expect(movieRow.firstElementChild.querySelector('a')).toBeNull();
    expect(movieRow.querySelector('.admin-actions-menu')).toBeNull();
    expect(movieRow.lastElementChild.textContent).toBe('—');
  });

  test('links uploaded movies to Analyze for superadmins', async () => {
    const adminPayload = payload();
    adminPayload.viewer.super_role = 'superadmin';
    fetch.mockResponseOnce(JSON.stringify(adminPayload));

    await loadAdminSummary();

    const movieRow = document.querySelector('#admin-movie-rows tr');
    expect(movieRow.querySelector('td a').href).toContain('/analyze?movie_id=movie-1');
    expect(movieRow.querySelector('.admin-actions-menu').textContent).toContain('Analyze');
  });

  test('keeps IDs and operational metadata hidden until verbose details is selected', async () => {
    fetch.mockResponseOnce(JSON.stringify(payload()));

    await loadAdminSummary();

    expect(document.body.textContent).not.toContain('Movie ID: movie-1');
    fetch.mockResponseOnce(JSON.stringify({
      error: false, movie_id: 'movie-1', original_object_state: 'present',
      traced_object_state: 'missing', zip_object_state: 'not created', pending_upload_age_seconds: null,
    }));
    document.getElementById('admin-verbose-details').click();
    await new Promise((resolve) => { setTimeout(resolve, 0); });
    expect(document.body.textContent).toContain('Movie ID: movie-1');
    expect(document.body.textContent).toContain('Description: Daily bean measurement');
    expect(document.body.textContent).toContain('Original object: present');
    expect(document.body.textContent).toContain('Traced object: missing');
    expect(document.body.textContent).toContain('ZIP object: not created');
    expect(document.body.textContent).toContain('Administrators: Ada');
    expect(document.body.textContent).toContain('User ID: user-1');
  });
});
