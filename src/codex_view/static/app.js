const container = document.querySelector("#messages");
const status = document.querySelector("#status");
const follow = document.querySelector("#follow");
const progress = document.querySelector("#progress");
const rows = new Map();
let available = true;
let connected = false;
let first = true;
let queue = window.MathJax.startup.promise;

function updateStatus() {
  if (!connected) status.textContent = "Disconnected · reconnecting automatically";
  else if (!available) status.textContent = "Waiting for the saved conversation to become available…";
  else {
    const count = [...rows.values()].filter(row => !row.classList.contains("progress")).length;
    status.textContent = `● Live · ${count} messages`;
  }
}

function latest() {
  [...container.children].reverse().find(row => row.offsetParent !== null)
    ?.scrollIntoView({ behavior: "smooth", block: "start" });
}

progress.addEventListener("change", () => document.body.classList.toggle("show-progress", progress.checked));
document.querySelector("#latest").addEventListener("click", latest);

async function render(data, snapshot) {
  const oldScroll = window.scrollY;
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
  else if (!first) window.scrollTo(0, oldScroll);
  first = false;
  updateStatus();
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
