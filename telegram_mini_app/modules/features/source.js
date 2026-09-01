export function createSourceFeature() {
  return {
    bind(context) {
      const source = context.dom.one("#source-uri");
      source?.addEventListener("input", () => {
        context.actions.updateSourceDetection();
        context.actions.scheduleSourceProbe();
      });
      source?.addEventListener("paste", () => queueMicrotask(() => {
        context.actions.updateSourceDetection();
        context.actions.scheduleSourceProbe();
      }));
      context.dom.one("#toggle-source-facts")?.addEventListener("click", context.actions.toggleSourceFacts);
    },
    render() {},
    enter() {},
    leave(context) {
      context.actions.cancelSourceProbe?.();
    }
  };
}
