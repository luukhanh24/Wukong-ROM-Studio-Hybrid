const TelegramApp = window.Telegram && window.Telegram.WebApp;
const sourceProbeEndpoint = document.querySelector('meta[name="wukong-source-probe-endpoint"]')?.content?.trim() || "";

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
    authenticated: "Đã xác thực phiên hiện tại", keyboardConnected: "Kết nối qua nút Telegram · danh tính được xác nhận khi gửi", runnerChecked: "Runner được kiểm tra khi submit", driveChecked: "Quyền truy cập được kiểm tra trước upload",
    navBuild: "Build", navJobs: "Jobs", navCloud: "Cloud", navSystem: "Hệ thống", selected: "đã chọn", catalogReady: "{mods} MOD · {versions} bộ nội dung sẵn sàng",
    catalogFailed: "Không tải được catalog. Hãy thử mở lại Mini App.", invalidUrl: "Nhập URL HTTP/HTTPS hoặc đường dẫn rclone hợp lệ.", invalidSha: "SHA-256 phải có đúng 64 ký tự hex.",
    invalidSize: "Dung lượng ROM phải là số nguyên dương.", invalidWorkspace: "Ước lượng workspace phải là số nguyên dương.", jobRequired: "Hãy nhập Job ID.", payloadLarge: "Recipe vượt giới hạn 4096 byte. Hãy giảm MOD hoặc đường dẫn debloat.",
    sent: "Đã gửi yêu cầu sang bot Telegram.", telegramOnly: "Hãy mở trang này từ nút Mini App trong bot Telegram để gửi yêu cầu.", noMods: "Bộ nội dung này chưa có MOD sẵn sàng.",
    runnerAuto: "GitHub Auto", runnerHosted: "GitHub Hosted", runnerSelf: "Self-hosted Linux", taskMirrorShort: "Lưu ROM gốc", taskPublishShort: "Phát hành", taskBuildShort: "Build", custom: "Custom",
    sourceIdleKicker: "SMART SOURCE", sourceIdleTitle: "Dán link để nhận diện", sourceIdleMessage: "Loại nguồn được nhận ra ngay; metadata sâu được bot kiểm tra mà không tải cả ROM.",
    sourceDetectedKicker: "ĐÃ NHẬN DIỆN", sourceInvalidKicker: "CHƯA HỢP LỆ", sourceInvalidTitle: "Không nhận ra nguồn ROM", sourceInvalidMessage: "Dùng URL HTTP/HTTPS hoặc đường dẫn rclone remote:path.",
    provider: "Nhà cung cấp", detectedType: "Loại nguồn", detectedDevice: "Thiết bị", detectedVersion: "Phiên bản", analyzeSource: "Phân tích ROM", editSourceManual: "Chỉnh thông tin thủ công",
    deepProbeHint: "Phân tích ngay tại đây để kiểm tra máy chủ, tên file và dung lượng mà không tải cả ROM.", probeAnalyzing: "Đang phân tích…", probeSuccess: "Nguồn ROM hoạt động và đã được nhận diện.", probeLimited: "Trình duyệt không được máy chủ ROM cho phép đọc metadata. Link vẫn được giữ nguyên và sẽ được kiểm tra đầy đủ ở bước preflight.", probeFailed: "Nguồn ROM không phản hồi hoặc đã hết hạn. Hãy dùng link mới hơn.", probeReadyKicker: "ROM KHẢ DỤNG", probeLimitedKicker: "CHỜ PREFLIGHT", probeFailedKicker: "KHÔNG KHẢ DỤNG", resolvedHost: "Máy chủ đích", fileName: "Tên file", chooseDevice: "Chọn đúng thiết bị sau khi nhận diện", deviceRequired: "Hãy chọn thiết bị trước khi tạo job.", incompleteLabel: "HỒ SƠ CHƯA ĐỦ", finishSource: "Hoàn tất cấu hình", completeSourceHint: "Dán nguồn ROM và chọn đúng thiết bị để tiếp tục.", chooseDeviceHint: "Nguồn đã hợp lệ. Hãy chọn thiết bị trong phần chỉnh thủ công bên dưới.", sourceDirect: "Tải trực tiếp", sourceResolver: "Link OTA chưa resolve", sourcePage: "Trang OTA", sourceDriveType: "Drive riêng tư", providerDirect: "Máy chủ HTTP", providerDrive: "Google Drive / rclone",
    runtimePipeline: "PIPELINE", runtimeWaiting: "Chờ recipe hợp lệ", runtimeReady: "Recipe sẵn sàng gửi", runtimeLastBuild: "BUILD GẦN NHẤT", runtimeJobs: "Xem trong Jobs", checklistSource: "Nguồn ROM", checklistSourcePending: "Chưa có URL hợp lệ", checklistSourceDone: "Đã nhận diện nguồn", checklistDevice: "Thiết bị đích", checklistDevicePending: "Cần chọn thủ công", checklistDeviceDone: "Đã chọn thiết bị", checklistRunner: "Tuyến thực thi", checklistRunnerDone: "Đã cấu hình runner", readinessProgress: "{done}/3 điều kiện", pipelinePending: "Chưa chạy", pipelineRunning: "Đang chạy", pipelineComplete: "Hoàn tất", pipelineFailed: "Lỗi", pipelineSkipped: "Bỏ qua", modGroupGoogle: "Google & ứng dụng", modGroupCamera: "Camera & hình ảnh", modGroupInterface: "Giao diện hệ thống", modGroupSecurity: "Bảo mật & quyền", modGroupCore: "Hệ thống & công cụ", modGroupOther: "Khác"
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
    authenticated: "Current session authenticated", keyboardConnected: "Connected through the Telegram button · identity is confirmed on send", runnerChecked: "Runner availability checked on submit", driveChecked: "Access verified before upload",
    navBuild: "Build", navJobs: "Jobs", navCloud: "Cloud", navSystem: "System", selected: "selected", catalogReady: "{mods} MODs · {versions} content packs ready",
    catalogFailed: "Catalog could not be loaded. Reopen the Mini App and try again.", invalidUrl: "Enter a valid HTTP/HTTPS URL or rclone reference.", invalidSha: "SHA-256 must contain exactly 64 hexadecimal characters.",
    invalidSize: "ROM size must be a positive integer.", invalidWorkspace: "Workspace estimate must be a positive integer.", jobRequired: "Enter a Job ID.", payloadLarge: "Recipe exceeds Telegram's 4096-byte limit. Reduce MODs or debloat paths.",
    sent: "Request sent to the Telegram bot.", telegramOnly: "Open this page from the Mini App button in Telegram to send requests.", noMods: "No ready MODs are available in this content pack.",
    runnerAuto: "GitHub Auto", runnerHosted: "GitHub Hosted", runnerSelf: "Self-hosted Linux", taskMirrorShort: "Mirror", taskPublishShort: "Publish", taskBuildShort: "Build", custom: "Custom",
    sourceIdleKicker: "SMART SOURCE", sourceIdleTitle: "Paste a link to identify it", sourceIdleMessage: "Source type is recognized immediately; the bot inspects deep metadata without downloading the entire ROM.",
    sourceDetectedKicker: "SOURCE RECOGNIZED", sourceInvalidKicker: "NOT VALID YET", sourceInvalidTitle: "ROM source not recognized", sourceInvalidMessage: "Use an HTTP/HTTPS URL or an rclone remote:path reference.",
    provider: "Provider", detectedType: "Source type", detectedDevice: "Device", detectedVersion: "Version", analyzeSource: "Analyze ROM", editSourceManual: "Edit source details manually",
    deepProbeHint: "Analyze here to check the host, filename and size without downloading the full ROM.", probeAnalyzing: "Analyzing…", probeSuccess: "The ROM source is reachable and has been identified.", probeLimited: "The ROM server does not allow browser metadata access. The link is preserved and will be fully checked during preflight.", probeFailed: "The ROM source did not respond or has expired. Use a newer link.", probeReadyKicker: "ROM AVAILABLE", probeLimitedKicker: "PREFLIGHT NEEDED", probeFailedKicker: "UNAVAILABLE", resolvedHost: "Resolved host", fileName: "Filename", chooseDevice: "Choose the correct device after detection", deviceRequired: "Choose a device before creating the job.", incompleteLabel: "DOCKET INCOMPLETE", finishSource: "Complete configuration", completeSourceHint: "Paste a ROM source and choose the correct device to continue.", chooseDeviceHint: "The source is valid. Choose a device in the manual details below.", sourceDirect: "Direct download", sourceResolver: "Unresolved OTA link", sourcePage: "OTA page", sourceDriveType: "Private Drive", providerDirect: "HTTP server", providerDrive: "Google Drive / rclone",
    runtimePipeline: "PIPELINE", runtimeWaiting: "Waiting for a valid recipe", runtimeReady: "Recipe ready to dispatch", runtimeLastBuild: "LAST BUILD", runtimeJobs: "Inspect in Jobs", checklistSource: "ROM source", checklistSourcePending: "Valid URL required", checklistSourceDone: "Source recognized", checklistDevice: "Target device", checklistDevicePending: "Manual selection required", checklistDeviceDone: "Device selected", checklistRunner: "Execution route", checklistRunnerDone: "Runner configured", readinessProgress: "{done}/3 checks", pipelinePending: "Not started", pipelineRunning: "Running", pipelineComplete: "Complete", pipelineFailed: "Failed", pipelineSkipped: "Skipped", modGroupGoogle: "Google & apps", modGroupCamera: "Camera & imaging", modGroupInterface: "System interface", modGroupSecurity: "Security & access", modGroupCore: "System & tools", modGroupOther: "Other"
  }
};

Object.assign(translations.vi, {
  navBuild: "Studio", navCloud: "Thư viện", navCatalog: "Catalog", buildTitle: "Lập hồ sơ build.",
  buildIntro: "Một recipe, một pipeline, cùng kết quả trên Windows và GitHub Actions.", routePolicy: "RUNNER",
  sourceHint: "URL trực tiếp, link OPlus chưa resolve, trang OTA Daniel Springer hoặc Drive riêng tư.", sourceUrl: "Dán link ROM", sourceSecure: "Chấp nhận link trực tiếp, OPlus chưa resolve, Daniel Springer và Drive. URL ký tạm thời không xuất hiện trong log.", taskMirror: "Lưu ROM gốc", taskPublish: "Phát hành file",
  recipeHint: "Preset là điểm bắt đầu; từng MOD và giai đoạn vẫn có thể chỉnh riêng.", runner: "Nơi chạy", modPack: "Nền MOD",
  deliveryTitle: "Đóng gói & phát hành", deliveryHint: "Kiểm SHA-256 trước khi công bố artifact.",
  packageZip: "ZIP flashable", packageHint: "Đóng gói sau repack", publish: "Upload Drive", publishHint: "Tạo link tải khi thành công",
  notify: "Báo qua Telegram", notifyHint: "Trạng thái và link trong chat", readyLabel: "HỒ SƠ SẴN SÀNG",
  fallbackWarning: "Auto kiểm tra runner trước khi gửi; không để job treo khi runner offline.",
  jobsTitle: "Điều khiển job.", jobsIntro: "Xem trạng thái, log, artifact, hủy hoặc tiếp tục từ checkpoint.", myJobs: "Danh sách của tôi",
  refreshJob: "Làm mới trạng thái", events: "Xem nhật ký", artifact: "Mở artifact", resume: "Tiếp tục checkpoint",
  stageKey: "Các trạng thái chuẩn", cloudTitle: "Thư viện ROM.", checkpoints: "Checkpoint & lịch sử", checkpointsHint: "Dùng Job ID để xem và resume",
  retention: "Source và artifact giữ đến khi admin xóa · checkpoint 7 ngày · log 30 ngày.",
  catalogTitle: "Catalog kỹ thuật.", catalogIntro: "Cùng danh mục thiết bị, content-pack và MOD mà Windows và Actions sử dụng.",
  searchCatalog: "Tìm thiết bị hoặc MOD", catalogPack: "Content-pack", devicesTitle: "Thiết bị", modsTitle: "MOD trong pack",
  systemTitle: "Hệ thống.", systemIntro: "Kiểm tra kết nối, content-pack và cache trước một job lớn.", maintenance: "Bảo trì & thiết đặt",
  inspectCache: "Xem stage cache", inspectCacheHint: "Dung lượng và lượt tái sử dụng", clearCache: "Xóa cache", adminOnly: "Chỉ admin",
  miniSettings: "Thiết đặt Mini App", defaultPreset: "Preset mặc định",
  secretBoundary: "Token GitHub, Telegram và rclone không hiển thị ở đây. Quản lý chúng trong Windows app hoặc GitHub Secrets.",
  catalogSummary: "{devices} thiết bị / {mods} MOD", noCatalogMatches: "Không có mục phù hợp. Hãy đổi từ khóa tìm kiếm.",
  searchMods: "Lọc MOD để chọn", jobActionHint: "Nhập ID để mở tác vụ; bot sẽ kiểm tra quyền và trạng thái.",
  stageQueued: "Chờ", stagePreflight: "Kiểm tra", stageDownloading: "Tải ROM", stageRunning: "Đang build", stageUploading: "Đang upload", stageTerminal: "Thành công / Lỗi",
  previewMode: "CHẾ ĐỘ XEM TRƯỚC", authenticatedPreview: "Chưa xác thực — mở từ nút Mini App trong bot"
});

Object.assign(translations.vi, {
  confirmSource: "Xác nhận nguồn",
  probeDeferred: "Đã nhận diện link. Máy chủ build sẽ xác minh khả dụng và metadata ở bước preflight trước khi tải ROM.",
  probeDeferredKicker: "SẴN SÀNG KIỂM TRA"
});

Object.assign(translations.en, {
  navBuild: "Studio", navCloud: "Library", navCatalog: "Catalog", buildTitle: "Compose a build docket.",
  buildIntro: "One recipe and one pipeline, with equivalent results on Windows and GitHub Actions.", routePolicy: "RUNNER",
  sourceHint: "Use a direct URL, unresolved OPlus link, Daniel Springer OTA page, or private Drive reference.", sourceUrl: "Paste a ROM link", sourceSecure: "Direct links, unresolved OPlus links, Daniel Springer and Drive are supported. Signed URLs never appear in logs.", taskMirror: "Mirror source", taskPublish: "Publish file",
  recipeHint: "A preset is the starting point; every MOD and stage remains editable.", runner: "Run on", modPack: "MOD base",
  deliveryTitle: "Package & publish", deliveryHint: "Verify SHA-256 before publishing an artifact.",
  packageZip: "Flashable ZIP", packageHint: "Package after repacking", publish: "Upload to Drive", publishHint: "Create a link after success",
  notify: "Telegram report", notifyHint: "Status and link in chat", readyLabel: "DOCKET READY",
  fallbackWarning: "Auto checks runner availability before dispatch so a job never waits on an offline runner.",
  jobsTitle: "Job control.", jobsIntro: "Inspect status, logs and artifacts, cancel work, or resume a checkpoint.", myJobs: "My job list",
  refreshJob: "Refresh status", events: "View event log", artifact: "Open artifact", resume: "Resume checkpoint",
  stageKey: "Canonical states", cloudTitle: "ROM library.", checkpoints: "Checkpoints & history", checkpointsHint: "Use a Job ID to inspect and resume",
  retention: "Sources and artifacts remain until admin deletion · checkpoints 7 days · logs 30 days.",
  catalogTitle: "Technical catalog.", catalogIntro: "The same device, content-pack and MOD catalog used by Windows and Actions.",
  searchCatalog: "Find a device or MOD", catalogPack: "Content pack", devicesTitle: "Devices", modsTitle: "MODs in pack",
  systemTitle: "System.", systemIntro: "Check connections, content packs and cache before a large job.", maintenance: "Maintenance & settings",
  inspectCache: "Inspect stage cache", inspectCacheHint: "Usage and reuse count", clearCache: "Clear cache", adminOnly: "Admin only",
  miniSettings: "Mini App settings", defaultPreset: "Default preset",
  secretBoundary: "GitHub, Telegram and rclone credentials are never shown here. Manage them in the Windows app or GitHub Secrets.",
  catalogSummary: "{devices} devices / {mods} MODs", noCatalogMatches: "No matching entries. Change the search term.",
  searchMods: "Filter selectable MODs", jobActionHint: "Enter an ID to reveal actions; the bot verifies ownership and state.",
  stageQueued: "Queued", stagePreflight: "Preflight", stageDownloading: "Downloading", stageRunning: "Running", stageUploading: "Uploading", stageTerminal: "Succeeded / Failed",
  previewMode: "PREVIEW MODE", authenticatedPreview: "Not authenticated — open from the bot's Mini App button"
});

Object.assign(translations.en, {
  confirmSource: "Confirm source",
  probeDeferred: "Link recognized. Build preflight will verify availability and metadata before downloading the ROM.",
  probeDeferredKicker: "READY FOR PREFLIGHT"
});

const pipelineLabels = {
  vi: {
    inspect_rom: "Kiểm tra ROM", extract_payload: "Tách payload", unpack_partitions: "Giải nén partition",
    debloat: "Gỡ ứng dụng thừa", apply_mod: "Áp dụng MOD", sync_configs: "Đồng bộ fs_config và SELinux",
    repack_partitions: "Đóng gói partition", repack_super: "Tạo super.img", patch_vbmeta: "Vá vbmeta",
    patch_vendor_boot: "Vá vendor_boot", package_zip: "Đóng gói ZIP", notify_telegram: "Báo Telegram"
  },
  en: {}
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const state = {
  language: localStorage.getItem("wukong-language") || "vi",
  catalog: null,
  toastTimer: null,
  defaultPreset: localStorage.getItem("wukong-default-preset") || "plus",
  sourceDetection: null,
  sourceAutoDevice: null,
  sourceProbe: null,
  delivery: { package: "pending", publish: "pending", notify: "pending" }
};

function t(key, values = {}) {
  let value = translations[state.language][key] || translations.vi[key] || key;
  for (const [name, replacement] of Object.entries(values)) value = value.replace(`{${name}}`, replacement);
  return value;
}

function applyLanguage() {
  document.documentElement.lang = state.language;
  $$('[data-i18n]').forEach((node) => { node.textContent = t(node.dataset.i18n); });
  $("#language").textContent = state.language === "vi" ? "VI / EN" : "EN / VI";
  const devicePlaceholder = $("#device option[value='']");
  if (devicePlaceholder) devicePlaceholder.textContent = t("chooseDevice");
  renderMods(false);
  renderPipelineSteps(false);
  renderCatalog();
  updateSummary();
  updateTelegramState();
  updateSourceDetection();
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
  if (!telegramTransportAvailable()) throw new Error(t("telegramOnly"));
  TelegramApp.sendData(data);
  toast(t("sent"));
}

function telegramTransportAvailable() {
  return typeof TelegramApp?.sendData === "function" && Boolean(TelegramApp.platform) && TelegramApp.platform !== "unknown";
}

function navigate(name, smooth = true) {
  if (!document.getElementById(name)) name = "build";
  $$(".view").forEach((node) => node.classList.toggle("active", node.id === name));
  $$(".bottom-nav [data-nav]").forEach((node) => node.classList.toggle("active", node.dataset.nav === name));
  $$(".contents-rail [data-nav]").forEach((node) => node.classList.toggle("active", node.dataset.nav === name));
  history.replaceState(null, "", `#${name}`);
  window.scrollTo({ top: 0, behavior: smooth ? "smooth" : "auto" });
}

function options(select, entries, preferred) {
  select.replaceChildren(...entries.map(({ value, label }) => {
    const option = document.createElement("option");
    option.value = value; option.textContent = label; return option;
  }));
  if (preferred && entries.some((entry) => entry.value === preferred)) select.value = preferred;
}

function classifySource(rawValue) {
  const value = rawValue.trim();
  if (!value) return null;
  if (/^[A-Za-z]:[\\/]/.test(value) || /^\\\\/.test(value)) return { valid: false };
  const rclone = /^([A-Za-z0-9][A-Za-z0-9_.-]*):(?!\/\/)(.+)$/.exec(value);
  if (rclone && !rclone[1].includes("\\")) {
    return { valid: true, kind: "rclone", provider: t("providerDrive"), type: t("sourceDriveType"), marker: "DRV" };
  }
  let url;
  try { url = new URL(value); } catch { return { valid: false }; }
  if (!/^https?:$/.test(url.protocol)) return { valid: false };
  const host = url.hostname.toLowerCase();
  const path = url.pathname.toLowerCase();
  let provider = t("providerDirect");
  let type = t("sourceDirect");
  let marker = "HTTP";
  if (host.includes("allawn") || host.includes("oppo") || host.includes("coloros") || path.endsWith("/downloadcheck")) {
    provider = "OPlus OTA"; type = path.endsWith("/downloadcheck") ? t("sourceResolver") : t("sourceDirect"); marker = "OTA";
  } else if (host === "roms.danielspringer.at") {
    provider = "Daniel Springer"; type = url.searchParams.has("build") ? t("sourcePage") : t("sourceDirect"); marker = "OTA";
  } else if (host.includes("drive.google.com")) {
    provider = "Google Drive"; type = t("sourceDriveType"); marker = "DRV";
  }
  let decoded = "";
  try { decoded = decodeURIComponent(url.pathname); } catch { decoded = url.pathname; }
  const device = state.catalog?.devices?.find((item) => decoded.toLowerCase().includes(String(item.product).toLowerCase()))?.product || "";
  const version = decoded.match(/(?:^|[_-])(\d{1,2}(?:\.\d+){1,3}(?:\([^)]*\))?)(?:[_./-]|$)/)?.[1] || "";
  return { valid: true, kind: url.protocol === "https:" ? "https" : "http", provider, type, marker, device, version };
}

function updateSourceDetection() {
  const node = $("#source-state");
  if (!node) return;
  const detection = classifySource($("#source-uri").value);
  if (state.sourceAutoDevice && $("#device").value === state.sourceAutoDevice) {
    $("#device").value = "";
    updateSummary();
  }
  state.sourceAutoDevice = null;
  state.sourceProbe = null;
  state.sourceDetection = detection;
  updateSummary();
  node.classList.toggle("detected", Boolean(detection?.valid));
  node.classList.toggle("invalid", Boolean(detection && !detection.valid));
  node.classList.remove("probing", "analyzed", "probe-deferred", "probe-limited", "probe-failed");
  const marker = node.querySelector(".source-state-mark span");
  const facts = $("#source-facts");
  const probe = $("#probe-source");
  probe.textContent = t(sourceProbeEndpoint ? "analyzeSource" : "confirmSource");
  if (!detection) {
    marker.textContent = "URL";
    $("#source-kicker").textContent = t("sourceIdleKicker");
    $("#source-state-title").textContent = t("sourceIdleTitle");
    $("#source-state-message").textContent = t("sourceIdleMessage");
    facts.hidden = true; probe.hidden = true; return;
  }
  if (!detection.valid) {
    marker.textContent = "?";
    $("#source-kicker").textContent = t("sourceInvalidKicker");
    $("#source-state-title").textContent = t("sourceInvalidTitle");
    $("#source-state-message").textContent = t("sourceInvalidMessage");
    facts.hidden = true; probe.hidden = true; return;
  }
  marker.textContent = detection.marker;
  $("#source-kicker").textContent = t("sourceDetectedKicker");
  $("#source-state-title").textContent = `${detection.provider} · ${detection.type}`;
  $("#source-state-message").textContent = t("deepProbeHint");
  $("#source-provider").textContent = detection.provider;
  $("#source-type").textContent = detection.type;
  $("#source-device-detected").textContent = detection.device || "—";
  $("#source-version-detected").textContent = detection.version || "—";
  $("#source-host").textContent = detection.kind === "rclone" ? "Google Drive" : new URL($("#source-uri").value.trim()).hostname;
  $("#source-filename").textContent = "—";
  facts.hidden = false;
  probe.hidden = detection.marker === "DRV";
  if (detection.device && [...$("#device").options].some((option) => option.value === detection.device)) {
    $("#device").value = detection.device;
    state.sourceAutoDevice = detection.device;
    updateSummary();
  }
  if (!$("#device").value) {
    $(".source-manual").open = true;
  }
}

function setProbePresentation(status, messageKey) {
  const node = $("#source-state");
  node.classList.remove("probing", "analyzed", "probe-deferred", "probe-limited", "probe-failed");
  node.classList.add(status);
  const kickerKey = status === "analyzed" ? "probeReadyKicker" : status === "probe-failed" ? "probeFailedKicker" : status === "probe-deferred" ? "probeDeferredKicker" : status === "probe-limited" ? "probeLimitedKicker" : "sourceDetectedKicker";
  $("#source-kicker").textContent = t(kickerKey);
  $("#source-state-message").textContent = t(messageKey);
}

async function probeSourceViaBackend(uri, signal) {
  if (!sourceProbeEndpoint) return null;
  const headers = { "Content-Type": "application/json" };
  if (TelegramApp?.initData) headers.Authorization = `tma ${TelegramApp.initData}`;
  const response = await fetch(sourceProbeEndpoint, {
    method: "POST",
    headers,
    body: JSON.stringify({ uri }),
    cache: "no-store",
    signal
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(payload.error || `HTTP ${response.status}`);
    error.sourceRejected = response.status >= 400 && response.status < 500;
    throw error;
  }
  return payload;
}

function applyProbeResult(result, uri) {
  const detected = state.sourceDetection;
  const url = new URL(uri);
  const rawFilename = url.pathname.split("/").filter(Boolean).at(-1) || "";
  const localFilename = /\.(?:zip|ozip|bin)$/i.test(rawFilename) ? decodeURIComponent(rawFilename) : "—";
  const filename = result?.filename || localFilename;
  const host = result?.host || url.hostname;
  const inferred = filename !== "—" ? classifySource(`https://${host}/${encodeURIComponent(filename)}`) : null;
  const device = result?.device || detected.device || inferred?.device || "";
  const version = result?.version || detected.version || inferred?.version || "";
  const size = Number(result?.sizeBytes || 0);
  $("#source-provider").textContent = result?.provider || detected.provider;
  $("#source-type").textContent = result?.type || detected.type;
  $("#source-host").textContent = host;
  $("#source-filename").textContent = filename;
  $("#source-device-detected").textContent = device || "—";
  $("#source-version-detected").textContent = version || "—";
  if (Number.isSafeInteger(size) && size > 0) $("#source-size").value = String(size);
  if (device && [...$("#device").options].some((option) => option.value === device)) {
    $("#device").value = device;
    state.sourceAutoDevice = device;
  }
  updateSummary();
}

async function probeSourceInPlace() {
  const button = $("#probe-source");
  const uri = $("#source-uri").value.trim();
  if (!state.sourceDetection?.valid || !/^https?:\/\//i.test(uri)) throw new Error(t("invalidUrl"));
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 12000);
  button.disabled = true;
  button.textContent = t("probeAnalyzing");
  setProbePresentation("probing", "probeAnalyzing");
  try {
    const result = await probeSourceViaBackend(uri, controller.signal);
    applyProbeResult(result, uri);
    state.sourceProbe = { status: result ? "analyzed" : "deferred" };
    setProbePresentation(result ? "analyzed" : "probe-deferred", result ? "probeSuccess" : "probeDeferred");
  } catch (error) {
    const unavailable = error?.sourceRejected || navigator.onLine === false;
    state.sourceProbe = { status: unavailable ? "failed" : "deferred" };
    setProbePresentation(unavailable ? "probe-failed" : "probe-deferred", unavailable ? "probeFailed" : "probeDeferred");
    if (unavailable) toast(t("probeFailed"), true);
  } finally {
    clearTimeout(timeout);
    button.disabled = false;
    button.textContent = t(sourceProbeEndpoint ? "analyzeSource" : "confirmSource");
  }
}

function selectedMods() {
  return $$("#mod-list input:checked").map((input) => input.value);
}

function defaultMods() {
  const version = $("#mod-version").value;
  const preset = $("#preset").value;
  return state.catalog?.presetDefaultsByVersion?.[version]?.[preset] || [];
}

function modCategory(name) {
  const value = name.toLocaleLowerCase();
  if (/gapps|google|play[_ -]?store|youtube|chrome|maps/.test(value)) return "google";
  if (/camera|cam|photo|gallery|image|video/.test(value)) return "camera";
  if (/security|secure|selinux|root|magisk|permission|safetynet|integrity/.test(value)) return "security";
  if (/system[_ -]?ui|launcher|theme|font|icon|wallpaper|aod|status|control[_ -]?center/.test(value)) return "interface";
  if (/wk|manager|framework|service|core|kernel|module|tools?/.test(value)) return "core";
  return "other";
}

function modCategoryLabel(category) {
  return t({
    google: "modGroupGoogle",
    camera: "modGroupCamera",
    interface: "modGroupInterface",
    security: "modGroupSecurity",
    core: "modGroupCore",
    other: "modGroupOther"
  }[category]);
}

function selectionMark() {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 16 16");
  svg.setAttribute("aria-hidden", "true");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", "M3.5 8.2 6.5 11l6-6.5");
  svg.append(path);
  return svg;
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
  const groups = new Map();
  names.forEach((name) => {
    const category = modCategory(name);
    if (!groups.has(category)) groups.set(category, []);
    groups.get(category).push(name);
  });
  ["google", "camera", "interface", "security", "core", "other"].forEach((category) => {
    const groupNames = groups.get(category);
    if (!groupNames?.length) return;
    const section = document.createElement("section"); section.className = "mod-group"; section.dataset.category = category;
    const header = document.createElement("header");
    const title = document.createElement("h3"); title.textContent = modCategoryLabel(category);
    const count = document.createElement("span"); count.textContent = String(groupNames.length);
    const items = document.createElement("div"); items.className = "mod-group-items";
    header.append(title, count); section.append(header, items);
    groupNames.forEach((name) => {
      const label = document.createElement("label");
      const input = document.createElement("input"); input.type = "checkbox"; input.value = name; input.checked = current.has(name);
      const span = document.createElement("span"); span.title = name;
      const text = document.createElement("b"); text.textContent = name;
      span.append(selectionMark(), text); label.append(input, span); items.append(label);
    });
    list.append(section);
  });
  updateSummary();
}

function renderPipelineSteps(reset = true) {
  const container = $("#steps");
  const current = new Set(reset ? [] : $$("#steps input:checked").map((input) => input.value));
  container.replaceChildren(...(state.catalog?.pipelineSteps || []).map((step) => {
    const label = document.createElement("label");
    const input = document.createElement("input"); input.type = "checkbox"; input.value = step.id; input.checked = reset ? Boolean(step.default) : current.has(step.id);
    const span = document.createElement("span"); span.textContent = pipelineLabels[state.language][step.id] || step.label;
    label.append(input, span); return label;
  }));
  updatePipelineCount();
}

function filterMods() {
  const query = ($("#mod-search")?.value || "").trim().toLocaleLowerCase();
  $$("#mod-list label").forEach((label) => {
    label.hidden = Boolean(query) && !label.textContent.toLocaleLowerCase().includes(query);
  });
  $$("#mod-list .mod-group").forEach((group) => {
    group.hidden = ![...group.querySelectorAll("label")].some((label) => !label.hidden);
  });
}

function updateTelegramState() {
  const authenticated = Boolean(TelegramApp?.initData);
  const keyboardConnected = telegramTransportAvailable();
  const connected = authenticated || keyboardConnected;
  const connection = $("#telegram-state");
  const connectionText = connection?.querySelector("span");
  if (connectionText) {
    connectionText.dataset.i18n = connected ? "connected" : "previewMode";
    connectionText.textContent = t(connected ? "connected" : "previewMode");
  }
  connection?.classList.toggle("preview", !connected);
  $("#telegram-health")?.classList.toggle("ok", connected);
  const authText = $("#telegram-auth-state");
  if (authText) {
    const stateKey = authenticated ? "authenticated" : keyboardConnected ? "keyboardConnected" : "authenticatedPreview";
    authText.dataset.i18n = stateKey;
    authText.textContent = t(stateKey);
  }
}

function updatePipelineCount() {
  const all = $$("#steps input");
  const selected = all.filter((input) => input.checked).length;
  if ($("#pipeline-count")) $("#pipeline-count").textContent = `${selected}/${all.length}`;
}

function renderCatalog() {
  if (!state.catalog || !$("#device-list")) return;
  const query = ($("#catalog-search")?.value || "").trim().toLocaleLowerCase();
  const version = $("#catalog-version")?.value || state.catalog.modVersions[0];
  const devices = state.catalog.devices.filter((item) => `${item.product} ${item.name}`.toLocaleLowerCase().includes(query));
  const mods = (state.catalog.modsByVersion[version] || []).filter((name) => name.toLocaleLowerCase().includes(query));
  $("#device-list").replaceChildren(...devices.map((item) => {
    const row = document.createElement("div"); row.className = "device-row";
    const code = document.createElement("b"); code.textContent = item.product;
    const name = document.createElement("span"); name.textContent = item.name;
    row.append(code, name); return row;
  }));
  $("#catalog-mod-list").replaceChildren(...mods.map((name) => {
    const item = document.createElement("span"); item.textContent = name; return item;
  }));
  if (!devices.length && !mods.length) {
    const empty = document.createElement("span"); empty.textContent = t("noCatalogMatches"); $("#catalog-mod-list").append(empty);
  }
  $("#device-count").textContent = String(devices.length);
  $("#catalog-mod-count").textContent = String(mods.length);
  const totalMods = Object.values(state.catalog.modsByVersion).reduce((total, names) => total + names.length, 0);
  $("#catalog-total").textContent = t("catalogSummary", { devices: state.catalog.devices.length, mods: totalMods });
}

function setMods(mode) {
  const defaults = new Set(defaultMods());
  $$("#mod-list input").forEach((input) => { input.checked = mode === "all" || (mode === "defaults" && defaults.has(input.value)); });
  updateSummary();
}

function runnerLabel(value) {
  return t(value === "github-hosted" ? "runnerHosted" : value === "self-hosted-linux" ? "runnerSelf" : "runnerAuto");
}

function updateDeliveryStates() {
  $$(".switches input").forEach((input) => {
    const status = input.checked ? state.delivery[input.id] || "pending" : "skipped";
    const label = input.closest("label");
    if (label) label.dataset.state = status;
    const stateText = input.closest("label")?.querySelector("em");
    const key = { pending: "pipelinePending", running: "pipelineRunning", complete: "pipelineComplete", failed: "pipelineFailed", skipped: "pipelineSkipped" }[status];
    if (stateText) stateText.textContent = t(key || "pipelinePending");
  });
}

function setDeliveryState(stage, status) {
  if (!Object.hasOwn(state.delivery, stage) || !["pending", "running", "complete", "failed"].includes(status)) return false;
  state.delivery[stage] = status;
  updateDeliveryStates();
  return true;
}

function updateChecklistItem(id, done, completeKey, pendingKey) {
  const item = document.getElementById(id);
  if (!item) return;
  item.classList.toggle("complete", done);
  const detail = item.querySelector("small");
  if (detail) detail.textContent = t(done ? completeKey : pendingKey);
}

function updateSummary() {
  const task = $('input[name="task"]:checked')?.value || "build";
  const selectedDevice = $("#device")?.value || "";
  const device = selectedDevice || "—";
  const preset = $("#preset")?.value || "plus";
  const runner = runnerLabel($("#execution")?.value || "github-auto");
  $("#route-label").textContent = runner;
  const simpleTask = task === "source_mirror" ? t("taskMirrorShort") : t("taskPublishShort");
  const summary = task !== "build" ? `${device} / ${simpleTask} / ${runner}` : `${device} / ${preset === "custom" ? t("custom") : preset.toUpperCase()} / ${runner}`;
  $("#launch-summary").textContent = summary;
  if ($("#mobile-launch-summary")) $("#mobile-launch-summary").textContent = summary;
  $("#mod-count").textContent = `${selectedMods().length} ${t("selected")}`;
  $("#build-options").hidden = task !== "build";
  $("#package").disabled = task !== "build";
  const sourceReady = Boolean(classifySource($("#source-uri")?.value || "")?.valid);
  const ready = sourceReady && Boolean(selectedDevice);
  const runnerReady = Boolean($("#execution")?.value);
  const completedChecks = [sourceReady, Boolean(selectedDevice), runnerReady].filter(Boolean).length;
  const docket = $(".dispatch-docket");
  docket?.classList.toggle("incomplete", !ready);
  const runtimeState = $("#runtime-pipeline-state");
  const runtimeDot = $("#runtime-pipeline-dot");
  if (runtimeState) runtimeState.textContent = t(ready ? "runtimeReady" : "runtimeWaiting");
  runtimeDot?.classList.toggle("waiting", !ready);
  runtimeDot?.classList.toggle("online", ready);
  if ($("#readiness-label")) $("#readiness-label").textContent = t(ready ? "readyLabel" : "incompleteLabel");
  if ($("#readiness-count")) $("#readiness-count").textContent = t("readinessProgress", { done: completedChecks });
  if ($("#launch-warning")) $("#launch-warning").textContent = t(ready ? "fallbackWarning" : sourceReady ? "chooseDeviceHint" : "completeSourceHint");
  updateChecklistItem("check-source", sourceReady, "checklistSourceDone", "checklistSourcePending");
  updateChecklistItem("check-device", Boolean(selectedDevice), "checklistDeviceDone", "checklistDevicePending");
  updateChecklistItem("check-runner", runnerReady, "checklistRunnerDone", "checklistRunnerDone");
  updateDeliveryStates();
  $$('[data-i18n="launch"], [data-i18n="finishSource"]').forEach((node) => {
    node.dataset.i18n = ready ? "launch" : "finishSource";
    node.textContent = t(ready ? "launch" : "finishSource");
  });
}

function positiveInteger(input, errorKey) {
  const raw = input.value.trim();
  if (!raw) return undefined;
  if (!/^\d+$/.test(raw) || Number(raw) <= 0 || !Number.isSafeInteger(Number(raw))) throw new Error(t(errorKey));
  return Number(raw);
}

function sourceSpec() {
  const uri = $("#source-uri").value.trim();
  const detection = classifySource(uri);
  if (!detection?.valid) throw new Error(t("invalidUrl"));
  const sha = $("#source-sha").value.trim().toLowerCase();
  if (sha && !/^[a-f0-9]{64}$/.test(sha)) throw new Error(t("invalidSha"));
  const source = { kind: detection.kind, uri };
  const size = positiveInteger($("#source-size"), "invalidSize");
  if (sha) source.sha256 = sha;
  if (size) source.sizeBytes = size;
  return source;
}

function buildRecipe() {
  const task = $('input[name="task"]:checked').value;
  if (!$("#device").value) throw new Error(t("deviceRequired"));
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
    if (!$("#debloat-paths").value.trim() && Array.isArray(catalog.defaultDebloatPaths)) {
      $("#debloat-paths").value = catalog.defaultDebloatPaths.join("\n");
    }
    options($("#device"), [{ value: "", label: t("chooseDevice") }, ...catalog.devices.map((item) => ({ value: item.product, label: `${item.product} — ${item.name}` }))]);
    options($("#mod-version"), catalog.modVersions.map((value) => ({ value, label: value })), catalog.modVersions.includes("ColorOS_16.0.9") ? "ColorOS_16.0.9" : catalog.modVersions.at(-1));
    options($("#catalog-version"), catalog.modVersions.map((value) => ({ value, label: value })), catalog.modVersions.includes("ColorOS_16.0.9") ? "ColorOS_16.0.9" : catalog.modVersions.at(-1));
    const count = Object.values(catalog.modsByVersion).reduce((total, names) => total + names.length, 0);
    $("#catalog-status").textContent = t("catalogReady", { mods: count, versions: catalog.modVersions.length });
    $("#catalog-status").closest("div").querySelector("i").classList.add("ok");
    renderPipelineSteps();
    renderMods();
    renderCatalog();
    updateSourceDetection();
  } catch (error) {
    $("#catalog-status").textContent = t("catalogFailed");
    toast(t("catalogFailed"), true);
  }
}

function bindEvents() {
  $("#language").addEventListener("click", () => { state.language = state.language === "vi" ? "en" : "vi"; localStorage.setItem("wukong-language", state.language); applyLanguage(); });
  $$('[data-nav]').forEach((button) => button.addEventListener("click", () => {
    if (button.dataset.task) {
      const task = $(`input[name="task"][value="${button.dataset.task}"]`);
      if (task) { task.checked = true; updateSummary(); }
    }
    navigate(button.dataset.nav);
  }));
  $$('[data-action]').forEach((button) => button.addEventListener("click", () => { try { send(button.dataset.action); } catch (error) { toast(error.message, true); } }));
  $$('[data-job-action]').forEach((button) => button.addEventListener("click", () => {
    try { const jobId = $("#job-id").value.trim(); if (!jobId) throw new Error(t("jobRequired")); send(button.dataset.jobAction, { jobId }); } catch (error) { toast(error.message, true); }
  }));
  $("#recipe-form").addEventListener("submit", (event) => { event.preventDefault(); try { send("submit_recipe", { recipe: buildRecipe() }); } catch (error) { toast(error.message, true); } });
  $("#source-uri").addEventListener("input", updateSourceDetection);
  $("#source-uri").addEventListener("paste", () => queueMicrotask(updateSourceDetection));
  $("#probe-source").addEventListener("click", () => {
    probeSourceInPlace().catch((error) => toast(error.message, true));
  });
  $("#select-defaults").addEventListener("click", () => setMods("defaults"));
  $("#select-all").addEventListener("click", () => setMods("all"));
  $("#clear-mods").addEventListener("click", () => setMods("none"));
  $("#mod-version").addEventListener("change", () => renderMods());
  $("#preset").addEventListener("change", () => renderMods());
  $("#execution").addEventListener("change", updateSummary);
  $("#device").addEventListener("change", updateSummary);
  $("#mod-list").addEventListener("change", updateSummary);
  $("#mod-search").addEventListener("input", filterMods);
  $("#steps").addEventListener("change", updatePipelineCount);
  $$(".switches input").forEach((input) => input.addEventListener("change", () => {
    state.delivery[input.id] = input.checked ? "pending" : "skipped";
    updateSummary();
  }));
  $("#catalog-search").addEventListener("input", renderCatalog);
  $("#catalog-version").addEventListener("change", renderCatalog);
  $("#default-preset").value = state.defaultPreset;
  $("#preset").value = state.defaultPreset;
  $("#default-preset").addEventListener("change", (event) => {
    state.defaultPreset = event.target.value;
    localStorage.setItem("wukong-default-preset", state.defaultPreset);
    $("#preset").value = state.defaultPreset;
    renderMods();
  });
  $("#job-id").addEventListener("input", (event) => {
    $("#state-actions").hidden = !event.target.value.trim();
  });
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
window.WukongMiniApp = Object.freeze({ setDeliveryState });
applyLanguage();
navigate(location.hash.slice(1) || "build", false);
loadCatalog();
