/* accounti — Tastaturbedienung der Prüfseite und Fehlerhinweis für htmx.
 *
 * Ohne Code-Auswertung, ohne HTML-Einsetzen, ohne Inline-Code (CSP). Die Texte
 * rendert der Server (versteckt im Markup); das Skript schaltet nur `hidden` um.
 * Tasten gelten nur, wo die Seite Elemente mit `data-taste` trägt, und nie bei
 * Modifikatoren (Strg+F, Alt+…), Tastenwiederholung, Eingabekomposition oder mit
 * dem Fokus in einem Eingabefeld (dort nur Strg+Enter = absenden, Esc = verlassen).
 * Abschaltbar in der Tastenhilfe (gemerkt in localStorage, nur dieser Wahrheitswert).
 */
(function () {
  "use strict";

  var TASTEN = ["j", "k", "f", "e", "r", "z", "b", "?"];
  var AUS = "accounti.tasten.aus";

  function abgeschaltet() {
    try {
      return window.localStorage.getItem(AUS) === "1";
    } catch (fehler) {
      return false;
    }
  }

  function schalte(aus) {
    try {
      if (aus) {
        window.localStorage.setItem(AUS, "1");
      } else {
        window.localStorage.removeItem(AUS);
      }
    } catch (fehler) {
      /* ohne Speicher gilt die Wahl nur für diese Seite */
    }
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
    if (box) {
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
          var knopf = formular.querySelector('button[type="submit"]');
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
    if (taste !== "?" && abgeschaltet()) {
      return;
    }
    if (ausloesen(taste)) {
      e.preventDefault();
    }
  });

  document.addEventListener("change", function (e) {
    if (e.target && e.target.id === "tasten-aus") {
      schalte(e.target.checked);
    }
  });

  function zeigeSchalter() {
    var schalter = document.getElementById("tasten-aus");
    if (schalter) {
      schalter.checked = abgeschaltet();
    }
  }

  /* Fehlerhinweis: htmx tauscht 4xx/5xx außer 409/422 nicht ein */
  function hinweis(status) {
    var box = document.getElementById("netzhinweis");
    if (!box) {
      return;
    }
    var allgemein = box.querySelector('[data-hinweis="allgemein"]');
    var beschaeftigt = box.querySelector('[data-hinweis="503"]');
    if (allgemein && beschaeftigt) {
      beschaeftigt.hidden = status !== 503;
      allgemein.hidden = status === 503;
    }
    box.hidden = false;
  }

  document.addEventListener("htmx:responseError", function (e) {
    var xhr = e.detail && e.detail.xhr;
    hinweis(xhr ? xhr.status : 0);
  });
  document.addEventListener("htmx:sendError", function () {
    hinweis(0);
  });
  document.addEventListener("htmx:beforeRequest", function () {
    var box = document.getElementById("netzhinweis");
    if (box) {
      box.hidden = true;
    }
  });
  document.addEventListener("htmx:afterSettle", zeigeSchalter);
  document.addEventListener("DOMContentLoaded", zeigeSchalter);
})();
