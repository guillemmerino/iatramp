(function () {
  function parseTopics(helper) {
    var script = helper && helper.previousElementSibling && helper.previousElementSibling.id === "avatar-helper-messages"
      ? helper.previousElementSibling
      : document.getElementById("avatar-helper-messages");
    if (!script) {
      return {};
    }
    try {
      return JSON.parse(script.textContent || "{}");
    } catch (err) {
      return {};
    }
  }

  function trimSlashes(value) {
    return String(value || "").replace(/^\/+/, "");
  }

  function assetUrl(helper, path) {
    var value = String(path || "");
    if (!value) {
      return "";
    }
    if (/^(https?:)?\/\//.test(value) || value.charAt(0) === "/" || value.indexOf("data:") === 0) {
      return value;
    }
    var prefix = String(helper.dataset.avatarAssetsPrefix || helper.dataset.staticPrefix || "/static/");
    return prefix + trimSlashes(value);
  }

  function topicFor(topics, topicId, fallbackId) {
    return topics[topicId] || topics[fallbackId] || topics.welcome || null;
  }

  function stepsFor(topic) {
    return Array.isArray(topic && topic.steps) ? topic.steps : [];
  }

  function avatarFor(topic, step, stepIndex) {
    if (step && step.avatar) {
      return step.avatar;
    }
    var avatars = Array.isArray(topic && topic.avatars) ? topic.avatars : [];
    if (avatars.length) {
      return avatars[stepIndex % avatars.length];
    }
    return topic && topic.avatar ? topic.avatar : "avatar/greeting_2.png";
  }

  function selectorForAction(action) {
    var selector = String(action && action.selector || "").trim();
    if (selector) {
      return selector;
    }
    var actionName = String(action && action.action || "").trim();
    if (!actionName) {
      return "";
    }
    return "[data-avatar-action='" + actionName.replace(/'/g, "\\'") + "']";
  }

  function targetForAction(action) {
    var selector = selectorForAction(action);
    if (!selector) {
      return null;
    }
    try {
      return document.querySelector(selector);
    } catch (err) {
      return null;
    }
  }

  function runAction(actionConfig) {
    var action = typeof actionConfig === "string" ? { action: actionConfig } : (actionConfig || {});
    var actionName = String(action.action || "").trim();
    if (actionName === "navigate") {
      var target = targetForAction(action);
      if (target && target.href) {
        window.location.href = target.href;
      }
      return;
    }
    if (actionName === "open_panel") {
      var panel = String(action.panel || "").trim();
      var panelApps = [window.InscripcionsApp, window.PhasePlanner, window.RotacionsPlanner];
      var panelApp = panelApps.find(function (candidate) {
        return candidate && typeof candidate.openPanel === "function";
      });
      if (panel && panelApp) {
        try {
          panelApp.openPanel(panel);
        } catch (err) {}
      }
      return;
    }
    if (actionName === "create_competition") {
      var createLink = document.querySelector("[data-avatar-action='create_competition']");
      if (createLink && createLink.href) {
        window.location.href = createLink.href;
      }
      return;
    }
    if (actionName === "create_apparatus") {
      var createApparatusLink = document.querySelector("[data-avatar-action='create_apparatus']");
      if (createApparatusLink && createApparatusLink.href) {
        window.location.href = createApparatusLink.href;
      }
      return;
    }
    if (actionName === "open_competition") {
      var grid = document.getElementById("competitionCardGrid");
      if (grid) {
        grid.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    }
  }

  function setupHelper(helper) {
    if (helper.__avatarHelperReady) {
      return;
    }
    var topics = parseTopics(helper);
    helper.__avatarTopics = topics;
    helper.__avatarHelperReady = true;
    var openButton = helper.querySelector(".avatar-helper__toggle");
    var hideButton = helper.querySelector(".avatar-helper__hide");
    var bubbleOpenButton = helper.querySelector(".avatar-helper__bubble-toggle");
    var bubbleCloseButton = helper.querySelector(".avatar-helper__bubble-close");
    var bubbleNode = helper.querySelector(".avatar-helper__bubble");
    var titleNode = helper.querySelector("[data-avatar-title]");
    var messageNode = helper.querySelector("[data-avatar-message]");
    var countNode = helper.querySelector("[data-avatar-step-count]");
    var imageNode = helper.querySelector("[data-avatar-image]");
    var prevButton = helper.querySelector("[data-avatar-prev]");
    var nextButton = helper.querySelector("[data-avatar-next]");
    var actionsNode = helper.querySelector("[data-avatar-actions]");
    var chatLogNode = helper.querySelector("[data-avatar-chat-log]");
    var chatEmptyNode = helper.querySelector("[data-avatar-chat-empty]");
    var chatFormNode = helper.querySelector("[data-avatar-chat-form]");
    var chatInputNode = helper.querySelector("[data-avatar-chat-input]");
    var chatSubmitNode = helper.querySelector("[data-avatar-chat-submit]");
    var chatStatusNode = helper.querySelector("[data-avatar-chat-status]");
    var initialTopicId = helper.dataset.avatarInitialTopic || "welcome";
    var currentTopicId = initialTopicId;
    var currentStep = 0;
    var chatHistory = [];
    var bubbleOffset = { x: 0, y: 0 };
    var dragState = null;
    var highlightedNodes = [];
    var contextRenderId = 0;

    function setOpenState(isOpen) {
      helper.classList.toggle("is-open", isOpen);
      if (!isOpen) {
        helper.classList.remove("is-bubble-hidden");
        clearContextHighlight();
        saveBubbleOffset();
      }
      if (openButton) {
        openButton.setAttribute("aria-expanded", isOpen ? "true" : "false");
      }
    }

    function storageKey() {
      return "ia-score-avatar-bubble-offset";
    }

    function chatStorageKey() {
      var scope = helper.dataset.avatarCompeticioId || window.location.pathname || "global";
      return "ia-score-avatar-chat-" + String(scope);
    }

    function normalizeOffset(value) {
      var x = Number(value && value.x);
      var y = Number(value && value.y);
      return {
        x: Number.isFinite(x) ? x : 0,
        y: Number.isFinite(y) ? y : 0,
      };
    }

    function applyBubbleOffset() {
      helper.style.setProperty("--avatar-bubble-x", String(Math.round(bubbleOffset.x)) + "px");
      helper.style.setProperty("--avatar-bubble-y", String(Math.round(bubbleOffset.y)) + "px");
    }

    function saveBubbleOffset() {
      try {
        window.localStorage.setItem(storageKey(), JSON.stringify(normalizeOffset(bubbleOffset)));
      } catch (err) {
        return;
      }
    }

    function restoreBubbleOffset() {
      try {
        var saved = JSON.parse(window.localStorage.getItem(storageKey()) || "null");
        if (saved) {
          bubbleOffset = normalizeOffset(saved);
          applyBubbleOffset();
        }
      } catch (err) {
        return;
      }
    }

    function getCookie(name) {
      var value = "; " + document.cookie;
      var parts = value.split("; " + name + "=");
      if (parts.length === 2) {
        return parts.pop().split(";").shift();
      }
      return "";
    }

    function trimChatHistory(history) {
      return history.slice(Math.max(0, history.length - 12));
    }

    function saveChatHistory() {
      try {
        window.localStorage.setItem(chatStorageKey(), JSON.stringify(trimChatHistory(chatHistory)));
      } catch (err) {
        return;
      }
    }

    function addChatMessage(role, content, save) {
      if (!chatLogNode) {
        return;
      }
      var text = String(content || "").trim();
      if (!text) {
        return;
      }
      if (chatEmptyNode) {
        chatEmptyNode.remove();
        chatEmptyNode = null;
      }
      var message = document.createElement("div");
      message.className = "avatar-helper__chat-message avatar-helper__chat-message--" + (role === "user" ? "user" : "assistant");
      message.textContent = text;
      chatLogNode.appendChild(message);
      chatLogNode.scrollTop = chatLogNode.scrollHeight;
      if (save !== false) {
        chatHistory.push({ role: role === "user" ? "user" : "assistant", content: text });
        chatHistory = trimChatHistory(chatHistory);
        saveChatHistory();
      }
    }

    function restoreChatHistory() {
      try {
        var saved = JSON.parse(window.localStorage.getItem(chatStorageKey()) || "[]");
        chatHistory = Array.isArray(saved) ? trimChatHistory(saved) : [];
      } catch (err) {
        chatHistory = [];
      }
      chatHistory.forEach(function (item) {
        if (item && item.role && item.content) {
          addChatMessage(item.role, item.content, false);
        }
      });
    }

    function setChatStatus(message) {
      if (chatStatusNode) {
        chatStatusNode.textContent = message || "";
      }
    }

    function setChatBusy(isBusy) {
      if (chatSubmitNode) {
        chatSubmitNode.disabled = isBusy;
        chatSubmitNode.textContent = isBusy ? "..." : "Envia";
      }
      if (chatInputNode) {
        chatInputNode.disabled = isBusy;
      }
    }

    function currentChatContext() {
      return {
        page_title: document.title || "",
        path: window.location.pathname || "",
        topic: currentTopicId || initialTopicId,
        competicio_id: helper.dataset.avatarCompeticioId || "",
      };
    }

    function sendChatMessage() {
      if (!chatInputNode || !helper.dataset.avatarChatUrl) {
        return;
      }
      var text = String(chatInputNode.value || "").trim();
      if (!text) {
        return;
      }
      addChatMessage("user", text, true);
      chatInputNode.value = "";
      setChatBusy(true);
      setChatStatus("Pensant...");

      fetch(helper.dataset.avatarChatUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCookie("csrftoken"),
        },
        body: JSON.stringify(Object.assign(currentChatContext(), {
          message: text,
          history: chatHistory.slice(0, -1),
        })),
      })
        .then(function (response) {
          return response.json().then(function (data) {
            if (!response.ok || !data.ok) {
              throw new Error(data.error || "No he pogut respondre ara mateix.");
            }
            return data;
          });
        })
        .then(function (data) {
          addChatMessage("assistant", data.reply || "No he rebut cap resposta.", true);
          setChatStatus("");
        })
        .catch(function (err) {
          addChatMessage("assistant", err.message || "No he pogut respondre ara mateix.", true);
          setChatStatus("");
        })
        .finally(function () {
          setChatBusy(false);
          if (chatInputNode) {
            chatInputNode.focus();
          }
        });
    }

    function clampBubbleOffset(nextX, nextY, startRect, startOffset) {
      var margin = 8;
      var minX = startOffset.x + margin - startRect.left;
      var maxX = startOffset.x + window.innerWidth - margin - startRect.right;
      var minY = startOffset.y + margin - startRect.top;
      var maxY = startOffset.y + window.innerHeight - margin - startRect.bottom;
      return {
        x: Math.min(Math.max(nextX, minX), maxX),
        y: Math.min(Math.max(nextY, minY), maxY),
      };
    }

    function constrainBubbleToViewport() {
      if (!bubbleNode || !helper.classList.contains("is-open")) {
        return;
      }
      var rect = bubbleNode.getBoundingClientRect();
      bubbleOffset = clampBubbleOffset(bubbleOffset.x, bubbleOffset.y, rect, bubbleOffset);
      applyBubbleOffset();
      saveBubbleOffset();
    }

    function safeQueryAll(selector) {
      try {
        return Array.prototype.slice.call(document.querySelectorAll(selector));
      } catch (err) {
        return [];
      }
    }

    function clearContextHighlight() {
      highlightedNodes.forEach(function (node) {
        if (node && node.classList) {
          node.classList.remove("avatar-context-highlight");
        }
      });
      highlightedNodes = [];
    }

    function isElementMostlyVisible(node) {
      if (!node || typeof node.getBoundingClientRect !== "function") {
        return true;
      }
      var rect = node.getBoundingClientRect();
      var margin = 72;
      return rect.top >= margin && rect.bottom <= (window.innerHeight - margin);
    }

    function firstNodeForSelector(selector) {
      var nodes = safeQueryAll(selector);
      return nodes.length ? nodes[0] : null;
    }

    function scrollTargetForStep(step, highlightedNodes) {
      if (step && step.scroll === false) {
        return null;
      }
      var scrollSelector = String(step && step.scroll || "").trim();
      if (scrollSelector) {
        return firstNodeForSelector(scrollSelector);
      }
      return highlightedNodes && highlightedNodes.length ? highlightedNodes[0] : null;
    }

    function applyHighlight(step) {
      clearContextHighlight();
      var cleanSelector = String(step && step.highlight || "").trim();
      if (!cleanSelector || !helper.classList.contains("is-open") || helper.classList.contains("is-bubble-hidden")) {
        return;
      }
      var nodes = safeQueryAll(cleanSelector);
      highlightedNodes = nodes;
      nodes.forEach(function (node) {
        node.classList.add("avatar-context-highlight");
      });
      var scrollNode = scrollTargetForStep(step, nodes);
      if (scrollNode && !isElementMostlyVisible(scrollNode)) {
        scrollNode.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "nearest" });
      }
    }

    function openStepPanel(step) {
      var panel = String(step && step.panel || "").trim();
      if (!panel) {
        return Promise.resolve();
      }
      var panelApps = [window.InscripcionsApp, window.PhasePlanner, window.RotacionsPlanner];
      var panelApp = panelApps.find(function (candidate) {
        return candidate && typeof candidate.openPanel === "function";
      });
      if (!panelApp) {
        return Promise.resolve();
      }
      try {
        return Promise.resolve(panelApp.openPanel(panel));
      } catch (err) {
        return Promise.resolve();
      }
    }

    function applyStepContext(step) {
      contextRenderId += 1;
      var renderId = contextRenderId;
      clearContextHighlight();
      if (!step || !step.highlight || !helper.classList.contains("is-open") || helper.classList.contains("is-bubble-hidden")) {
        return;
      }
      openStepPanel(step).then(function () {
        if (renderId !== contextRenderId) {
          return;
        }
        applyHighlight(step);
      });
    }

    function renderActions(topic, step) {
      if (!actionsNode) {
        return;
      }
      actionsNode.textContent = "";
      var stepActions = Array.isArray(step && step.actions) ? step.actions : null;
      var actions = stepActions || (Array.isArray(topic && topic.actions) ? topic.actions : []);
      actions.forEach(function (action) {
        if (!action || !action.label) {
          return;
        }
        if (action.action === "create_competition" && !document.querySelector("[data-avatar-action='create_competition']")) {
          return;
        }
        if (action.action === "create_apparatus" && !document.querySelector("[data-avatar-action='create_apparatus']")) {
          return;
        }
        if (action.action === "navigate" && !targetForAction(action)) {
          return;
        }
        var button = document.createElement("button");
        button.type = "button";
        button.className = "avatar-helper__action";
        button.textContent = action.label;
        button.addEventListener("click", function () {
          if (action.topic && topics[action.topic]) {
            loadTopic(action.topic, { open: true });
            return;
          }
          if (action.action) {
            runAction(action);
          }
        });
        actionsNode.appendChild(button);
      });
    }

    function render() {
      var topic = topicFor(topics, currentTopicId, initialTopicId);
      if (!topic) {
        return;
      }
      helper.dataset.avatarCurrentTopic = currentTopicId || initialTopicId;
      var steps = stepsFor(topic);
      var maxStep = Math.max(steps.length - 1, 0);
      currentStep = Math.min(Math.max(currentStep, 0), maxStep);
      var step = steps[currentStep] || {};

      if (titleNode) {
        titleNode.textContent = topic.title || "Assistent IA Score";
      }
      if (messageNode) {
        messageNode.textContent = step.text || "";
      }
      if (countNode) {
        countNode.textContent = steps.length > 1 ? String(currentStep + 1) + " / " + String(steps.length) : "";
      }
      if (imageNode) {
        imageNode.src = assetUrl(helper, avatarFor(topic, step, currentStep));
      }
      if (prevButton) {
        prevButton.disabled = currentStep <= 0;
      }
      if (nextButton) {
        nextButton.disabled = currentStep >= maxStep;
      }
      renderActions(topic, step);
      applyStepContext(step);
    }

    function openHelper() {
      applyBubbleOffset();
      setOpenState(true);
      helper.classList.remove("is-bubble-hidden");
      render();
    }

    function loadTopic(topicId, options) {
      var requestedTopicId = String(topicId || "").trim();
      if (requestedTopicId && !topics[requestedTopicId]) {
        return;
      }
      currentTopicId = requestedTopicId || initialTopicId;
      currentStep = Number(options && options.step) || 0;
      if (options && options.open) {
        openHelper();
      } else {
        render();
      }
    }

    helper.addEventListener("avatar:topic", function (event) {
      loadTopic(event.detail && event.detail.topic, { open: true });
    });

    if (openButton) {
      openButton.addEventListener("click", function () {
        loadTopic(currentTopicId || initialTopicId, { open: true, step: currentStep });
      });
    }
    if (hideButton) {
      hideButton.addEventListener("click", function () {
        setOpenState(false);
      });
    }
    if (bubbleOpenButton) {
      bubbleOpenButton.addEventListener("click", function () {
        helper.classList.remove("is-bubble-hidden");
        render();
      });
    }
    if (bubbleCloseButton) {
      bubbleCloseButton.addEventListener("click", function () {
        setOpenState(false);
      });
    }
    if (prevButton) {
      prevButton.addEventListener("click", function () {
        currentStep -= 1;
        render();
      });
    }
    if (nextButton) {
      nextButton.addEventListener("click", function () {
        currentStep += 1;
        render();
      });
    }
    if (chatFormNode) {
      chatFormNode.addEventListener("submit", function (event) {
        event.preventDefault();
        sendChatMessage();
      });
    }

    if (bubbleNode) {
      bubbleNode.addEventListener("pointerdown", function (event) {
        if (event.button !== undefined && event.button !== 0) {
          return;
        }
        if (event.target.closest("button, a, input, select, textarea")) {
          return;
        }
        var rect = bubbleNode.getBoundingClientRect();
        dragState = {
          pointerId: event.pointerId,
          startClientX: event.clientX,
          startClientY: event.clientY,
          startOffset: { x: bubbleOffset.x, y: bubbleOffset.y },
          startRect: rect,
        };
        helper.classList.add("is-dragging");
        bubbleNode.setPointerCapture(event.pointerId);
      });

      bubbleNode.addEventListener("pointermove", function (event) {
        if (!dragState || event.pointerId !== dragState.pointerId) {
          return;
        }
        var nextX = dragState.startOffset.x + event.clientX - dragState.startClientX;
        var nextY = dragState.startOffset.y + event.clientY - dragState.startClientY;
        bubbleOffset = clampBubbleOffset(nextX, nextY, dragState.startRect, dragState.startOffset);
        applyBubbleOffset();
        saveBubbleOffset();
      });

      bubbleNode.addEventListener("pointerup", function (event) {
        if (!dragState || event.pointerId !== dragState.pointerId) {
          return;
        }
        dragState = null;
        helper.classList.remove("is-dragging");
        constrainBubbleToViewport();
        saveBubbleOffset();
      });

      bubbleNode.addEventListener("pointercancel", function () {
        dragState = null;
        helper.classList.remove("is-dragging");
        constrainBubbleToViewport();
        saveBubbleOffset();
      });
    }

    window.addEventListener("beforeunload", saveBubbleOffset);
    window.addEventListener("resize", constrainBubbleToViewport);
    restoreBubbleOffset();
    restoreChatHistory();
    loadTopic(initialTopicId, { open: helper.classList.contains("is-open") });
  }

  var helpers = Array.prototype.slice.call(document.querySelectorAll(".avatar-helper"));
  helpers.forEach(function (helper) {
    setupHelper(helper);
    if (document.body && helper.parentNode !== document.body) {
      document.body.appendChild(helper);
    }
  });

  function helperForTopic(topicId) {
    var topic = String(topicId || "").trim();
    var candidates = Array.prototype.slice.call(document.querySelectorAll(".avatar-helper"));
    if (topic) {
      for (var index = 0; index < candidates.length; index += 1) {
        var candidate = candidates[index];
        if (candidate && candidate.__avatarTopics && candidate.__avatarTopics[topic]) {
          return candidate;
        }
      }
    }
    return candidates.length ? candidates[0] : null;
  }

  if (!window.__avatarHelperTopicClickBound) {
    window.__avatarHelperTopicClickBound = true;
    document.addEventListener("click", function (event) {
      var trigger = event.target.closest("[data-avatar-topic]");
      if (!trigger) {
        return;
      }
      event.preventDefault();
      var helper = helperForTopic(trigger.dataset.avatarTopic);
      if (!helper) {
        return;
      }
      helper.dispatchEvent(new CustomEvent("avatar:topic", {
        detail: { topic: trigger.dataset.avatarTopic }
      }));
    });
  }
})();
