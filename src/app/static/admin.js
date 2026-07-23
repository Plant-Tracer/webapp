const TABLE_CONFIG = {
  courses: {
    bodyId: "admin-course-rows", markerParam: "course_marker",
    idKey: "course_id", defaultKey: "course_name",
  },
  users: {
    bodyId: "admin-user-rows", markerParam: "user_marker",
    idKey: "user_id", defaultKey: "user_name",
  },
  movies: {
    bodyId: "admin-movie-rows", markerParam: "movie_marker",
    idKey: "movie_id", defaultKey: "title",
  },
};
const TABLE_NAMES = Object.keys(TABLE_CONFIG);
const state = {
  courses: [],
  users: [],
  movies: [],
  sort: Object.fromEntries(TABLE_NAMES.map((table) => [
    table,
    { key: TABLE_CONFIG[table].defaultKey, direction: 1 },
  ])),
};

function textCell(value) {
  const cell = document.createElement("td");
  cell.textContent = value === null || value === undefined ? "" : String(value);
  return cell;
}

function setText(id, value) {
  document.getElementById(id).textContent = String(value);
}

function eyeIcon(slashed) {
  const namespace = "http://www.w3.org/2000/svg";
  const icon = document.createElementNS(namespace, "svg");
  icon.setAttribute("viewBox", "0 0 24 24");
  icon.setAttribute("aria-hidden", "true");
  const eye = document.createElementNS(namespace, "path");
  eye.setAttribute("d", "M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z");
  const pupil = document.createElementNS(namespace, "circle");
  pupil.setAttribute("cx", "12");
  pupil.setAttribute("cy", "12");
  pupil.setAttribute("r", "3");
  icon.append(eye, pupil);
  if (slashed) {
    const slash = document.createElementNS(namespace, "line");
    slash.setAttribute("class", "admin-eye-slash");
    slash.setAttribute("x1", "3");
    slash.setAttribute("y1", "3");
    slash.setAttribute("x2", "21");
    slash.setAttribute("y2", "21");
    icon.append(slash);
  }
  return icon;
}

function courseKeyCell(course) {
  const cell = document.createElement("td");
  const key = document.createElement("code");
  key.className = "admin-course-key";
  const toggle = document.createElement("button");
  toggle.className = "admin-key-toggle";
  toggle.type = "button";
  let hidden = true;
  const render = () => {
    key.textContent = hidden ? "••••••••" : course.course_key;
    const action = hidden ? "Show" : "Hide";
    toggle.replaceChildren(eyeIcon(hidden));
    toggle.setAttribute("aria-label", `${action} course key for ${course.course_name}`);
    toggle.setAttribute("aria-pressed", String(!hidden));
    toggle.title = `${action} course key`;
  };
  toggle.addEventListener("click", () => {
    hidden = !hidden;
    render();
  });
  render();
  cell.append(key, toggle);
  return cell;
}

function appendCourseRows(courses) {
  const tbody = document.getElementById("admin-course-rows");
  for (const course of courses) {
    const row = document.createElement("tr");
    row.append(
      textCell(course.course_id),
      courseKeyCell(course),
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

function sortValue(row, key) {
  if (key === "courses") {
    return row.courses.map((course) => course.course_name).join("\u0000");
  }
  return row[key];
}

function compareValues(left, right) {
  if (typeof left === "number" && typeof right === "number") {
    return left - right;
  }
  return String(left ?? "").localeCompare(String(right ?? ""), undefined, {
    numeric: true,
    sensitivity: "base",
  });
}

function sortedRows(table) {
  const config = TABLE_CONFIG[table];
  const { key, direction } = state.sort[table];
  return [...state[table]].sort((left, right) => (
    direction * (
      compareValues(sortValue(left, key), sortValue(right, key))
      || compareValues(left[config.idKey], right[config.idKey])
    )
  ));
}

function updateSortIndicators(table) {
  const current = state.sort[table];
  document.querySelectorAll(`[data-table="${table}"]`).forEach((button) => {
    const selected = button.dataset.key === current.key;
    button.closest("th").setAttribute(
      "aria-sort",
      selected ? (current.direction === 1 ? "ascending" : "descending") : "none",
    );
    button.querySelector(".admin-sort-indicator").textContent = selected
      ? (current.direction === 1 ? "▲" : "▼")
      : "";
  });
}

function renderTable(table) {
  document.getElementById(TABLE_CONFIG[table].bodyId).replaceChildren();
  const appendRows = {
    courses: appendCourseRows,
    users: appendUserRows,
    movies: appendMovieRows,
  }[table];
  appendRows(sortedRows(table));
  updateSortIndicators(table);
}

function changeSort(table, key) {
  const current = state.sort[table];
  state.sort[table] = {
    key,
    direction: current.key === key ? -current.direction : 1,
  };
  renderTable(table);
}

function bindSortButtons() {
  document.querySelectorAll(".admin-sort").forEach((button) => {
    if (button.dataset.sortBound) {
      return;
    }
    button.dataset.sortBound = "true";
    button.addEventListener("click", () => changeSort(button.dataset.table, button.dataset.key));
  });
}

function reportAdminError(error) {
  const status = document.getElementById("admin-status");
  status.className = "admin-error";
  status.textContent = error.message;
}

async function fetchAdminPage(section, marker = null) {
  const params = new URLSearchParams({ limit: "100", section });
  if (marker) {
    params.set(TABLE_CONFIG[section].markerParam, marker);
  }
  const response = await fetch(`${API_BASE}api/admin/summary?${params}`, {
    credentials: "same-origin",
  });
  const payload = await response.json();
  if (!response.ok || payload.error) {
    throw new Error(payload.message || `Admin summary failed with HTTP ${response.status}`);
  }
  return payload;
}

async function loadRemainingPages(table, marker) {
  // Product sizing assumes no more than roughly 10 courses with 80 students
  // each. Loading every page is deliberate: complete local datasets make the
  // column sorts global. A larger deployment should move sorting and pagination
  // to the server rather than silently stop after an arbitrary page count.
  let nextMarker = marker;
  while (nextMarker) {
    const payload = await fetchAdminPage(table, nextMarker);
    state[table].push(...payload[table].items);
    nextMarker = payload[table].restart_marker;
  }
}

async function loadAdminSummary() {
  bindSortButtons();
  const status = document.getElementById("admin-status");
  status.className = "";
  status.textContent = "Loading all admin records...";
  const payload = await fetchAdminPage("all");
  setText("admin-course-count", payload.counts.courses);
  setText("admin-user-count", payload.counts.users);
  setText("admin-movie-count", payload.counts.movies);
  TABLE_NAMES.forEach((table) => {
    state[table] = [...payload[table].items];
  });
  await Promise.all(TABLE_NAMES.map(
    (table) => loadRemainingPages(table, payload[table].restart_marker),
  ));
  TABLE_NAMES.forEach(renderTable);
  status.textContent = `Read-only access as ${payload.viewer.user_name}. Loaded all records.`;
}

export {
  appendCourseRows,
  appendMovieRows,
  appendUserRows,
  changeSort,
  loadAdminSummary,
  sortedRows,
  state,
};

if (document.getElementById("admin-status")) {
  loadAdminSummary().catch(reportAdminError);
}
