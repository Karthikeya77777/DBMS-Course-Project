// Small helpers: confirm dialogs, auto-hide alerts, live cost estimate, odometer prefill.
document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll("form[data-confirm]").forEach(function (f) {
    f.addEventListener("submit", function (e) { if (!confirm(f.dataset.confirm)) e.preventDefault(); });
  });
  setTimeout(function () {
    document.querySelectorAll(".toast-wrap .alert-success, .toast-wrap .alert-info").forEach(function (a) {
      bootstrap.Alert.getOrCreateInstance(a).close();
    });
  }, 5000);

  var v = document.getElementById("vehicle_id"), s = document.getElementById("start_date"),
      e = document.getElementById("expected_return_date"), out = document.getElementById("estimate");
  function estimate() {
    if (!v || !s || !e || !out) return;
    var rate = v.selectedOptions[0] ? parseFloat(v.selectedOptions[0].dataset.rate) : NaN;
    var days = (new Date(e.value) - new Date(s.value)) / 86400000;
    out.textContent = (rate && days > 0)
      ? days + " day(s) x ₹" + rate.toFixed(2) + " = ₹" + (rate * days).toLocaleString("en-IN", {minimumFractionDigits: 2})
      : "Pick a vehicle and valid dates to see the estimate.";
  }
  [v, s, e].forEach(function (el) { if (el) el.addEventListener("change", estimate); });
  estimate();

  var res = document.getElementById("reservation_id"), odo = document.getElementById("pickup_odometer");
  if (res && odo) {
    var hint = document.getElementById("odo_hint");
    function fill() {
      var o = res.selectedOptions[0];
      if (!o || !o.dataset.odo) { return; }
      if (!odo.value) odo.value = o.dataset.odo;
      if (hint) hint.textContent = "Last recorded reading for this vehicle: " + o.dataset.odo + " km";
    }
    res.addEventListener("change", fill); fill();
  }
});
