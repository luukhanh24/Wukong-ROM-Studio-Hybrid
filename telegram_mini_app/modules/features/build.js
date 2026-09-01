export function createBuildFeature() {
  return {
    bind(context) {
      context.dom.one("#recipe-form")?.setAttribute("data-feature", "build");
    },
    render(context) {
      context.actions.updateSummary?.();
      // Repaint the shared MOD list without resetting the user's in-progress
      // selection when navigation returns to Studio.
      context.actions.renderMods?.(false);
    },
    enter() {},
    leave() {}
  };
}
