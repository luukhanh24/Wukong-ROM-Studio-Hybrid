/**
 * Small lifecycle registry shared by Mini App feature surfaces.
 *
 * The legacy implementation still owns the domain functions for this
 * release; registering them here gives each surface an explicit seam for the
 * remaining mechanical extraction without changing runtime contracts.
 */
export function createFeatureRegistry(context, definitions = {}) {
  const lifecycle = ["bind", "render", "enter", "leave"];
  const features = new Map(Object.entries(definitions).map(([name, feature]) => {
    if (!feature || lifecycle.some((method) => typeof feature[method] !== "function")) {
      throw new TypeError(`Feature ${name} must implement ${lifecycle.join(", ")}`);
    }
    return [name, Object.freeze({
      name,
      bind: () => feature.bind(context),
      render: (...args) => feature.render(context, ...args),
      enter: (...args) => feature.enter(context, ...args),
      leave: (...args) => feature.leave(context, ...args)
    })];
  }));
  return Object.freeze({
    context,
    features,
    bind() { features.forEach((feature) => feature.bind()); },
    render(name, ...args) { return features.get(name)?.render(...args); },
    enter(name, ...args) { return features.get(name)?.enter(...args); },
    leave(name, ...args) { return features.get(name)?.leave(...args); }
  });
}

/** Compose adjacent surfaces that share one route (Build owns Source). */
export function composeFeatures(...features) {
  return {
    bind(context) { features.forEach((feature) => feature.bind(context)); },
    render(context, ...args) { features.forEach((feature) => feature.render(context, ...args)); },
    enter(context, ...args) { features.forEach((feature) => feature.enter(context, ...args)); },
    leave(context, ...args) { [...features].reverse().forEach((feature) => feature.leave(context, ...args)); }
  };
}
