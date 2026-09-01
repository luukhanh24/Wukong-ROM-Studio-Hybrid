export function createProfileFeature() {
  return {
    bind(context) {
      context.dom.one("#profile")?.setAttribute("data-feature", "profile");
    },
    render(context) {
      context.actions.renderProfileView?.();
    },
    enter() {},
    leave() {}
  };
}
