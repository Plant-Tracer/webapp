const { changeCurrentCourse, initCurrentCourse, makeDefaultCourse } = require('current_course');

function coursePicker() {
  document.body.innerHTML = `
    <select id="current-course-select" data-current-course-id="BIO-1" data-default-course-id="BIO-1">
      <option value="BIO-1">Biology</option>
      <option value="CHEM-2">Chemistry</option>
    </select>
    <span id="current-course-name">Biology</span>
    <span id="current-course-status"></span>`;
  return document.getElementById('current-course-select');
}

describe('current course picker', () => {
  beforeEach(() => {
    global.API_BASE = '/';
    global.user_default_course_id = 'BIO-1';
    global.course_choices = [
      { course_id: 'BIO-1', course_name: 'Biology' },
      { course_id: 'CHEM-2', course_name: 'Chemistry' },
    ];
    global.course_view_id = null;
    sessionStorage.clear();
    fetch.resetMocks();
  });

  test('saves the selected membership in this tab without changing the profile', () => {
    const select = coursePicker();
    const navigate = jest.fn();
    select.value = 'CHEM-2';

    changeCurrentCourse(select, navigate);

    expect(fetch).not.toHaveBeenCalled();
    expect(sessionStorage.getItem('planttracer.active_course_id')).toBe('CHEM-2');
    expect(select.dataset.currentCourseId).toBe('CHEM-2');
    expect(navigate).toHaveBeenCalledWith('CHEM-2');
  });

  test('restores the previous course when the selection is not a membership', () => {
    const select = coursePicker();
    const option = document.createElement('option');
    option.value = 'MISSING';
    select.append(option);
    select.value = 'MISSING';

    changeCurrentCourse(select, jest.fn());

    expect(select.value).toBe('BIO-1');
    const status = document.getElementById('current-course-status');
    expect(status.textContent).toBe('Course membership required');
    expect(status.className).toBe('course-error');
  });

  test('changes the profile default only through the explicit action', async () => {
    const select = coursePicker();
    select.value = 'CHEM-2';
    fetch.mockResponseOnce(JSON.stringify({
      error: false,
      course: { course_id: 'CHEM-2', course_name: 'Chemistry' },
    }));

    await makeDefaultCourse(select);

    expect(fetch).toHaveBeenCalledWith('/api/default-course', expect.objectContaining({
      method: 'PATCH',
      body: JSON.stringify({ course_id: 'CHEM-2' }),
    }));
  });

  test('preserves the server label for an explicit course view', () => {
    const select = coursePicker();
    global.course_view_id = 'BIO-1';
    sessionStorage.setItem('planttracer.active_course_id', 'CHEM-2');

    initCurrentCourse();

    expect(select.value).toBe('CHEM-2');
    expect(document.getElementById('current-course-name').textContent).toBe('Biology');
  });
});
