(() => {
  const canvas = document.querySelector("[data-run-canvas]");
  if (!canvas) return;

  canvas.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;
    const links = Array.from(canvas.querySelectorAll(".run-node-link"));
    const index = links.indexOf(document.activeElement);
    if (index < 0) return;
    const grid = canvas.querySelector(".run-grid");
    const columns = grid
      ? getComputedStyle(grid).gridTemplateColumns.split(" ").filter(Boolean).length
      : 1;
    const delta = {
      ArrowLeft: -1,
      ArrowRight: 1,
      ArrowUp: -columns,
      ArrowDown: columns,
    }[event.key];
    const next = links[index + delta];
    if (!next) return;
    event.preventDefault();
    next.focus();
  });
})();
