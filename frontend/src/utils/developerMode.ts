export const DEVELOPER_ACTIVE_STORAGE_KEY = "lazyrag:developer-active";
export const DEVELOPER_ACTIVE_EVENT = "lazyrag:developer-active-change";

export function isDeveloperModeActive() {
  try {
    return localStorage.getItem(DEVELOPER_ACTIVE_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

export function setDeveloperModeActive(active: boolean) {
  try {
    if (active) {
      localStorage.setItem(DEVELOPER_ACTIVE_STORAGE_KEY, "1");
    } else {
      localStorage.removeItem(DEVELOPER_ACTIVE_STORAGE_KEY);
    }
  } catch {
    // Ignore storage errors.
  }

  window.dispatchEvent(
    new CustomEvent(DEVELOPER_ACTIVE_EVENT, { detail: { active } }),
  );
}
