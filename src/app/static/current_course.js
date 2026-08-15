import {
  activeCourseId,
  courseName,
  courseUrl,
  storeActiveCourse,
} from "./course_context.js";

async function responsePayload(response) {
  try {
    return await response.json();
  } catch (_error) {
    return {};
  }
}

export function changeCurrentCourse(select, navigate = (courseId) => window.location.assign(courseUrl(courseId))) {
  const status = document.getElementById("current-course-status");
  const previousCourseId = activeCourseId();
  if (select.value === previousCourseId) {
    return;
  }
  try {
    storeActiveCourse(select.value);
    select.dataset.currentCourseId = select.value;
    navigate(select.value);
  } catch (error) {
    select.value = previousCourseId;
    status.className = "course-error";
    status.textContent = error.message;
  }
}

export async function makeDefaultCourse(select) {
  const status = document.getElementById("current-course-status");
  status.className = "";
  status.textContent = "Saving default...";
  const response = await fetch(`${API_BASE}api/default-course`, {
    method: "PATCH",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ course_id: select.value }),
  });
  const payload = await responsePayload(response);
  if (!response.ok || payload.error) {
    status.className = "course-error";
    status.textContent = payload.message || `Default course change failed with HTTP ${response.status}`;
    return;
  }
  status.textContent = `${courseName(select.value)} is now the default course.`;
  document.getElementById("current-course-make-default")?.setAttribute("disabled", "disabled");
}

export function initCurrentCourse() {
  const select = document.getElementById("current-course-select");
  if (select) {
    const courseId = activeCourseId();
    if (courseId) {
      select.value = courseId;
      select.dataset.currentCourseId = courseId;
      const label = document.getElementById("current-course-name");
      if (label) {
        label.textContent = courseName(courseId);
      }
    }
    select.addEventListener("change", () => changeCurrentCourse(select));
    const makeDefault = document.getElementById("current-course-make-default");
    if (makeDefault) {
      makeDefault.disabled = select.value === select.dataset.defaultCourseId;
      makeDefault.addEventListener("click", () => makeDefaultCourse(select));
    }
  }
}

initCurrentCourse();
