async function responsePayload(response) {
  try {
    return await response.json();
  } catch (_error) {
    return {};
  }
}

export async function changeCurrentCourse(select, reload = () => window.location.reload()) {
  const status = document.getElementById("current-course-status");
  const previousCourseId = select.dataset.currentCourseId;
  if (select.value === previousCourseId) {
    return;
  }

  select.disabled = true;
  status.className = "";
  status.textContent = "Switching course...";
  try {
    const response = await fetch(`${API_BASE}api/current-course`, {
      method: "PATCH",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ course_id: select.value }),
    });
    const payload = await responsePayload(response);
    if (!response.ok || payload.error) {
      throw new Error(payload.message || `Course change failed with HTTP ${response.status}`);
    }
    select.dataset.currentCourseId = payload.course.course_id;
    reload();
  } catch (error) {
    select.value = previousCourseId;
    status.className = "course-error";
    status.textContent = error.message;
  } finally {
    select.disabled = false;
  }
}

export function initCurrentCourse() {
  const select = document.getElementById("current-course-select");
  if (select) {
    select.addEventListener("change", () => changeCurrentCourse(select));
  }
}

initCurrentCourse();
