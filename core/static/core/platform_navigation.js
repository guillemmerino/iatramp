(function () {
  "use strict";

  var navigation = document.querySelector("[data-platform-navigation]");
  if (!navigation) return;

  var trigger = navigation.querySelector("[data-platform-nav-open]");
  var panel = navigation.querySelector("[data-platform-nav-panel]");
  var closeButton = navigation.querySelector("[data-platform-nav-close]");
  var backdrop = navigation.querySelector("[data-platform-nav-backdrop]");
  var assistantTrigger = navigation.querySelector("[data-platform-avatar-open]");
  var lastFocusedElement = null;
  var restoreAssistantFocus = false;
  var assistantStateObserver = null;

  function connectAvatarAssistant() {
    if (!assistantTrigger) return;
    var helper = document.querySelector(".avatar-helper");
    if (!helper) return;
    var helperOpenButton = helper.querySelector(".avatar-helper__toggle");
    var helperCloseButton = helper.querySelector(".avatar-helper__bubble-close");
    if (!helperOpenButton) return;

    if (!helper.id) helper.id = "competition-avatar-helper";
    assistantTrigger.setAttribute("aria-controls", helper.id);
    assistantTrigger.hidden = false;
    document.body.classList.add("has-integrated-avatar-assistant");

    function syncAssistantState() {
      var isOpen = helper.classList.contains("is-open");
      assistantTrigger.setAttribute("aria-expanded", isOpen ? "true" : "false");
      navigation.classList.toggle("is-avatar-open", isOpen);
      if (isOpen && restoreAssistantFocus && helperCloseButton) {
        window.setTimeout(function () { helperCloseButton.focus(); }, 120);
      } else if (!isOpen && restoreAssistantFocus) {
        restoreAssistantFocus = false;
        window.setTimeout(function () { assistantTrigger.focus(); }, 220);
      }
    }

    assistantTrigger.addEventListener("click", function () {
      restoreAssistantFocus = true;
      helperOpenButton.click();
      syncAssistantState();
    });
    assistantStateObserver = new MutationObserver(syncAssistantState);
    assistantStateObserver.observe(helper, { attributes: true, attributeFilter: ["class"] });
    syncAssistantState();
  }

  connectAvatarAssistant();

  function focusableElements() {
    return Array.prototype.slice.call(
      panel.querySelectorAll('a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])')
    ).filter(function (element) {
      return !element.hasAttribute("hidden");
    });
  }

  function focusPanelClose() {
    if (navigation.classList.contains("is-open")) closeButton.focus();
  }

  function openNavigation() {
    lastFocusedElement = document.activeElement;
    navigation.classList.add("is-open");
    document.body.classList.add("platform-nav-open");
    trigger.setAttribute("aria-expanded", "true");
    trigger.setAttribute("tabindex", "-1");
    panel.setAttribute("aria-hidden", "false");
    panel.removeAttribute("inert");
    backdrop.hidden = false;
    panel.addEventListener("transitionend", focusPanelClose, { once: true });
    window.setTimeout(focusPanelClose, 0);
  }

  function closeNavigation(restoreFocus) {
    navigation.classList.remove("is-open");
    document.body.classList.remove("platform-nav-open");
    trigger.setAttribute("aria-expanded", "false");
    trigger.removeAttribute("tabindex");
    panel.setAttribute("aria-hidden", "true");
    panel.setAttribute("inert", "");
    backdrop.hidden = true;
    if (restoreFocus !== false && lastFocusedElement && typeof lastFocusedElement.focus === "function") {
      lastFocusedElement.focus();
    }
  }

  trigger.addEventListener("click", openNavigation);
  closeButton.addEventListener("click", function () { closeNavigation(true); });
  backdrop.addEventListener("click", function () { closeNavigation(true); });

  panel.addEventListener("click", function (event) {
    if (event.target.closest("a[href]")) closeNavigation(false);
  });

  document.addEventListener("keydown", function (event) {
    if (!navigation.classList.contains("is-open")) return;
    if (event.key === "Escape") {
      event.preventDefault();
      closeNavigation(true);
      return;
    }
    if (event.key !== "Tab") return;

    var focusable = focusableElements();
    if (!focusable.length) return;
    var first = focusable[0];
    var last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });

  window.addEventListener("pageshow", function () { closeNavigation(false); });
})();
