export function createCatalogFeature() {
  return {
    bind(context) {
      const $ = context.dom.one;
      $("#rom-catalog-form")?.addEventListener("submit", (event) => {
        event.preventDefault();
        context.actions.searchRomCatalog();
      });
      $("#rom-device-search")?.addEventListener("input", context.actions.renderRomDevices);
      $("#rom-region-filter")?.addEventListener("change", () => {
        context.actions.resetRomResolved();
        context.actions.renderRomVersions(false);
        context.actions.renderRomCatalogResults();
      });
      $("#rom-version-filter")?.addEventListener("change", () => {
        context.actions.resetRomResolved();
        context.actions.renderRomCatalogResults();
      });
      $("#rom-device-search")?.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          context.dom.one("[data-rom-device]")?.focus();
        }
      });
      $("#rom-devices-retry")?.addEventListener("click", context.actions.loadRomDevices);
      $("#rom-device-picker")?.addEventListener("toggle", () => {
        if ($("#rom-device-picker")?.open) context.actions.loadRomDevices();
      });
      $("#rom-device-picker")?.addEventListener("keydown", (event) => {
        if (event.key !== "Escape") return;
        event.preventDefault();
        $("#rom-device-picker").open = false;
        $("#rom-device-picker summary")?.focus();
      });
    },
    enter(context) {
      context.dom.one("#search-rom-catalog")?.removeAttribute("disabled");
      const request = context.actions.loadRomDevices?.();
      request?.catch?.(() => {});
    },
    render() {},
    leave(context) {
      context.actions.cancelCatalogRequests?.();
    }
  };
}
