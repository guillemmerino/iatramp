(function () {
  "use strict";

  document.querySelectorAll("[data-generation-form]").forEach(function (form) {
    form.addEventListener("submit", function () {
      var button = form.querySelector("button[type='submit']");
      if (!button || button.disabled) return;
      button.disabled = true;
      button.setAttribute("aria-busy", "true");
      var label = button.querySelector("[data-generation-label]");
      if (label) label.textContent = "Generant…";
    });
  });

  var progress = document.querySelector("[data-generation-progress]");
  if (!progress) return;

  var statusUrl = progress.getAttribute("data-status-url");
  var message = progress.querySelector("[data-progress-message]");
  var time = progress.querySelector("[data-progress-time]");
  var events = progress.querySelector("[data-progress-events]");
  var startedAt = Date.now();
  var serverElapsed = 0;

  function formatTime(seconds) {
    var minutes = Math.floor(seconds / 60);
    var remainder = seconds % 60;
    return minutes + ":" + String(remainder).padStart(2, "0") + " transcorreguts";
  }

  function setText(selector, value) {
    var node = progress.querySelector(selector);
    if (node) node.textContent = String(value);
  }

  function renderEvents(rows) {
    if (!events || !rows || !rows.length) return;
    events.replaceChildren();
    rows.forEach(function (row) {
      var item = document.createElement("li");
      var label = document.createElement("strong");
      var detail = document.createElement("span");
      label.textContent = row.label;
      detail.textContent = row.detail;
      item.append(label, detail);
      if (!row.ok) item.classList.add("is-error");
      events.appendChild(item);
    });
  }

  function poll() {
    fetch(statusUrl, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (response) {
        if (!response.ok) throw new Error("status unavailable");
        return response.json();
      })
      .then(function (data) {
        serverElapsed = data.progress.elapsed_seconds || serverElapsed;
        startedAt = Date.now();
        if (message) message.textContent = data.progress.message;
        setText("[data-progress-searches]", data.stats.searches);
        setText("[data-progress-candidates]", data.stats.unique_candidates);
        setText("[data-progress-tools]", data.stats.tool_calls);
        setText("[data-progress-rounds]", data.stats.rounds);
        renderEvents(data.events);
        if (data.terminal) {
          var target = new URL(data.redirect_url, window.location.href);
          if (
            target.pathname === window.location.pathname &&
            target.search === window.location.search
          ) {
            window.location.reload();
          } else {
            window.location.assign(target.href);
          }
          return;
        }
        window.setTimeout(poll, data.poll_after_ms || 1500);
      })
      .catch(function () {
        if (message) message.textContent = "Reconnectant amb el procés de generació…";
        window.setTimeout(poll, 3000);
      });
  }

  window.setInterval(function () {
    if (!time) return;
    var elapsed = serverElapsed + Math.floor((Date.now() - startedAt) / 1000);
    time.textContent = formatTime(elapsed);
  }, 1000);

  poll();
})();
