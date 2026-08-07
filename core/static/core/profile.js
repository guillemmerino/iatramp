(function () {
  "use strict";

  var dialog = document.querySelector("[data-profile-dialog]");
  if (!dialog) return;

  function openDialog() {
    if (typeof dialog.showModal === "function") {
      if (!dialog.open) dialog.showModal();
    } else {
      dialog.setAttribute("open", "");
    }
  }

  function closeDialog() {
    if (typeof dialog.close === "function") dialog.close();
    else dialog.removeAttribute("open");
  }

  document.querySelectorAll("[data-profile-dialog-open]").forEach(function (button) {
    button.addEventListener("click", openDialog);
  });
  dialog.querySelectorAll("[data-profile-dialog-close]").forEach(function (button) {
    button.addEventListener("click", closeDialog);
  });
  dialog.addEventListener("click", function (event) {
    if (event.target === dialog) closeDialog();
  });
  if (dialog.hasAttribute("data-open-on-load")) openDialog();
})();
