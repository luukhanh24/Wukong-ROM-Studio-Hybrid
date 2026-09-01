export const MOTION = Object.freeze({
  control: 160,
  panel: 240,
  view: 280,
  dock: 360,
  easing: "cubic-bezier(.16,1,.3,1)"
});

export function reducedMotion(windowObject = window) {
  return windowObject.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches === true;
}
