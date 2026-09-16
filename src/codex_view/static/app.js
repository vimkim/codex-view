const container = document.querySelector("#messages");
const status = document.querySelector("#status");
const follow = document.querySelector("#follow");
const progress = document.querySelector("#progress");
const themeButtons = [...document.querySelectorAll("[data-theme-choice]")];
const copyStatus = document.querySelector("#copy-status");
const latestButton = document.querySelector("#latest");
const latestCount = document.querySelector("#latest-count");
const rows = new Map();
let available = true;
let connected = false;
let first = true;
let queue = window.MathJax.startup.promise;
let unseenCount = 0;
let scrollFrame;
const alignmentSensitiveLanguages = new Set([
  "console",
  "diff",
  "log",
  "logs",
  "output",
  "patch",
  "shell-session",
  "terminal",
]);

function updateThemeButtons() {
  for (const button of themeButtons) {
    button.setAttribute(
      "aria-pressed",
      String(button.dataset.themeChoice === window.codexViewTheme.mode),
    );
  }
}

for (const button of themeButtons) {
  button.addEventListener("click", () => {
    window.codexViewTheme.set(button.dataset.themeChoice);
    updateThemeButtons();
  });
  button.addEventListener("keydown", event => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const direction = event.key === "ArrowRight" ? 1 : -1;
    const current = themeButtons.indexOf(button);
    const next = themeButtons[(current + direction + themeButtons.length) % themeButtons.length];
    next.focus();
    window.codexViewTheme.set(next.dataset.themeChoice);
    updateThemeButtons();
  });
}
updateThemeButtons();

function enhanceCodeBlocks(root) {
  for (const code of root.querySelectorAll("pre > code")) {
    const pre = code.parentElement;
    if (pre.closest(".code-block")) continue;
    const languageClass = [...code.classList].find(name => name.startsWith("language-"));
    const original = languageClass?.slice("language-".length) || "";
    const label = pre.dataset.language || original;
    pre.classList.add("code-surface");
    if (!label) {
      pre.classList.add("code-plain");
      continue;
    }

    const block = document.createElement("div");
    block.className = "code-block";
    if (alignmentSensitiveLanguages.has(original.toLowerCase())) {
      block.classList.add("code-scroll");
    }
    const toolbar = document.createElement("div");
    toolbar.className = "code-toolbar";
    const language = document.createElement("span");
    language.className = "code-language";
    language.textContent = label;
    const copy = document.createElement("button");
    copy.type = "button";
    copy.className = "copy-button";
    copy.dataset.copyCode = "";
    copy.setAttribute("aria-label", `Copy ${label} code`);
    copy.innerHTML = "<span>Copy</span>";
    toolbar.append(language, copy);
    pre.replaceWith(block);
    block.append(toolbar, pre);
  }
}

function selectCode(code) {
  const selection = window.getSelection();
  const range = document.createRange();
  range.selectNodeContents(code);
  selection.removeAllRanges();
  selection.addRange(range);
}

function legacyCopy(source) {
  const textarea = document.createElement("textarea");
  textarea.value = source;
  textarea.readOnly = true;
  textarea.style.cssText = "position:fixed;inset:0 auto auto -9999px";
  document.body.append(textarea);
  textarea.select();
  let copied = false;
  try {
    copied = document.execCommand("copy");
  } catch (_error) {
    copied = false;
  }
  textarea.remove();
  return copied;
}

async function copyCode(button) {
  const block = button.closest(".code-block");
  const code = block?.querySelector("code");
  if (!code) return;
  const source = code.textContent;
  const language = block.querySelector(".code-language").textContent;
  let copied = false;

  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(source);
      copied = true;
    } catch (_error) {
      copied = false;
    }
  }
  if (!copied) copied = legacyCopy(source);

  const label = button.querySelector("span");
  if (copied) {
    button.dataset.state = "copied";
    label.textContent = "Copied";
    copyStatus.textContent = `${language} code copied to the clipboard.`;
  } else {
    selectCode(code);
    button.dataset.state = "manual";
    label.textContent = "Selected";
    copyStatus.textContent =
      "Automatic copy failed. The code is selected; copy it manually.";
  }
  window.setTimeout(() => {
    delete button.dataset.state;
    label.textContent = "Copy";
  }, 1800);
}

document.addEventListener("click", event => {
  const button = event.target.closest("[data-copy-code]");
  if (button) copyCode(button);
});

function updateStatus() {
  if (!connected) status.textContent = "Disconnected · reconnecting automatically";
  else if (!available) status.textContent = "Waiting for the saved conversation to become available…";
  else {
    const count = [...rows.values()].filter(row => !row.classList.contains("progress")).length;
    status.textContent = `● Live · ${count} messages`;
  }
}

function distanceFromBottom() {
  return document.documentElement.scrollHeight - (window.scrollY + window.innerHeight);
}

function clearUnseen() {
  unseenCount = 0;
  latestButton.classList.remove("has-unseen");
  latestCount.textContent = "";
}

function updateLatestVisibility() {
  const threshold = Math.max(220, window.innerHeight * .4);
  if (distanceFromBottom() < 70) clearUnseen();
  latestButton.hidden = distanceFromBottom() <= threshold;
}

function latest() {
  clearUnseen();
  window.scrollTo({
    top: document.documentElement.scrollHeight,
    behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
  });
}

progress.addEventListener("change", () => document.body.classList.toggle("show-progress", progress.checked));
latestButton.addEventListener("click", latest);
window.addEventListener("scroll", () => {
  if (scrollFrame) return;
  scrollFrame = requestAnimationFrame(() => {
    updateLatestVisibility();
    scrollFrame = undefined;
  });
}, { passive: true });
window.addEventListener("resize", updateLatestVisibility);

async function render(data, snapshot) {
  const oldScroll = window.scrollY;
  const wasNearEnd = distanceFromBottom() < 70;
  available = data.available;
  if (snapshot) {
    document.querySelector("#title").textContent = data.title;
    document.title = `${data.title} · Codex View`;
    document.querySelector("#directory").textContent = data.cwd;
    const ids = new Set(data.messages.map(message => message.id));
    for (const [id, row] of rows) {
      if (!ids.has(id)) {
        window.MathJax.typesetClear([row]);
        row.remove();
        rows.delete(id);
      }
    }
  }
  const added = [];
  for (const message of data.messages) {
    const previous = rows.get(message.id);
    if (previous?.dataset.source === message.html) continue;
    const row = document.createElement("article");
    row.className = `message ${message.role} ${message.phase}`;
    row.dataset.source = message.html;
    row.id = `message-${message.id}`;
    const heading = document.createElement("div");
    heading.className = "message-heading";
    const speaker = document.createElement("strong");
    speaker.textContent = message.role === "user" ? "You" : (message.phase === "progress" ? "Codex · progress" : "Codex");
    const time = document.createElement("time");
    const date = new Date(message.time);
    if (!Number.isNaN(date.getTime())) {
      time.dateTime = date.toISOString();
      time.textContent = date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
    }
    heading.append(speaker, time);
    const body = document.createElement("div");
    body.className = "message-body";
    body.innerHTML = message.html;
    body.querySelectorAll("a").forEach(link => {
      link.target = "_blank";
      link.rel = "noopener noreferrer";
    });
    enhanceCodeBlocks(body);
    row.append(heading, body);
    if (previous) {
      window.MathJax.typesetClear([previous]);
      previous.replaceWith(row);
    } else container.append(row);
    rows.set(message.id, row);
    added.push(row);
  }
  if (added.length) await window.MathJax.typesetPromise(added);
  if (!first && follow.checked && added.some(row => row.offsetParent !== null)) latest();
  else if (!first) {
    window.scrollTo(0, oldScroll);
    if (!wasNearEnd) {
      const visibleAdded = added.filter(row => row.offsetParent !== null).length;
      if (visibleAdded) {
        unseenCount += visibleAdded;
        latestButton.classList.add("has-unseen");
        latestCount.textContent = `${unseenCount} new`;
      }
    }
  }
  first = false;
  updateStatus();
  updateLatestVisibility();
}

const events = new EventSource("/api/events");
events.onopen = () => { connected = true; updateStatus(); };
events.onerror = () => { connected = false; updateStatus(); };
for (const kind of ["snapshot", "append", "status"]) {
  events.addEventListener(kind, event => {
    queue = queue.then(async () => {
      const data = JSON.parse(event.data);
      if (kind === "status") {
        available = data.available;
        updateStatus();
      } else await render(data, kind === "snapshot");
    }).catch(error => {
      console.error(error);
      status.textContent = "A message could not be rendered. Reload this page to retry.";
    });
  });
}
