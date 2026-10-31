(() => {
  const baseline = document.getElementById("baseline");
  const candidate = document.getElementById("candidate");
  if (!baseline || !candidate) return;

  const apply = () => {
    const key = baseline.selectedOptions[0]?.dataset.benchmark || "";
    for (const option of candidate.options) {
      if (!option.value) {
        option.hidden = false;
        option.disabled = false;
        continue;
      }
      const compatible = !key || option.dataset.benchmark === key;
      option.hidden = !compatible;
      option.disabled = !compatible;
    }
    if (candidate.selectedOptions[0]?.disabled) candidate.value = "";
  };

  baseline.addEventListener("change", apply);
  apply();
})();
