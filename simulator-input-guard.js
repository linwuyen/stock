// Keep allocation weight inputs editable without rebuilding their row on every keystroke.
// app.js currently listens to `input`; intercept only allocation inputs, then commit on `change`.
document.addEventListener('input', event => {
  if (event.target instanceof HTMLInputElement && event.target.matches('[data-allocation]')) {
    event.stopPropagation();
  }
}, true);

document.addEventListener('change', event => {
  const input = event.target instanceof HTMLInputElement && event.target.matches('[data-allocation]')
    ? event.target
    : null;
  if (!input) return;

  const item = state.allocations.find(allocation => allocation.ticker === input.dataset.allocation);
  if (!item) return;

  item.weight = Math.max(0, Math.min(100, Number(input.value) || 0));
  renderAllocations();
  renderSimulationSummary();
});
