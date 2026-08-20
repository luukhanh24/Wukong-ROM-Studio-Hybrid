const TelegramApp = window.Telegram && window.Telegram.WebApp;

const translations = {
  vi: {
    connected: "BOT ĐÃ KẾT NỐI", buildTitle: "Chuẩn bị chuyến build", buildIntro: "Kiểm tra nguồn ROM, runner và đầu ra trước khi gửi recipe.",
    routePolicy: "ĐỊNH TUYẾN", sourceTitle: "ROM nguồn", sourceHint: "Dùng URL trực tiếp, trang build Daniel Springer hoặc đường dẫn Drive riêng tư.",
    taskBuild: "Build đầy đủ", taskMirror: "Chỉ lưu ROM gốc", taskPublish: "Phát hành artifact", sourceUrl: "URL hoặc Drive reference", sourceSecure: "URL ký tạm thời được che khỏi bản tóm tắt và log.",
    device: "Thiết bị", sourceSize: "Dung lượng ROM (byte)", checksum: "SHA-256 tùy chọn", recipeTitle: "Cấu hình bản ROM",
    recipeHint: "Preset đặt mặc định; bạn vẫn có thể chọn chính xác từng MOD và bước pipeline.", runner: "Runner", edition: "Phiên bản", modPack: "Bộ MOD",
    mods: "MOD áp dụng", defaults: "Mặc định", selectAll: "Chọn tất cả", clear: "Bỏ chọn", advanced: "Thiết đặt pipeline nâng cao",
    debloatPaths: "Đường dẫn cần xóa (mỗi dòng một mục)", workspaceEstimate: "Ước lượng workspace (byte, để trống = tự động)",
    deliveryTitle: "Đóng gói và phát hành", deliveryHint: "Artifact thành công được kiểm checksum trước khi phát hành.", packageZip: "Tạo ZIP flashable",
    packageHint: "Đóng gói ROM sau khi repack", publish: "Upload lên Drive", publishHint: "Tạo link tải artifact khi thành công", notify: "Thông báo Telegram",
    notifyHint: "Nhận trạng thái và link ngay trong chat", readyLabel: "RECIPE SẴN SÀNG", fallbackWarning: "Auto ưu tiên runner phù hợp và dùng GitHub Hosted mở rộng đĩa khi self-hosted offline.",
    launch: "Tạo job build", jobsTitle: "Điều khiển job", jobsIntro: "Các yêu cầu được xác thực bằng tài khoản Telegram đang mở Mini App.", myJobs: "Mở danh sách trong chat",
    refreshJob: "Làm mới", events: "Nhật ký", artifact: "Artifact", resume: "Tiếp tục", cancel: "Hủy job", cloudTitle: "Cloud library",
    cloudIntro: "ROM nguồn, checkpoint và artifact vẫn riêng tư; chỉ artifact được phát hành mới có link chia sẻ.", browseCloud: "Duyệt thư viện",
    browseCloudHint: "Mở danh sách nguồn và artifact trong chat", mirrorRom: "Lưu ROM gốc", mirrorHint: "Chọn “Chỉ lưu ROM gốc” trong màn hình Build",
    systemTitle: "Tình trạng hệ thống", systemIntro: "Kiểm tra bot, Drive, runner và content-pack trước khi tạo job lớn.", runDiagnostics: "Chạy chẩn đoán",
    authenticated: "Đã xác thực phiên hiện tại", runnerChecked: "Runner được kiểm tra khi submit", driveChecked: "Quyền truy cập được kiểm tra trước upload",
    navBuild: "Build", navJobs: "Jobs", navCloud: "Cloud", navSystem: "Hệ thống", selected: "đã chọn", catalogReady: "{mods} MOD · {versions} bộ nội dung sẵn sàng",
    catalogFailed: "Không tải được catalog. Hãy thử mở lại Mini App.", invalidUrl: "Nhập URL HTTP/HTTPS hoặc đường dẫn rclone hợp lệ.", invalidSha: "SHA-256 phải có đúng 64 ký tự hex.",
    invalidSize: "Dung lượng ROM phải là số nguyên dương.", invalidWorkspace: "Ước lượng workspace phải là số nguyên dương.", jobRequired: "Hãy nhập Job ID.", payloadLarge: "Recipe vượt giới hạn 4096 byte. Hãy giảm MOD hoặc đường dẫn debloat.",
    sent: "Đã gửi yêu cầu sang bot Telegram.", telegramOnly: "Hãy mở trang này từ nút Mini App trong bot Telegram để gửi yêu cầu.", noMods: "Bộ nội dung này chưa có MOD sẵn sàng.",
    runnerAuto: "GitHub Auto", runnerHosted: "GitHub Hosted", runnerSelf: "Self-hosted Linux", taskMirrorShort: "Lưu ROM gốc", taskPublishShort: "Phát hành", taskBuildShort: "Build", custom: "Custom"
  },
  en: {
    connected: "BOT CONNECTED", buildTitle: "Prepare a build flight", buildIntro: "Verify the ROM source, runner and delivery before dispatching the recipe.",
    routePolicy: "ROUTING", sourceTitle: "Source ROM", sourceHint: "Use a direct URL, Daniel Springer build page, or a private Drive reference.",
    taskBuild: "Full build", taskMirror: "Mirror source only", taskPublish: "Publish artifact", sourceUrl: "URL or Drive reference", sourceSecure: "Short-lived signed URLs are hidden from summaries and logs.",
    device: "Device", sourceSize: "ROM size (bytes)", checksum: "Optional SHA-256", recipeTitle: "ROM configuration",
    recipeHint: "Presets provide defaults; every MOD and pipeline stage remains selectable.", runner: "Runner", edition: "Edition", modPack: "MOD pack",
    mods: "Applied MODs", defaults: "Defaults", selectAll: "Select all", clear: "Clear", advanced: "Advanced pipeline settings",
    debloatPaths: "Paths to remove (one per line)", workspaceEstimate: "Estimated workspace bytes (blank = automatic)",
    deliveryTitle: "Package and publish", deliveryHint: "Successful artifacts are checksum-verified before publishing.", packageZip: "Create flashable ZIP",
    packageHint: "Package the ROM after repacking", publish: "Upload to Drive", publishHint: "Create an artifact download link on success", notify: "Telegram notification",
    notifyHint: "Receive status and the link in chat", readyLabel: "RECIPE READY", fallbackWarning: "Auto selects a suitable runner and uses expanded GitHub Hosted storage when self-hosted is offline.",
    launch: "Create build job", jobsTitle: "Job control", jobsIntro: "Requests are authenticated with the Telegram account that opened this Mini App.", myJobs: "Open my jobs in chat",
    refreshJob: "Refresh", events: "Events", artifact: "Artifact", resume: "Resume", cancel: "Cancel job", cloudTitle: "Cloud library",
    cloudIntro: "Sources, checkpoints and artifacts stay private; only published artifacts receive a share link.", browseCloud: "Browse library",
    browseCloudHint: "Open source and artifact lists in chat", mirrorRom: "Mirror source ROM", mirrorHint: "Choose “Mirror source only” on the Build screen",
    systemTitle: "System status", systemIntro: "Check the bot, Drive, runners and content packs before a large build.", runDiagnostics: "Run diagnostics",
    authenticated: "Current session authenticated", runnerChecked: "Runner availability checked on submit", driveChecked: "Access verified before upload",
    navBuild: "Build", navJobs: "Jobs", navCloud: "Cloud", navSystem: "System", selected: "selected", catalogReady: "{mods} MODs · {versions} content packs ready",
    catalogFailed: "Catalog could not be loaded. Reopen the Mini App and try again.", invalidUrl: "Enter a valid HTTP/HTTPS URL or rclone reference.", invalidSha: "SHA-256 must contain exactly 64 hexadecimal characters.",
    invalidSize: "ROM size must be a positive integer.", invalidWorkspace: "Workspace estimate must be a positive integer.", jobRequired: "Enter a Job ID.", payloadLarge: "Recipe exceeds Telegram's 4096-byte limit. Reduce MODs or debloat paths.",
    sent: "Request sent to the Telegram bot.", telegramOnly: "Open this page from the Mini App button in Telegram to send requests.", noMods: "No ready MODs are available in this content pack.",
    runnerAuto: "GitHub Auto", runnerHosted: "GitHub Hosted", runnerSelf: "Self-hosted Linux", taskMirrorShort: "Mirror", taskPublishShort: "Publish", taskBuildShort: "Build", custom: "Custom"
  }
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const state = { language: localStorage.getItem("wukong-language") || "vi", catalog: null, toastTimer: null };

function t(key, values = {}) {
  let value = translations[state.language][key] || translations.vi[key] || key;
  for (const [name, replacement] of Object.entries(values)) value = value.replace(`{${name}}`, replacement);
  return value;
}

function applyLanguage() {
  document.documentElement.lang = state.language;
  $$('[data-i18n]').forEach((node) => { node.textContent = t(node.dataset.i18n); });
  $("#language").textContent = state.language === "vi" ? "VI / EN" : "EN / VI";
  renderMods(false);
  updateSummary();
}

function toast(message, error = false) {
  const node = $("#toast");
  node.textContent = message;
  node.classList.toggle("error", error);
  node.classList.add("visible");
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => node.classList.remove("visible"), 3600);
  if (TelegramApp?.HapticFeedback) TelegramApp.HapticFeedback.notificationOccurred(error ? "error" : "success");
}

function send(action, extra = {}) {
  const data = JSON.stringify({ version: 1, action, ...extra });
  if (new TextEncoder().encode(data).length > 4096) throw new Error(t("payloadLarge"));
  if (!TelegramApp?.sendData || !TelegramApp.initData) throw new Error(t("telegramOnly"));
  TelegramApp.sendData(data);
  toast(t("sent"));
}

function navigate(name) {
  $$(".view").forEach((node) => node.classList.toggle("active", node.id === name));
  $$(".bottom-nav [data-nav]").forEach((node) => node.classList.toggle("active", node.dataset.nav === name));
  history.replaceState(null, "", `#${name}`);
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function options(select, entries, preferred) {
  select.replaceChildren(...entries.map(({ value, label }) => {
    const option = document.createElement("option");
    option.value = value; option.textContent = label; return option;
  }));
  if (preferred && entries.some((entry) => entry.value === preferred)) select.value = preferred;
}

function selectedMods() {
  return $$("#mod-list input:checked").map((input) => input.value);
}

function defaultMods() {
  const version = $("#mod-version").value;
  const preset = $("#preset").value;
  return state.catalog?.presetDefaultsByVersion?.[version]?.[preset] || [];
}

function renderMods(reset = true) {
  const list = $("#mod-list");
  if (!list || !state.catalog) return;
  const current = new Set(reset ? defaultMods() : selectedMods());
  const names = state.catalog.modsByVersion[$("#mod-version").value] || [];
  list.replaceChildren();
  if (!names.length) {
    const empty = document.createElement("div"); empty.className = "mod-empty"; empty.textContent = t("noMods"); list.append(empty);
  }
  names.forEach((name) => {
    const label = document.createElement("label");
    const input = document.createElement("input"); input.type = "checkbox"; input.value = name; input.checked = current.has(name);
    const span = document.createElement("span"); span.textContent = name; span.title = name;
    label.append(input, span); list.append(label);
  });
  updateSummary();
}

function renderPipelineSteps() {
  const container = $("#steps");
  container.replaceChildren(...(state.catalog?.pipelineSteps || []).map((step) => {
    const label = document.createElement("label");
    const input = document.createElement("input"); input.type = "checkbox"; input.value = step.id; input.checked = Boolean(step.default);
    const span = document.createElement("span"); span.textContent = step.label;
    label.append(input, span); return label;
  }));
}

function setMods(mode) {
  const defaults = new Set(defaultMods());
  $$("#mod-list input").forEach((input) => { input.checked = mode === "all" || (mode === "defaults" && defaults.has(input.value)); });
  updateSummary();
}

function runnerLabel(value) {
  return t(value === "github-hosted" ? "runnerHosted" : value === "self-hosted-linux" ? "runnerSelf" : "runnerAuto");
}

function updateSummary() {
  const task = $('input[name="task"]:checked')?.value || "build";
  const device = $("#device")?.value || "—";
  const preset = $("#preset")?.value || "plus";
  const runner = runnerLabel($("#execution")?.value || "github-auto");
  $("#route-label").textContent = runner;
  const simpleTask = task === "source_mirror" ? t("taskMirrorShort") : t("taskPublishShort");
  $("#launch-summary").textContent = task !== "build" ? `${device} · ${simpleTask} · ${runner}` : `${device} · ${preset === "custom" ? t("custom") : preset[0].toUpperCase() + preset.slice(1)} · ${runner}`;
  $("#mod-count").textContent = `${selectedMods().length} ${t("selected")}`;
  $("#build-options").hidden = task !== "build";
  $("#package").disabled = task !== "build";
}

function positiveInteger(input, errorKey) {
  const raw = input.value.trim();
  if (!raw) return undefined;
  if (!/^\d+$/.test(raw) || Number(raw) <= 0 || !Number.isSafeInteger(Number(raw))) throw new Error(t(errorKey));
  return Number(raw);
}

function sourceSpec() {
  const uri = $("#source-uri").value.trim();
  const url = /^https?:\/\//i.test(uri);
  const remote = /^[A-Za-z0-9][A-Za-z0-9_.-]*:(?!\/\/).+/.test(uri) && !uri.split(":", 1)[0].includes("\\");
  if (!url && !remote) throw new Error(t("invalidUrl"));
  const sha = $("#source-sha").value.trim().toLowerCase();
  if (sha && !/^[a-f0-9]{64}$/.test(sha)) throw new Error(t("invalidSha"));
  const source = { kind: url ? (uri.toLowerCase().startsWith("https://") ? "https" : "http") : "rclone", uri };
  const size = positiveInteger($("#source-size"), "invalidSize");
  if (sha) source.sha256 = sha;
  if (size) source.sizeBytes = size;
  return source;
}

function buildRecipe() {
  const task = $('input[name="task"]:checked').value;
  const recipe = {
    schemaVersion: 1, task, device: $("#device").value, source: sourceSpec(),
    execution: { target: $("#execution").value },
    storage: { remote: "wukong-gdrive", publishArtifact: $("#publish").checked }
  };
  const workspace = positiveInteger($("#workspace-estimate"), "invalidWorkspace");
  if (workspace) recipe.execution.estimatedWorkspaceBytes = workspace;
  if (task === "build") {
    recipe.build = {
      preset: $("#preset").value, modVersion: $("#mod-version").value, mods: selectedMods(),
      enabledSteps: $$("#steps input:checked").map((input) => input.value),
      package: $("#package").checked, notifyTelegram: $("#notify").checked
    };
    const paths = $("#debloat-paths").value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
    if (paths.length) recipe.build.debloatPaths = paths;
  }
  return recipe;
}

async function loadCatalog() {
  try {
    const response = await fetch("./catalog.json", { cache: "no-cache" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const catalog = await response.json();
    if (catalog.schemaVersion !== 1 || !Array.isArray(catalog.devices) || !Array.isArray(catalog.modVersions)) throw new Error("Invalid catalog");
    state.catalog = catalog;
    options($("#device"), catalog.devices.map((item) => ({ value: item.product, label: `${item.product} — ${item.name}` })), "PKG110");
    options($("#mod-version"), catalog.modVersions.map((value) => ({ value, label: value })), catalog.modVersions.includes("ColorOS_16.0.9") ? "ColorOS_16.0.9" : catalog.modVersions.at(-1));
    const count = Object.values(catalog.modsByVersion).reduce((total, names) => total + names.length, 0);
    $("#catalog-status").textContent = t("catalogReady", { mods: count, versions: catalog.modVersions.length });
    $("#catalog-status").closest("div").querySelector("i").classList.add("ok");
    renderPipelineSteps();
    renderMods();
  } catch (error) {
    $("#catalog-status").textContent = t("catalogFailed");
    toast(t("catalogFailed"), true);
  }
}

function bindEvents() {
  $("#language").addEventListener("click", () => { state.language = state.language === "vi" ? "en" : "vi"; localStorage.setItem("wukong-language", state.language); applyLanguage(); });
  $$('[data-nav]').forEach((button) => button.addEventListener("click", () => navigate(button.dataset.nav)));
  $$('[data-action]').forEach((button) => button.addEventListener("click", () => { try { send(button.dataset.action); } catch (error) { toast(error.message, true); } }));
  $$('[data-job-action]').forEach((button) => button.addEventListener("click", () => {
    try { const jobId = $("#job-id").value.trim(); if (!jobId) throw new Error(t("jobRequired")); send(button.dataset.jobAction, { jobId }); } catch (error) { toast(error.message, true); }
  }));
  $("#recipe-form").addEventListener("submit", (event) => { event.preventDefault(); try { send("submit_recipe", { recipe: buildRecipe() }); } catch (error) { toast(error.message, true); } });
  $("#select-defaults").addEventListener("click", () => setMods("defaults"));
  $("#select-all").addEventListener("click", () => setMods("all"));
  $("#clear-mods").addEventListener("click", () => setMods("none"));
  $("#mod-version").addEventListener("change", () => renderMods());
  $("#preset").addEventListener("change", () => renderMods());
  $("#execution").addEventListener("change", updateSummary);
  $("#device").addEventListener("change", updateSummary);
  $("#mod-list").addEventListener("change", updateSummary);
  $$('input[name="task"]').forEach((input) => input.addEventListener("change", updateSummary));
}

if (TelegramApp) {
  TelegramApp.ready(); TelegramApp.expand();
  if (TelegramApp.isVersionAtLeast?.("7.7")) TelegramApp.disableVerticalSwipes?.();
  if (TelegramApp.isVersionAtLeast?.("6.1")) {
    TelegramApp.setHeaderColor?.("secondary_bg_color");
    TelegramApp.setBackgroundColor?.("secondary_bg_color");
  }
}

bindEvents();
applyLanguage();
navigate(location.hash.slice(1) || "build");
loadCatalog();
