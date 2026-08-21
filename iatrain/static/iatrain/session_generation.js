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
})();
