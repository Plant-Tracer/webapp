const state = {
  courseMarker: null,
  userMarker: null,
  movieMarker: null,
};

function textCell(value) {
  const cell = document.createElement("td");
  cell.textContent = value === null || value === undefined ? "" : String(value);
  return cell;
}

function setText(id, value) {
  document.getElementById(id).textContent = String(value);
}

function appendCourseRows(courses) {
  const tbody = document.getElementById("admin-course-rows");
  for (const course of courses) {
    const row = document.createElement("tr");
    row.append(
      textCell(course.course_id),
      textCell(course.course_name),
      textCell(course.admin_count),
      textCell(`${course.enrollment_count} / ${course.max_enrollment}`),
    );
    tbody.append(row);
  }
}

function coursesCell(courses) {
  const cell = document.createElement("td");
  courses.forEach((course, index) => {
    if (index > 0) {
      cell.append(document.createTextNode(", "));
    }
    const name = course.is_admin ? document.createElement("strong") : document.createElement("span");
    name.textContent = course.course_name;
    name.title = course.course_id;
    cell.append(name);
  });
  return cell;
}

function appendUserRows(users) {
  const tbody = document.getElementById("admin-user-rows");
  for (const user of users) {
    const row = document.createElement("tr");
    row.append(
      textCell(user.user_name),
      textCell(user.email),
      textCell(user.primary_course_id),
      textCell(user.super_role === "none" ? "no" : user.super_role),
      coursesCell(user.courses),
    );
    tbody.append(row);
  }
}

function appendMovieRows(movies) {
  const tbody = document.getElementById("admin-movie-rows");
  for (const movie of movies) {
    const row = document.createElement("tr");
    row.append(
      textCell(movie.title),
      textCell(movie.course_name),
      textCell(movie.owner_name),
      textCell(movie.state),
      textCell(movie.status),
    );
    tbody.append(row);
  }
}

function reportAdminError(error) {
  const status = document.getElementById("admin-status");
  status.className = "admin-error";
  status.textContent = error.message;
}

function setMoreButton(id, marker, handler) {
  const button = document.getElementById(id);
  button.hidden = !marker;
  button.onclick = marker ? () => handler().catch(reportAdminError) : null;
}

async function loadAdminSummary({ appendCourses = false, appendUsers = false, appendMovies = false } = {}) {
  const params = new URLSearchParams({ limit: "25" });
  if (appendCourses && state.courseMarker) {
    params.set("course_marker", state.courseMarker);
  }
  if (appendUsers && state.userMarker) {
    params.set("user_marker", state.userMarker);
  }
  if (appendMovies && state.movieMarker) {
    params.set("movie_marker", state.movieMarker);
  }
  const response = await fetch(`${API_BASE}api/admin/summary?${params}`, {
    credentials: "same-origin",
  });
  const payload = await response.json();
  if (!response.ok || payload.error) {
    throw new Error(payload.message || `Admin summary failed with HTTP ${response.status}`);
  }

  setText("admin-course-count", payload.counts.courses);
  setText("admin-user-count", payload.counts.users);
  setText("admin-movie-count", payload.counts.movies);

  if (!appendCourses && !appendUsers && !appendMovies) {
    document.getElementById("admin-course-rows").replaceChildren();
    document.getElementById("admin-user-rows").replaceChildren();
    document.getElementById("admin-movie-rows").replaceChildren();
    appendCourseRows(payload.courses.items);
    appendUserRows(payload.users.items);
    appendMovieRows(payload.movies.items);
    state.courseMarker = payload.courses.restart_marker;
    state.userMarker = payload.users.restart_marker;
    state.movieMarker = payload.movies.restart_marker;
  } else if (appendCourses) {
    appendCourseRows(payload.courses.items);
    state.courseMarker = payload.courses.restart_marker;
  } else if (appendUsers) {
    appendUserRows(payload.users.items);
    state.userMarker = payload.users.restart_marker;
  } else if (appendMovies) {
    appendMovieRows(payload.movies.items);
    state.movieMarker = payload.movies.restart_marker;
  }

  setMoreButton("admin-more-courses", state.courseMarker, () => loadAdminSummary({ appendCourses: true }));
  setMoreButton("admin-more-users", state.userMarker, () => loadAdminSummary({ appendUsers: true }));
  setMoreButton("admin-more-movies", state.movieMarker, () => loadAdminSummary({ appendMovies: true }));
  document.getElementById("admin-status").textContent = `Read-only access as ${payload.viewer.user_name}`;
}

export { appendCourseRows, appendMovieRows, appendUserRows, loadAdminSummary, state };

if (document.getElementById("admin-status")) {
  loadAdminSummary().catch(reportAdminError);
}
