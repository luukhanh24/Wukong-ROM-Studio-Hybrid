import { $, $$, liquidSlots, requestScopes, runtime, state, t, themeMedia } from "./state.js";
import { closeAdminUserPage, renderProfileView } from "./profile.js";
import { loadJobs } from "./jobs.js";
import { loadRomDevices } from "./rom-catalog.js";
import { loadAdminUsers, loadLatestBatch } from "./admin.js";

function telegramColorScheme() {
  const scheme = String(runtime.TelegramApp?.colorScheme || "").toLowerCase();
  return ["light", "dark"].includes(scheme) ? scheme : null;
}

function resolvedTheme() {
  if (state.theme !== "system") return state.theme;
  return telegramColorScheme() || (themeMedia?.matches ? "dark" : "light");
}

function handleSystemThemeChange() {
  if (state.theme === "system") applyTheme("system");
}

function bindTelegramThemeEvents() {
  if (!runtime.TelegramApp || runtime.TelegramApp === runtime.telegramThemeEventsBoundTo) return;
  runtime.TelegramApp.onEvent?.("themeChanged", handleSystemThemeChange);
  runtime.telegramThemeEventsBoundTo = runtime.TelegramApp;
}

function applyTheme(theme = state.theme, persist = false) {
  state.theme = ["system", "light", "dark"].includes(theme) ? theme : "system";
  const resolved = resolvedTheme();
  document.documentElement.dataset.theme = state.theme;
  document.documentElement.dataset.colorScheme = resolved;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", resolved === "dark" ? "#0a0a0a" : "#fafafa");
  $$("[data-theme-value]").forEach((button) => {
    const active = button.dataset.themeValue === state.theme;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  if (persist) localStorage.setItem("wukong-theme", state.theme);
  try {
    runtime.TelegramApp?.setHeaderColor?.(resolved === "dark" ? "#141414" : "#ffffff");
    runtime.TelegramApp?.setBackgroundColor?.(resolved === "dark" ? "#0a0a0a" : "#fafafa");
  } catch (_) {}
}

function greetingName() {
  return String(state.me?.displayName || state.me?.username || "Wukong").trim().split(/\s+/)[0];
}

function greetingMessages() {
  const hour = new Date().getHours();
  const timeKey = hour < 12 ? "greetingMorning" : hour < 18 ? "greetingAfternoon" : "greetingEvening";
  const values = { name: greetingName(), jobs: Number(state.me?.jobCount || 0), remaining: Number(state.me?.buildCredits || 0) };
  return [
    { key: timeKey },
    { key: "greetingWish" },
    { key: state.me?.unlimited ? "greetingUnlimited" : "greetingAllowance", values }
  ].map((item) => ({ ...item, text: t(item.key, { ...values, ...(item.values || {}) }) }));
}

function updateGreetingOverflow() {
  const viewport = $(".greeting-message-viewport");
  const message = $("#greeting-message");
  if (!viewport || !message) return;
  message.classList.remove("is-marquee");
  message.style.removeProperty("--greeting-travel");
  message.style.removeProperty("--greeting-marquee-duration");
  if (prefersReducedMotion()) return;
  requestAnimationFrame(() => {
    const overflow = Math.ceil(message.scrollWidth - viewport.clientWidth);
    if (overflow <= 2) return;
    message.style.setProperty("--greeting-travel", `${-(overflow + 18)}px`);
    message.style.setProperty("--greeting-marquee-duration", `${Math.min(16, Math.max(8, 6 + overflow / 24)).toFixed(1)}s`);
    message.classList.add("is-marquee");
  });
}

function renderGreeting() {
  const root = $("#greeting-carousel");
  if (!root) return;
  root.hidden = !state.me;
  if (!state.me) return;
  const messages = greetingMessages();
  const item = messages[state.greetingIndex % messages.length];
  $("#greeting-kicker").textContent = state.me?.unlimited ? t("unlimited") : t("buildAllowance");
  const message = $("#greeting-message");
  if (!message) return;
  if (!prefersReducedMotion() && message.textContent !== "—") {
    message.animate(
      [{ opacity: .2, filter: "blur(5px)", transform: "translateY(4px)" }, { opacity: 1, filter: "blur(0)", transform: "translateY(0)" }],
      { duration: 360, easing: "cubic-bezier(.16,1,.3,1)" }
    );
  }
  message.textContent = item.text;
  updateGreetingOverflow();
}

function scheduleGreeting() {
  clearInterval(state.greetingTimer);
  state.greetingTimer = 0;
  if (prefersReducedMotion() || document.hidden) return;
  state.greetingTimer = window.setInterval(() => {
    state.greetingIndex = (state.greetingIndex + 1) % greetingMessages().length;
    renderGreeting();
  }, 6000);
}

function updateMastheadScroll() {
  cancelAnimationFrame(state.mastheadFrame);
  state.mastheadFrame = requestAnimationFrame(() => {
    const progress = Math.max(0, Math.min(1, window.scrollY / 80));
    const root = document.documentElement.style;
    root.setProperty("--masthead-scroll", progress.toFixed(3));
    root.setProperty("--masthead-height", `${Math.round((window.innerWidth <= 860 ? 60 : 64) - progress * 6)}px`);
    root.setProperty("--masthead-surface-mix", `${Math.round(94 + progress * 6)}%`);
    root.setProperty("--masthead-backdrop-blur", `${Math.round(progress * 10)}px`);
    root.setProperty("--masthead-greeting-opacity", String(1 - progress * .18));
    root.setProperty("--masthead-greeting-offset", `${(-progress * 2).toFixed(2)}px`);
    document.body.classList.toggle("masthead-compact", progress > .82);
  });
}

function nearestLiquidSlot(value) {
  return liquidSlots.reduce((best, slot) => Math.abs(slot - value) < Math.abs(best - value) ? slot : best, liquidSlots[0]);
}

function setLiquidPosition(value, velocity = 0, pressed = false) {
  const nav = $(".bottom-nav");
  const position = Math.max(0, Math.min(4, Number(value) || 0));
  state.liquidPosition = position;
  nav?.style.setProperty("--liquid-position", String(position));
  nav?.style.setProperty("--liquid-offset", `${position * 100}%`);
  nav?.style.setProperty("--liquid-press", pressed ? ".97" : "1");
}

function updateDockShellPath() {
  const nav = $(".bottom-nav");
  const shell = $(".dock-shell");
  const clipPath = $("#dock-shell-path");
  const rimPath = $("#dock-rim-path");
  if (!nav || !shell || !clipPath || !rimPath) return;
  const width = Math.max(1, nav.getBoundingClientRect().width);
  const height = 96;
  const bodyTop = 32;
  const bodyBottom = 96;
  const capRadius = Math.min(42, width / 5);
  const capCenterY = 45;
  const capShoulder = capRadius + 10;
  const capArcX = capRadius * Math.cos(Math.PI / 6);
  const capArcY = capCenterY - capRadius / 2;
  const capBlendHandle = 7;
  const capTangentX = capBlendHandle / 2;
  const capTangentY = capBlendHandle * Math.sqrt(3) / 2;
  const sideRadius = (bodyBottom - bodyTop) / 2;
  const center = width / 2;
  const path = [
    `M ${sideRadius} ${bodyTop}`,
    `H ${center - capShoulder}`,
    `C ${center - capRadius - 4} ${bodyTop} ${center - capArcX - capTangentX} ${capArcY + capTangentY} ${center - capArcX} ${capArcY}`,
    `A ${capRadius} ${capRadius} 0 0 1 ${center + capArcX} ${capArcY}`,
    `C ${center + capArcX + capTangentX} ${capArcY + capTangentY} ${center + capRadius + 4} ${bodyTop} ${center + capShoulder} ${bodyTop}`,
    `H ${width - sideRadius}`,
    `A ${sideRadius} ${sideRadius} 0 0 1 ${width - sideRadius} ${bodyBottom}`,
    `H ${sideRadius}`,
    `A ${sideRadius} ${sideRadius} 0 0 1 ${sideRadius} ${bodyTop}`,
    "Z"
  ].join(" ");
  shell.setAttribute("viewBox", `0 0 ${width} ${height}`);
  clipPath.setAttribute("d", path);
  rimPath.setAttribute("d", path);
}

function easeOutQuint(value) {
  return 1 - Math.pow(1 - value, 5);
}

function animateLiquidPosition(target) {
  cancelAnimationFrame(state.liquidAnimationFrame);
  if (prefersReducedMotion()) { setLiquidPosition(target); return; }
  const start = state.liquidPosition;
  const distance = target - start;
  const duration = 360;
  const startedAt = performance.now();
  const tick = (now) => {
    const progress = Math.min(1, (now - startedAt) / duration);
    setLiquidPosition(start + distance * easeOutQuint(progress));
    if (progress >= 1) {
      setLiquidPosition(target);
      return;
    }
    state.liquidAnimationFrame = requestAnimationFrame(tick);
  };
  state.liquidAnimationFrame = requestAnimationFrame(tick);
}

function navigate(name, smooth = true) {
  if (!document.getElementById(name)) name = "build";
  if (name !== "system") {
    for (const scope of ["adminUsers", "adminUser", "adminActivity", "adminJob", "batch"]) requestScopes.cancel(scope);
    clearTimeout(state.adminUsersPollTimer);
    state.adminUsersPollTimer = null;
    clearTimeout(state.adminUserPollTimer);
    state.adminUserPollTimer = null;
    clearTimeout(state.batchPollTimer);
    state.batchPollTimer = null;
  }
  document.body.dataset.view = name;
  if ($("#system")?.classList.contains("admin-user-open")) {
    closeAdminUserPage({ restoreFocus: false, scroll: false });
  }
  $$(".view").forEach((node) => node.classList.toggle("active", node.id === name));
  $$(".bottom-nav [data-nav], .contents-rail [data-nav], .masthead-meta [data-nav]").forEach((node) => {
    const active = node.dataset.nav === name;
    node.classList.toggle("active", active);
    if (active) node.setAttribute("aria-current", "page"); else node.removeAttribute("aria-current");
  });
  const bottomNav = $(".bottom-nav");
  const activeButton = $$(".bottom-nav [data-nav]").find((node) => node.dataset.nav === name);
  const activeSlot = Number(activeButton?.dataset.slot || 0);
  bottomNav?.style.setProperty("--active-index", String(activeSlot));
  bottomNav?.classList.toggle("profile-active", name === "profile");
  if (smooth) animateLiquidPosition(activeSlot); else setLiquidPosition(activeSlot);
  if (smooth) runtime.TelegramApp?.HapticFeedback?.selectionChanged?.();
  bottomNav?.classList.remove("is-shifting");
  if (smooth && !prefersReducedMotion()) {
    void bottomNav?.offsetWidth;
    bottomNav?.classList.add("is-shifting");
    setTimeout(() => bottomNav?.classList.remove("is-shifting"), 520);
  }
  history.replaceState(null, "", `#${name}`);
  window.scrollTo({ top: 0, behavior: smooth && !prefersReducedMotion() ? "smooth" : "auto" });
  updateDispatchFab();
  if (name === "jobs") loadJobs({ force: true }).catch(() => {});
  if (name === "profile") renderProfileView();
  if (name === "catalog") loadRomDevices();
  if (name === "system" && state.me?.role === "admin") {
    loadAdminUsers().catch(() => {});
    if (!$("#admin-batch-page").hidden) loadLatestBatch().catch(() => {});
  }
}

function bindLiquidBottomTabs() {
  const nav = $(".bottom-nav");
  const buttons = $$(".bottom-nav [data-nav]");
  if (!nav || !buttons.length) return;
  updateDockShellPath();
  state.dockResizeObserver?.disconnect?.();
  if ("ResizeObserver" in window) {
    state.dockResizeObserver = new ResizeObserver(() => updateDockShellPath());
    state.dockResizeObserver.observe(nav);
  }
  if (!("PointerEvent" in window)) return;
  let pointerId = null;
  let startX = 0;
  let startPosition = 0;
  let lastX = 0;
  let lastTime = 0;
  let dragged = false;
  let velocity = 0;
  let pressedButton = null;

  nav.addEventListener("click", (event) => {
    const targetButton = event.target?.closest?.("button[data-nav]") || pressedButton;
    if (state.liquidSuppressClick) {
      state.liquidSuppressClick = false;
      pressedButton = null;
      event.preventDefault();
      event.stopImmediatePropagation();
      return;
    }
    // Pointer capture retargets the synthetic click to the nav container.
    // Preserve the button pressed at pointerdown so a normal click still
    // navigates; dragging remains handled by the liquid snap logic below.
    if (!targetButton) return;
    pressedButton = null;
    event.preventDefault();
    event.stopImmediatePropagation();
    navigate(targetButton.dataset.nav);
  }, true);
  nav.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 && event.pointerType !== "touch") return;
    cancelAnimationFrame(state.liquidAnimationFrame);
    pointerId = event.pointerId;
    startX = lastX = event.clientX;
    lastTime = performance.now();
    startPosition = state.liquidPosition;
    dragged = false;
    velocity = 0;
    pressedButton = event.target?.closest?.("button[data-nav]") || null;
    nav.classList.add("is-pressed");
    nav.setPointerCapture?.(pointerId);
    setLiquidPosition(startPosition, 0, true);
  });
  nav.addEventListener("pointermove", (event) => {
    if (event.pointerId !== pointerId) return;
    const now = performance.now();
    const tabWidth = Math.max(1, (nav.clientWidth - 8) / 5);
    const delta = event.clientX - startX;
    if (Math.abs(delta) > 5) dragged = true;
    nav.classList.toggle("profile-dragging", dragged && nav.classList.contains("profile-active"));
    const instantaneous = ((event.clientX - lastX) / Math.max(8, now - lastTime)) * 16 / tabWidth;
    velocity = velocity * .6 + instantaneous * .4;
    const position = Math.max(0, Math.min(4, startPosition + delta / tabWidth));
    setLiquidPosition(position, velocity, true);
    lastX = event.clientX;
    lastTime = now;
  });
  const finish = (event) => {
    if (event.pointerId !== pointerId) return;
    nav.releasePointerCapture?.(pointerId);
    pointerId = null;
    nav.classList.remove("is-pressed");
    nav.classList.remove("profile-dragging");
    const target = nearestLiquidSlot(state.liquidPosition + Math.max(-.18, Math.min(.18, velocity * .08)));
    if (dragged) {
      const releasedPosition = state.liquidPosition;
      state.liquidSuppressClick = true;
      const targetButton = buttons.find((button) => Number(button.dataset.slot) === target);
      if (targetButton) navigate(targetButton.dataset.nav, false);
      setLiquidPosition(releasedPosition, velocity, true);
      animateLiquidPosition(target);
    } else {
      const active = buttons.find((button) => button.classList.contains("active"));
      animateLiquidPosition(Number(active?.dataset.slot || 0));
    }
    setTimeout(() => { state.liquidSuppressClick = false; }, 350);
  };
  nav.addEventListener("pointerup", finish);
  nav.addEventListener("pointercancel", finish);
}

function prefersReducedMotion() {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
}

function updateDispatchFab() {
  const fab = $("#dispatch-fab");
  if (!fab) return;
  const show = $("#build")?.classList.contains("active") && !state.docketInView;
  clearTimeout(state.dispatchFabHideTimer);
  if (show) {
    fab.hidden = false;
    requestAnimationFrame(() => fab.classList.add("visible"));
  } else {
    fab.classList.remove("visible");
    state.dispatchFabHideTimer = setTimeout(() => {
      if (!fab.classList.contains("visible")) fab.hidden = true;
    }, prefersReducedMotion() ? 0 : 260);
  }
  fab.setAttribute("aria-hidden", show ? "false" : "true");
  fab.tabIndex = show ? 0 : -1;
}

export { telegramColorScheme, resolvedTheme, handleSystemThemeChange, bindTelegramThemeEvents, applyTheme, greetingName, greetingMessages, updateGreetingOverflow, renderGreeting, scheduleGreeting, updateMastheadScroll, nearestLiquidSlot, setLiquidPosition, updateDockShellPath, easeOutQuint, animateLiquidPosition, navigate, bindLiquidBottomTabs, prefersReducedMotion, updateDispatchFab };
