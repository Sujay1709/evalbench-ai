(() => {
  const motion = window.matchMedia("(prefers-reduced-motion: reduce)");

  const clear = (surface) => {
    surface.style.removeProperty("--glare-x");
    surface.style.removeProperty("--glare-y");
    surface.classList.remove("is-lit");
  };

  // Only CSS variables change here: transforming a surface mid-press can move a
  // link out from under the pointer and swallow the click.
  for (const surface of document.querySelectorAll(".glass-interactive")) {
    surface.addEventListener("pointermove", (event) => {
      if (motion.matches || event.pointerType === "touch") return;
      const rect = surface.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      const x = ((event.clientX - rect.left) / rect.width) * 100;
      const y = ((event.clientY - rect.top) / rect.height) * 100;
      surface.style.setProperty("--glare-x", `${x.toFixed(1)}%`);
      surface.style.setProperty("--glare-y", `${y.toFixed(1)}%`);
      surface.classList.add("is-lit");
    });
    surface.addEventListener("pointerleave", () => clear(surface));
    surface.addEventListener("pointercancel", () => clear(surface));
  }

  motion.addEventListener("change", () => {
    if (motion.matches) document.querySelectorAll(".glass-interactive").forEach(clear);
  });
})();
