(() => {
  const storageKey = "codex-view-theme";
  const systemTheme = window.matchMedia("(prefers-color-scheme: dark)");
  const choices = new Set(["system", "light", "dark"]);
  let mode = "system";

  try {
    const saved = localStorage.getItem(storageKey);
    if (choices.has(saved)) mode = saved;
  } catch (_error) {
    // Storage can be unavailable in privacy modes; the system theme still works.
  }

  function apply() {
    document.documentElement.dataset.theme =
      mode === "system" ? (systemTheme.matches ? "dark" : "light") : mode;
  }

  function set(next) {
    if (!choices.has(next)) return;
    mode = next;
    try {
      localStorage.setItem(storageKey, mode);
    } catch (_error) {
      // Theme selection remains effective for the current page.
    }
    apply();
  }

  systemTheme.addEventListener("change", () => {
    if (mode === "system") apply();
  });
  apply();

  window.codexViewTheme = {
    get mode() { return mode; },
    set,
  };
})();
