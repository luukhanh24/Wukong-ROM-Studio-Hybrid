// Telegram and browser geometry share one CSS contract. Older bridges use env().
let boundBridge;
let boundBrowser = false;
export function bindViewport(bridge) {
  const update = () => {
    const root = document.documentElement;
    const viewport = window.visualViewport;
    const editing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName || "");
    const keyboard = editing && (viewport ? window.innerHeight - viewport.height > 120 : false);
    root.dataset.keyboard = String(keyboard);
    root.style.setProperty("--viewport-height", `${boundBridge?.viewportStableHeight || window.innerHeight}px`);
    for (const edge of ["top", "right", "bottom", "left"]) {
      const inset = Math.max(Number(boundBridge?.safeAreaInset?.[edge]) || 0, Number(boundBridge?.contentSafeAreaInset?.[edge]) || 0);
      root.style.setProperty(`--telegram-safe-${edge}`, `${inset}px`);
    }
    if (keyboard) document.activeElement?.scrollIntoView({ block: "nearest", behavior: "instant" });
  };
  if (!boundBrowser) {
    window.addEventListener("resize", update);
    window.visualViewport?.addEventListener("resize", update);
    document.addEventListener("focusin", update);
    document.addEventListener("focusout", update);
    boundBrowser = true;
  }
  if (bridge && boundBridge !== bridge) {
    for (const event of ["safeAreaChanged", "contentSafeAreaChanged", "viewportChanged"]) bridge.onEvent?.(event, update);
    boundBridge = bridge;
  }
  update();
}
