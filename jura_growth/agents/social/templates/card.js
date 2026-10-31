/* Once the web fonts are in, shrink the card's type in small steps until
   nothing overflows, then note which font families loaded (read back by
   `render.fonts_loaded`). */
(function () {
  function overflowing(main) {
    if (main.scrollHeight > main.clientHeight) return true;
    // Centred content spills over the top as well, which scrollHeight doesn't count.
    var box = main.getBoundingClientRect();
    for (var c = 0; c < main.children.length; c++) {
      var child = main.children[c].getBoundingClientRect();
      if (child.top < box.top - 0.5 || child.bottom > box.bottom + 0.5) return true;
    }
    var wide = main.querySelectorAll(".headline, .subtitle, .items .text, .panel, .visual, .step-label, .column, .figure-text");
    for (var i = 0; i < wide.length; i++) {
      if (wide[i].scrollWidth > wide[i].clientWidth + 1) return true;
    }
    return false;
  }

  function fit() {
    var card = document.querySelector(".card");
    var main = document.querySelector(".main");
    if (!card || !main || getComputedStyle(main).display === "none") return;
    var scale = 1;
    while (overflowing(main) && scale > 0.56) {
      scale = Math.round((scale - 0.04) * 100) / 100;
      card.style.setProperty("--fit", String(scale));
    }
    document.documentElement.setAttribute("data-fit", String(scale));
  }

  function report() {
    var loaded = [];
    document.fonts.forEach(function (face) {
      var family = face.family.replace(/["']/g, "");
      if (face.status === "loaded" && loaded.indexOf(family) < 0) loaded.push(family);
    });
    document.documentElement.setAttribute("data-fonts", loaded.join("|"));
  }

  var ready = document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve();
  ready.then(function () {
    fit();
    if (document.fonts) report();
  });
})();
