/**
 * Shared feedback service for the Mini App. It intentionally has no DOM or
 * Telegram dependency so the composition root can provide those adapters.
 */
export function createFeedback({ getNode, getHaptics, duration = 3600 } = {}) {
  let timer = null;
  return {
    show(message, { error = false, haptic = null } = {}) {
      const node = getNode?.();
      if (!node) return;
      node.textContent = String(message || "");
      node.classList.toggle("error", error);
      node.classList.add("visible");
      clearTimeout(timer);
      timer = setTimeout(() => node.classList.remove("visible"), duration);
      if (haptic !== false) getHaptics?.()?.notificationOccurred?.(haptic || (error ? "error" : "success"));
    },
    clear() {
      clearTimeout(timer);
      timer = null;
      getNode?.()?.classList.remove("visible");
    },
    dispose() {
      clearTimeout(timer);
      timer = null;
    }
  };
}
