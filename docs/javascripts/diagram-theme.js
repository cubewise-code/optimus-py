/* Keep the embedded diagrams in the site's theme.
 *
 * Each diagram is a self-contained viewer that picks its theme from data-theme
 * ("light" or "dark") on its own <html>. Material marks the site's scheme on
 * <body> as data-md-color-scheme ("default" or "slate"). The diagrams are
 * same-origin, so the attribute can be set from here. Nothing is written to
 * localStorage: the site's toggle is the only switch. If a frame can't be
 * reached, the diagram keeps its own default theme.
 */
(function () {
  function siteTheme() {
    return document.body.getAttribute("data-md-color-scheme") === "slate" ? "dark" : "light";
  }

  function applyTo(frame) {
    try {
      var doc = frame.contentDocument;
      if (!doc || !doc.documentElement) return;
      var theme = siteTheme();
      doc.documentElement.setAttribute("data-theme", theme);
      // Mirror what the viewer's own toggle updates alongside the attribute.
      var label = doc.getElementById("theme-label");
      if (label) label.textContent = theme === "dark" ? "Dark" : "Light";
      var button = doc.getElementById("btn-theme");
      if (button) button.setAttribute("aria-pressed", theme === "light" ? "true" : "false");
    } catch (_) {}
  }

  function frames() {
    return document.querySelectorAll(".diagram-frame iframe");
  }

  function syncAll() {
    frames().forEach(applyTo);
  }

  // Once per page: navigation.instant swaps the content without a full load.
  document$.subscribe(function () {
    frames().forEach(function (frame) {
      if (frame.dataset.themeSync) return;
      frame.dataset.themeSync = "on";
      frame.addEventListener("load", function () { applyTo(frame); });
      applyTo(frame);
    });
  });

  // The site's toggle, which survives instant navigation along with <body>.
  new MutationObserver(syncAll).observe(document.body, {
    attributes: true,
    attributeFilter: ["data-md-color-scheme"],
  });

  // The viewer follows OS theme changes on its own; put it back in line.
  try {
    var media = window.matchMedia("(prefers-color-scheme: light)");
    var later = function () { setTimeout(syncAll, 0); };
    if (media.addEventListener) media.addEventListener("change", later);
    else if (media.addListener) media.addListener(later);
  } catch (_) {}
})();
