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
    <table>
      <thead><tr>
        <th><button class="admin-sort" data-table="courses" data-key="course_name">
          Name <span class="admin-sort-indicator"></span>
        </button></th>
      </tr></thead>
      <tbody id="admin-course-rows"></tbody>
    </table>
    <table>
      <thead><tr>
        <th><button class="admin-sort" data-table="users" data-key="user_name">
          Name <span class="admin-sort-indicator"></span>
        </button></th>
      </tr></thead>
      <tbody id="admin-user-rows"></tbody>
    </table>
    <table>
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
    viewer: { user_name: 'Root Reader' },
    counts: { courses: 2, users: 1, movies: 1 },
    courses: {
      items: [
        {
          course_id: 'BIO-1', course_key: 'grow-beans', course_name: 'Biology', admin_count: 1,
          enrollment_count: 7, max_enrollment: 10,
        },
        {
          course_id: 'CHEM-2', course_key: 'grow-salts', course_name: 'Chemistry', admin_count: 1,
          enrollment_count: 4, max_enrollment: 10,
        },
      ],
      restart_marker: null,
    },
    users: {
      items: [{
        user_id: 'user-1', user_name: 'Ada', email: 'ada@example.test', primary_course_id: 'BIO-1',
        super_role: 'none',
        courses: [
          { course_id: 'BIO-1', is_admin: true },
          { course_id: 'CHEM-2', is_admin: false },
        ],
      }],
      restart_marker: null,
    },
    movies: {
      items: [{
        movie_id: 'movie-1', title: 'Bean Growth', course_id: 'BIO-1', owner_name: 'Ada',
        state: 'published', status: 'ready',
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
    expect(document.getElementById('admin-movie-rows').textContent)
      .toContain('Bean GrowthBiologyAdapublishedready');
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
});
