/** Keyboard behavior shared by tablists. */
export function bindRovingTablist(root, { onSelect } = {}) {
  if (!root) return () => {};
  const tabs = () => [...root.querySelectorAll('[role="tab"]')].filter((tab) => {
    const style = getComputedStyle(tab);
    return !tab.closest("[hidden]") && style.display !== "none" && style.visibility !== "hidden";
  });
  const sync = (selected) => tabs().forEach((tab) => {
    const active = tab === selected;
    tab.tabIndex = active ? 0 : -1;
    tab.setAttribute("aria-selected", String(active));
  });
  const handle = (event) => {
    const current = event.currentTarget;
    const items = tabs();
    const index = items.indexOf(current);
    if (!items.length || !["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const targetIndex = event.key === "Home" ? 0 : event.key === "End" ? items.length - 1
      : (index + (event.key === "ArrowRight" ? 1 : -1) + items.length) % items.length;
    const target = items[targetIndex];
    target.focus();
    sync(target);
    onSelect?.(target);
  };
  tabs().forEach((tab) => tab.addEventListener("keydown", handle));
  return () => tabs().forEach((tab) => tab.removeEventListener("keydown", handle));
}
