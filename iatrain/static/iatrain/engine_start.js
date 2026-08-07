(function () {
  "use strict";

  var form = document.querySelector("[data-engine-start-form]");
  if (!form) return;

  var organization = form.querySelector("[name='organization']");
  var group = form.querySelector("[name='training_group']");
  var gym = form.querySelector("[name='gym']");
  var optionsUrl = form.dataset.optionsUrl;

  if (!organization.value) {
    group.disabled = true;
    gym.disabled = true;
  }

  function replaceOptions(select, items, emptyLabel) {
    var previous = select.value;
    select.replaceChildren(new Option(emptyLabel, ""));
    items.forEach(function (item) {
      select.add(new Option(item.label, String(item.id)));
    });
    if (Array.from(select.options).some(function (option) { return option.value === previous; })) {
      select.value = previous;
    }
  }

  organization.addEventListener("change", function () {
    var organizationId = organization.value;
    if (!organizationId) {
      replaceOptions(group, [], "Sense grup predefinit");
      replaceOptions(gym, [], "Sense gimnàs assignat");
      return;
    }
    group.disabled = true;
    gym.disabled = true;
    fetch(optionsUrl + "?organization=" + encodeURIComponent(organizationId), {
      headers: { "X-Requested-With": "XMLHttpRequest" }
    })
      .then(function (response) {
        if (!response.ok) throw new Error("No s’han pogut carregar les opcions.");
        return response.json();
      })
      .then(function (data) {
        replaceOptions(group, data.groups, "Sense grup predefinit");
        replaceOptions(gym, data.gyms, "Sense gimnàs assignat");
      })
      .finally(function () {
        group.disabled = false;
        gym.disabled = false;
      });
  });
})();
