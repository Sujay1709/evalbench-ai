(() => {
  const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const selector = [
    ".slab",
    ".result-card",
    ".detail-header",
    ".calibration-control",
    ".repeatability-card",
    ".agreement-field",
    ".report-panel",
    ".compare-form",
  ].join(", ");

  const slabs = () => Array.from(document.querySelectorAll(selector));

  const reset = (slab) => {
    slab.style.transform = "";
    slab.classList.remove("is-pressed");
  };

  const tilt = (slab, event, pressed) => {
    if (motion.matches) return;
    const control = event.target.closest("input, select, textarea, button");
    if (control && slab.contains(control)) return;
    const rect = slab.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const x = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
    const y = Math.min(1, Math.max(0, (event.clientY - rect.top) / rect.height));
    const maxTilt = 7;
    const restX = slab.classList.contains("hero-panel") ? 4 : 0;
    const restY = slab.classList.contains("hero-panel") ? -8 : 0;
    const rotateX = restX + (y - 0.5) * maxTilt;
    const rotateY = restY + (0.5 - x) * maxTilt;
    const depth = pressed ? -16 : 12;
    slab.style.transform = `rotateX(${rotateX.toFixed(2)}deg) rotateY(${rotateY.toFixed(2)}deg) translateZ(${depth}px)`;
  };

  for (const slab of slabs()) {
    slab.addEventListener("pointermove", (event) => {
      if (event.pointerType === "touch" && !slab.classList.contains("is-pressed")) return;
      tilt(slab, event, slab.classList.contains("is-pressed"));
    });
    slab.addEventListener("pointerdown", (event) => {
      slab.classList.add("is-pressed");
      tilt(slab, event, true);
    });
    slab.addEventListener("pointerup", (event) => {
      slab.classList.remove("is-pressed");
      if (event.pointerType === "mouse" && !motion.matches) tilt(slab, event, false);
      else reset(slab);
    });
    slab.addEventListener("pointercancel", () => reset(slab));
    slab.addEventListener("pointerleave", () => reset(slab));
  }

  motion.addEventListener("change", () => {
    if (motion.matches) slabs().forEach(reset);
  });
})();
