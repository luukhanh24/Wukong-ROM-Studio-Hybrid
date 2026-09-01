export function createJobsFeature() {
  return {
    bind(context) {
      context.dom.one("#jobs")?.setAttribute("data-feature", "jobs");
    },
    render() {},
    enter(context) {
      const request = context.actions.loadJobs?.({ force: true });
      request?.catch?.(() => {});
    },
    leave(context) {
      context.actions.cancelJobsRequests?.();
    }
  };
}
