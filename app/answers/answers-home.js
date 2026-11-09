/* Answers front door (JEG-1543): names the saved league the values use, if there is one. */
(function () {
  "use strict";
  var A = window.DDF && window.DDF.answers;
  var line = document.getElementById("league-line");
  if (!A || !line) return;
  A.ready.then(function () {
    var label = A.label(A.settings());
    var saved = null;
    try { saved = localStorage.getItem("ddf.v2.league-settings"); } catch (e) { saved = null; }
    if (!saved) return;
    line.textContent = "Using your saved league settings: " + label + ".";
    line.hidden = false;
  });
})();
