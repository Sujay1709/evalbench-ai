(() => {
  const rows = [...document.querySelectorAll("[data-evidence-row]")];
  const selectionCount = document.querySelector("[data-selection-count]");
  const selectionState = document.querySelector("[data-selection-state] strong");
  const selectionMessage = document.querySelector("[data-selection-message]");
  const buildButton = document.querySelector("[data-build-report]");

  if (!rows.length || !selectionCount || !selectionState || !selectionMessage || !buildButton) {
    return;
  }

  const updateState = () => {
    let completePairs = 0;
    let partialPairs = 0;
    for (const row of rows) {
      const judge = row.querySelector('[data-pair-select="judge"]');
      const human = row.querySelector('[data-pair-select="human"]');
      const state = row.querySelector("[data-pair-state]");
      const hasJudge = Boolean(judge?.value);
      const hasHuman = Boolean(human?.value);
      state.classList.remove("pair-state-complete", "pair-state-partial");
      if (hasJudge && hasHuman) {
        completePairs += 1;
        state.textContent = "Complete pair";
        state.classList.add("pair-state-complete");
      } else if (hasJudge || hasHuman) {
        partialPairs += 1;
        state.textContent = "Incomplete pair";
        state.classList.add("pair-state-partial");
      } else {
        state.textContent = "Unselected";
      }
    }

    selectionCount.textContent = `${completePairs} selected`;
    if (partialPairs) {
      selectionState.textContent = "Complete each selected row";
      selectionMessage.textContent = `Complete ${partialPairs} partial selection${partialPairs === 1 ? "" : "s"} before building a report.`;
    } else if (completePairs) {
      selectionState.textContent = "Ready to validate";
      selectionMessage.textContent = `${completePairs} complete pair${completePairs === 1 ? "" : "s"} selected. The report remains advisory.`;
    } else {
      selectionState.textContent = "Select evidence";
      selectionMessage.textContent = "Select one or more complete evidence pairs to build an advisory report.";
    }
    buildButton.disabled = !completePairs || Boolean(partialPairs);
  };

  document.querySelectorAll("[data-pair-select]").forEach((select) => {
    select.addEventListener("change", updateState);
  });
  updateState();
})();
