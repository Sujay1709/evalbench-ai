(function () {
  const album = document.querySelector("[data-run-album]");
  if (!album) return;

  const motion = window.matchMedia("(prefers-reduced-motion: reduce)");

  function plates() {
    return Array.from(album.querySelectorAll("[data-album-plate]"));
  }

  function clearTilt(plate) {
    plate.classList.remove("is-tilting", "is-pressed");
    plate.style.removeProperty("--tilt-x");
    plate.style.removeProperty("--tilt-y");
    plate.style.removeProperty("--glare-x");
    plate.style.removeProperty("--glare-y");
  }

  function applyMotion() {
    const reduced = motion.matches;
    album.classList.toggle("is-reduced-motion", reduced);
    if (reduced) plates().forEach(clearTilt);
  }

  function tilt(plate, clientX, clientY) {
    if (motion.matches) return;
    const rect = plate.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const x = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
    const y = Math.min(1, Math.max(0, (clientY - rect.top) / rect.height));
    const maxTilt = 16;
    plate.style.setProperty("--tilt-x", ((y - 0.5) * maxTilt).toFixed(2) + "deg");
    plate.style.setProperty("--tilt-y", ((0.5 - x) * maxTilt).toFixed(2) + "deg");
    plate.style.setProperty("--glare-x", (x * 100).toFixed(1) + "%");
    plate.style.setProperty("--glare-y", (y * 100).toFixed(1) + "%");
    plate.classList.add("is-tilting");
  }

  function plateFrom(event) {
    const target = event.target;
    if (!target || typeof target.closest !== "function") return null;
    const plate = target.closest("[data-album-plate]");
    return plate && album.contains(plate) ? plate : null;
  }

  applyMotion();
  motion.addEventListener("change", applyMotion);

  album.addEventListener("pointermove", (event) => {
    const plate = plateFrom(event);
    if (!plate) return;
    tilt(plate, event.clientX, event.clientY);
  });

  album.addEventListener("pointerdown", (event) => {
    const plate = plateFrom(event);
    if (!plate || motion.matches) return;
    plate.classList.add("is-pressed");
    tilt(plate, event.clientX, event.clientY);
  });

  album.addEventListener("pointerout", (event) => {
    const plate = plateFrom(event);
    if (!plate) return;
    const next = event.relatedTarget;
    if (next instanceof Node && plate.contains(next)) return;
    clearTilt(plate);
  });

  window.addEventListener("pointerup", () => {
    plates().forEach((plate) => plate.classList.remove("is-pressed"));
  });

  window.addEventListener("pointercancel", () => {
    plates().forEach(clearTilt);
  });

  album.addEventListener("keydown", (event) => {
    const key = event.key;
    const deltas = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: null, ArrowDown: null };
    if (!(key in deltas)) return;
    const links = Array.from(album.querySelectorAll(".album-plate-link"));
    const index = links.indexOf(document.activeElement);
    if (index < 0) return;
    const stage = album.querySelector(".album-stage");
    const columns = stage
      ? getComputedStyle(stage).gridTemplateColumns.split(" ").filter(Boolean).length
      : 1;
    let delta = columns;
    if (key === "ArrowLeft") delta = -1;
    else if (key === "ArrowRight") delta = 1;
    else if (key === "ArrowUp") delta = -columns;
    const next = links[index + delta];
    if (!next) return;
    event.preventDefault();
    next.focus();
  });
})();
