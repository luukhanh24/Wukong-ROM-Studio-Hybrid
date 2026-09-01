export function createAdminFeature() {
  return {
    bind(context) {
      context.dom.one("#system")?.setAttribute("data-feature", "admin");
    },
    render() {},
    enter(context) {
      if (context.state.me?.role === "admin") {
        const request = context.actions.loadAdminUsers?.();
        request?.catch?.(() => {});
      }
    },
    leave(context) {
      context.actions.cancelAdminRequests?.();
    }
  };
}
