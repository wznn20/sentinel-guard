const state = {
  selectedSession: "",
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

async function api(path, body) {
  const options = body
    ? {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }
    : {};
  const response = await fetch(path, options);
  return await response.json();
}

function renderMetrics(data) {
  const grid = document.getElementById("metricGrid");
  const cards = [
    ["Sessions", data.sessions],
    ["Tasks", data.tasks],
    ["Approvals", data.approvals],
    ["Adapters", Array.isArray(data.adapters) ? data.adapters.length : 0],
  ];
  grid.innerHTML = cards
    .map(
      ([label, value]) => `
        <article class="metric-card">
          <div class="metric-label">${escapeHtml(label)}</div>
          <div class="metric-value">${escapeHtml(value)}</div>
        </article>
      `,
    )
    .join("");
}

function renderTable(targetId, headings, rows) {
  const target = document.getElementById(targetId);
  target.innerHTML = `
    <table>
      <thead>
        <tr>${headings.map((heading) => `<th>${escapeHtml(heading)}</th>`).join("")}</tr>
      </thead>
      <tbody>
        ${rows.length ? rows.join("") : `<tr><td colspan="${headings.length}">No data.</td></tr>`}
      </tbody>
    </table>
  `;
}

async function refreshOverview() {
  const data = await api("/api/overview");
  document.getElementById("identityLabel").textContent = `${data.identity} · ${data.model}`;
  renderMetrics(data);

  renderTable(
    "sessionsTable",
    ["Session", "Agent", "Channel", "Summary"],
    (data.recent_sessions || []).map(
      (row) => `
        <tr>
          <td><button class="secondary" type="button" data-session="${escapeHtml(row.session_id)}">${escapeHtml(row.session_id)}</button></td>
          <td><span class="tag">${escapeHtml(row.agent_id)}</span></td>
          <td>${escapeHtml(row.channel)}</td>
          <td>${escapeHtml(row.summary || "")}</td>
        </tr>
      `,
    ),
  );

  renderTable(
    "tasksTable",
    ["ID", "Status", "Owner", "Title", "Action"],
    (data.recent_tasks || []).map(
      (row) => `
        <tr>
          <td>${escapeHtml(row.id)}</td>
          <td><span class="tag soft">${escapeHtml(row.status)}</span></td>
          <td>${escapeHtml(row.owner)}</td>
          <td>${escapeHtml(row.title)}</td>
          <td><button type="button" data-review-task="${escapeHtml(row.id)}">Mark Review</button></td>
        </tr>
      `,
    ),
  );

  renderTable(
    "approvalsTable",
    ["ID", "Action", "Session", "Decision"],
    (data.approvals_detail || []).map(
      (row) => `
        <tr>
          <td>${escapeHtml(row.id)}</td>
          <td><span class="tag warn">${escapeHtml(row.action)}</span></td>
          <td>${escapeHtml(row.session_id)}</td>
          <td>
            <button type="button" data-approval="${escapeHtml(row.id)}:approved">Approve</button>
            <button class="secondary" type="button" data-approval="${escapeHtml(row.id)}:denied">Deny</button>
          </td>
        </tr>
      `,
    ),
  );

  renderTable(
    "delegationsTable",
    ["ID", "Status", "Child Task", "Action"],
    (data.delegations_detail || []).map(
      (row) => `
        <tr>
          <td>${escapeHtml(row.id)}</td>
          <td><span class="tag">${escapeHtml(row.status)}</span></td>
          <td>${escapeHtml(row.child_task_id || "")}</td>
          <td><button type="button" data-delegation="${escapeHtml(row.id)}">Run</button></td>
        </tr>
      `,
    ),
  );

  document.getElementById("sandboxBlock").textContent = JSON.stringify(data.sandbox, null, 2);

  const select = document.getElementById("sessionSelect");
  const previous = state.selectedSession;
  select.innerHTML =
    '<option value="">Select session…</option>' +
    (data.recent_sessions || [])
      .map(
        (row) =>
          `<option value="${escapeHtml(row.session_id)}">${escapeHtml(row.session_id)}</option>`,
      )
      .join("");
  if (previous) {
    select.value = previous;
    if (select.value) {
      await loadSession(previous);
    }
  }
}

async function loadSession(sessionId) {
  state.selectedSession = sessionId;
  if (!sessionId) {
    document.getElementById("sessionTimeline").textContent = "Select a session.";
    document.getElementById("sessionTree").textContent = "Select a session.";
    document.getElementById("sessionTools").textContent = "Select a session.";
    document.getElementById("sessionTasks").textContent = "Select a session.";
    return;
  }

  const data = await fetch(`/api/session?session_id=${encodeURIComponent(sessionId)}`).then((res) =>
    res.json(),
  );
  document.getElementById("sessionTimeline").classList.remove("empty");
  document.getElementById("sessionTimeline").innerHTML = (data.turns || [])
    .map((turn) => {
      let cls = turn.role || "assistant";
      const channel = String(turn.channel || "");
      if (channel.includes("tool")) cls = "tool";
      else if (channel.includes("approval")) cls = "approval";
      else if (channel.includes("worker")) cls = "worker";
      return `
        <div class="message ${escapeHtml(cls)}">
          <div class="message-meta">
            ${escapeHtml(turn.role)} · ${escapeHtml(turn.skill || "-")} · ${escapeHtml(
              turn.created_at || "",
            )}
          </div>
          <div>${escapeHtml(turn.content || "")}</div>
        </div>
      `;
    })
    .join("");
  document.getElementById("sessionTree").textContent = JSON.stringify(data.tree, null, 2);
  document.getElementById("sessionTools").textContent = JSON.stringify(data.tool_runs, null, 2);
  document.getElementById("sessionTasks").textContent = JSON.stringify(data.tasks, null, 2);
}

async function planGoal() {
  const goal = document.getElementById("goalInput").value.trim();
  if (!goal) return;
  await api("/api/plan", { goal });
  document.getElementById("goalInput").value = "";
  await refreshOverview();
}

async function aggregateNext() {
  await api("/api/aggregate-next", {});
  await refreshOverview();
}

async function sendMessage() {
  const sessionId = document.getElementById("sessionSelect").value;
  const message = document.getElementById("chatInput").value.trim();
  if (!sessionId || !message) return;
  await api("/api/chat/send", { session_id: sessionId, message });
  document.getElementById("chatInput").value = "";
  await refreshOverview();
  await loadSession(sessionId);
}

document.addEventListener("click", async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;

  const sessionId = target.getAttribute("data-session");
  if (sessionId) {
    document.getElementById("sessionSelect").value = sessionId;
    await loadSession(sessionId);
    return;
  }

  const approval = target.getAttribute("data-approval");
  if (approval) {
    const [approvalId, status] = approval.split(":");
    await api("/api/approval/decide", {
      approval_id: Number(approvalId),
      status,
    });
    await refreshOverview();
    return;
  }

  const delegationId = target.getAttribute("data-delegation");
  if (delegationId) {
    await api("/api/delegation/run", { delegation_id: Number(delegationId) });
    await refreshOverview();
    return;
  }

  const reviewTaskId = target.getAttribute("data-review-task");
  if (reviewTaskId) {
    await api("/api/task/update", {
      task_id: Number(reviewTaskId),
      status: "review",
    });
    await refreshOverview();
  }
});

document.getElementById("sessionSelect").addEventListener("change", async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLSelectElement)) return;
  await loadSession(target.value);
});

document.getElementById("planButton").addEventListener("click", planGoal);
document.getElementById("aggregateButton").addEventListener("click", aggregateNext);
document.getElementById("refreshButton").addEventListener("click", refreshOverview);
document.getElementById("sendButton").addEventListener("click", sendMessage);

refreshOverview();
setInterval(refreshOverview, 5000);
