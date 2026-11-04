/* accounti — Tastaturbedienung der Prüfseite.
 *
 * Ohne Code-Auswertung, ohne HTML-Einsetzen, ohne Inline-Code (CSP). Tasten gelten nur,
 * wo die Seite Elemente mit `data-taste` trägt, und nie bei Modifikatoren (Strg+F,
 * Alt+…), Tastenwiederholung, Eingabekomposition oder mit dem Fokus in einem
 * Eingabefeld (dort nur Strg+Enter = absenden, Esc = verlassen). Abschaltbar am Benutzer
 * („Mein Konto“, Tastenhilfe): <body data-tastenkuerzel="aus"> — kein Speicher im
 * Browser. Den Fehlerhinweis für htmx gibt accounti.js.
 */
(function () {
  "use strict";

  var TASTEN = ["j", "k", "f", "e", "r", "z", "b", "?"];

  function abgeschaltet() {
    return document.body !== null && document.body.dataset.tastenkuerzel === "aus";
  }

  function imEingabefeld(ziel) {
    if (!ziel || !ziel.tagName) {
      return false;
    }
    var name = ziel.tagName.toLowerCase();
    return (
      name === "input" ||
      name === "textarea" ||
      name === "select" ||
      ziel.isContentEditable === true
    );
  }

  function element(taste) {
    var treffer = document.querySelectorAll('[data-taste="' + taste + '"]');
    for (var i = 0; i < treffer.length; i += 1) {
      if (!treffer[i].closest("[hidden]") && !treffer[i].disabled) {
        return treffer[i];
      }
    }
    return null;
  }

  function hilfe() {
    var box = document.getElementById("tastenhilfe");
    if (box && box.tagName.toLowerCase() === "details") {
      box.open = !box.open; /* <details>: ohne Skript per Klick bedienbar */
    } else if (box) {
      box.hidden = !box.hidden;
    }
  }

  function ausloesen(taste) {
    if (taste === "?") {
      hilfe();
      return true;
    }
    var ziel = element(taste);
    if (!ziel) {
      return false;
    }
    var name = ziel.tagName.toLowerCase();
    if (name === "input" && ziel.type === "checkbox") {
      ziel.click();
      ziel.focus();
    } else if (name === "input" || name === "textarea" || name === "select") {
      ziel.focus();
    } else {
      ziel.click(); /* Knopf oder Link: dieselbe Anfrage wie mit der Maus */
    }
    return true;
  }

  document.addEventListener("keydown", function (e) {
    if (e.defaultPrevented || e.isComposing || e.repeat) {
      return;
    }
    if (imEingabefeld(e.target)) {
      if (e.key === "Enter" && e.ctrlKey && !e.altKey && !e.metaKey) {
        var formular = e.target.form;
        if (formular) {
          var knopf =
            formular.querySelector("button[data-hauptknopf]") ||
            formular.querySelector('button[type="submit"]');
          if (knopf && !knopf.disabled) {
            e.preventDefault();
            knopf.click();
          }
        }
      } else if (e.key === "Escape") {
        e.target.blur();
      }
      return;
    }
    if (e.ctrlKey || e.metaKey || e.altKey) {
      return;
    }
    var taste = e.key === "?" ? "?" : String(e.key || "").toLowerCase();
    if (TASTEN.indexOf(taste) < 0) {
      return;
    }
    if (abgeschaltet()) {
      return; /* auch „?“: jedes Einzeichen-Kürzel ist abschaltbar (WCAG 2.1.4) */
    }
    if (ausloesen(taste)) {
      e.preventDefault();
    }
  });
})();
