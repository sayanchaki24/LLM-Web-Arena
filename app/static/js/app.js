document.addEventListener("DOMContentLoaded", () => {
  // Elements
  const promptInput = document.getElementById("prompt-input");
  const btnSubmit = document.getElementById("btn-submit");
  const checkChatGPT = document.getElementById("check-chatgpt");
  const checkClaude = document.getElementById("check-claude");
  const checkGemini = document.getElementById("check-gemini");
  const checkGLM = document.getElementById("check-glm");
  const judgeSelect = document.getElementById("judge-select");
  const checkVisibleBrowser = document.getElementById("check-visible-browser");

  // Status elements
  const btnRefreshStatus = document.getElementById("btn-refresh-status");
  const badgeChatGPT = document.getElementById("status-badge-chatgpt");
  const badgeClaude = document.getElementById("status-badge-claude");
  const badgeGemini = document.getElementById("status-badge-gemini");
  const badgeGLM = document.getElementById("status-badge-glm");
  const textChatGPT = document.getElementById("status-text-chatgpt");
  const textClaude = document.getElementById("status-text-claude");
  const textGemini = document.getElementById("status-text-gemini");
  const textGLM = document.getElementById("status-text-glm");

  // Login Modal
  const btnLoginWindow = document.getElementById("btn-login-window");
  const loginModal = document.getElementById("login-modal");
  const btnCloseModal = document.getElementById("btn-close-modal");
  const btnLaunchLogin = document.getElementById("btn-launch-login");
  const btnSaveSession = document.getElementById("btn-save-session");
  const loginModalStatus = document.getElementById("login-modal-status");

  // Progress & Results
  const progressSection = document.getElementById("progress-section");
  const progressSummary = document.getElementById("progress-summary");
  const progressTimeline = document.getElementById("progress-timeline");
  const verdictSection = document.getElementById("verdict-section");
  const verdictWinnerTitle = document.getElementById("verdict-winner-title");
  const verdictReason = document.getElementById("verdict-reason");
  const btnCopyBest = document.getElementById("btn-copy-best");
  const btnToggleJudgeDetails = document.getElementById("btn-toggle-judge-details");
  const judgeDetailsCollapse = document.getElementById("judge-details-collapse");
  const judgeMarkdownBody = document.getElementById("judge-markdown-body");
  const resultsSection = document.getElementById("results-section");
  const responsesGrid = document.getElementById("responses-grid");

  // History Drawer
  const btnToggleHistory = document.getElementById("btn-toggle-history");
  const historyDrawer = document.getElementById("history-drawer");
  const drawerBackdrop = document.getElementById("drawer-backdrop");
  const btnCloseHistory = document.getElementById("btn-close-history");
  const historyList = document.getElementById("history-list");

  let currentWinnerResponseText = "";
  let websocket = null;

  // Initialize marked configuration
  if (window.marked) {
    marked.setOptions({
      highlight: function(code, lang) {
        if (window.hljs && lang && hljs.getLanguage(lang)) {
          return hljs.highlight(code, { language: lang }).value;
        }
        return window.hljs ? hljs.highlightAuto(code).value : code;
      },
      breaks: true
    });
  }

  // --- Login Status Management ---
  async function refreshLoginStatus() {
    badgeChatGPT.textContent = "Checking...";
    badgeClaude.textContent = "Checking...";
    badgeGemini.textContent = "Checking...";
    if (badgeGLM) badgeGLM.textContent = "Checking...";

    badgeChatGPT.className = "status-indicator status-unknown";
    badgeClaude.className = "status-indicator status-unknown";
    badgeGemini.className = "status-indicator status-unknown";
    if (badgeGLM) badgeGLM.className = "status-indicator status-unknown";

    try {
      const res = await fetch("/api/login/status");
      const data = await res.json();

      updateProviderBadge(badgeChatGPT, textChatGPT, data.ChatGPT);
      updateProviderBadge(badgeClaude, textClaude, data.Claude);
      updateProviderBadge(badgeGemini, textGemini, data.Gemini);
      if (badgeGLM && textGLM) updateProviderBadge(badgeGLM, textGLM, data.GLM);
    } catch (err) {
      console.error("Failed to fetch login status:", err);
      textChatGPT.textContent = "Status check error";
      textClaude.textContent = "Status check error";
      textGemini.textContent = "Status check error";
      if (textGLM) textGLM.textContent = "Status check error";
    }
  }

  function updateProviderBadge(badgeEl, textEl, info) {
    if (!info) return;
    if (info.logged_in) {
      badgeEl.textContent = "Logged In";
      badgeEl.className = "status-indicator status-ready";
      textEl.textContent = info.status || "Ready for inquiries";
    } else {
      badgeEl.textContent = "Sign-In Needed";
      badgeEl.className = "status-indicator status-offline";
      textEl.textContent = info.status || "Click 'Manage Logins' to sign in";
    }
  }

  btnRefreshStatus.addEventListener("click", refreshLoginStatus);

  // --- Login Modal Handlers ---
  btnLoginWindow.addEventListener("click", () => {
    loginModal.classList.remove("hidden");
    loginModalStatus.textContent = "";
  });

  btnCloseModal.addEventListener("click", () => {
    loginModal.classList.add("hidden");
  });

  btnLaunchLogin.addEventListener("click", async () => {
    loginModalStatus.textContent = "Opening Chromium browser window with ChatGPT, Claude, and Gemini tabs...";
    try {
      const res = await fetch("/api/login/open", { method: "POST" });
      const data = await res.json();
      loginModalStatus.textContent = data.message || "Browser window is open. Sign in to your accounts.";
    } catch (err) {
      loginModalStatus.textContent = "Error launching browser: " + err.message;
    }
  });

  btnSaveSession.addEventListener("click", async () => {
    loginModalStatus.textContent = "Saving session and closing browser...";
    try {
      const res = await fetch("/api/login/close", { method: "POST" });
      const data = await res.json();
      loginModalStatus.textContent = data.message || "Session saved!";
      setTimeout(() => {
        loginModal.classList.add("hidden");
        refreshLoginStatus();
      }, 1000);
    } catch (err) {
      loginModalStatus.textContent = "Error closing browser: " + err.message;
    }
  });

  // --- Query Execution & WebSocket ---
  btnSubmit.addEventListener("click", startQueryExecution);

  function startQueryExecution() {
    const prompt = promptInput.value.trim();
    if (!prompt) {
      alert("Please enter a question or prompt first.");
      return;
    }

    const selectedModels = [];
    if (checkChatGPT.checked) selectedModels.push("ChatGPT");
    if (checkClaude.checked) selectedModels.push("Claude");
    if (checkGemini.checked) selectedModels.push("Gemini");
    if (checkGLM && checkGLM.checked) selectedModels.push("GLM");

    if (selectedModels.length === 0) {
      alert("Please select at least one AI model to query.");
      return;
    }

    const judgeModel = judgeSelect.value;
    const headless = !checkVisibleBrowser.checked;

    // Reset UI state
    btnSubmit.disabled = true;
    progressSection.classList.remove("hidden");
    progressTimeline.innerHTML = "";
    progressSummary.textContent = `Dispatching query across ${selectedModels.join(", ")}...`;
    verdictSection.classList.add("hidden");
    resultsSection.classList.add("hidden");
    responsesGrid.innerHTML = "";

    let queryCompleted = false;
    const payload = {
      prompt: prompt,
      models: selectedModels,
      judge_model: judgeModel,
      headless: headless
    };

    // Connect WebSocket
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws/query`;
    websocket = new WebSocket(wsUrl);

    websocket.onopen = () => {
      websocket.send(JSON.stringify({
        prompt: prompt,
        models: selectedModels,
        judge: judgeModel,
        headless: headless
      }));
    };

    websocket.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.type === "progress") {
        addProgressEntry(msg.source, msg.message);
      } else if (msg.type === "complete") {
        queryCompleted = true;
        handleQueryComplete(msg.data);
      } else if (msg.type === "error") {
        addProgressEntry("Error", msg.message);
        btnSubmit.disabled = false;
        progressSummary.textContent = "Query failed: " + msg.message;
      }
    };

    websocket.onerror = (err) => {
      console.warn("WebSocket error, falling back to HTTP endpoint:", err);
      if (!queryCompleted) {
        addProgressEntry("Network", "WebSocket unavailable, automatically switching to direct HTTP request...");
        executeHttpFallback(payload);
      }
    };

    websocket.onclose = () => {
      if (!queryCompleted) {
        executeHttpFallback(payload);
      }
    };
  }

  async function executeHttpFallback(payload) {
    addProgressEntry("System", "Executing multi-model query in background...");
    try {
      const resp = await fetch("/api/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (!resp.ok) {
        const errJson = await resp.json();
        throw new Error(errJson.detail || "HTTP Query failed");
      }
      const data = await resp.json();
      handleQueryComplete(data);
    } catch (e) {
      addProgressEntry("Error", e.message);
      progressSummary.textContent = "Query failed: " + e.message;
      btnSubmit.disabled = false;
    }
  }

  function addProgressEntry(source, message) {
    progressSummary.textContent = `[${source}] ${message}`;
    const item = document.createElement("div");
    item.className = "progress-item";

    const badge = document.createElement("span");
    badge.className = `progress-badge badge-${source.toLowerCase()}`;
    badge.textContent = source;

    const text = document.createElement("span");
    text.textContent = message;

    item.appendChild(badge);
    item.appendChild(text);
    progressTimeline.appendChild(item);
    progressTimeline.scrollTop = progressTimeline.scrollHeight;
  }

  function handleQueryComplete(data) {
    btnSubmit.disabled = false;
    progressSection.classList.add("hidden");

    // Display Verdict Hero
    verdictSection.classList.remove("hidden");
    const winner = data.winner || "None";
    verdictWinnerTitle.textContent = `Winner: ${winner}`;
    verdictReason.textContent = data.judge_reason || "Selected based on evaluation criteria.";

    // Render detailed AI evaluation
    if (data.evaluation_summary) {
      judgeMarkdownBody.innerHTML = marked.parse(data.evaluation_summary);
      btnToggleJudgeDetails.classList.remove("hidden");
    } else {
      btnToggleJudgeDetails.classList.add("hidden");
    }

    // Populate responses side-by-side
    resultsSection.classList.remove("hidden");
    responsesGrid.innerHTML = "";

    data.results.forEach((res) => {
      const isWinner = res.model_name === data.winner;
      if (isWinner && res.response_text) {
        currentWinnerResponseText = res.response_text;
      }

      const card = createResponseCard(res, isWinner);
      responsesGrid.appendChild(card);
    });

    if (window.hljs) {
      hljs.highlightAll();
    }
  }

  function createResponseCard(res, isWinner) {
    const card = document.createElement("div");
    card.className = `model-response-card ${isWinner ? "is-winner" : ""}`;

    const headerBar = document.createElement("div");
    headerBar.className = "card-header-bar";

    const titleArea = document.createElement("div");
    titleArea.className = "card-header-title";
    const pill = document.createElement("span");
    pill.className = `provider-pill pill-${res.model_name.toLowerCase()}`;
    pill.textContent = res.model_name;
    titleArea.appendChild(pill);

    if (isWinner) {
      const crown = document.createElement("span");
      crown.className = "crown-badge";
      crown.textContent = "🏆 WINNER";
      titleArea.appendChild(crown);
    }
    headerBar.appendChild(titleArea);

    // Metrics Strip
    const metricsStrip = document.createElement("div");
    metricsStrip.className = "metrics-strip";
    if (res.status === "success") {
      metricsStrip.innerHTML = `
        <span class="metric-item"><strong>${res.word_count || 0}</strong> words</span>
        <span class="metric-item"><strong>${res.code_blocks || 0}</strong> code blocks</span>
        <span class="metric-item"><strong>${res.elapsed_seconds || 0}s</strong></span>
        <span class="metric-item">Score: <strong>${res.heuristic_score || 0}</strong>/100</span>
      `;
    } else {
      metricsStrip.innerHTML = `<span class="metric-item" style="color:#ef4444;">Status: ${res.status.toUpperCase()}</span>`;
    }

    // Body content
    const cardBody = document.createElement("div");
    cardBody.className = "card-body-content markdown-body";
    if (res.status === "success" && res.response_text) {
      cardBody.innerHTML = marked.parse(res.response_text);
    } else {
      cardBody.innerHTML = `<p style="color:#f87171;"><em>${res.error_message || "No response received or model not logged in."}</em></p>`;
    }

    // Footer actions
    const footer = document.createElement("div");
    footer.className = "card-footer-actions";
    const copyBtn = document.createElement("button");
    copyBtn.className = "btn-secondary-small";
    copyBtn.textContent = "📋 Copy Response";
    copyBtn.addEventListener("click", () => {
      if (res.response_text) {
        navigator.clipboard.writeText(res.response_text);
        copyBtn.textContent = "✓ Copied!";
        setTimeout(() => copyBtn.textContent = "📋 Copy Response", 2000);
      }
    });
    footer.appendChild(copyBtn);

    card.appendChild(headerBar);
    card.appendChild(metricsStrip);
    card.appendChild(cardBody);
    card.appendChild(footer);

    return card;
  }

  // Toggle Judge Details
  btnToggleJudgeDetails.addEventListener("click", () => {
    judgeDetailsCollapse.classList.toggle("hidden");
    btnToggleJudgeDetails.textContent = judgeDetailsCollapse.classList.contains("hidden")
      ? "🔍 Show Detailed AI Evaluation"
      : "▲ Hide Detailed AI Evaluation";
  });

  // Copy Best Response
  btnCopyBest.addEventListener("click", () => {
    if (currentWinnerResponseText) {
      navigator.clipboard.writeText(currentWinnerResponseText);
      btnCopyBest.textContent = "✓ Copied Best Answer!";
      setTimeout(() => btnCopyBest.textContent = "📋 Copy Best Answer", 2000);
    }
  });

  // --- History Drawer ---
  btnToggleHistory.addEventListener("click", openHistory);
  btnCloseHistory.addEventListener("click", closeHistory);
  drawerBackdrop.addEventListener("click", closeHistory);

  async function openHistory() {
    historyDrawer.classList.remove("hidden");
    drawerBackdrop.classList.remove("hidden");
    historyList.innerHTML = "<p style='color:var(--text-muted); font-size:0.85rem;'>Loading past inquiries...</p>";

    try {
      const res = await fetch("/api/history");
      const list = await res.json();
      historyList.innerHTML = "";

      if (list.length === 0) {
        historyList.innerHTML = "<p style='color:var(--text-muted); font-size:0.85rem;'>No past inquiries recorded yet.</p>";
        return;
      }

      list.forEach((item) => {
        const div = document.createElement("div");
        div.className = "history-item";
        const dateStr = new Date(item.created_at).toLocaleString();
        div.innerHTML = `
          <div class="history-item-prompt">${item.prompt}</div>
          <div class="history-item-meta">
            <span>Winner: <strong style="color:var(--accent-gold);">${item.winner || "None"}</strong></span>
            <span>${dateStr}</span>
          </div>
        `;
        div.addEventListener("click", () => {
          loadHistoryItem(item);
          closeHistory();
        });
        historyList.appendChild(div);
      });
    } catch (err) {
      historyList.innerHTML = "<p style='color:red;'>Failed to load history.</p>";
    }
  }

  function closeHistory() {
    historyDrawer.classList.add("hidden");
    drawerBackdrop.classList.add("hidden");
  }

  function loadHistoryItem(item) {
    promptInput.value = item.prompt;
    handleQueryComplete({
      winner: item.winner,
      judge_reason: item.judge_reason,
      evaluation_summary: item.evaluation_summary,
      results: item.responses || []
    });
  }

  // Initial check on load
  refreshLoginStatus();
});
