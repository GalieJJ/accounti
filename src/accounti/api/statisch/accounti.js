/* accounti — Verhalten auf allen Seiten (Baustein 10c, Plan P1).
 *
 * - Fehlerhinweis: htmx tauscht 4xx/5xx außer 409/422 nicht ein — der Hinweis
 *   #netzhinweis (Texte rendert der Server) wird sichtbar.
 * - aria-busy am Ziel, solange eine htmx-Anfrage läuft.
 * - Fokus auf das erste Element mit data-fokus: nach dem Laden (Fehlerliste) und nach
 *   jedem Austausch im neuen Inhalt — außer in Beispielen ([data-beispiel], /muster).
 * - Benutzermenü (<details>) schließen mit Esc und mit einem Klick daneben.
 * - Rückweg der Vorlieben (input[data-hier]: Benutzermenü, Tastenhilfe): beim Absenden
 *   die Seite, die der Browser jetzt zeigt — nach einer htmx-Navigation nicht mehr die,
 *   mit der das Formular kam (ohne ?erledigt=, die Meldung gilt einmal).
 *
 * Ohne Speicher im Browser, ohne Code-Auswertung, ohne HTML-Einsetzen (CSP).
 */
(function () {
  "use strict";

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

  function ziel(e) {
    var t = e.detail && e.detail.target;
    return t && t.setAttribute ? t : null;
  }

  function fokus(wurzel) {
    var kandidaten = [];
    if (wurzel.matches && wurzel.matches("[data-fokus]")) {
      kandidaten.push(wurzel);
    }
    var innen = wurzel.querySelectorAll("[data-fokus]");
    for (var i = 0; i < innen.length; i += 1) {
      kandidaten.push(innen[i]);
    }
    for (var j = 0; j < kandidaten.length; j += 1) {
      if (!kandidaten[j].closest("[data-beispiel]")) {
        kandidaten[j].focus();
        return;
      }
    }
  }

  document.addEventListener("htmx:responseError", function (e) {
    var xhr = e.detail && e.detail.xhr;
    hinweis(xhr ? xhr.status : 0);
  });
  document.addEventListener("htmx:sendError", function () {
    hinweis(0);
  });
  document.addEventListener("htmx:beforeRequest", function (e) {
    var box = document.getElementById("netzhinweis");
    if (box) {
      box.hidden = true;
    }
    var t = ziel(e);
    if (t) {
      t.setAttribute("aria-busy", "true");
    }
  });
  document.addEventListener("htmx:afterRequest", function (e) {
    var t = ziel(e);
    if (t) {
      t.removeAttribute("aria-busy");
    }
  });
  document.addEventListener("htmx:afterSettle", function (e) {
    var t = e.detail && e.detail.elt;
    fokus(t && t.querySelectorAll ? t : document);
  });
  document.addEventListener("DOMContentLoaded", function () {
    fokus(document);
  });

  // Rückweg der Vorlieben: der Server-Wert gilt, solange htmx die Adresse nicht geändert
  // hat — eine Seite als Antwort auf ein POST steht unter dem Pfad des POST (GET → 405)
  var geladen = window.location.pathname + window.location.search;
  document.addEventListener(
    "submit",
    function (e) {
      var form = e.target;
      var feld = form && form.querySelector ? form.querySelector("input[data-hier]") : null;
      if (feld) {
        var hier = window.location.pathname + window.location.search;
        // sonst der Server-Wert, nicht ein früher hineingeschriebener (Runde 3)
        var ziel = new URL(hier !== geladen ? hier : feld.defaultValue, window.location.origin);
        ziel.searchParams.delete("erledigt");
        var rest = ziel.searchParams.toString();
        feld.value = ziel.pathname + (rest ? "?" + rest : "");
      }
    },
    true
  );

  function offenesMenue() {
    return document.querySelector("details.benutzermenue[open]");
  }

  document.addEventListener("keydown", function (e) {
    var menue = offenesMenue();
    if (menue && e.key === "Escape") {
      menue.open = false;
      var ausloeser = menue.querySelector("summary");
      if (ausloeser) {
        ausloeser.focus();
      }
    }
  });
  document.addEventListener("click", function (e) {
    var menue = offenesMenue();
    if (menue && !menue.contains(e.target)) {
      menue.open = false;
    }
  });
})();
