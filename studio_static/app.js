const token = document.querySelector('meta[name="studio-token"]').content;

const desktopBridgeAvailable = Boolean(window.chrome?.webview);
const nativeBridgePending = new Map();

const state = {
  bootstrap: null,
  jobs: [],
  artifacts: [],
  devices: [],
  mods: [],
  modVersion: "ColorOS_16.0.7",
  settings: {},
  diagnostics: {},
  romQueue: [],
  activeJob: null,
  buildTimerInterval: null,
  eventSource: null,
  logLines: [],
  pendingLogLines: [],
  logRenderTimer: null,
  maxLogLines: 1800,
  maxPendingLogLines: 2200,
  queueInspectTimer: null,
  jobsRefreshing: false,
  creatingJobs: false,
  streamGeneration: 0,
  pipelineSelection: null,
  modSelection: new Set(),
  draftModSelection: new Set(),
  debloatPaths: [],
  defaultDebloatPaths: [],
  locale: "vi",
  workbenchTab: "overview",
  loadingActions: new Set(),
  lastFocusedElement: null,
  consoleFullscreen: false,
};

if (desktopBridgeAvailable) {
  window.chrome.webview.addEventListener("message", (event) => {
    const response = event.data;
    const pending = response?.id ? nativeBridgePending.get(response.id) : null;
    if (!pending) return;
    nativeBridgePending.delete(response.id);
    if (pending.timer) clearTimeout(pending.timer);
    if (response.ok) pending.resolve(response.result);
    else pending.reject(new Error(response.error || "Native bridge request failed"));
  });
}

function nativeAction(action, payload = {}, { timeout = 60000 } = {}) {
  if (!desktopBridgeAvailable) return Promise.reject(new Error("Native bridge is unavailable"));
  const id = crypto.randomUUID();
  return new Promise((resolve, reject) => {
    const timer = timeout > 0 ? setTimeout(() => {
      nativeBridgePending.delete(id);
      reject(new Error(`Native action timed out: ${action}`));
    }, timeout) : null;
    nativeBridgePending.set(id, { resolve, reject, timer });
    window.chrome.webview.postMessage({ id, action, payload });
  });
}

const presetDefaultModExcludes = {
  resume: new Set(["Gallery_mod_CN"]),
  both: new Set(["Gallery_mod_CN"]),
};
const forcedLiteDefaultMods = ["Fix_Metis", "WK_Installer"];

const i18n = {
  vi: {
    "nav.workbench": "Bảng điều khiển",
    "nav.artifacts": "Bản build",
    "nav.catalog": "Danh mục",
    "nav.diagnostics": "Chẩn đoán",
    "nav.settings": "Cài đặt",
    "status.local": "LOCALHOST AN TOÀN",
    "action.newBuild": "+ Tạo build",
    "action.startBuild": "Bắt đầu build",
    "action.viewAll": "Xem tất cả",
    "action.details": "Chi tiết",
    "action.preflight": "Chạy preflight",
    "action.queueBuild": "Đưa vào hàng đợi",
    "action.cancel": "Hủy job",
    "action.clear": "Xóa màn hình",
    "action.customize": "Tùy chỉnh",
    "action.dismiss": "Hủy",
    "action.restoreDefault": "Khôi phục mặc định",
    "action.saveChanges": "Lưu thay đổi",
    "action.add": "Thêm",
    "action.save": "Lưu cài đặt",
    "action.resume": "Tiếp tục job",
    "action.refresh": "Làm mới",
    "action.scan": "Quét lại",
    "action.copy": "Sao chép path",
    "action.open": "Mở thư mục",
    "action.copyLog": "Copy log",
    "action.downloadLog": "Tải log",
    "action.fullscreen": "Fullscreen",
    "action.exitFullscreen": "Thoát fullscreen",
    "workbench.overview": "Tổng quan",
    "workbench.build": "Build",
    "workbench.console": "Console",
    "empty.romQueueTitle": "Chưa có ROM trong queue",
    "empty.romQueueHint": "Duyệt một ROM ZIP hoặc nhập folder để tự thêm toàn bộ ROM theo thứ tự tên file.",
    "overview.hero": "Quản lý preflight, queue, build và log trong một màn hình.",
    "overview.subtitle": "Chọn ROM, cấu hình pipeline, theo dõi log realtime và kiểm tra artifact trước khi phát hành.",
    "overview.recentJobs": "Build gần đây",
    "overview.health": "Tình trạng hệ thống",
    "builder.romQueue": "Danh sách ROM",
    "builder.browse": "Duyệt ROM ZIP",
    "builder.folder": "Nhập folder",
    "builder.folderHint": "Sau khi chọn ROM, Studio tự đọc metadata và xác nhận thiết bị. Nhập folder sẽ thêm các file .zip theo thứ tự tên.",
    "builder.folderPrompt": "Không mở được cửa sổ chọn folder. Nhập đường dẫn tuyệt đối của folder chứa ROM ZIP:",
    "builder.romPath": "Nhập đường dẫn ROM ZIP tuyệt đối",
    "builder.pipeline": "Các bước build",
    "builder.modVersion": "Phiên bản MOD",
    "builder.buildEdition": "Phiên bản build",
    "label.modVersion": "Phiên bản MOD",
    "builder.pipelineHint": "Preset chỉ chọn target mặc định. Bạn có thể bật hoặc tắt bất kỳ bước nào; preflight sẽ báo lỗi nếu cấu hình chưa đủ điều kiện.",
    "builder.ready": "Chạy preflight trước khi đưa vào queue",
    "builder.telegram": "Gửi thông báo Telegram khi hoàn tất",
    "debloat.title": "Tùy chỉnh đường dẫn cần xóa",
    "debloat.hint": "Mỗi dòng là một đường dẫn tương đối bắt đầu bằng tên partition. Ví dụ: my_stock\\app\\Browser",
    "mods.title": "Chọn MOD",
    "mods.hint": "Mỗi thư mục con là một lựa chọn độc lập. MOD có cảnh báo vẫn hiển thị để bạn biết trạng thái preflight.",
    "mods.selectLite": "Chọn Lite",
    "mods.selectAll": "Chọn tất cả",
    "mods.clear": "Bỏ chọn",
    "console.jobs": "Danh sách job",
    "console.select": "Chọn một job để xem log",
    "console.filter": "Lọc log...",
    "console.autoscroll": "Tự cuộn",
    "artifacts.title": "Lịch sử ROM ZIP",
    "catalog.devices": "Thiết bị hỗ trợ",
    "catalog.mods": "Danh mục MOD",
    "diagnostics.title": "Chẩn đoán",
    "settings.title": "Cài đặt Studio",
    "settings.locale": "Ngôn ngữ",
    "settings.preset": "Preset mặc định",
    "settings.notify": "Bật Telegram mặc định",
    "settings.roots": "Root được phép duyệt",
    "settings.secret": "Thông tin Telegram được mã hóa bằng Windows DPAPI và không hiển thị trong UI.",
    "label.artifactFile": "File ZIP",
    "label.file": "File ROM",
    "label.device": "Thiết bị",
    "label.product": "Product",
    "label.version": "Phiên bản",
    "label.size": "Dung lượng",
    "label.superSize": "Super Size",
    "label.groupSize": "Group Size",
    "label.mod": "MOD",
    "label.preflight": "Preflight",
    "label.errors": "Lỗi",
    "label.warnings": "Cảnh báo",
    "label.valid": "Hợp lệ",
    "label.created": "Thời gian",
    "label.path": "Đường dẫn",
    "label.outputArtifact": "Artifact tạo ra",
    "label.extraPartitions": "{count} phân vùng bổ sung",
    "label.total": "Tổng",
    "status.success": "Thành công",
    "status.failed": "Lỗi",
    "status.running": "Đang chạy",
    "status.packaging": "Đang đóng gói nền",
    "status.queued": "Đang chờ",
    "status.pending": "Chưa chạy",
    "status.cancelled": "Đã hủy",
    "status.unknown": "Không rõ",
    "common.ready": "Sẵn sàng",
    "common.missingBinary": "Thiếu binary bắt buộc",
    "common.missingDependency": "Thiếu dependency",
    "common.optionalMissing": "Thiếu dependency tùy chọn",
    "common.configured": "Đã cấu hình",
    "common.notConfigured": "Tùy chọn, chưa cấu hình",
    "common.noJobs": "Chưa có job.",
    "common.noArtifacts": "Chưa có artifact.",
    "common.artifactMissing": "File không còn tồn tại",
    "common.noLog": "Chưa có log.",
    "common.awaitingPreflight": "Chưa chạy preflight",
    "common.inspecting": "Đang tự kiểm tra ROM...",
    "common.readyToBuild": "Đủ điều kiện build",
    "common.blockedBuild": "Chưa đủ điều kiện build",
    "common.warningBuild": "Có cảnh báo nhưng vẫn có thể build",
    "common.noMod": "Không MOD",
    "common.selectedMods": "{count} MOD đã chọn",
    "common.debloatPaths": "{count} đường dẫn",
    "common.noSelection": "Chưa chọn MOD",
    "common.blockedMod": "Chưa sẵn sàng",
    "common.invalid": "không hợp lệ",
    "common.queue": "Queue tuần tự",
    "toast.preflightPassed": "Preflight đạt.",
    "toast.queued": "Đã đưa {count} job vào queue tuần tự.",
    "toast.copied": "Đã copy path.",
    "toast.settingsSaved": "Đã lưu cài đặt.",
    "toast.resumeQueued": "Đã tạo job tiếp tục.",
    "toast.folderAdded": "Đã thêm {count} ROM từ folder.",
    "toast.noZipInFolder": "Không tìm thấy file .zip trong folder đã chọn.",
    "toast.autoInspectDone": "Đã tự xác nhận thông tin ROM.",
    "error.selectRom": "Chọn ít nhất một ROM ZIP.",
    "error.preflightFailed": "{count} ROM không đạt preflight.",
    "error.bannerTitle": "Cần xử lý trước khi build",
    "step.defaultTarget": "Bật mặc định theo preset",
    "step.optional": "Tùy chọn — có thể tắt",
    "step.unavailable": "Thiếu công cụ phụ thuộc; bổ sung xong mới bật được",
    "step.avb": "Cảnh báo: bước này chỉnh verified boot (vbmeta)",
    "step.inspect_rom": "1. Kiểm tra thông tin ROM",
    "step.extract_payload": "2. Tách ảnh hệ thống từ OTA",
    "step.unpack_partitions": "3. Mở các phân vùng",
    "step.debloat": "4. Gỡ app rác",
    "step.apply_mod": "5. Cài MOD đã chọn",
    "step.sync_configs": "6. Cập nhật quyền file & SELinux",
    "step.repack_partitions": "7. Đóng gói lại phân vùng",
    "step.repack_super": "8. Tạo super.img",
    "step.patch_vbmeta": "9. Vá vbmeta (kiểm tra boot)",
    "step.patch_vendor_boot": "10. Vá vendor_boot",
    "step.package_zip": "11. Tạo file ZIP cài ROM",
    "step.notify_telegram": "12. Gửi báo cáo Telegram",
  },
  en: {
    "nav.workbench": "Workbench",
    "nav.artifacts": "Artifacts",
    "nav.catalog": "Catalog",
    "nav.diagnostics": "Diagnostics",
    "nav.settings": "Settings",
    "status.local": "LOCALHOST SECURE",
    "action.newBuild": "+ Build ROM",
    "action.startBuild": "Start build",
    "action.viewAll": "View all",
    "action.details": "Details",
    "action.preflight": "Run preflight",
    "action.queueBuild": "Queue build",
    "action.cancel": "Cancel job",
    "action.clear": "Clear console",
    "action.customize": "Customize",
    "action.dismiss": "Cancel",
    "action.restoreDefault": "Restore defaults",
    "action.saveChanges": "Save changes",
    "action.add": "Add",
    "action.save": "Save settings",
    "action.resume": "Resume job",
    "action.refresh": "Refresh",
    "action.scan": "Scan again",
    "action.copy": "Copy path",
    "action.open": "Open folder",
    "action.copyLog": "Copy log",
    "action.downloadLog": "Download log",
    "action.fullscreen": "Fullscreen",
    "action.exitFullscreen": "Exit fullscreen",
    "workbench.overview": "Overview",
    "workbench.build": "Build",
    "workbench.console": "Console",
    "empty.romQueueTitle": "No ROMs in the queue",
    "empty.romQueueHint": "Browse a ROM ZIP or import a folder to add all ROMs by filename order.",
    "overview.hero": "Manage preflight, queue, build and logs in one screen.",
    "overview.subtitle": "Select ROMs, configure the pipeline, watch realtime logs and validate artifacts before release.",
    "overview.recentJobs": "Recent builds",
    "overview.health": "System health",
    "builder.romQueue": "ROM queue",
    "builder.browse": "Browse ROM ZIP",
    "builder.folder": "Import folder",
    "builder.folderHint": "After selection, Studio reads metadata and confirms the device automatically. Import folder adds .zip files by filename order.",
    "builder.folderPrompt": "The folder picker could not be opened. Enter the absolute path of the folder containing ROM ZIP files:",
    "builder.romPath": "Enter an absolute ROM ZIP path",
    "builder.pipeline": "Build steps",
    "builder.modVersion": "MOD version",
    "builder.buildEdition": "Build edition",
    "label.modVersion": "MOD version",
    "builder.pipelineHint": "Presets only select default targets. You can toggle any step; preflight reports invalid configurations.",
    "builder.ready": "Run preflight before queueing builds",
    "builder.telegram": "Send Telegram notification when completed",
    "debloat.title": "Customize removal paths",
    "debloat.hint": "Enter one relative path per line, starting with a partition name. Example: my_stock\\app\\Browser",
    "mods.title": "Select MODs",
    "mods.hint": "Each child folder is an independent option. MODs with warnings remain visible so preflight status is explicit.",
    "mods.selectLite": "Select Lite",
    "mods.selectAll": "Select all",
    "mods.clear": "Clear",
    "console.jobs": "Build jobs",
    "console.select": "Select a job to inspect logs",
    "console.filter": "Filter log...",
    "console.autoscroll": "Auto-scroll",
    "artifacts.title": "ROM artifacts",
    "catalog.devices": "Supported devices",
    "catalog.mods": "MOD catalog",
    "diagnostics.title": "Diagnostics",
    "settings.title": "Studio settings",
    "settings.locale": "Language",
    "settings.preset": "Default preset",
    "settings.notify": "Enable Telegram by default",
    "settings.roots": "Allowed browser roots",
    "settings.secret": "Telegram credentials are protected by Windows DPAPI and never displayed in the UI.",
    "label.artifactFile": "ZIP file",
    "label.file": "ROM file",
    "label.device": "Device",
    "label.product": "Product",
    "label.version": "Version",
    "label.size": "Size",
    "label.superSize": "Super Size",
    "label.groupSize": "Group Size",
    "label.mod": "MOD",
    "label.preflight": "Preflight",
    "label.errors": "Errors",
    "label.warnings": "Warnings",
    "label.valid": "Valid",
    "label.created": "Created",
    "label.path": "Path",
    "label.outputArtifact": "Output artifact",
    "label.extraPartitions": "{count} extra partitions",
    "label.total": "Total",
    "status.success": "Success",
    "status.failed": "Failed",
    "status.running": "Running",
    "status.packaging": "Packaging in background",
    "status.queued": "Queued",
    "status.pending": "Pending",
    "status.cancelled": "Cancelled",
    "status.unknown": "Unknown",
    "common.ready": "Ready",
    "common.missingBinary": "Missing required binary",
    "common.missingDependency": "Dependency missing",
    "common.optionalMissing": "Optional dependency missing",
    "common.configured": "Configured",
    "common.notConfigured": "Optional, not configured",
    "common.noJobs": "No jobs yet.",
    "common.noArtifacts": "No artifacts yet.",
    "common.artifactMissing": "File no longer exists",
    "common.noLog": "No log output yet.",
    "common.awaitingPreflight": "Awaiting preflight",
    "common.inspecting": "Inspecting ROM automatically...",
    "common.readyToBuild": "Ready to build",
    "common.blockedBuild": "Blocked from build",
    "common.warningBuild": "Warnings present but build can continue",
    "common.noMod": "No MOD",
    "common.selectedMods": "{count} MOD(s) selected",
    "common.debloatPaths": "{count} paths",
    "common.noSelection": "No MOD selected",
    "common.blockedMod": "Not ready",
    "common.invalid": "invalid",
    "common.queue": "Sequential queue",
    "toast.preflightPassed": "Preflight passed.",
    "toast.queued": "{count} build job(s) queued sequentially.",
    "toast.copied": "Path copied.",
    "toast.settingsSaved": "Settings saved.",
    "toast.resumeQueued": "Resume job queued.",
    "toast.folderAdded": "Added {count} ROM(s) from folder.",
    "toast.noZipInFolder": "No .zip files found in the selected folder.",
    "toast.autoInspectDone": "ROM information confirmed automatically.",
    "error.selectRom": "Select at least one ROM ZIP.",
    "error.preflightFailed": "{count} ROM(s) failed preflight.",
    "error.bannerTitle": "Fix this before building",
    "step.defaultTarget": "On by default for this preset",
    "step.optional": "Optional — can be turned off",
    "step.unavailable": "Missing dependency; add it before enabling this step",
    "step.avb": "Warning: this step changes verified boot (vbmeta)",
    "step.inspect_rom": "1. Check ROM info",
    "step.extract_payload": "2. Extract system images from OTA",
    "step.unpack_partitions": "3. Open partition images",
    "step.debloat": "4. Remove bloat apps",
    "step.apply_mod": "5. Apply selected MODs",
    "step.sync_configs": "6. Update permissions & SELinux",
    "step.repack_partitions": "7. Rebuild partition images",
    "step.repack_super": "8. Rebuild super.img",
    "step.patch_vbmeta": "9. Patch vbmeta (boot verify)",
    "step.patch_vendor_boot": "10. Patch vendor_boot",
    "step.package_zip": "11. Create flashable ZIP",
    "step.notify_telegram": "12. Send Telegram report",
  },
};

function t(key, fallback = key) {
  return i18n[state.locale]?.[key] || i18n.vi[key] || fallback;
}

function fmt(key, values = {}) {
  return Object.entries(values).reduce(
    (text, [name, value]) => text.replaceAll(`{${name}}`, value),
    t(key),
  );
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-Studio-Token": token,
      ...(options.headers || {}),
    },
  });
  const payload = await response.json();
  if (response.status === 403) {
    window.location.reload();
    throw new Error("Studio session expired");
  }
  if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  }[char]));
}

function bytes(value) {
  if (!Number.isFinite(Number(value))) return "-";
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  let number = Number(value);
  let index = 0;
  while (number >= 1024 && index < units.length - 1) {
    number /= 1024;
    index += 1;
  }
  return `${number.toFixed(index ? 2 : 0)} ${units[index]}`;
}

function duration(value) {
  if (!Number.isFinite(Number(value))) return "-";
  const totalMs = Math.max(0, Number(value));
  if (totalMs < 1000) return `${Math.round(totalMs)} ms`;
  const seconds = totalMs / 1000;
  if (seconds < 60) return `${seconds.toFixed(seconds >= 10 ? 1 : 2)} s`;
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  if (minutes < 60) return `${minutes}m ${String(rest).padStart(2, "0")}s`;
  const hours = Math.floor(minutes / 60);
  const minuteRest = minutes % 60;
  return `${hours}h ${String(minuteRest).padStart(2, "0")}m`;
}

function clockDuration(value) {
  if (!Number.isFinite(Number(value))) return "00:00:00";
  const totalSeconds = Math.max(0, Math.floor(Number(value) / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  return [hours, minutes, seconds].map((part) => String(part).padStart(2, "0")).join(":");
}

function date(value) {
  return value ? new Date(value).toLocaleString() : "-";
}

function statusLabel(status) {
  return t(`status.${status}`, status || t("status.unknown"));
}

function badge(status) {
  return `<span class="badge ${esc(status)}">${esc(statusLabel(status))}</span>`;
}

function stepLabel(stepOrId, fallback = "") {
  const id = typeof stepOrId === "string" ? stepOrId : stepOrId.id;
  const label = typeof stepOrId === "string" ? fallback : stepOrId.label;
  return t(`step.${id}`, label || id);
}

function jobName(job) {
  const workspaceName = job.workspace && !/[\\/]\.wkstudio[\\/]jobs[\\/]/i.test(job.workspace)
    ? job.workspace.split(/[\\/]/).pop()
    : "";
  return job.versionName || job.spec?.versionName || workspaceName || job.spec?.romPath?.split(/[\\/]/).pop() || job.id;
}

function romName(item) {
  return item.inspect?.metadata?.version_name || item.path.split(/[\\/]/).pop();
}

function toast(message, error = false) {
  const element = document.createElement("div");
  element.className = `toast ${error ? "error" : ""}`;
  element.textContent = message;
  document.querySelector("#toast-container").append(element);
  setTimeout(() => element.remove(), 4200);
}

function setLoading(action, loading) {
  if (!action) return;
  if (loading) state.loadingActions.add(action);
  else state.loadingActions.delete(action);
  document.querySelectorAll(`[data-loading-action="${action}"]`).forEach((button) => {
    button.classList.toggle("is-loading", loading);
    button.setAttribute("aria-busy", loading ? "true" : "false");
  });
}

async function withLoading(action, task) {
  setLoading(action, true);
  try {
    return await task();
  } finally {
    setLoading(action, false);
  }
}

function showWorkbenchError(message) {
  document.querySelector("#workbench-error-message").textContent = message;
  document.querySelector("#workbench-error").classList.remove("hidden");
}

function clearWorkbenchError() {
  document.querySelector("#workbench-error").classList.add("hidden");
  document.querySelector("#workbench-error-message").textContent = "";
}

function focusPageHeading() {
  const page = document.querySelector(".page.active h2, .page.active h3, #page-title");
  if (!page) return;
  page.setAttribute("tabindex", "-1");
  page.focus({ preventScroll: true });
}

function focusSectionHeading(container) {
  const heading = container?.querySelector("h2, h3");
  if (!heading) return;
  heading.setAttribute("tabindex", "-1");
  heading.focus({ preventScroll: true });
}

function setWorkbenchTab(tab, { focus = true } = {}) {
  state.workbenchTab = tab || "overview";
  document.querySelectorAll(".workbench-tab").forEach((button) => {
    const active = button.dataset.workbenchTab === state.workbenchTab;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", active ? "true" : "false");
  });
  document.querySelectorAll("[data-workbench-pane]").forEach((pane) => {
    pane.classList.add("active");
  });
  if (focus) {
    const selector = {
      overview: "[data-workbench-pane='overview']",
      build: "#workbench-builder",
      console: "#workbench-console",
    }[state.workbenchTab] || "[data-workbench-pane='overview']";
    const target = document.querySelector(selector);
    target?.scrollIntoView({ behavior: "smooth", block: "start" });
    focusSectionHeading(target);
  }
}

function translate() {
  document.documentElement.lang = state.locale;
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    const translated = t(node.dataset.i18n, "");
    if (translated) node.textContent = translated;
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((node) => {
    const translated = t(node.dataset.i18nPlaceholder, "");
    if (translated) node.placeholder = translated;
  });
  const active = document.querySelector(".nav-item.active b");
  if (active) document.querySelector("#page-title").textContent = active.textContent;
  setWorkbenchTab(state.workbenchTab, { focus: false });
  if (state.consoleFullscreen) setConsoleFullscreen(true);
}

function setPage(page, { focus = true } = {}) {
  document.querySelectorAll(".page").forEach((node) => node.classList.remove("active"));
  document.querySelectorAll(".nav-item").forEach((node) => node.classList.remove("active"));
  document.querySelector(`#page-${page}`)?.classList.add("active");
  const nav = document.querySelector(`.nav-item[data-page="${page}"]`);
  if (nav) {
    nav.classList.add("active");
    document.querySelector("#page-title").textContent = nav.querySelector("b").textContent;
  }
  if (page === "diagnostics") refreshDiagnostics();
  if (page === "artifacts") refreshArtifacts();
  if (focus) focusPageHeading();
}

function renderOverview() {
  const running = state.jobs.filter((job) => ["running", "packaging"].includes(job.status)).length;
  const queued = state.jobs.filter((job) => job.status === "queued").length;
  document.querySelector("#queue-summary").textContent = `${running} ${statusLabel("running").toLowerCase()} · ${queued} ${statusLabel("queued").toLowerCase()}`;
  document.querySelector("#overview-stats").innerHTML = [
    [state.locale === "vi" ? "JOB ĐANG CHẠY" : "ACTIVE JOBS", running],
    [state.locale === "vi" ? "ROM ĐANG CHỜ" : "QUEUED ROMS", queued],
    [state.locale === "vi" ? "ARTIFACT HỢP LỆ" : "VALID ARTIFACTS", state.artifacts.filter((item) => item.artifactExists !== false).length],
    [state.locale === "vi" ? "THIẾT BỊ HỖ TRỢ" : "SUPPORTED DEVICES", state.devices.length],
  ].map(([label, value]) => `<article class="stat"><span>${esc(label)}</span><strong>${value}</strong><small class="muted">${t("common.queue")}</small></article>`).join("");

  document.querySelector("#recent-jobs").innerHTML = state.jobs.slice(0, 6).map((job) => `
    <article class="list-card">
      <div><strong>${esc(jobName(job))}</strong><small>${date(job.createdAt)}</small></div>
      <div class="actions">${badge(job.status)}<button class="ghost compact" data-open-job="${esc(job.id)}">${t("action.details")}</button></div>
    </article>`).join("") || `<p class="muted">${t("common.noJobs")}</p>`;

  const diag = state.diagnostics;
  const binariesOk = Object.values(diag.binaries || {}).every(Boolean);
  const packagesOk = Object.values(diag.packages || {}).every(Boolean);
  document.querySelector("#health-list").innerHTML = [
    [state.locale === "vi" ? "Binary build" : "Build binaries", binariesOk, binariesOk ? t("common.ready") : t("common.missingBinary")],
    [state.locale === "vi" ? "Gói Python" : "Python packages", packagesOk, packagesOk ? t("common.ready") : t("common.missingDependency")],
    ["Telegram", diag.telegramConfigured, diag.telegramConfigured ? t("common.configured") : t("common.notConfigured")],
    [state.locale === "vi" ? "Dung lượng trống" : "Disk free", true, bytes(diag.disk?.free)],
  ].map(([name, ok, detail]) => `<article class="list-card"><div><strong>${esc(name)}</strong><small>${esc(detail)}</small></div>${badge(ok ? "success" : "failed")}</article>`).join("");
}

function liteSelected(step) {
  return new Set([
    "inspect_rom", "extract_payload", "unpack_partitions", "debloat", "apply_mod", "sync_configs",
    "repack_partitions", "repack_super",
    "patch_vbmeta", "package_zip",
  ]).has(step.id);
}

function presetSelected(step, preset) {
  return liteSelected(step);
}

function stepUnavailable() {
  return false;
}

function applyPresetSelection(preset) {
  state.pipelineSelection = new Set(
    preset === "custom"
      ? []
      : state.bootstrap.steps.filter((step) => presetSelected(step, preset)).map((step) => step.id),
  );
  if (preset !== "custom") {
    state.modSelection = new Set(defaultModsForPreset(preset));
  }
  const notifyToggle = document.querySelector("#notify-toggle");
  if (notifyToggle.checked && !notifyToggle.disabled) {
    state.pipelineSelection.add("notify_telegram");
  } else {
    state.pipelineSelection.delete("notify_telegram");
  }
  enforcePipelineDependencies();
}

function enforcePipelineDependencies() {
  if (!state.pipelineSelection) state.pipelineSelection = new Set();
  if (state.pipelineSelection.has("notify_telegram")) {
    state.pipelineSelection.add("package_zip");
  }
}

function defaultModsForPreset(preset) {
  const versionDefaults = state.bootstrap.presetDefaultsByVersion?.[state.modVersion]
    || state.bootstrap.presetDefaults
    || {};
  const names = [...(versionDefaults[preset] || [])];
  if (preset === "lite") {
    const availableMods = new Set(state.mods.map((mod) => mod.name));
    forcedLiteDefaultMods.forEach((name) => {
      if (availableMods.has(name) && !names.includes(name)) names.push(name);
    });
  }
  const excluded = presetDefaultModExcludes[preset];
  return excluded ? names.filter((name) => !excluded.has(name)) : names;
}

function activateModVersion(version, { resetSelection = true } = {}) {
  const availableVersions = state.bootstrap.modVersions || [];
  state.modVersion = availableVersions.includes(version) ? version : (availableVersions[0] || "ColorOS_16.0.7");
  state.mods = [...(state.bootstrap.modsByVersion?.[state.modVersion] || state.bootstrap.mods || [])];
  const availableMods = new Set(state.mods.map((mod) => mod.name));
  const preset = document.querySelector("#preset-select").value;
  state.modSelection = resetSelection && preset !== "custom"
    ? new Set(defaultModsForPreset(preset))
    : new Set([...state.modSelection].filter((name) => availableMods.has(name)));
  document.querySelector("#mod-version-select").value = state.modVersion;
}

function renderSteps({ reset = false } = {}) {
  const preset = document.querySelector("#preset-select").value;
  if (!state.pipelineSelection || reset) applyPresetSelection(preset);
  enforcePipelineDependencies();
  document.querySelector("#step-selector").innerHTML = state.bootstrap.steps.map((step, index) => {
    const unavailable = stepUnavailable(step);
    const checked = state.pipelineSelection.has(step.id);
    const avbWarning = step.id === "patch_vbmeta" || step.id === "patch_vendor_boot";
    const configure = step.id === "debloat"
      ? `<button class="ghost compact step-configure" type="button" data-configure-debloat>${t("action.customize")} · ${fmt("common.debloatPaths", { count: state.debloatPaths.length })}</button>`
      : (step.id === "apply_mod"
        ? `<button class="ghost compact step-configure" type="button" data-configure-mods>${t("action.customize")} · ${fmt("common.selectedMods", { count: state.modSelection.size })}</button>`
        : "");
    return `<label class="step">
      <input type="checkbox" data-step="${esc(step.id)}" ${checked ? "checked" : ""}>
      <span><strong>${String(index + 1).padStart(2, "0")} · ${esc(stepLabel(step))}</strong><small>${unavailable ? t("step.unavailable") : (avbWarning ? t("step.avb") : (checked && preset !== "custom" ? t("step.defaultTarget") : t("step.optional")))}</small>${configure}</span>
    </label>`;
  }).join("");
}

function selectedModsText() {
  return state.modSelection.size
    ? fmt("common.selectedMods", { count: state.modSelection.size })
    : t("common.noSelection");
}

function romStatusText(item) {
  if (item.inspecting) return t("common.inspecting");
  if (!item.inspect) return t("common.awaitingPreflight");
  if (item.inspect.ok && item.inspect.warnings?.length) return t("common.warningBuild");
  return item.inspect.ok ? t("common.readyToBuild") : t("common.blockedBuild");
}

function romMetaRow(label, value) {
  return `<div><span>${esc(label)}</span><strong>${esc(value || "-")}</strong></div>`;
}

function renderRomDetails(item) {
  const info = item.inspect || {};
  const metadata = info.metadata || {};
  const device = info.device || {};
  const errors = info.errors || [];
  const warnings = info.warnings || [];
  const details = [
    romMetaRow(t("label.version"), metadata.version_name),
    romMetaRow(t("label.product"), metadata.product_name),
    romMetaRow(t("label.modVersion"), info.modVersion || state.modVersion),
    romMetaRow(t("label.device"), device.name),
    romMetaRow(t("label.superSize"), device.SuperSize ? bytes(device.SuperSize) : ""),
    romMetaRow(t("label.groupSize"), device.GroupSize ? bytes(device.GroupSize) : ""),
    romMetaRow(t("label.size"), info.size ? bytes(info.size) : ""),
  ].join("");
  const messages = [
    ...errors.map((message) => `<li class="error">${esc(message)}</li>`),
    ...warnings.map((message) => `<li class="warn">${esc(message)}</li>`),
  ].join("");
  return `
    <div class="rom-confirm ${item.inspecting ? "running" : (info.ok ? "success" : (item.inspect ? "failed" : "pending"))}">
      <div class="rom-meta-grid">${details}</div>
      ${messages ? `<ul class="rom-messages">${messages}</ul>` : ""}
    </div>`;
}

function renderRomQueue() {
  if (!state.romQueue.length) {
    document.querySelector("#rom-queue").innerHTML = `
      <div class="empty-state">
        <strong>${t("empty.romQueueTitle")}</strong>
        <p>${t("empty.romQueueHint")}</p>
        <div class="empty-state-actions">
          <button class="primary" type="button" data-empty-browse-rom data-loading-action="browseRom">${t("builder.browse")}</button>
          <button class="ghost" type="button" data-empty-browse-folder data-loading-action="browseFolder">${t("builder.folder")}</button>
        </div>
      </div>`;
    updateBuildButtons();
    return;
  }
  document.querySelector("#rom-queue").innerHTML = state.romQueue.map((item, index) => `
    <article class="list-card rom-card">
      <div class="rom-card-head">
        <div class="rom-card-title">
          <strong>${esc(romName(item))}</strong>
          <code title="${esc(item.path)}">${esc(item.path)}</code>
        </div>
        <div class="actions">
          ${item.inspecting ? badge("running") : (item.inspect ? badge(item.inspect.ok ? "success" : "failed") : badge("pending"))}
          <span class="chip">${esc(selectedModsText())}</span>
          <button class="danger compact rom-remove" aria-label="Remove ROM" title="Remove ROM" data-remove-rom="${index}">×</button>
        </div>
      </div>
      ${renderRomDetails(item)}
    </article>`).join("");
  updateBuildButtons();
}

function closeDialog(id) {
  document.querySelector(id)?.close();
  if (state.lastFocusedElement?.isConnected) {
    state.lastFocusedElement.focus();
  }
  state.lastFocusedElement = null;
}

function openDebloatEditor() {
  state.lastFocusedElement = document.activeElement;
  document.querySelector("#debloat-paths").value = state.debloatPaths.join("\n");
  document.querySelector("#debloat-dialog").showModal();
}

async function saveDebloatEditor() {
  state.debloatPaths = document.querySelector("#debloat-paths").value
    .split(/\r?\n/)
    .map((path) => path.trim())
    .filter(Boolean);
  closeDialog("#debloat-dialog");
  document.querySelector("#preset-select").value = "custom";
  renderSteps();
  scheduleQueueInspection();
  await saveSettings({ silent: true });
  toast(t("toast.settingsSaved"));
}

function renderModDialog() {
  const selection = state.draftModSelection;
  document.querySelector("#mod-selection-summary").textContent = `${state.modVersion} · ${
    selection.size ? fmt("common.selectedMods", { count: selection.size }) : t("common.noSelection")
  }`;
  document.querySelector("#mod-options-grid").innerHTML = state.mods.map((mod) => {
    const warnings = [
      ...(mod.specialActions || []),
      ...(mod.blockedReason ? [mod.blockedReason] : []),
    ];
    return `<label class="mod-option ${mod.ready ? "" : "blocked"}">
      <input type="checkbox" data-draft-mod="${esc(mod.name)}" ${selection.has(mod.name) ? "checked" : ""}>
      <span>
        <strong>${esc(mod.name)}</strong>
        <small>${esc(modTargetText(mod))}</small>
        ${warnings.map((warning) => `<em>${esc(warning)}</em>`).join("")}
      </span>
      ${badge(mod.ready ? "success" : "failed")}
    </label>`;
  }).join("");
}

function modTargetText(mod) {
  if (mod.partitions?.length) return mod.partitions.join(", ");
  if (mod.patchOnly && mod.specialActions?.length) return mod.specialActions[0];
  return t("common.invalid");
}

function openModEditor() {
  state.lastFocusedElement = document.activeElement;
  state.draftModSelection = new Set(state.modSelection);
  renderModDialog();
  document.querySelector("#mod-dialog").showModal();
}

function setDraftMods(names) {
  state.draftModSelection = new Set(names);
  renderModDialog();
}

function saveModEditor() {
  state.modSelection = new Set(state.draftModSelection);
  if (!state.pipelineSelection) state.pipelineSelection = new Set();
  if (state.modSelection.size) state.pipelineSelection.add("apply_mod");
  else state.pipelineSelection.delete("apply_mod");
  document.querySelector("#preset-select").value = "custom";
  closeDialog("#mod-dialog");
  renderSteps();
  renderRomQueue();
  scheduleQueueInspection();
}

async function inspectQueue() {
  if (!state.romQueue.length) throw new Error(t("error.selectRom"));
  await inspectRomItems(state.romQueue);
  renderRomQueue();
  const failed = state.romQueue.filter((item) => !item.inspect.ok);
  if (failed.length) {
    const message = fmt("error.preflightFailed", { count: failed.length });
    showWorkbenchError(message);
    setWorkbenchTab("build", { focus: false });
    throw new Error(message);
  }
  clearWorkbenchError();
  toast(t("toast.preflightPassed"));
}

function selectedSteps() {
  enforcePipelineDependencies();
  return [...(state.pipelineSelection || [])];
}

function updateBuildButtons() {
  const inspecting = state.romQueue.some((item) => item.inspecting);
  document.querySelector("#inspect-all").disabled = state.creatingJobs || inspecting;
  document.querySelector("#create-jobs").disabled = state.creatingJobs || inspecting || !state.romQueue.length;
  document.querySelector("#start-build-hero").disabled = state.creatingJobs || inspecting;
}

async function inspectRomItem(item, { silent = true } = {}) {
  const requestId = (item.inspectRequestId || 0) + 1;
  item.inspectRequestId = requestId;
  item.inspecting = true;
  renderRomQueue();
  updateBuildButtons();
  try {
    const inspect = await api("/api/roms/inspect", {
      method: "POST",
      body: JSON.stringify({
        romPath: item.path,
        modNames: [...state.modSelection],
        modVersion: state.modVersion,
        debloatPaths: state.debloatPaths,
        preset: document.querySelector("#preset-select").value,
        enabledSteps: selectedSteps(),
      }),
    });
    if (item.inspectRequestId !== requestId) return;
    item.inspect = inspect;
    if (!silent && inspect.ok) toast(t("toast.autoInspectDone"));
  } catch (error) {
    if (item.inspectRequestId !== requestId) return;
    item.inspect = {
      ok: false,
      errors: [error.message],
      warnings: [],
      metadata: {},
      device: null,
      size: 0,
    };
  } finally {
    if (item.inspectRequestId === requestId) {
      item.inspecting = false;
      renderRomQueue();
      updateBuildButtons();
    }
  }
}

async function inspectRomItems(items, concurrency = 3) {
  const queue = [...items];
  const workers = Array.from({ length: Math.min(concurrency, queue.length) }, async () => {
    while (queue.length) await inspectRomItem(queue.shift());
  });
  await Promise.all(workers);
}

function scheduleQueueInspection() {
  clearTimeout(state.queueInspectTimer);
  state.queueInspectTimer = setTimeout(() => {
    inspectRomItems(state.romQueue).catch((error) => toast(error.message, true));
  }, 180);
}

async function createJobs() {
  if (state.creatingJobs) return;
  state.creatingJobs = true;
  updateBuildButtons();
  try {
    await inspectQueue();
    const specs = state.romQueue.map((item) => ({
      romPath: item.path,
      modNames: [...state.modSelection],
      modVersion: state.modVersion,
      debloatPaths: state.debloatPaths,
      preset: document.querySelector("#preset-select").value,
      enabledSteps: selectedSteps(),
      notifyTelegram: document.querySelector("#notify-toggle").checked,
    }));
    const result = await api("/api/jobs", { method: "POST", body: JSON.stringify({ specs }) });
    toast(fmt("toast.queued", { count: result.jobs.length }));
    state.romQueue = [];
    renderRomQueue();
    await refreshJobs();
    setPage("workbench");
    setWorkbenchTab("console", { focus: false });
    await openJob(result.jobs[0].id);
  } finally {
    state.creatingJobs = false;
    updateBuildButtons();
  }
}

function scrollToBuilder() {
  setPage("workbench");
  setWorkbenchTab("build");
}

async function startBuildFromHero() {
  if (!state.romQueue.length) {
    scrollToBuilder();
    toast(t("error.selectRom"), true);
    return;
  }
  await createJobs();
}

function addRomToQueue(path, { autoInspect = true } = {}) {
  let item = state.romQueue.find((candidate) => candidate.path === path);
  if (!item) {
    item = { path, inspect: null, inspecting: false };
    state.romQueue.push(item);
  }
  renderRomQueue();
  updateBuildButtons();
  if (autoInspect) inspectRomItem(item).catch((error) => toast(error.message, true));
  return item;
}

async function addTypedRomPath() {
  const input = document.querySelector("#rom-path-input");
  const data = await api("/api/fs/authorize-rom", {
    method: "POST",
    body: JSON.stringify({ romPath: input.value }),
  });
  addRomToQueue(data.path);
  input.value = "";
}

async function pickRom() {
  if (desktopBridgeAvailable) {
    const result = await nativeAction("pickRom", {}, { timeout: 0 });
    const selected = result?.paths?.[0];
    if (!selected) return;
    const data = await api("/api/fs/authorize-rom", {
      method: "POST",
      body: JSON.stringify({ romPath: selected }),
    });
    addRomToQueue(data.path);
    return;
  }
  const data = await api("/api/fs/pick-rom", { method: "POST" });
  if (data.path) addRomToQueue(data.path);
}

async function pickFolder() {
  let data;
  if (desktopBridgeAvailable) {
    const result = await nativeAction("pickRomFolder", {}, { timeout: 0 });
    if (!result?.path) return;
    data = await api("/api/fs/authorize-rom-folder", {
      method: "POST",
      body: JSON.stringify({ folderPath: result.path }),
    });
  } else {
    try {
      data = await api("/api/fs/pick-rom-folder", { method: "POST" });
    } catch (error) {
      const folderPath = window.prompt(t("builder.folderPrompt"));
      if (!folderPath?.trim()) throw error;
      data = await api("/api/fs/authorize-rom-folder", {
        method: "POST",
        body: JSON.stringify({ folderPath }),
      });
    }
  }
  if (!data.folder) return;
  if (!data.roms?.length) {
    toast(t("toast.noZipInFolder"), true);
    return;
  }
  const items = data.roms.map((path) => addRomToQueue(path, { autoInspect: false }));
  await inspectRomItems(items);
  toast(fmt("toast.folderAdded", { count: data.roms.length }));
}

function renderJobs() {
  document.querySelector("#job-list").innerHTML = state.jobs.map((job) => `
    <button class="list-card ${state.activeJob?.id === job.id ? "selected" : ""}" data-open-job="${esc(job.id)}">
      <div><strong>${esc(jobName(job))}</strong><small>${job.currentStep ? `${esc(stepLabel(job.currentStep))} · ` : ""}${date(job.createdAt)}</small></div>
      ${badge(job.status)}
    </button>`).join("") || `<p class="muted">${t("common.noJobs")}</p>`;
  renderOverview();
}

function activeConsoleStepId(job) {
  const steps = job.steps || [];
  if (job.currentStep) return job.currentStep;
  const active = steps.find((step) => ["running", "failed", "cancelled"].includes(step.status));
  if (active) return active.id;
  const completed = [...steps].reverse().find((step) => step.status === "success");
  return completed?.id || steps[0]?.id || "";
}

function scrollConsoleStepIntoView(job) {
  const stepId = activeConsoleStepId(job);
  if (!stepId) return;
  requestAnimationFrame(() => {
    const container = document.querySelector("#console-steps");
    const target = [...(container?.querySelectorAll(".console-step") || [])]
      .find((element) => element.dataset.stepId === stepId);
    target?.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
  });
}

function buildProgress(job) {
  const steps = job.steps || [];
  if (!steps.length) return null;
  const started = job.startedAt ? new Date(job.startedAt).getTime() : null;
  const finished = job.finishedAt ? new Date(job.finishedAt).getTime() : null;
  const elapsedMs = started && Number.isFinite(started)
    ? ((finished && Number.isFinite(finished)) ? finished : Date.now()) - started
    : 0;
  if (job.status === "success") return { progress: 100, step: null, detail: statusLabel("success"), elapsedMs };
  if (job.status === "queued") return { progress: 0, step: steps[0], detail: statusLabel("queued"), elapsedMs: 0 };
  const activeId = activeConsoleStepId(job);
  const activeIndex = Math.max(0, steps.findIndex((step) => step.id === activeId));
  const activeStep = steps[activeIndex] || steps[0];
  const completedBefore = steps
    .slice(0, activeIndex)
    .filter((step) => step.status === "success").length;
  let partial = activeStep?.status === "success" ? 1 : 0;
  if (activeStep?.status === "running") {
    const rawStepProgress = Number(activeStep.details?.progress);
    partial = Number.isFinite(rawStepProgress)
      ? Math.max(0, Math.min(100, rawStepProgress)) / 100
      : 0;
  }
  if (["failed", "cancelled"].includes(activeStep?.status)) partial = 0;
  const progress = ((completedBefore + partial) / steps.length) * 100;
  const detailParts = [];
  if (activeStep) {
    const stepPrefix = state.locale === "vi" ? "Bước" : "Step";
    detailParts.push(`${stepPrefix} ${activeIndex + 1}/${steps.length}: ${stepLabel(activeStep.id)}`);
  }
  if (activeStep?.details?.progressMessage) detailParts.push(activeStep.details.progressMessage);
  return {
    progress: Math.max(0, Math.min(100, progress)),
    step: activeStep,
    detail: detailParts.join(" · "),
    elapsedMs,
  };
}

function renderBuildProgress(job) {
  const element = document.querySelector("#console-build-progress");
  const progressState = buildProgress(job);
  if (!progressState) {
    element.classList.add("hidden");
    element.innerHTML = "";
    return;
  }
  const progress = progressState.progress;
  const statusText = `${Math.round(progress)}%`;
  const timerText = clockDuration(progressState.elapsedMs);
  const title = state.locale === "vi" ? "Tiến trình build ROM" : "ROM build progress";
  element.classList.remove("hidden");
  element.innerHTML = `
    <div class="build-progress-head">
      <span>${esc(title)}</span>
      <span class="build-progress-stats"><b>${esc(timerText)}</b><b>${esc(statusText)}</b></span>
    </div>
    <div class="build-progress-track"><div class="build-progress-fill" style="width: ${progress}%"></div></div>
    ${progressState.detail ? `<small>${esc(progressState.detail)}</small>` : ""}
  `;
}

function syncBuildTimer() {
  const shouldRun = state.activeJob
    && ["running", "packaging"].includes(state.activeJob.status)
    && state.activeJob.startedAt;
  if (shouldRun && !state.buildTimerInterval) {
    state.buildTimerInterval = setInterval(() => {
      if (["running", "packaging"].includes(state.activeJob?.status)) renderBuildProgress(state.activeJob);
      else syncBuildTimer();
    }, 1000);
  }
  if (!shouldRun && state.buildTimerInterval) {
    clearInterval(state.buildTimerInterval);
    state.buildTimerInterval = null;
  }
}

async function refreshJobs() {
  if (state.jobsRefreshing) return;
  state.jobsRefreshing = true;
  try {
    const data = await api("/api/jobs");
    state.jobs = data.jobs;
    renderJobs();
    if (state.activeJob) {
      const updated = state.jobs.find((job) => job.id === state.activeJob.id);
      if (updated) renderActiveJob(updated);
    }
  } finally {
    state.jobsRefreshing = false;
  }
}

function renderActiveJob(job) {
  state.activeJob = job;
  document.querySelector("#console-job-id").textContent = job.currentStep
    ? `${statusLabel(job.status)} · ${stepLabel(job.currentStep)}`
    : statusLabel(job.status);
  document.querySelector("#console-job-title").textContent = jobName(job);
  document.querySelector("#cancel-job").classList.toggle("hidden", ["success", "failed", "cancelled"].includes(job.status));
  document.querySelector("#resume-job").classList.toggle("hidden", !["failed", "cancelled"].includes(job.status));
  const packageStep = (job.steps || []).find((step) => step.id === "package_zip");
  const outputZips = packageStep?.details?.outputZips || (job.outputZip ? [job.outputZip] : []);
  document.querySelector("#console-artifact").textContent = outputZips.length
    ? `${t("label.outputArtifact")}: ${outputZips.join(" | ")}`
    : "";
  document.querySelector("#console-steps").innerHTML = (job.steps || []).map((step) =>
    `<span class="console-step ${esc(step.status)}" data-step-id="${esc(step.id)}" title="${esc(stepLabel(step.id))}">${esc(stepLabel(step.id))}</span>`
  ).join("");
  scrollConsoleStepIntoView(job);
  renderBuildProgress(job);
  syncBuildTimer();
  renderJobs();
}

function logClass(line) {
  const lower = String(line).toLowerCase();
  if (/^(=+|\[#+\]|#+\s)|^\s*(step|stage)\s+\d+/i.test(line)) return "log-stage";
  if (/\bcmd\b|\bcommand\b|chạy lệnh|running command|\$ /.test(lower)) return "log-command";
  if (/error|failed|fail|exception|traceback|không thành công|lỗi/.test(lower)) return "log-error";
  if (/warn|warning|missing|skip|bỏ qua|thiếu|cảnh báo/.test(lower)) return "log-warn";
  if (/success|done| ok\b|\[ok\]|hoàn tất|thành công|validated/.test(lower)) return "log-success";
  return "";
}

function renderLogLine(line) {
  const css = logClass(line);
  return `<span class="terminal-line ${css}">${esc(line)}</span>`;
}

function renderLogs() {
  if (state.pendingLogLines.length) {
    state.logLines.push(...state.pendingLogLines);
    state.pendingLogLines = [];
    if (state.logLines.length > state.maxLogLines) {
      state.logLines.splice(0, state.logLines.length - state.maxLogLines);
    }
  }
  const query = document.querySelector("#log-search").value.toLowerCase();
  const lines = state.logLines.filter((line) => line.toLowerCase().includes(query));
  const output = document.querySelector("#log-output");
  output.innerHTML = lines.length ? lines.map(renderLogLine).join("") : esc(t("common.noLog"));
  if (document.querySelector("#auto-scroll").checked) {
    output.scrollTop = output.scrollHeight;
  }
}

function scheduleLogRender() {
  if (!state.logRenderTimer) {
    state.logRenderTimer = setTimeout(() => {
      state.logRenderTimer = null;
      renderLogs();
    }, 250);
  }
}

function clearLogs() {
  clearTimeout(state.logRenderTimer);
  state.logRenderTimer = null;
  state.pendingLogLines = [];
  state.logLines = [];
  renderLogs();
}

async function copyLog() {
  const text = state.logLines.join("\n");
  const value = text || t("common.noLog");
  if (desktopBridgeAvailable) await nativeAction("copyText", { text: value });
  else await navigator.clipboard.writeText(value);
  toast(t("toast.copied"));
}

async function downloadLog() {
  if (!state.activeJob) return;
  const response = await fetch(`/api/jobs/${encodeURIComponent(state.activeJob.id)}/log`, {
    headers: { "X-Studio-Token": token },
  });
  if (response.status === 403) {
    window.location.reload();
    throw new Error("Studio session expired");
  }
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${jobName(state.activeJob)}.log`;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function setConsoleFullscreen(enabled) {
  state.consoleFullscreen = enabled;
  document.querySelector(".console-main")?.classList.toggle("fullscreen", enabled);
  const button = document.querySelector("#fullscreen-console");
  if (button) {
    button.textContent = enabled ? t("action.exitFullscreen") : t("action.fullscreen");
    button.setAttribute("aria-pressed", enabled ? "true" : "false");
  }
}

async function openJob(id) {
  const job = await api(`/api/jobs/${id}`);
  renderActiveJob(job);
  setPage("workbench");
  setWorkbenchTab("console");
  clearLogs();
  if (state.eventSource) state.eventSource.close();
  const generation = ++state.streamGeneration;
  state.eventSource = new EventSource(`/api/jobs/${id}/events?token=${encodeURIComponent(token)}`);
  state.eventSource.addEventListener("log", (event) => {
    if (generation !== state.streamGeneration) return;
    const payload = JSON.parse(event.data);
    state.pendingLogLines.push(...(payload.lines || [payload.line]).filter((line) => line !== undefined));
    if (state.pendingLogLines.length > state.maxPendingLogLines) {
      state.pendingLogLines.splice(0, state.pendingLogLines.length - state.maxPendingLogLines);
    }
    scheduleLogRender();
  });
  state.eventSource.addEventListener("state", (event) => {
    if (generation !== state.streamGeneration) return;
    renderActiveJob(JSON.parse(event.data));
    refreshJobs();
  });
}

async function resumeActiveJob() {
  if (!state.activeJob || !["failed", "cancelled"].includes(state.activeJob.status)) return;
  const result = await api("/api/jobs", {
    method: "POST",
    body: JSON.stringify({
      ...state.activeJob.spec,
      preset: "resume",
      modNames: state.activeJob.spec.modNames || [],
      debloatPaths: state.activeJob.spec.debloatPaths || state.debloatPaths,
      resumeFromJobId: state.activeJob.id,
    }),
  });
  toast(t("toast.resumeQueued"));
  await refreshJobs();
  openJob(result.jobs[0].id);
}

async function refreshArtifacts() {
  const data = await api("/api/artifacts");
  state.artifacts = data.artifacts;
  document.querySelector("#artifact-list").innerHTML = state.artifacts.length ? `<table><thead><tr><th>${t("label.artifactFile")}</th><th>${t("label.valid")}</th><th>${t("label.created")}</th><th>${t("label.path")}</th><th></th></tr></thead><tbody>${
    state.artifacts.map((item) => `<tr><td><strong>${esc(item.outputZip.split(/[\\/]/).pop())}</strong></td><td>${badge(item.artifactExists === false ? "failed" : "success")}${item.artifactExists === false ? `<small class="warning">${t("common.artifactMissing")}</small>` : ""}</td><td>${date(item.finishedAt)}</td><td><code>${esc(item.outputZip)}</code></td><td><button class="ghost compact" data-copy="${esc(item.outputZip)}">${t("action.copy")}</button> <button class="ghost compact" data-open-artifact="${esc(item.outputZip)}" ${item.artifactExists === false ? "disabled" : ""}>${t("action.open")}</button></td></tr>`).join("")
  }</tbody></table>` : `<p class="muted">${t("common.noArtifacts")}</p>`;
  renderOverview();
}

function renderCatalog() {
  const packs = state.bootstrap.contentPacks || [];
  document.querySelector("#device-count").textContent = state.devices.length;
  document.querySelector("#mod-count").textContent = state.mods.length + packs.length;
  document.querySelector("#device-list").innerHTML = state.devices.map((device) => `
    <article class="list-card"><div><strong>${esc(device.name)}</strong><small>${esc(device.product_name)} · SoC ${esc(device.soc)}</small></div><span class="chip">${fmt("label.extraPartitions", { count: device.Partitions.length })}</span></article>`).join("");
  document.querySelector("#mod-list").innerHTML = packs.map((pack) => `
    <article class="list-card"><div><strong>${esc(pack.displayName)}</strong><small>${esc(pack.target)} · ${esc(pack.version)}</small></div>${badge(pack.healthy ? "success" : "failed")}</article>`).join("") + state.mods.map((mod) => `
    <article class="list-card"><div><strong>${esc(mod.name)}</strong><small>${esc(modTargetText(mod))}</small>${mod.specialActions?.length && !mod.patchOnly ? `<small>${esc(mod.specialActions.join(" · "))}</small>` : ""}${mod.blockedReason ? `<small class="warning">${esc(mod.blockedReason)}</small>` : ""}</div>${badge(mod.ready ? "success" : "failed")}</article>`).join("");
}

async function refreshDiagnostics() {
  state.diagnostics = await api("/api/diagnostics");
  const diag = state.diagnostics;
  document.querySelector("#diagnostics-grid").innerHTML = [
    [state.locale === "vi" ? "Runtime" : "Runtime", `<p>Python <b>${esc(diag.python)}</b></p><p>Java <b>${esc(diag.java)}</b></p><p>7-Zip <b>${esc(diag.sevenZip)}</b></p>`],
    [state.locale === "vi" ? "Binary build" : "Build binaries", Object.entries(diag.binaries).map(([key, ok]) => `<p>${esc(key)} ${badge(ok ? "success" : "failed")}</p>`).join("")],
    [state.locale === "vi" ? "Gói Python" : "Python packages", Object.entries(diag.packages).map(([key, ok]) => `<p>${esc(key)} ${badge(ok ? "success" : "failed")}</p>`).join("")],
    ["apktool · MOD JAR", `<p>${badge(diag.apktool?.ready ? "success" : "failed")}</p><p>${esc(diag.apktool?.path || "-")}</p>`],
    [state.locale === "vi" ? "Dung lượng" : "Storage", `<p>${state.locale === "vi" ? "Trống" : "Free"} <b>${bytes(diag.disk.free)}</b></p><p>${t("label.total")} <b>${bytes(diag.disk.total)}</b></p>`],
    ["Telegram", `<p>${badge(diag.telegramConfigured ? "success" : "failed")}</p><p>${state.locale === "vi" ? "Secret được bảo vệ bằng Windows DPAPI" : "Secret protected by Windows DPAPI"}</p>`],
    [state.locale === "vi" ? "Chuỗi cung ứng" : "Supply chain", `<p class="warning">${state.locale === "vi" ? "Binary chưa ký số." : "Unsigned build binaries detected."}</p><p class="warning">${state.locale === "vi" ? "MD5 chỉ kiểm tra toàn vẹn, không phải chữ ký tin cậy." : "MD5 verifies integrity, not authenticity."}</p>`],
  ].map(([title, body]) => `<article class="diag"><h4>${esc(title)}</h4>${body}</article>`).join("");
  renderSteps();
  renderOverview();
}

function renderSettings() {
  document.querySelector("#settings-locale").value = state.settings.locale || "vi";
  document.querySelector("#settings-preset").value = state.settings.defaultPreset || "lite";
  document.querySelector("#settings-notify").checked = Boolean(state.settings.notifyTelegram);
  document.querySelector("#settings-notify").disabled = !state.diagnostics.telegramConfigured;
  document.querySelector("#settings-roots").innerHTML = (state.settings.roots || []).map((root, index) =>
    `<article class="list-card"><code>${esc(root)}</code><button class="danger compact" data-remove-root="${index}">X</button></article>`
  ).join("");
}

async function saveSettings({ silent = false } = {}) {
  state.settings = await api("/api/settings", {
    method: "POST",
    body: JSON.stringify({
      roots: state.settings.roots,
      locale: document.querySelector("#settings-locale").value,
      defaultPreset: document.querySelector("#settings-preset").value,
      notifyTelegram: document.querySelector("#settings-notify").checked,
      debloatPaths: state.debloatPaths,
    }),
  });
  state.locale = state.settings.locale;
  translate();
  renderSettings();
  renderOverview();
  if (!silent) toast(t("toast.settingsSaved"));
}

async function bootstrap() {
  state.bootstrap = await api("/api/bootstrap");
  state.settings = state.bootstrap.settings;
  state.locale = state.settings.locale || "vi";
  state.jobs = state.bootstrap.jobs;
  state.artifacts = state.bootstrap.artifacts;
  state.devices = state.bootstrap.devices;
  const versions = state.bootstrap.modVersions || ["ColorOS_16.0.7"];
  const versionSelect = document.querySelector("#mod-version-select");
  versionSelect.innerHTML = versions.map((version) => `<option value="${esc(version)}">${esc(version.replaceAll("_", " "))}</option>`).join("");
  state.diagnostics = state.bootstrap.diagnostics;
  state.defaultDebloatPaths = [...(state.bootstrap.defaultDebloatPaths || [])];
  state.debloatPaths = [...(state.settings.debloatPaths || state.defaultDebloatPaths)];
  document.querySelector("#preset-select").value = state.settings.defaultPreset || "lite";
  activateModVersion(versions.includes("ColorOS_16.0.7") ? "ColorOS_16.0.7" : versions[0], { resetSelection: false });
  document.querySelector("#notify-toggle").checked = Boolean(state.settings.notifyTelegram);
  document.querySelector("#notify-toggle").disabled = !state.diagnostics.telegramConfigured;
  translate();
  renderSteps({ reset: true });
  renderRomQueue();
  renderJobs();
  renderCatalog();
  renderSettings();
  await refreshDiagnostics();
  const requestedJob = new URLSearchParams(window.location.search).get("job");
  if (requestedJob) {
    await openJob(requestedJob);
    window.history.replaceState({}, "", window.location.pathname);
  }
}

document.addEventListener("click", async (event) => {
  const target = event.target.closest("button");
  if (!target) return;
  try {
    if (target.dataset.configureDebloat !== undefined) {
      event.preventDefault();
      openDebloatEditor();
    }
    if (target.dataset.configureMods !== undefined) {
      event.preventDefault();
      openModEditor();
    }
    if (target.id === "reset-debloat") {
      document.querySelector("#debloat-paths").value = state.defaultDebloatPaths.join("\n");
    }
    if (target.id === "save-debloat") await saveDebloatEditor();
    if (["cancel-debloat", "cancel-debloat-bottom"].includes(target.id)) closeDialog("#debloat-dialog");
    if (target.id === "select-lite-mods") setDraftMods(defaultModsForPreset("lite"));
    if (target.id === "select-all-mods") setDraftMods(state.mods.map((mod) => mod.name));
    if (target.id === "clear-mods") setDraftMods([]);
    if (target.id === "save-mods") saveModEditor();
    if (["cancel-mods", "cancel-mods-bottom"].includes(target.id)) closeDialog("#mod-dialog");
    if (target.dataset.page) setPage(target.dataset.page);
    if (target.dataset.nav) setPage(target.dataset.nav);
    if (target.dataset.workbenchTab) {
      setPage("workbench");
      setWorkbenchTab(target.dataset.workbenchTab);
    }
    if (target.id === "new-build-shortcut") scrollToBuilder();
    if (target.id === "dismiss-workbench-error") clearWorkbenchError();
    if (target.id === "start-build-hero") await withLoading("create", startBuildFromHero);
    if (target.dataset.openJob) await openJob(target.dataset.openJob);
    if (target.id === "browse-rom" || target.dataset.emptyBrowseRom !== undefined) await withLoading("browseRom", pickRom);
    if (target.id === "browse-folder" || target.dataset.emptyBrowseFolder !== undefined) await withLoading("browseFolder", pickFolder);
    if (target.id === "add-rom-path") await withLoading("browseRom", addTypedRomPath);
    if (target.dataset.removeRom !== undefined) {
      state.romQueue.splice(Number(target.dataset.removeRom), 1);
      renderRomQueue();
    }
    if (target.id === "inspect-all") await withLoading("inspect", inspectQueue);
    if (target.id === "create-jobs") await withLoading("create", createJobs);
    if (target.id === "refresh-jobs") await withLoading("refreshJobs", refreshJobs);
    if (target.id === "cancel-job" && state.activeJob) {
      await api(`/api/jobs/${state.activeJob.id}/cancel`, { method: "POST" });
      refreshJobs();
    }
    if (target.id === "resume-job") resumeActiveJob();
    if (target.id === "copy-log") await copyLog();
    if (target.id === "download-log") await downloadLog();
    if (target.id === "fullscreen-console") setConsoleFullscreen(!state.consoleFullscreen);
    if (target.id === "clear-console") {
      clearLogs();
    }
    if (target.id === "refresh-artifacts") refreshArtifacts();
    if (target.dataset.copy) {
      if (desktopBridgeAvailable) await nativeAction("copyText", { text: target.dataset.copy });
      else await navigator.clipboard.writeText(target.dataset.copy);
      toast(t("toast.copied"));
    }
    if (target.dataset.openArtifact) {
      if (desktopBridgeAvailable) await nativeAction("openFolder", { path: target.dataset.openArtifact });
      else await api("/api/artifacts/open", { method: "POST", body: JSON.stringify({ path: target.dataset.openArtifact }) });
    }
    if (target.id === "refresh-diagnostics") await withLoading("diagnostics", refreshDiagnostics);
    if (target.id === "lang-toggle") {
      state.locale = state.locale === "vi" ? "en" : "vi";
      translate();
      renderSteps();
      renderRomQueue();
      renderJobs();
      renderCatalog();
      renderSettings();
      renderModDialog();
      renderDiagnosticsIfVisible();
    }
    if (target.dataset.removeRoot !== undefined) {
      state.settings.roots.splice(Number(target.dataset.removeRoot), 1);
      renderSettings();
    }
    if (target.id === "add-root") {
      const input = document.querySelector("#new-root");
      if (input.value.trim()) state.settings.roots.push(input.value.trim());
      input.value = "";
      renderSettings();
    }
    if (target.id === "save-settings") await saveSettings();
  } catch (error) {
    if (document.querySelector("#page-workbench").classList.contains("active")) {
      showWorkbenchError(error.message);
    }
    toast(error.message, true);
  }
});

function renderDiagnosticsIfVisible() {
  if (document.querySelector("#page-diagnostics").classList.contains("active")) {
    refreshDiagnostics();
  } else {
    renderOverview();
  }
}

document.addEventListener("change", (event) => {
  if (event.target.matches("[data-draft-mod]")) {
    if (event.target.checked) state.draftModSelection.add(event.target.dataset.draftMod);
    else state.draftModSelection.delete(event.target.dataset.draftMod);
    renderModDialog();
  }
  if (event.target.id === "notify-toggle") {
    if (!state.pipelineSelection) state.pipelineSelection = new Set();
    if (event.target.checked) state.pipelineSelection.add("notify_telegram");
    else state.pipelineSelection.delete("notify_telegram");
    enforcePipelineDependencies();
    document.querySelector("#preset-select").value = "custom";
    renderSteps();
    scheduleQueueInspection();
  }
  if (event.target.id === "preset-select") {
    renderSteps({ reset: true });
    renderRomQueue();
    scheduleQueueInspection();
  }
  if (event.target.id === "mod-version-select") {
    activateModVersion(event.target.value);
    renderSteps();
    renderRomQueue();
    renderCatalog();
    scheduleQueueInspection();
  }
  if (event.target.matches("[data-step]")) {
    if (!state.pipelineSelection) state.pipelineSelection = new Set();
    if (event.target.checked) state.pipelineSelection.add(event.target.dataset.step);
    else state.pipelineSelection.delete(event.target.dataset.step);
    if (event.target.dataset.step === "notify_telegram") {
      document.querySelector("#notify-toggle").checked = event.target.checked;
    }
    enforcePipelineDependencies();
    if (document.querySelector("#preset-select").value !== "custom") {
      document.querySelector("#preset-select").value = "custom";
    }
    renderSteps();
    scheduleQueueInspection();
  }
});

document.querySelector("#log-search").addEventListener("input", renderLogs);
document.querySelector("#rom-path-input").addEventListener("keydown", (event) => {
  if (event.key === "Enter") addTypedRomPath().catch((error) => toast(error.message, true));
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && state.consoleFullscreen) {
    setConsoleFullscreen(false);
    return;
  }
  if (event.ctrlKey && event.key === "Enter" && state.workbenchTab === "build") {
    event.preventDefault();
    withLoading("create", createJobs).catch((error) => {
      showWorkbenchError(error.message);
      toast(error.message, true);
    });
    return;
  }
  const active = document.activeElement;
  const editing = active && ["INPUT", "TEXTAREA", "SELECT"].includes(active.tagName);
  if (event.key === "/" && state.workbenchTab === "console" && !editing) {
    event.preventDefault();
    document.querySelector("#log-search").focus();
  }
});

bootstrap().catch((error) => toast(error.message, true));
setInterval(refreshJobs, 5000);
