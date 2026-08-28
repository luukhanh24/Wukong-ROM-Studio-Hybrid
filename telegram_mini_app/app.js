let TelegramApp = window.Telegram && window.Telegram.WebApp;
const configuredMiniApiEndpoint = document.querySelector('meta[name="wukong-mini-api-endpoint"]')?.content?.trim() || "";
const miniApiEndpoint = configuredMiniApiEndpoint.startsWith("__") ? "" : configuredMiniApiEndpoint.replace(/\/$/, "");
const telegramBotUsername = (document.querySelector('meta[name="wukong-telegram-bot"]')?.content?.trim().replace(/^@/, "") || "");

function validSignedLaunchToken(token) {
  const value = String(token || "");
  const parts = value.split(".");
  return /^v1\.\d+\.\d+\.\d+\.[0-9a-f]{64}$/i.test(value)
    && Number(parts[3]) > Math.floor(Date.now() / 1000);
}

function consumeSignedLaunchToken() {
  let token = "";
  try {
    const url = new URL(location.href);
    const supplied = String(url.searchParams.get("wkLaunch") || "");
    if (/^v1\.\d+\.\d+\.\d+\.[0-9a-f]{64}$/i.test(supplied)) {
      token = supplied;
      sessionStorage.setItem("wukong-signed-launch", supplied);
      localStorage.setItem("wukong-signed-launch", supplied);
    } else {
      token = String(
        sessionStorage.getItem("wukong-signed-launch")
        || localStorage.getItem("wukong-signed-launch")
        || ""
      );
    }
    if (url.searchParams.has("wkLaunch")) {
      url.searchParams.delete("wkLaunch");
      history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
    }
  } catch (_) {}
  const valid = validSignedLaunchToken(token);
  if (!valid) try {
    sessionStorage.removeItem("wukong-signed-launch");
    localStorage.removeItem("wukong-signed-launch");
  } catch (_) {}
  return valid ? token : "";
}

let signedTelegramLaunchToken = consumeSignedLaunchToken();

function setSignedTelegramLaunchToken(token) {
  if (!validSignedLaunchToken(token)) return false;
  signedTelegramLaunchToken = String(token);
  try {
    sessionStorage.setItem("wukong-signed-launch", signedTelegramLaunchToken);
    localStorage.setItem("wukong-signed-launch", signedTelegramLaunchToken);
  } catch (_) {}
  return true;
}

function activeSignedLaunchToken() {
  if (validSignedLaunchToken(signedTelegramLaunchToken)) return signedTelegramLaunchToken;
  signedTelegramLaunchToken = "";
  try {
    sessionStorage.removeItem("wukong-signed-launch");
    localStorage.removeItem("wukong-signed-launch");
  } catch (_) {}
  return "";
}

function parseInitDataFromHash() {
  try {
    const raw = location.hash.startsWith("#") ? location.hash.slice(1) : location.hash;
    if (!raw) return "";
    const params = new URLSearchParams(raw);
    const encoded = params.get("tgWebAppData");
    if (!encoded) return "";
    // Telegram's tgWebAppData is a URL-encoded query string (query_id=...&user=...&hash=...)
    try { return decodeURIComponent(encoded); } catch (_) { return encoded; }
  } catch (_) { return ""; }
}

// Preserve Telegram's signed launch payload before the app replaces the
// initial URL fragment with the active view (for example #build). Some
// Telegram Android builds expose this fragment before WebApp.initData.
let cachedTelegramInitData = parseInitDataFromHash();

function effectiveInitData() {
  const direct = String(TelegramApp?.initData || "");
  if (direct) {
    cachedTelegramInitData = direct;
    return direct;
  }
  if (cachedTelegramInitData) return cachedTelegramInitData;
  cachedTelegramInitData = parseInitDataFromHash();
  return cachedTelegramInitData;
}
function effectiveInitDataUnsafe() {
  const direct = TelegramApp?.initDataUnsafe;
  if (direct && typeof direct === "object") return direct;
  // Fallback: parse hash ourselves so start_param still works even if bridge missed it
  try {
    const data = effectiveInitData();
    if (!data) return {};
    const usp = new URLSearchParams(data);
    const userRaw = usp.get("user");
    let user = null;
    try { user = userRaw ? JSON.parse(userRaw) : null; } catch (_) {}
    return {
      query_id: usp.get("query_id") || "",
      user,
      auth_date: usp.get("auth_date") || "",
      hash: usp.get("hash") || "",
      start_param: usp.get("start_param") || "",
    };
  } catch (_) { return {}; }
}

const translations = {
  vi: {
    connected: "BOT ĐÃ KẾT NỐI", buildTitle: "Wukong Studio", buildIntro: "Cấu hình, khởi chạy và theo dõi ROM ngay trong Mini App.",
    routePolicy: "ĐỊNH TUYẾN", sourceTitle: "ROM nguồn", sourceHint: "Dùng URL trực tiếp, link OPlus chưa resolve hoặc trang build Daniel Springer.",
    taskBuild: "Build đầy đủ", sourceUrl: "Dán link ROM", sourceSecure: "URL ký tạm thời được che khỏi bản tóm tắt và log.",
    device: "Thiết bị", sourceSize: "Dung lượng ROM (byte)", recipeTitle: "Cấu hình bản ROM",
    recipeHint: "Preset đặt mặc định; bạn vẫn có thể chọn chính xác từng MOD và bước pipeline.", runner: "Runner", edition: "Phiên bản", modPack: "Bộ MOD",
    mods: "MOD áp dụng", defaults: "Mặc định", selectAll: "Chọn tất cả", clear: "Bỏ chọn", advanced: "Thiết đặt pipeline nâng cao",
    debloatPaths: "Đường dẫn cần xóa (mỗi dòng một mục)", workspaceEstimate: "Ước lượng workspace (byte, để trống = tự động)",
    deliveryTitle: "Kết quả build", deliveryHint: "Đóng gói ZIP, tải lên Drive và gửi link qua Telegram.", packageZip: "Tạo ZIP flashable",
    packageHint: "Đóng gói ROM sau khi repack", publish: "Upload lên Drive", publishHint: "Tạo link tải artifact khi thành công", notify: "Thông báo Telegram",
    notifyHint: "Nhận trạng thái và link ngay trong chat", readyLabel: "RECIPE SẴN SÀNG", fallbackWarning: "Auto ưu tiên runner phù hợp và dùng GitHub Hosted mở rộng đĩa khi self-hosted offline.",
    launch: "Tạo job build", fabBuild: "Build", jobsTitle: "Tiến trình & lịch sử", jobsIntro: "Theo dõi từng giai đoạn, thông số MOD và link tải của mỗi job.", myJobs: "Mở danh sách trong chat",
    refreshJob: "Làm mới", events: "Nhật ký", artifact: "Artifact", resume: "Tiếp tục", cancel: "Hủy job",
    systemTitle: "Trạng thái dịch vụ", systemIntro: "Telegram, runner, Drive và content-pack trong một màn hình.", runDiagnostics: "Chạy chẩn đoán",
    authenticated: "Đã xác thực phiên hiện tại", keyboardConnected: "Kết nối qua nút Telegram · danh tính được xác nhận khi gửi", runnerChecked: "Runner được kiểm tra khi submit", driveChecked: "Quyền truy cập được kiểm tra trước upload",
    navBuild: "Build", navJobs: "Jobs", navCatalog: "Catalog", navSystem: "Hệ thống", selected: "đã chọn", catalogReady: "{mods} MOD · {versions} bộ nội dung sẵn sàng",
    catalogFailed: "Không tải được catalog. Hãy thử mở lại Mini App.", invalidUrl: "Nhập URL HTTP/HTTPS hoặc đường dẫn rclone hợp lệ.",
    invalidSize: "Dung lượng ROM phải là số nguyên dương.", invalidWorkspace: "Ước lượng workspace phải là số nguyên dương.", jobRequired: "Hãy nhập Job ID.", payloadLarge: "Recipe vượt giới hạn 4096 byte. Hãy giảm MOD hoặc đường dẫn debloat.", buildConcurrencyLimit: "Hệ thống đã đạt giới hạn build đồng thời. Hãy chờ một job hoàn tất rồi thử lại.",
    sent: "Đã gửi yêu cầu sang bot Telegram.", telegramOnly: "Phiên Telegram chưa được kết nối. Hãy bấm Kết nối Telegram để tiếp tục.", noMods: "Bộ nội dung này chưa có MOD sẵn sàng.",
    runnerAuto: "GitHub Auto", runnerHosted: "GitHub Hosted", runnerSelf: "Self-hosted Linux", taskBuildShort: "Build", custom: "Custom",
    sourceIdleKicker: "SMART SOURCE", sourceIdleTitle: "Dán link để nhận diện", sourceIdleMessage: "Loại nguồn được nhận ra ngay; metadata sâu được bot kiểm tra mà không tải cả ROM.",
    sourceDetectedKicker: "ĐÃ NHẬN DIỆN", sourceInvalidKicker: "CHƯA HỢP LỆ", sourceInvalidTitle: "Không nhận ra nguồn ROM", sourceInvalidMessage: "Dùng URL HTTP/HTTPS hoặc đường dẫn rclone remote:path.",
    provider: "Nhà cung cấp", detectedType: "Loại nguồn", detectedDevice: "Thiết bị", detectedVersion: "Phiên bản", analyzeSource: "Phân tích ROM", editSourceManual: "Chỉnh thông tin thủ công",
    deepProbeHint: "Phân tích ngay tại đây để kiểm tra máy chủ, tên file và dung lượng mà không tải cả ROM.", probeAnalyzing: "Đang phân tích…", probeSuccess: "Nguồn ROM hoạt động và đã được nhận diện.", probeLimited: "Trình duyệt không được máy chủ ROM cho phép đọc metadata. Link vẫn được giữ nguyên và sẽ được kiểm tra đầy đủ ở bước preflight.", probeFailed: "Nguồn ROM không phản hồi hoặc đã hết hạn. Hãy dùng link mới hơn.", probeReadyKicker: "ROM KHẢ DỤNG", probeLimitedKicker: "CHỜ PREFLIGHT", probeFailedKicker: "KHÔNG KHẢ DỤNG", resolvedHost: "Máy chủ đích", fileName: "Tên file", chooseDevice: "Chọn đúng thiết bị sau khi nhận diện", deviceRequired: "Hãy chọn thiết bị trước khi tạo job.", incompleteLabel: "HỒ SƠ CHƯA ĐỦ", finishSource: "Hoàn tất cấu hình", completeSourceHint: "Dán nguồn ROM và chọn đúng thiết bị để tiếp tục.", chooseDeviceHint: "Nguồn đã hợp lệ. Hãy chọn thiết bị trong phần chỉnh thủ công bên dưới.", sourceDirect: "Tải trực tiếp", sourceResolver: "Link OTA chưa resolve", sourcePage: "Trang OTA", sourceDriveType: "Drive riêng tư", providerDirect: "Máy chủ HTTP", providerDrive: "Google Drive / rclone",
    runtimePipeline: "PIPELINE", runtimeWaiting: "Chờ recipe hợp lệ", runtimeReady: "Recipe sẵn sàng gửi", runtimeLastBuild: "BUILD GẦN NHẤT", runtimeJobs: "Xem trong Jobs", checklistSource: "Nguồn ROM", checklistSourcePending: "Chưa có URL hợp lệ", checklistSourceDone: "Đã nhận diện nguồn", checklistDevice: "Thiết bị đích", checklistDevicePending: "Cần chọn thủ công", checklistDeviceDone: "Đã chọn thiết bị", checklistRunner: "Tuyến thực thi", checklistRunnerDone: "Đã cấu hình runner", readinessProgress: "{done}/3 điều kiện", pipelinePending: "Chưa chạy", pipelineRunning: "Đang chạy", pipelineComplete: "Hoàn tất", pipelineFailed: "Lỗi", pipelineSkipped: "Bỏ qua", modGroupGoogle: "Google & ứng dụng", modGroupCamera: "Camera & hình ảnh", modGroupInterface: "Giao diện hệ thống", modGroupSecurity: "Bảo mật & quyền", modGroupCore: "Hệ thống & công cụ", modGroupOther: "Khác"
  },
  en: {
    connected: "BOT CONNECTED", buildTitle: "Wukong Studio", buildIntro: "Configure, launch and monitor a ROM directly in the Mini App.",
    routePolicy: "ROUTING", sourceTitle: "Source ROM", sourceHint: "Use a direct URL, unresolved OPlus link, or Daniel Springer build page.",
    taskBuild: "Full build", sourceUrl: "Paste a ROM link", sourceSecure: "Short-lived signed URLs are hidden from summaries and logs.",
    device: "Device", sourceSize: "ROM size (bytes)", recipeTitle: "ROM configuration",
    recipeHint: "Presets provide defaults; every MOD and pipeline stage remains selectable.", runner: "Runner", edition: "Edition", modPack: "MOD pack",
    mods: "Applied MODs", defaults: "Defaults", selectAll: "Select all", clear: "Clear", advanced: "Advanced pipeline settings",
    debloatPaths: "Paths to remove (one per line)", workspaceEstimate: "Estimated workspace bytes (blank = automatic)",
    deliveryTitle: "Build result", deliveryHint: "Package the ZIP, upload it to Drive and send the link through Telegram.", packageZip: "Create flashable ZIP",
    packageHint: "Package the ROM after repacking", publish: "Upload to Drive", publishHint: "Create an artifact download link on success", notify: "Telegram notification",
    notifyHint: "Receive status and the link in chat", readyLabel: "RECIPE READY", fallbackWarning: "Auto selects a suitable runner and uses expanded GitHub Hosted storage when self-hosted is offline.",
    launch: "Create build job", fabBuild: "Build", jobsTitle: "Progress & history", jobsIntro: "Follow every stage, MOD detail and download link for each job.", myJobs: "Open my jobs in chat",
    refreshJob: "Refresh", events: "Events", artifact: "Artifact", resume: "Resume", cancel: "Cancel job",
    systemTitle: "Service status", systemIntro: "Telegram, runners, Drive and content packs in one place.", runDiagnostics: "Run diagnostics",
    authenticated: "Current session authenticated", keyboardConnected: "Connected through the Telegram button · identity is confirmed on send", runnerChecked: "Runner availability checked on submit", driveChecked: "Access verified before upload",
    navBuild: "Build", navJobs: "Jobs", navCatalog: "Catalog", navSystem: "System", selected: "selected", catalogReady: "{mods} MODs · {versions} content packs ready",
    catalogFailed: "Catalog could not be loaded. Reopen the Mini App and try again.", invalidUrl: "Enter a valid HTTP/HTTPS URL or rclone reference.",
    invalidSize: "ROM size must be a positive integer.", invalidWorkspace: "Workspace estimate must be a positive integer.", jobRequired: "Enter a Job ID.", payloadLarge: "Recipe exceeds Telegram's 4096-byte limit. Reduce MODs or debloat paths.", buildConcurrencyLimit: "The system has reached its concurrent build limit. Wait for one job to finish and try again.",
    sent: "Request sent to the Telegram bot.", telegramOnly: "The Telegram session is not connected. Press Connect Telegram to continue.", noMods: "No ready MODs are available in this content pack.",
    runnerAuto: "GitHub Auto", runnerHosted: "GitHub Hosted", runnerSelf: "Self-hosted Linux", taskBuildShort: "Build", custom: "Custom",
    sourceIdleKicker: "SMART SOURCE", sourceIdleTitle: "Paste a link to identify it", sourceIdleMessage: "Source type is recognized immediately; the bot inspects deep metadata without downloading the entire ROM.",
    sourceDetectedKicker: "SOURCE RECOGNIZED", sourceInvalidKicker: "NOT VALID YET", sourceInvalidTitle: "ROM source not recognized", sourceInvalidMessage: "Use an HTTP/HTTPS URL or an rclone remote:path reference.",
    provider: "Provider", detectedType: "Source type", detectedDevice: "Device", detectedVersion: "Version", analyzeSource: "Analyze ROM", editSourceManual: "Edit source details manually",
    deepProbeHint: "Analyze here to check the host, filename and size without downloading the full ROM.", probeAnalyzing: "Analyzing…", probeSuccess: "The ROM source is reachable and has been identified.", probeLimited: "The ROM server does not allow browser metadata access. The link is preserved and will be fully checked during preflight.", probeFailed: "The ROM source did not respond or has expired. Use a newer link.", probeReadyKicker: "ROM AVAILABLE", probeLimitedKicker: "PREFLIGHT NEEDED", probeFailedKicker: "UNAVAILABLE", resolvedHost: "Resolved host", fileName: "Filename", chooseDevice: "Choose the correct device after detection", deviceRequired: "Choose a device before creating the job.", incompleteLabel: "DOCKET INCOMPLETE", finishSource: "Complete configuration", completeSourceHint: "Paste a ROM source and choose the correct device to continue.", chooseDeviceHint: "The source is valid. Choose a device in the manual details below.", sourceDirect: "Direct download", sourceResolver: "Unresolved OTA link", sourcePage: "OTA page", sourceDriveType: "Private Drive", providerDirect: "HTTP server", providerDrive: "Google Drive / rclone",
    runtimePipeline: "PIPELINE", runtimeWaiting: "Waiting for a valid recipe", runtimeReady: "Recipe ready to dispatch", runtimeLastBuild: "LAST BUILD", runtimeJobs: "Inspect in Jobs", checklistSource: "ROM source", checklistSourcePending: "Valid URL required", checklistSourceDone: "Source recognized", checklistDevice: "Target device", checklistDevicePending: "Manual selection required", checklistDeviceDone: "Device selected", checklistRunner: "Execution route", checklistRunnerDone: "Runner configured", readinessProgress: "{done}/3 checks", pipelinePending: "Not started", pipelineRunning: "Running", pipelineComplete: "Complete", pipelineFailed: "Failed", pipelineSkipped: "Skipped", modGroupGoogle: "Google & apps", modGroupCamera: "Camera & imaging", modGroupInterface: "System interface", modGroupSecurity: "Security & access", modGroupCore: "System & tools", modGroupOther: "Other"
  }
};

Object.assign(translations.vi, {
  navBuild: "Studio", navCatalog: "Catalog", buildTitle: "Wukong Studio",
  buildIntro: "Cấu hình, khởi chạy và theo dõi ROM ngay trong Mini App.", routePolicy: "RUNNER",
  sourceHint: "URL trực tiếp hoặc link OPlus chưa resolve.", sourceUrl: "Dán link ROM", sourceSecure: "Chấp nhận link trực tiếp và OPlus chưa resolve. URL ký tạm thời không xuất hiện trong log.",
  recipeHint: "Preset là điểm bắt đầu; từng MOD và giai đoạn vẫn có thể chỉnh riêng.", runner: "Nơi chạy", modPack: "Nền MOD",
  deliveryTitle: "Kết quả build", deliveryHint: "Đóng gói ZIP, tải lên Drive và gửi link qua Telegram.",
  packageZip: "ZIP flashable", packageHint: "Đóng gói sau repack", publish: "Upload Drive", publishHint: "Tạo link tải khi thành công",
  notify: "Báo qua Telegram", notifyHint: "Trạng thái và link trong chat", readyLabel: "HỒ SƠ SẴN SÀNG",
  fallbackWarning: "Auto kiểm tra runner trước khi gửi; không để job treo khi runner offline.",
  jobsTitle: "Tiến trình & lịch sử", jobsIntro: "Theo dõi từng giai đoạn, thông số MOD và link tải của mỗi job.", myJobs: "Danh sách của tôi",
  refreshJob: "Làm mới trạng thái", events: "Xem nhật ký", artifact: "Mở artifact", resume: "Tiếp tục checkpoint",
  stageKey: "Các trạng thái chuẩn",
  catalogTitle: "Catalog kỹ thuật", catalogIntro: "Danh mục thiết bị, content-pack và MOD đang sẵn sàng cho mọi runner.", searchCatalog: "Tìm thiết bị hoặc MOD", catalogPack: "Content-pack", devicesTitle: "Thiết bị", modsTitle: "MOD trong pack", catalogSummary: "{devices} thiết bị / {mods} MOD", noCatalogMatches: "Không có mục phù hợp. Hãy đổi từ khóa tìm kiếm.",
  systemTitle: "Trạng thái dịch vụ", systemIntro: "Telegram, runner, Drive và content-pack trong một màn hình.", maintenance: "Bảo trì & thiết đặt",
  inspectCache: "Xem stage cache", inspectCacheHint: "Dung lượng và lượt tái sử dụng", clearCache: "Xóa cache", adminOnly: "Chỉ admin",
  miniSettings: "Thiết đặt Mini App", defaultPreset: "Preset mặc định",
  searchMods: "Lọc MOD để chọn", jobActionHint: "Nhập ID để mở tác vụ; bot sẽ kiểm tra quyền và trạng thái.",
  stageQueued: "Chờ", stagePreflight: "Kiểm tra", stageDownloading: "Tải ROM", stageRunning: "Đang build", stageUploading: "Đang upload", stageTerminal: "Thành công / Lỗi",
  previewMode: "CHẾ ĐỘ XEM TRƯỚC", authenticatedPreview: "Chưa xác thực — mở từ nút Mini App trong bot"
});

Object.assign(translations.vi, {
  buildTitle: "Wukong Studio", buildIntro: "Cấu hình, khởi chạy và theo dõi ROM ngay trong Mini App.",
  releaseVersion: "Phiên bản phát hành", releaseVersionHint: "Nhãn hiển thị cùng MOD pack trong mỗi job.", saveReleaseVersion: "Lưu nhãn", invalidReleaseVersion: "Nhãn dài 1–64 ký tự và không được có / hoặc \\.", releaseVersionSaved: "Đã lưu nhãn phát hành.", jobContext: "Ngữ cảnh job", uploadingNow: "Đang upload", uploadSummary: "Upload gần nhất", noModsSelected: "Không có MOD tùy chọn",
  probeDeferred: "Máy chủ đang bận phân tích ROM. Hãy thử lại sau ít phút.",
  probeDeferredKicker: "ĐANG CHỜ MÁY CHỦ"
});

Object.assign(translations.vi, {
  detectedProduct: "Product", productCode: "Mã sản phẩm", deviceName: "Tên thiết bị", detectedDevice: "Mã thiết bị", androidVersion: "Android", securityPatch: "Bản vá bảo mật", buildDate: "Ngày build", sourceSizeDetected: "Dung lượng ROM nguồn", otaType: "Kiểu OTA", contentType: "Định dạng", lastModified: "Cập nhật máy chủ", deepInspection: "Kiểm tra ZIP",
  metadataTitle: "ROM METADATA", metadataCompleteness: "{complete}/{total} thông số", copyMetadata: "Sao chép thông số", metadataCopied: "Đã sao chép toàn bộ thông số ROM.", pasteLink: "Dán", clearLink: "Xóa", linkPasted: "Đã dán link ROM và bắt đầu phân tích.", draftPasted: "Đã lấy link ROM bạn gửi cho bot và bắt đầu phân tích.", clipboardEmpty: "Clipboard không có văn bản và bot chưa có link nháp.", clipboardDenied: "Không đọc được clipboard. Hãy cấp quyền hoặc dán thủ công.", clipboardManual: "Telegram chặn clipboard. Hãy gửi link cho bot rồi quay lại bấm Dán, hoặc nhấn giữ ô để dán thủ công.", sourceCleared: "Đã xóa nguồn ROM.", deepInspected: "Đã đọc metadata trong ZIP", headersOnly: "Chỉ đọc được header máy chủ",
  apiUnavailableKicker: "API CHƯA KẾT NỐI", apiUnavailableMessage: "Bản Mini App này chưa được gắn máy chủ API. Không thể đọc metadata sâu hoặc tạo job cho đến khi quản trị viên triển khai API.", apiUnavailableButton: "Chưa có máy chủ API", apiSessionOnly: "TELEGRAM · CHƯA CÓ API",
  apiAuthKicker: "CẦN PHIÊN TELEGRAM", apiAuthMessage: "Lần mở này thiếu phiên Telegram. Bấm Kết nối Telegram để phục hồi an toàn.", apiAuthButton: "Kết nối Telegram", pairingHint: "Telegram không gửi phiên cho lần mở này. Kết nối một lần qua bot; nếu được hỏi, bấm START rồi quay lại Mini App.", pairingButton: "Kết nối Telegram", pairingOpening: "Đã mở bot. Hãy bấm START nếu Telegram yêu cầu rồi quay lại đây…", pairingWaiting: "Đang chờ bot xác nhận tài khoản…", pairingReady: "Đã kết nối Telegram. Mini App API sẵn sàng.", pairingFailed: "Không thể kết nối phiên Telegram. Hãy thử lại.", apiOfflineKicker: "MẤT KẾT NỐI API", apiOfflineMessage: "Không kết nối được máy chủ Mini App API. Link vẫn được giữ nguyên; hãy thử lại khi API hoạt động.",
  sessionDiagTitle: "Phiên Telegram", sessionDiagOk: "Thư viện Telegram đã nạp · nền {platform} · initData {chars} ký tự · phiên hợp lệ.", sessionDiagNoData: "Thư viện đã nạp nhưng initData trống. Quay lại tab Studio và bấm Kết nối Telegram để phục hồi phiên an toàn.", sessionDiagNoLib: "Không nạp được thư viện Telegram. Bấm Kết nối Telegram để dùng phiên dự phòng qua bot.", sessionDiagLaunchToken: "Bot đã cấp phiên dự phòng có chữ ký · Mini App API đã sẵn sàng.",
  probePartial: "Nguồn ROM hoạt động nhưng metadata chưa đủ. Hãy kiểm tra link hoặc dùng trang OTA có metadata đầy đủ.", probeStale: "Đã bỏ kết quả cũ vì URL nguồn đã thay đổi.", probeSignedExpired: "Link tải ký trực tiếp đã hết hạn hoặc không còn đủ thời gian cho build cloud. Hãy dán link OPlus downloadCheck hoặc trang Daniel Springer gốc để runner tự tạo link mới khi bắt đầu tải.", probeSignedPreviewOnly: "Link còn hiệu lực để phân tích nhưng không đủ thời gian cho build cloud. Hãy dán link OPlus downloadCheck hoặc trang Daniel Springer gốc để runner tự tạo link mới khi bắt đầu tải.",
  checklistApi: "Mini App API", checklistApiDone: "Đã xác thực với máy chủ", checklistApiPending: "Chưa kết nối máy chủ", checklistApiAuthPending: "Bấm Kết nối Telegram", checklistSourceVerified: "Đã đọc metadata ROM", checklistSourceProbePending: "Đang chờ phân tích metadata", checklistSourceRefreshRequired: "Cần link gốc để build cloud", readinessProgress: "{done}/4 điều kiện", apiRequiredHint: "Mini App API chưa sẵn sàng nên chưa thể tạo job.", sourceProbePendingHint: "Hãy chờ phân tích metadata ROM hoàn tất.",
  jobsLoading: "Đang đồng bộ lịch sử job…", jobsConnected: "Đã đồng bộ · tự làm mới khi job đang chạy", jobsOffline: "Mất kết nối API · sẽ tự thử lại", jobHistoryKicker: "LỊCH SỬ", jobHistory: "Các lần chạy gần đây",
  noJobsTitle: "Chưa có job", noJobsMessage: "Tạo một cấu hình build; job sẽ được lưu và theo dõi tại đây.", newBuild: "Tạo build đầu tiên", buildCreated: "Đã tạo job và bắt đầu theo dõi trong Mini App.",
  activeJob: "JOB ĐANG CHẠY", eventTimeline: "Nhật ký trực tiếp", eventsPreview: "{visible}/{total} sự kiện gần nhất", viewFullLog: "Xem toàn bộ nhật ký", hideFullLog: "Thu gọn nhật ký", fullLogTitle: "Toàn bộ nhật ký build", eventRunning: "Đang thực hiện", eventSucceeded: "Đã hoàn tất", eventFailed: "Thất bại", eventSteps: "bước", eventDetails: "Thông số chi tiết", finishBuild: "Hoàn tất cấu hình build", artifactsReady: "Artifact & link tải", noEvents: "Chưa có sự kiện mới.", noArtifacts: "Artifact sẽ xuất hiện sau khi build và upload hoàn tất.",
  retryJob: "Chạy lại", openActionsLog: "Mở log GitHub Actions", elapsed: "Thời gian", createdAt: "Khởi tạo", modConfiguration: "Cấu hình", autoSelected: "Đã tự chọn thiết bị {device} từ metadata ROM.", apiRequired: "Mini App API chưa được cấu hình. Hãy liên hệ quản trị viên.", requestFailed: "Không thể kết nối Mini App API.",
  openArtifactCloud: "Mở trên {provider}", copyArtifactLink: "Sao chép link tải", artifactLinkCopied: "Đã sao chép link tải.", artifactLinkUnavailable: "Link cloud chưa sẵn sàng."
});

Object.assign(translations.en, {
  navBuild: "Studio", navCatalog: "Catalog", buildTitle: "Wukong Studio",
  buildIntro: "Configure, launch and monitor a ROM directly in the Mini App.", routePolicy: "RUNNER",
  sourceHint: "Use a direct URL or unresolved OPlus link.", sourceUrl: "Paste a ROM link", sourceSecure: "Direct and unresolved OPlus links are supported. Signed URLs never appear in logs.",
  recipeHint: "A preset is the starting point; every MOD and stage remains editable.", runner: "Run on", modPack: "MOD base",
  deliveryTitle: "Build result", deliveryHint: "Package the ZIP, upload it to Drive and send the link through Telegram.",
  packageZip: "Flashable ZIP", packageHint: "Package after repacking", publish: "Upload to Drive", publishHint: "Create a link after success",
  notify: "Telegram report", notifyHint: "Status and link in chat", readyLabel: "DOCKET READY",
  fallbackWarning: "Auto checks runner availability before dispatch so a job never waits on an offline runner.",
  jobsTitle: "Progress & history", jobsIntro: "Follow every stage, MOD detail and download link for each job.", myJobs: "My job list",
  refreshJob: "Refresh status", events: "View event log", artifact: "Open artifact", resume: "Resume checkpoint",
  stageKey: "Canonical states",
  catalogTitle: "Technical catalog", catalogIntro: "Devices, content packs and MODs currently ready across every runner.", searchCatalog: "Find a device or MOD", catalogPack: "Content pack", devicesTitle: "Devices", modsTitle: "MODs in pack", catalogSummary: "{devices} devices / {mods} MODs", noCatalogMatches: "No matching entries. Change the search term.",
  systemTitle: "Service status", systemIntro: "Telegram, runners, Drive and content packs in one place.", maintenance: "Maintenance & settings",
  inspectCache: "Inspect stage cache", inspectCacheHint: "Usage and reuse count", clearCache: "Clear cache", adminOnly: "Admin only",
  miniSettings: "Mini App settings", defaultPreset: "Default preset",
  searchMods: "Filter selectable MODs", jobActionHint: "Enter an ID to reveal actions; the bot verifies ownership and state.",
  stageQueued: "Queued", stagePreflight: "Preflight", stageDownloading: "Downloading", stageRunning: "Running", stageUploading: "Uploading", stageTerminal: "Succeeded / Failed",
  previewMode: "PREVIEW MODE", authenticatedPreview: "Not authenticated — open from the bot's Mini App button"
});

Object.assign(translations.vi, {
  buildAllowance: "LƯỢT BUILD", unlimited: "Không giới hạn", pending: "Chờ duyệt", approved: "Đã duyệt", revoked: "Đã thu hồi",
  quotaExhausted: "Đã hết lượt", quotaRequiredHint: "Tài khoản chưa được duyệt hoặc đã hết lượt build.",
  userLedgerKicker: "QUẢN TRỊ TRUY CẬP", userLedgerTitle: "Người dùng & lượt build", userLedgerHint: "Duyệt tài khoản, cấp lượt và xem lịch sử mà không xóa dấu vết.",
  addUser: "Thêm Telegram ID", addUserKicker: "HỒ SƠ MỚI", searchUsers: "Tìm người dùng", accessStatus: "Trạng thái", allUsers: "Tất cả",
  sortUsers: "Sắp xếp", lastAccess: "Truy cập gần nhất", firstAccess: "Truy cập đầu tiên", jobCount: "Số job", buildCredits: "Lượt còn lại",
  activity: "Hoạt động", allowance: "Hạn mức", displayName: "Tên hiển thị", cancelDialog: "Hủy", createPendingUser: "Tạo hồ sơ chờ duyệt", quotaFilter: "Hạn mức", quotaAvailable: "Còn lượt", activityFilter: "Hoạt động", openedMiniApp: "Đã mở Mini App", neverOpened: "Chưa từng mở", hasJobs: "Đã tạo job", subtractCredit: "Trừ lượt", jobHistory: "Lịch sử job",
  userCreated: "Đã tạo hồ sơ chờ duyệt.", userUpdated: "Đã cập nhật quyền người dùng.", noUsers: "Không có người dùng phù hợp.",
  openCount: "{count} lần mở", jobsCount: "{count} job", approveUser: "Duyệt + 1 lượt", revokeUser: "Thu hồi", addCredit: "+1 lượt", setCredit: "Đặt số lượt", toggleUnlimited: "Đổi unlimited", auditTitle: "Nhật ký thay đổi", loadMoreAudit: "Tải thêm nhật ký",
  accessChecking: "ĐANG XÁC THỰC TÀI KHOẢN", accessCheckingTitle: "Đang kiểm tra quyền truy cập", accessCheckingMessage: "Wukong đang đọc hồ sơ Telegram đã ký trước khi mở Studio.",
  accessPendingKicker: "YÊU CẦU ĐÃ ĐƯỢC GHI NHẬN", accessPendingTitle: "Chờ quản trị viên cấp quyền", accessPendingMessage: "Tài khoản của bạn đang ở hàng chờ duyệt. Bot sẽ tự thông báo khi quyền được cấp; bạn không cần gửi ID thủ công.",
  accessRevokedKicker: "QUYỀN TRUY CẬP ĐÃ THU HỒI", accessRevokedTitle: "Tài khoản chưa thể mở Studio", accessRevokedMessage: "Liên hệ quản trị viên nếu bạn cần khôi phục quyền truy cập.",
  accessConnectKicker: "CHƯA KẾT NỐI TELEGRAM", accessConnectTitle: "Kết nối tài khoản để tiếp tục", accessConnectMessage: "Mở Mini App từ bot hoặc kết nối Telegram để xác thực an toàn.",
  accountDetails: "Thông tin tài khoản", refreshAccess: "Kiểm tra lại quyền", runtimeAllowance: "LƯỢT BUILD · JOBS", allowanceSummary: "{remaining} còn lại · {used} đã dùng · {jobs} job",
  lastJob: "Job gần nhất", role: "Vai trò", lifetime: "Tổng lượt", lifetimeSummary: "{granted} đã cấp · {used} đã dùng", client: "Thiết bị khách", approvedAt: "Thời điểm duyệt", revokedAt: "Thời điểm thu hồi", accessActor: "Người thao tác", accessReason: "Lý do", totalUsers: "Tổng người dùng", approvedUsers: "Đã cấp quyền", pendingUsers: "Chờ cấp quyền", revokedUsers: "Đã thu hồi",
  backToUsers: "Người dùng & lượt build", adminActionKicker: "CẬP NHẬT QUYỀN", creditValue: "Số lượt build", actionReason: "Lý do", confirmAction: "Xác nhận", adminActionMessage: "Thay đổi này sẽ được lưu vào nhật ký truy cập của người dùng.", actionValueInvalid: "Nhập số lượt hợp lệ.", actionReasonRequired: "Hãy nhập lý do cho thay đổi này."
});
Object.assign(translations.en, {
  buildAllowance: "BUILD CREDIT", unlimited: "Unlimited", pending: "Pending", approved: "Approved", revoked: "Revoked",
  quotaExhausted: "No credits", quotaRequiredHint: "This account is pending, revoked, or has no build credits left.",
  userLedgerKicker: "ACCESS CONTROL", userLedgerTitle: "Users & build credits", userLedgerHint: "Approve accounts, allocate credits and retain a complete audit trail.",
  addUser: "Add Telegram ID", addUserKicker: "NEW PROFILE", searchUsers: "Find user", accessStatus: "Status", allUsers: "All",
  sortUsers: "Sort", lastAccess: "Last access", firstAccess: "First access", jobCount: "Jobs", buildCredits: "Credits",
  activity: "Activity", allowance: "Allowance", displayName: "Display name", cancelDialog: "Cancel", createPendingUser: "Create pending profile", quotaFilter: "Quota", quotaAvailable: "Credits available", activityFilter: "Activity", openedMiniApp: "Opened Mini App", neverOpened: "Never opened", hasJobs: "Has jobs", subtractCredit: "Subtract credit", jobHistory: "Job history",
  userCreated: "Pending profile created.", userUpdated: "User access updated.", noUsers: "No matching users.",
  openCount: "{count} opens", jobsCount: "{count} jobs", approveUser: "Approve + 1", revokeUser: "Revoke", addCredit: "+1 credit", setCredit: "Set credits", toggleUnlimited: "Toggle unlimited", auditTitle: "Audit history", loadMoreAudit: "Load more audit events",
  accessChecking: "AUTHENTICATING ACCOUNT", accessCheckingTitle: "Checking access", accessCheckingMessage: "Wukong is reading the signed Telegram profile before opening Studio.",
  accessPendingKicker: "REQUEST RECORDED", accessPendingTitle: "Waiting for administrator approval", accessPendingMessage: "Your account is in the approval queue. The bot will notify you automatically; you do not need to send your ID manually.",
  accessRevokedKicker: "ACCESS REVOKED", accessRevokedTitle: "Studio is not available for this account", accessRevokedMessage: "Contact an administrator if you need access restored.",
  accessConnectKicker: "TELEGRAM NOT CONNECTED", accessConnectTitle: "Connect your account to continue", accessConnectMessage: "Open the Mini App from the bot or connect Telegram for secure authentication.",
  accountDetails: "Account details", refreshAccess: "Check access again", runtimeAllowance: "BUILD ALLOWANCE · JOBS", allowanceSummary: "{remaining} left · {used} used · {jobs} jobs",
  lastJob: "Last job", role: "Role", lifetime: "Lifetime allowance", lifetimeSummary: "{granted} granted · {used} used", client: "Client", approvedAt: "Approved at", revokedAt: "Revoked at", accessActor: "Access actor", accessReason: "Access reason", totalUsers: "Total users", approvedUsers: "Approved", pendingUsers: "Pending approval", revokedUsers: "Revoked",
  backToUsers: "Users & build credits", adminActionKicker: "UPDATE ACCESS", creditValue: "Build credits", actionReason: "Reason", confirmAction: "Confirm", adminActionMessage: "This change will be retained in the user's access audit trail.", actionValueInvalid: "Enter a valid credit value.", actionReasonRequired: "Enter a reason for this change."
});

Object.assign(translations.vi, {
  openProfile: "Mở hồ sơ", profileKicker: "HỒ SƠ TELEGRAM", profileStatus: "Quyền truy cập",
  profileConfiguredAdmin: "Nguồn quản trị", configuredAdminYes: "Admin cấu hình", configuredAdminNo: "Tài khoản thông thường",
  unlimitedLabel: "Quyền không giới hạn", yes: "Có", no: "Không", lifetimeGrantedLabel: "Tổng lượt đã cấp", lifetimeUsedLabel: "Tổng lượt đã dùng", lastJobStatusLabel: "Trạng thái job gần nhất",
  languageLabel: "Ngôn ngữ", platformLabel: "Nền tảng", appVersionLabel: "Phiên bản ứng dụng", roleAdmin: "Quản trị viên", roleUser: "Người dùng", closeDialog: "Đóng",
  themeTitle: "Chủ đề hệ thống", themeSystem: "Theo hệ thống", themeLight: "Sáng", themeDark: "Tối",
  clearCacheConfirmTitle: "Xóa cache dùng chung?", clearCacheConfirmMessage: "Chỉ quản trị viên được phép thực hiện. Toàn bộ stage cache dùng chung sẽ bị xóa và các job sau có thể cần tải, xử lý lại dữ liệu.",
  confirmClearCache: "Xóa cache", cacheClearing: "Đang xóa cache…", cacheCleared: "Đã xóa {count} mục cache.",
  greetingMorning: "Chào buổi sáng, {name}", greetingAfternoon: "Buổi chiều hiệu quả nhé, {name}", greetingEvening: "Chào buổi tối, {name}",
  greetingWish: "Chúc bạn có một bản build thật mượt", greetingAllowance: "{remaining} lượt còn lại · {jobs} job",
  greetingUnlimited: "Không giới hạn lượt build · {jobs} job",
  profileIdentityGroup: "Danh tính", profileAccessGroup: "Quyền & lượt build", profileActivityGroup: "Hoạt động", profileClientGroup: "Thiết bị & phiên",
  profileMoreGroup: "Thông tin khác", profileBuilds: "Lượt build", profileJobs: "Jobs", profileAccess: "Truy cập"
});
Object.assign(translations.en, {
  openProfile: "Open profile", profileKicker: "TELEGRAM PROFILE", profileStatus: "Access status",
  profileConfiguredAdmin: "Admin source", configuredAdminYes: "Configured admin", configuredAdminNo: "Standard account",
  unlimitedLabel: "Unlimited access", yes: "Yes", no: "No", lifetimeGrantedLabel: "Lifetime granted", lifetimeUsedLabel: "Lifetime used", lastJobStatusLabel: "Last job status",
  languageLabel: "Language", platformLabel: "Platform", appVersionLabel: "App version", roleAdmin: "Administrator", roleUser: "User", closeDialog: "Close",
  themeTitle: "System theme", themeSystem: "Use system", themeLight: "Light", themeDark: "Dark",
  clearCacheConfirmTitle: "Clear shared cache?", clearCacheConfirmMessage: "Only administrators may perform this action. The shared stage cache will be removed, so later jobs may need to download and process data again.",
  confirmClearCache: "Clear cache", cacheClearing: "Clearing cache…", cacheCleared: "Cleared {count} cache entries.",
  greetingMorning: "Good morning, {name}", greetingAfternoon: "Have a focused afternoon, {name}", greetingEvening: "Good evening, {name}",
  greetingWish: "Wishing you a beautifully smooth build", greetingAllowance: "{remaining} credits left · {jobs} jobs",
  greetingUnlimited: "Unlimited build allowance · {jobs} jobs",
  profileIdentityGroup: "Identity", profileAccessGroup: "Access & builds", profileActivityGroup: "Activity", profileClientGroup: "Device & session",
  profileMoreGroup: "More details", profileBuilds: "Builds", profileJobs: "Jobs", profileAccess: "Access"
});

Object.assign(translations.vi, {
  allowanceUnlimitedSummary: "Không giới hạn lượt còn lại · {used} đã dùng · {jobs} job",
  releaseVersionHint: "Mặc định cố định theo MOD pack; thay đổi chỉ áp dụng cho job hiện tại.",
  saveReleaseVersion: "Áp dụng cho job",
  releaseVersionSaved: "Đã áp dụng nhãn phát hành cho job hiện tại.",
  debloatPathsHint: "Danh sách tùy chỉnh chỉ dùng cho job hiện tại và tự khôi phục sau khi gửi build.",
  editDebloatPaths: "Tùy chỉnh",
  debloatEditorHint: "Mỗi dòng là một đường dẫn tương đối",
  saveDebloatPaths: "Lưu cho job này",
  debloatDefaultState: "Đang dùng danh sách mặc định",
  debloatCustomState: "Tùy chỉnh cho job hiện tại",
  debloatPathCount: "{count} đường dẫn",
  debloatSaved: "Đã lưu đường dẫn cho job hiện tại.",
  debloatPaths: "Đường dẫn cần xóa",
  jobTabActive: "Đang chạy",
  jobTabSucceeded: "Hoàn tất",
  jobTabFailed: "Lỗi / hủy",
  noJobsInTab: "Không có job trong nhóm này.",
  historicalJob: "JOB LỊCH SỬ"
});
Object.assign(translations.en, {
  allowanceUnlimitedSummary: "Unlimited credits remaining · {used} used · {jobs} jobs",
  releaseVersionHint: "The MOD pack default stays fixed; an edit applies only to the current job.",
  saveReleaseVersion: "Apply to job",
  releaseVersionSaved: "Release label applied to the current job.",
  debloatPathsHint: "Custom paths apply only to the current job and reset after dispatch.",
  editDebloatPaths: "Customize",
  debloatEditorHint: "Enter one relative path per line",
  saveDebloatPaths: "Save for this job",
  debloatDefaultState: "Using the default path list",
  debloatCustomState: "Customized for the current job",
  debloatPathCount: "{count} paths",
  debloatSaved: "Paths saved for the current job.",
  debloatPaths: "Paths to remove",
  jobTabActive: "Active",
  jobTabSucceeded: "Completed",
  jobTabFailed: "Failed / cancelled",
  noJobsInTab: "No jobs in this group.",
  historicalJob: "HISTORICAL JOB"
});

Object.assign(translations.en, {
  buildTitle: "Wukong Studio", buildIntro: "Configure, launch and monitor a ROM directly in the Mini App.",
  releaseVersion: "Release version", releaseVersionHint: "This label follows the MOD pack into every job.", saveReleaseVersion: "Save label", invalidReleaseVersion: "The label must be 1–64 characters and cannot contain / or \\.", releaseVersionSaved: "Release label saved.", jobContext: "Job context", uploadingNow: "Uploading now", uploadSummary: "Latest upload", noModsSelected: "No optional MODs",
  probeDeferred: "The server is busy analyzing ROMs. Try again in a moment.",
  probeDeferredKicker: "WAITING FOR SERVER"
});

Object.assign(translations.en, {
  detectedProduct: "Product", productCode: "Product code", deviceName: "Device name", detectedDevice: "Device code", androidVersion: "Android", securityPatch: "Security patch", buildDate: "Build date", sourceSizeDetected: "Source ROM size", otaType: "OTA type", contentType: "Content type", lastModified: "Server modified", deepInspection: "ZIP inspection",
  metadataTitle: "ROM METADATA", metadataCompleteness: "{complete}/{total} fields", copyMetadata: "Copy metadata", metadataCopied: "All ROM metadata was copied.", pasteLink: "Paste", clearLink: "Clear", linkPasted: "ROM link pasted and analysis started.", draftPasted: "ROM link retrieved from the bot and analysis started.", clipboardEmpty: "The clipboard is empty and the bot has no saved link.", clipboardDenied: "Clipboard access failed. Allow access or paste manually.", clipboardManual: "Telegram blocked clipboard access. Send the link to the bot and press Paste again, or long-press the field to paste manually.", sourceCleared: "ROM source cleared.", deepInspected: "Metadata read from ZIP", headersOnly: "Server headers only",
  apiUnavailableKicker: "API NOT CONNECTED", apiUnavailableMessage: "This Mini App release is not bound to an API server. Deep metadata and job creation remain unavailable until the administrator deploys the API.", apiUnavailableButton: "API server unavailable", apiSessionOnly: "TELEGRAM · API OFFLINE",
  apiAuthKicker: "TELEGRAM SESSION REQUIRED", apiAuthMessage: "This launch is missing a Telegram session. Press Connect Telegram to recover securely.", apiAuthButton: "Connect Telegram", pairingHint: "Telegram did not provide a session. Connect once through the bot; press START if prompted, then return to the Mini App.", pairingButton: "Connect Telegram", pairingOpening: "The bot is open. Press START if prompted, then return here…", pairingWaiting: "Waiting for the bot to confirm your account…", pairingReady: "Telegram connected. The Mini App API is ready.", pairingFailed: "Could not connect the Telegram session. Please try again.", apiOfflineKicker: "API CONNECTION LOST", apiOfflineMessage: "The Mini App API could not be reached. The link is preserved; retry when the API is online.",
  sessionDiagTitle: "Telegram session", sessionDiagOk: "Telegram bridge loaded · platform {platform} · initData {chars} chars · session valid.", sessionDiagNoData: "The bridge loaded but initData is empty. Return to Studio and press Connect Telegram to recover securely.", sessionDiagNoLib: "The Telegram bridge did not load. Press Connect Telegram to use the bot pairing fallback.", sessionDiagLaunchToken: "The bot supplied a signed fallback session · Mini App API is ready.",
  probePartial: "The ROM source is reachable, but metadata is incomplete. Check the link or use an OTA page with complete metadata.", probeStale: "The old result was discarded because the source URL changed.", probeSignedExpired: "The direct signed download link expired or does not have enough time left for a cloud build. Paste the original OPlus downloadCheck or Daniel Springer page so a fresh link can be generated when the runner starts.", probeSignedPreviewOnly: "The link is still valid for analysis but does not have enough time left for a cloud build. Paste the original OPlus downloadCheck or Daniel Springer page so the runner can create a fresh link when downloading starts.",
  checklistApi: "Mini App API", checklistApiDone: "Authenticated with server", checklistApiPending: "API server not connected", checklistApiAuthPending: "Press Connect Telegram", checklistSourceVerified: "ROM metadata inspected", checklistSourceProbePending: "Waiting for metadata analysis", checklistSourceRefreshRequired: "Original link required for cloud build", readinessProgress: "{done}/4 checks", apiRequiredHint: "The Mini App API is not ready, so a job cannot be created.", sourceProbePendingHint: "Wait for ROM metadata analysis to finish.",
  jobsLoading: "Syncing job history…", jobsConnected: "Synced · active jobs refresh automatically", jobsOffline: "API connection lost · retrying automatically", jobHistoryKicker: "HISTORY", jobHistory: "Recent runs",
  noJobsTitle: "No jobs yet", noJobsMessage: "Create a build configuration; its progress and result will remain here.", newBuild: "Create first build", buildCreated: "Job created and now tracked inside the Mini App.",
  activeJob: "ACTIVE JOB", eventTimeline: "Live event log", eventsPreview: "Latest {visible}/{total} events", viewFullLog: "View full log", hideFullLog: "Collapse log", fullLogTitle: "Complete build log", eventRunning: "In progress", eventSucceeded: "Completed", eventFailed: "Failed", eventSteps: "steps", eventDetails: "Detailed data", finishBuild: "Complete build configuration", artifactsReady: "Artifacts & downloads", noEvents: "No new events yet.", noArtifacts: "Artifacts appear after the build and upload finish.",
  retryJob: "Retry", openActionsLog: "Open GitHub Actions log", elapsed: "Elapsed", createdAt: "Created", modConfiguration: "Configuration", autoSelected: "Device {device} was selected from ROM metadata.", apiRequired: "The Mini App API is not configured. Contact the administrator.", requestFailed: "Could not reach the Mini App API.",
  openArtifactCloud: "Open in {provider}", copyArtifactLink: "Copy download link", artifactLinkCopied: "Download link copied.", artifactLinkUnavailable: "The cloud link is not ready yet."
});

Object.assign(translations.vi, {
  userBuildingRom: "Đang build ROM", userSearchingRom: "Đang tìm ROM nguồn",
  userRomSearchCompleted: "Đã tìm thấy {count} bản ROM", userRomSearchFailed: "Tìm ROM nguồn thất bại",
  currentUserActivity: "Hoạt động hiện tại", noCurrentUserActivity: "Hiện không có tác vụ đang hoạt động.",
  activityDevice: "Thiết bị", activityProduct: "Mã sản phẩm", activityConfiguration: "Cấu hình",
  activityRelease: "Phiên bản phát hành", activityStage: "Tiến trình",
  romSearchStartedLog: "Bắt đầu tìm ROM nguồn", romSearchCompletedLog: "Hoàn tất tìm ROM nguồn",
  romSearchFailedLog: "Tìm ROM nguồn thất bại", romSearchFilters: "Bộ lọc tìm kiếm",
  romSearchResults: "Kết quả ROM", romSearchDuration: "Thời gian xử lý",
  backToUserJobs: "Lịch sử job của user", userJobDetail: "Chi tiết job của user",
  userJobLoading: "Đang đồng bộ job…", userJobSynced: "Đã đồng bộ · trang tự cập nhật tiến độ",
  maintenanceGateKicker: "BẢO TRÌ HỆ THỐNG",
  navCatalog: "Thư viện", catalogTitle: "Thư viện",
  libraryIntro: "Tìm ROM nguồn, tra cứu thiết bị và bộ MOD.",
  libraryRom: "ROM / OTA", libraryTechnical: "Thiết bị & MOD",
  romCatalogHint: "Chọn thiết bị và khu vực. Chọn bản ROM để phân tích trong Studio.",
  romDeviceChoose: "Chọn thiết bị", romDeviceSearch: "Tìm tên máy hoặc mã model",
  romDevicesLoading: "Đang tải danh sách thiết bị…", romDevicesError: "Chưa tải được danh sách thiết bị. Hãy bấm Tải lại danh sách.",
  romDevicesRetry: "Tải lại danh sách", romDevicesEmpty: "Không có thiết bị phù hợp.", romDevicesCount: "{count} thiết bị",
  romDeviceClear: "Bỏ chọn thiết bị",
  romVersionFilter: "Phiên bản", romChooseDeviceFirst: "Chọn thiết bị trước", romVersionsOrder: "Phiên bản mới nhất xếp trước",
  romCopyLink: "Copy link ROM", romLinkCopied: "Đã sao chép link ROM gốc.", romResolve: "Resolve", romResolving: "Đang resolve…",
  romResolveFailed: "Chưa resolve được link. Hãy thử lại hoặc chọn phiên bản khác.", romResolvedCopy: "Copy link đã resolve",
  romResolvedCopied: "Đã sao chép link tải trực tiếp.", romResolvedLabel: "Link tải đã resolve",
  romResolvedHint: "Link tải tạm thời; nếu hết hạn, bấm Resolve lại. Build vẫn dùng link ROM gốc.",
  romVersionsTruncated: "Chỉ hiển thị các phiên bản mới nhất trong giới hạn dữ liệu.",
  romAllRegions: "Tất cả khu vực", romLatestOnly: "Bản mới nhất mỗi khu vực", romAllVersions: "Toàn bộ phiên bản",
  romCatalogIdle: "Tìm ROM theo thiết bị của bạn",
  romCatalogIdleHint: "Chọn thiết bị OnePlus, OPPO hoặc Realme, sau đó chọn khu vực và phiên bản.",
  romCatalogCount: "{count} bản ROM", romCatalogRetry: "Không tải được kho ROM. Hãy thử tìm lại.",
  romFilterRequired: "Chọn thiết bị để tải các phiên bản ROM.",
  maintenanceGateTitle: "Studio đang tạm đóng",
  maintenanceGateStatus: "Các job đang chạy vẫn được xử lý an toàn.",
  maintenanceRefresh: "Kiểm tra lại",
  maintenanceMessage: "Thông báo cho người dùng",
  enableMaintenance: "Bật chế độ bảo trì",
  disableMaintenance: "Mở lại Mini App",
  maintenanceAdminHint: "Admin vẫn truy cập đầy đủ; người dùng chỉ thấy màn hình bảo trì.",
  maintenanceOpenStatus: "Studio đang mở cho người dùng.",
  maintenanceClosedStatus: "Người dùng đang bị chuyển tới màn hình bảo trì.",
  maintenanceEnabledToast: "Đã bật chế độ bảo trì.",
  maintenanceDisabledToast: "Mini App đã mở lại cho người dùng.",
  findRom: "Tìm ROM",
  romCatalogKicker: "KHO OTA CÔNG KHAI",
  romCatalogTitle: "Tìm ROM nguồn",
  romDeviceFilter: "Thiết bị / dòng máy",
  romModelFilter: "Mã model",
  romRegionFilter: "Khu vực",
  searchRom: "Tìm ROM",
  romCatalogNote: "Nguồn: Daniel Springer · Danh sách ROM không đồng nghĩa mọi thiết bị đều được Wukong hỗ trợ build.",
  romCatalogEmpty: "Không tìm thấy bản ROM phù hợp.",
  romCatalogLoading: "Đang tải các phiên bản ROM…",
  useRom: "Phân tích trong Studio",
  romSelected: "Đã đưa link OTA vào Studio và bắt đầu phân tích."
});
Object.assign(translations.en, {
  userBuildingRom: "Building ROM", userSearchingRom: "Searching for source ROM",
  userRomSearchCompleted: "Found {count} ROM releases", userRomSearchFailed: "Source ROM search failed",
  currentUserActivity: "Current activity", noCurrentUserActivity: "No task is currently active.",
  activityDevice: "Device", activityProduct: "Product code", activityConfiguration: "Configuration",
  activityRelease: "Release version", activityStage: "Progress",
  romSearchStartedLog: "Started source ROM search", romSearchCompletedLog: "Completed source ROM search",
  romSearchFailedLog: "Source ROM search failed", romSearchFilters: "Search filters",
  romSearchResults: "ROM results", romSearchDuration: "Processing time",
  backToUserJobs: "User job history", userJobDetail: "User job details",
  userJobLoading: "Syncing job…", userJobSynced: "Synced · progress updates automatically",
  maintenanceGateKicker: "SYSTEM MAINTENANCE",
  navCatalog: "Library", catalogTitle: "Library",
  libraryIntro: "Find a source ROM or explore supported devices and MOD packs.",
  libraryRom: "ROM / OTA", libraryTechnical: "Devices & MODs",
  romCatalogHint: "Choose a device and region, then select a release to analyze in Studio.",
  romDeviceChoose: "Choose a device", romDeviceSearch: "Search device name or model",
  romDevicesLoading: "Loading devices…", romDevicesError: "Could not load devices. Use Reload devices to retry.",
  romDevicesRetry: "Reload devices", romDevicesEmpty: "No matching devices.", romDevicesCount: "{count} devices",
  romDeviceClear: "Clear device selection",
  romVersionFilter: "Version", romChooseDeviceFirst: "Choose a device first", romVersionsOrder: "Newest versions first",
  romCopyLink: "Copy ROM link", romLinkCopied: "Original ROM link copied.", romResolve: "Resolve", romResolving: "Resolving…",
  romResolveFailed: "Could not resolve this link. Retry or choose another version.", romResolvedCopy: "Copy resolved link",
  romResolvedCopied: "Direct download link copied.", romResolvedLabel: "Resolved download link",
  romResolvedHint: "This temporary link can expire. Resolve again to refresh it; builds still use the original ROM link.",
  romVersionsTruncated: "Only the newest versions within the data limit are shown.",
  romAllRegions: "All regions", romLatestOnly: "Latest release per region", romAllVersions: "All versions",
  romCatalogIdle: "Find a ROM for your device",
  romCatalogIdleHint: "Choose a OnePlus, OPPO or Realme device, then select a region and version.",
  romCatalogCount: "{count} releases", romCatalogRetry: "Could not load the ROM library. Search again to retry.",
  romFilterRequired: "Choose a device to load its ROM versions.",
  maintenanceGateTitle: "Studio is temporarily closed",
  maintenanceGateStatus: "Running jobs continue safely in the background.",
  maintenanceRefresh: "Check again",
  maintenanceMessage: "Message shown to users",
  enableMaintenance: "Enable maintenance",
  disableMaintenance: "Reopen Mini App",
  maintenanceAdminHint: "The admin keeps full access; users only see the maintenance screen.",
  maintenanceOpenStatus: "Studio is open to users.",
  maintenanceClosedStatus: "Users are being redirected to the maintenance screen.",
  maintenanceEnabledToast: "Maintenance mode enabled.",
  maintenanceDisabledToast: "The Mini App is open to users again.",
  findRom: "Find ROM",
  romCatalogKicker: "PUBLIC OTA CATALOG",
  romCatalogTitle: "Find a source ROM",
  romDeviceFilter: "Device / family",
  romModelFilter: "Model code",
  romRegionFilter: "Region",
  searchRom: "Find ROM",
  romCatalogNote: "Source: Daniel Springer · A listed ROM does not mean Wukong supports building for that device.",
  romCatalogEmpty: "No matching ROM release was found.",
  romCatalogLoading: "Loading ROM versions…",
  useRom: "Analyze in Studio",
  romSelected: "The OTA link was added to Studio and analysis has started."
});

const pipelineLabels = {
  vi: {
    inspect_rom: "Kiểm tra ROM", extract_payload: "Tách payload", unpack_partitions: "Giải nén partition",
    debloat: "Gỡ ứng dụng thừa", apply_mod: "Áp dụng MOD", sync_configs: "Đồng bộ fs_config và SELinux",
    repack_partitions: "Đóng gói partition", repack_super: "Tạo super.img", patch_vbmeta: "Vá vbmeta",
    patch_vendor_boot: "Vá vendor_boot", package_zip: "Đóng gói ZIP", notify_telegram: "Báo Telegram"
  },
  en: {
    inspect_rom: "Inspect ROM", extract_payload: "Extract payload", unpack_partitions: "Unpack partitions",
    debloat: "Remove bloatware", apply_mod: "Apply MODs", sync_configs: "Sync fs_config and SELinux",
    repack_partitions: "Repack partitions", repack_super: "Build super.img", patch_vbmeta: "Patch vbmeta",
    patch_vendor_boot: "Patch vendor_boot", package_zip: "Package ZIP", notify_telegram: "Notify Telegram"
  }
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
Object.assign(translations.vi, {
  openUserJob: "Xem job", jobCreator: "Người tạo job", jobParameters: "Toàn bộ thông số job", loadMoreUserJobs: "Tải thêm job cũ",
  jobParametersHint: "Chỉ đọc · Cấu hình đã lưu và trạng thái thực tế. Thông tin xác thực và link ROM nguồn ký tạm thời được ẩn.",
  jobRecipeData: "Cấu hình yêu cầu", jobRuntimeData: "Trạng thái và kết quả", copyJobParameters: "Copy thông số",
  jobParametersCopied: "Đã sao chép thông số job.", jobUnavailable: "Không mở được job này. Hãy làm mới hoặc chọn job khác.",
  jobCreatedAt: "Tạo lúc", jobUpdatedAt: "Cập nhật lúc", loadMoreJobEvents: "Tải thêm nhật ký", viewJobUser: "Mở hồ sơ user"
});
Object.assign(translations.en, {
  openUserJob: "View job", jobCreator: "Created by", jobParameters: "All job parameters", loadMoreUserJobs: "Load older jobs",
  jobParametersHint: "Read-only · Saved configuration and actual state. Credentials and temporary signed source ROM links are hidden.",
  jobRecipeData: "Requested configuration", jobRuntimeData: "State and results", copyJobParameters: "Copy parameters",
  jobParametersCopied: "Job parameters copied.", jobUnavailable: "Could not open this job. Refresh or select another job.",
  jobCreatedAt: "Created", jobUpdatedAt: "Updated", loadMoreJobEvents: "Load more events", viewJobUser: "Open user profile"
});

const state = {
  language: localStorage.getItem("wukong-language") || "vi",
  theme: localStorage.getItem("wukong-theme") || "system",
  catalog: null,
  toastTimer: null,
  defaultPreset: localStorage.getItem("wukong-default-preset") || "plus",
  sourceDetection: null,
  sourceAutoDevice: null,
  sourceProbe: null,
  delivery: { package: "pending", publish: "pending", notify: "pending" },
  jobs: [],
  activeJobId: localStorage.getItem("wukong-active-job") || "",
  activeEvents: [],
  activeEventsJobId: "",
  jobsPollTimer: null,
  jobsLoading: false,
  jobsUnchangedPolls: 0,
  jobsSyncSignature: "",
  jobDetailRequestId: 0,
  expandedConfigJobId: "",
  jobEventsHasMore: false,
  jobHistoryFilter: "",
  sourceProbeTimer: null,
  sourceProbeUri: "",
  sourceInputUri: "",
  sourceProbeController: null,
  sourceProbeRequestId: 0,
  pairingPollTimer: null,
  pairingPollAttempt: 0,
  pairingInFlight: false,
  docketInView: true,
  releaseVersionOverrides: {},
  debloatPaths: [],
  debloatPathsCustomized: false,
  dispatchFabHideTimer: null,
  expandedLogJobId: "",
  liquidPosition: 0,
  liquidAnimationFrame: 0,
  liquidSuppressClick: false,
  greetingIndex: 0,
  greetingTimer: 0,
  mastheadFrame: 0,
  cacheClearPending: false,
  me: null,
  maintenance: { enabled: false, message: "", updatedAt: "", updatedBy: "" },
  maintenancePollTimer: null,
  maintenanceMessageDirty: false,
  romCatalogReleases: [],
  romCatalogStatus: "idle",
  romCatalogRequestId: 0,
  romDevices: [],
  romDevicesStatus: "idle",
  romResolved: null,
  romResolveController: null,
  romCatalogTruncated: false,
  miniSessionId: "",
  adminUsers: [],
  adminUsersTotal: 0,
  adminUserStatusCounts: { approved: 0, pending: 0, revoked: 0 },
  adminUsersOffset: 0,
  adminUsersLoading: false,
  activeBatchId: localStorage.getItem("wukong-active-batch") || "",
  batchPollTimer: null,
  adminUsersPollTimer: null,
  adminUserPollTimer: null,
  adminUserEventCursor: { createdAt: "1970-01-01T00:00:00.000Z", eventId: "" },
  selectedAdminUserId: "",
  adminUserReturnScrollY: 0,
  adminJobView: null,
  workspaceLoaded: false
};

function t(key, values = {}) {
  let value = translations[state.language][key] || translations.vi[key] || key;
  for (const [name, replacement] of Object.entries(values)) value = value.replace(`{${name}}`, replacement);
  return value;
}

function renderSelectedJob() {
  if (state.adminJobView) renderActiveJob(state.adminJobView.job, state.adminJobView.events, state.adminJobView);
  const activeJob = state.jobs.find((job) => (job.job_id || job.jobId) === state.activeJobId);
  if (!activeJob) return;
  const activeId = activeJob.job_id || activeJob.jobId;
  renderActiveJob(activeJob, state.activeEventsJobId === activeId ? state.activeEvents : []);
}

function applyLanguage() {
  document.documentElement.lang = state.language;
  $$('[data-i18n]').forEach((node) => { node.textContent = t(node.dataset.i18n); });
  $$("[data-i18n-aria]").forEach((node) => node.setAttribute("aria-label", t(node.dataset.i18nAria)));
  $("#language").textContent = state.language === "vi" ? "VI / EN" : "EN / VI";
  const devicePlaceholder = $("#device option[value='']");
  if (devicePlaceholder) devicePlaceholder.textContent = t("chooseDevice");
  renderMods(false);
  renderPipelineSteps(false);
  renderCatalog();
  renderJobHistory();
  renderSelectedJob();
  renderSessionDiagnostics();
  renderAccount();
  renderRomVersions();
  renderRomCatalogResults();
  renderRomDevices();
  renderAdminUsers();
  renderDebloatSummary();
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

const themeMedia = window.matchMedia?.("(prefers-color-scheme: dark)");
let telegramThemeEventsBoundTo = null;

function telegramColorScheme() {
  const scheme = String(TelegramApp?.colorScheme || "").toLowerCase();
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
  if (!TelegramApp || TelegramApp === telegramThemeEventsBoundTo) return;
  TelegramApp.onEvent?.("themeChanged", handleSystemThemeChange);
  telegramThemeEventsBoundTo = TelegramApp;
}

function applyTheme(theme = state.theme, persist = false) {
  state.theme = ["system", "light", "dark"].includes(theme) ? theme : "system";
  const resolved = resolvedTheme();
  document.documentElement.dataset.theme = state.theme;
  document.documentElement.dataset.colorScheme = resolved;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", resolved === "dark" ? "#17191d" : "#f3f1eb");
  $$("[data-theme-value]").forEach((button) => {
    const active = button.dataset.themeValue === state.theme;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  if (persist) localStorage.setItem("wukong-theme", state.theme);
  try {
    TelegramApp?.setHeaderColor?.(resolved === "dark" ? "#1d2025" : "#f8f7f2");
    TelegramApp?.setBackgroundColor?.(resolved === "dark" ? "#17191d" : "#f3f1eb");
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
    root.setProperty("--masthead-surface-mix", `${Math.round(3 + progress * 5)}%`);
    root.setProperty("--masthead-backdrop-blur", `${Math.round(3 + progress * 5)}px`);
    root.setProperty("--masthead-greeting-opacity", String(1 - progress * .18));
    root.setProperty("--masthead-greeting-offset", `${(-progress * 2).toFixed(2)}px`);
    document.body.classList.toggle("masthead-compact", progress > .82);
  });
}

function miniApiAvailable() {
  return Boolean(miniApiEndpoint && (effectiveInitData() || activeSignedLaunchToken()));
}

function privateApiAvailable() {
  return miniApiAvailable() && state.me?.accessStatus === "approved"
    && (!state.maintenance?.enabled || state.me?.role === "admin");
}

function getMiniSessionId() {
  if (state.miniSessionId) return state.miniSessionId;
  try {
    state.miniSessionId = sessionStorage.getItem("wukong-mini-session-id") || "";
    if (!state.miniSessionId) {
      state.miniSessionId = crypto.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
      sessionStorage.setItem("wukong-mini-session-id", state.miniSessionId);
    }
  } catch (_) { state.miniSessionId = `${Date.now()}-${Math.random().toString(16).slice(2)}`; }
  return state.miniSessionId;
}

function miniApiState() {
  if (!miniApiEndpoint) return "unconfigured";
  if (!effectiveInitData() && !activeSignedLaunchToken()) return "unauthenticated";
  return "ready";
}

function miniApiUnavailableMessageKey() {
  return miniApiState() === "unconfigured" ? "apiRequired" : "telegramOnly";
}

async function apiRequest(path, options = {}) {
  if (!miniApiEndpoint) throw new Error(t("apiRequired"));
  const initData = effectiveInitData();
  const launchToken = activeSignedLaunchToken();
  if (!initData && !launchToken) throw new Error(t("telegramOnly"));
  const headers = new Headers(options.headers || {});
  headers.set("Authorization", initData ? `tma ${initData}` : `wla ${launchToken}`);
  headers.set("X-Wukong-Session-Id", getMiniSessionId());
  headers.set("X-Wukong-Client-Version", "2026.08.25");
  headers.set("X-Telegram-Platform", String(TelegramApp?.platform || "web"));
  if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  let response;
  try {
    response = await fetch(`${miniApiEndpoint}${path}`, { ...options, headers, cache: "no-store" });
  } catch (cause) {
    if (cause?.name === "AbortError") throw cause;
    const error = new Error(t("requestFailed"));
    error.connectionFailed = true;
    throw error;
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (payload.code === "maintenance_mode" && payload.maintenance) {
      state.maintenance = payload.maintenance;
      renderAccessGate();
    }
    const message = payload.code === "build_concurrency_limit"
      ? t("buildConcurrencyLimit")
      : payload.error || `HTTP ${response.status}`;
    const error = new Error(message);
    error.code = payload.code || "";
    error.status = response.status;
    error.sourceRejected = response.status >= 400 && response.status < 500;
    throw error;
  }
  return payload;
}

async function publicApiRequest(path, options = {}) {
  if (!miniApiEndpoint) throw new Error(t("apiRequired"));
  const headers = new Headers(options.headers || {});
  if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(`${miniApiEndpoint}${path}`, { ...options, headers, cache: "no-store" });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok && response.status !== 202) throw new Error(payload.error || `HTTP ${response.status}`);
  return { payload, status: response.status };
}

function telegramTransportAvailable() {
  return typeof TelegramApp?.sendData === "function" && Boolean(TelegramApp.platform) && TelegramApp.platform !== "unknown";
}

const liquidSlots = [0, 1, 2, 3, 4];

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
  $$(".bottom-nav [data-nav], .contents-rail [data-nav]").forEach((node) => {
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
  if (smooth) TelegramApp?.HapticFeedback?.selectionChanged?.();
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

  nav.addEventListener("click", (event) => {
    if (!state.liquidSuppressClick) return;
    state.liquidSuppressClick = false;
    event.preventDefault();
    event.stopImmediatePropagation();
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

const sourceFactDefinitions = [
  ["source-provider", "provider"],
  ["source-product-detected", "detectedProduct"],
  ["source-device-detected", "detectedDevice"],
  ["source-version-detected", "detectedVersion"],
  ["source-android-version", "androidVersion"],
  ["source-security-patch", "securityPatch"],
  ["source-build-date", "buildDate"],
  ["source-size-detected", "sourceSizeDetected"],
  ["source-ota-type", "otaType"],
  ["source-content-type", "contentType"],
  ["source-filename", "fileName"],
  ["source-host", "resolvedHost"],
  ["source-md5", "MD5"],
  ["source-last-modified", "lastModified"],
  ["source-deep-inspection", "deepInspection"]
];

const completenessSourceFactIds = sourceFactDefinitions
  .map(([id]) => id)
  .filter((id) => id !== "source-deep-inspection");

const requiredSourceFactIds = sourceFactDefinitions
  .map(([id]) => id)
  .filter((id) => ![
    "source-md5",
    "source-last-modified",
    "source-deep-inspection"
  ].includes(id));

function setSourceFact(id, value) {
  const node = $(`#${id}`);
  if (!node) return;
  const text = String(value || "").trim();
  node.textContent = text || "—";
  node.dataset.empty = text && text !== "—" ? "false" : "true";
  node.title = text && text !== "—" ? text : "";
}

function updateMetadataCompleteness() {
  const completed = (ids) => ids.filter((id) => {
    const value = $(`#${id}`)?.textContent?.trim();
    return value && value !== "—" && value !== "···";
  }).length;
  const complete = completed(completenessSourceFactIds);
  const total = completenessSourceFactIds.length;
  const requiredComplete = completed(requiredSourceFactIds);
  $("#source-metadata-count").textContent = t("metadataCompleteness", { complete, total });
  return {
    complete,
    total,
    requiredComplete,
    requiredTotal: requiredSourceFactIds.length
  };
}

function resetSourceFacts(detection, uri) {
  sourceFactDefinitions.forEach(([id]) => setSourceFact(id, ""));
  if (!detection?.valid) { updateMetadataCompleteness(); return; }
  setSourceFact("source-provider", detection.provider);
  setSourceFact("source-product-detected", detection.device);
  setSourceFact("source-version-detected", detection.version);
  setSourceFact("source-host", detection.kind === "rclone" ? "Google Drive" : new URL(uri).hostname);
  updateMetadataCompleteness();
}

function sourceMetadataText() {
  return sourceFactDefinitions.map(([id, key]) => `${t(key)}: ${$(`#${id}`)?.textContent?.trim() || "—"}`).join("\n");
}

async function copyText(text) {
  if (navigator.clipboard?.writeText) {
    try { await navigator.clipboard.writeText(text); return; } catch (_) { /* Try the WebView-compatible copy path. */ }
  }
  {
    const input = document.createElement("textarea"); input.value = text;
    input.style.position = "fixed"; input.style.opacity = "0"; input.style.pointerEvents = "none";
    document.body.append(input); input.select();
    const copied = document.execCommand("copy");
    input.remove();
    if (!copied) throw new Error("Clipboard copy failed");
  }
}

async function copySourceMetadata() {
  await copyText(sourceMetadataText());
  toast(t("metadataCopied"));
}

function readTelegramClipboard() {
  if (typeof TelegramApp?.readTextFromClipboard !== "function") return Promise.resolve({ text: "", readable: false });
  return new Promise((resolve) => {
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      clearTimeout(timeout);
      resolve({ text: typeof value === "string" ? value : "", readable: typeof value === "string" });
    };
    const timeout = setTimeout(() => finish(null), 1200);
    try { TelegramApp.readTextFromClipboard(finish); } catch (_) { finish(null); }
  });
}

async function readClipboardText() {
  const input = $("#source-uri");
  input.focus({ preventScroll: true });
  // Some Android WebViews only honor the legacy paste command while the
  // original trusted click is still active. Try it synchronously before any
  // Promise/await can consume that transient user activation.
  try {
    const accepted = document.execCommand?.("paste") === true;
    const text = input.value.trim();
    if (accepted && text) return { text, readable: true };
  } catch (_) {}
  if (navigator.clipboard?.readText) {
    try {
      const result = await Promise.race([
        navigator.clipboard.readText().then((text) => ({ text, readable: true })),
        new Promise((resolve) => setTimeout(() => resolve({ text: "", readable: false }), 500)),
      ]);
      if (result.readable) return result;
    } catch (_) {}
  }
  const telegram = await readTelegramClipboard();
  if (telegram.readable) return telegram;
  return { text: "", readable: false };
}

async function pasteSourceFromClipboard() {
  const clipboard = await readClipboardText();
  let value = String(clipboard.text || "").trim();
  let fromDraft = false;
  if (!value && miniApiAvailable()) {
    try {
      const draft = await apiRequest("/v1/drafts/source");
      value = String(draft.uri || "").trim();
      fromDraft = Boolean(value);
    } catch (_) {}
  }
  const input = $("#source-uri");
  if (!value) {
    input.focus({ preventScroll: true });
    input.select();
    toast(t(clipboard.readable ? "clipboardEmpty" : "clipboardManual"));
    return;
  }
  input.value = value;
  input.dispatchEvent(new Event("input", { bubbles: true }));
  input.focus({ preventScroll: true });
  toast(t(fromDraft ? "draftPasted" : "linkPasted"));
}

function clearSource() {
  const input = $("#source-uri");
  input.value = "";
  input.dispatchEvent(new Event("input", { bubbles: true }));
  toast(t("sourceCleared"));
}

function presentMissingApi() {
  const status = miniApiState();
  const node = $("#source-state");
  node.classList.remove("probing", "analyzed", "probe-deferred", "probe-limited", "probe-failed", "probe-unavailable", "backend-offline");
  node.classList.add("probe-unavailable");
  const unconfigured = status === "unconfigured";
  const insideTelegram = Boolean(TelegramApp?.platform && TelegramApp.platform !== "unknown");
  $("#source-kicker").textContent = t(unconfigured ? "apiUnavailableKicker" : "apiAuthKicker");
  $("#source-state-message").textContent = t(unconfigured ? "apiUnavailableMessage" : "apiAuthMessage");
  const button = $("#probe-source");
  button.textContent = t(unconfigured ? "apiUnavailableButton" : "apiAuthButton");
  if (unconfigured) {
    button.disabled = true;
    delete button.dataset.openBot;
    delete button.dataset.closeApp;
    return;
  }
  // Always offer a way out: inside Telegram just close and reopen from the
  // menu button so initData is attached; outside Telegram jump to the bot.
  if (insideTelegram) {
    button.disabled = false;
    button.dataset.connectTelegram = "1";
    delete button.dataset.openBot;
    delete button.dataset.closeApp;
  } else if (telegramBotUsername) {
    button.disabled = false;
    button.dataset.openBot = "1";
    delete button.dataset.closeApp;
  } else {
    button.disabled = true;
    delete button.dataset.openBot;
    delete button.dataset.closeApp;
  }
}

function telegramBotLink() {
  return `https://t.me/${telegramBotUsername}`;
}

function openTelegramBot() {
  const link = telegramBotLink();
  try {
    if (TelegramApp?.openTelegramLink) { TelegramApp.openTelegramLink(link); return; }
  } catch (_) {}
  window.open(link, "_blank", "noopener");
}

function storedPairing() {
  try { return JSON.parse(sessionStorage.getItem("wukong-telegram-pairing") || "null"); }
  catch (_) { return null; }
}

async function pollTelegramPairing(pairing) {
  clearTimeout(state.pairingPollTimer);
  if (!pairing?.pairId || !pairing?.pairSecret || miniApiAvailable()) return;
  const { payload, status } = await publicApiRequest("/v1/session/pair/status", {
    method: "POST",
    body: JSON.stringify({ pairId: pairing.pairId, pairSecret: pairing.pairSecret })
  });
  if (status === 200 && setSignedTelegramLaunchToken(payload.launchToken)) {
    try { sessionStorage.removeItem("wukong-telegram-pairing"); } catch (_) {}
    state.pairingInFlight = false;
    state.pairingPollAttempt = 0;
    renderSessionDiagnostics();
    updateTelegramState();
    updateSummary();
    updateSourceDetection();
    loadSession().then(() => {
      initializeApprovedWorkspace();
    }).catch(() => {});
    toast(t("pairingReady"));
    return;
  }
  const recoveryText = $("#session-recovery p");
  if (recoveryText) recoveryText.textContent = t("pairingWaiting");
  const pairingBackoff = [3000, 5000, 8000, 10000];
  const delay = pairingBackoff[Math.min(state.pairingPollAttempt, pairingBackoff.length - 1)];
  state.pairingPollAttempt += 1;
  state.pairingPollTimer = setTimeout(() => {
    pollTelegramPairing(pairing).catch(() => {
      state.pairingInFlight = false;
      updateSummary();
      toast(t("pairingFailed"), true);
    });
  }, delay);
}

async function connectTelegramSession() {
  if (state.pairingInFlight || miniApiAvailable()) return;
  state.pairingInFlight = true;
  state.pairingPollAttempt = 0;
  updateSummary();
  const recoveryText = $("#session-recovery p");
  if (recoveryText) recoveryText.textContent = t("pairingOpening");
  try {
    const { payload: pairing } = await publicApiRequest("/v1/session/pair", { method: "POST" });
    sessionStorage.setItem("wukong-telegram-pairing", JSON.stringify(pairing));
    try {
      if (TelegramApp?.openTelegramLink) TelegramApp.openTelegramLink(pairing.botLink);
      else window.open(pairing.botLink, "_blank", "noopener");
    } catch (_) { window.open(pairing.botLink, "_blank", "noopener"); }
    await pollTelegramPairing(pairing);
  } catch (error) {
    state.pairingInFlight = false;
    updateSummary();
    toast(error.message || t("pairingFailed"), true);
  }
}

function closeTelegramApp() {
  try { TelegramApp?.close(); } catch (_) {}
  // Fallback for browsers/testing: just navigate away from the stale entry.
  setTimeout(() => { try { window.close(); } catch (_) {} }, 120);
}

function restoreSourceDraft() {
  // One-time cleanup of the legacy draft that used to persist signed links.
  try { localStorage.removeItem("wukong-source-draft"); } catch (_) {}
  try { localStorage.removeItem("wukong-recipe-draft"); } catch (_) {}
  // Clear a fragment-only paste (e.g. "6a8a..." pasted without https://) that
  // was left in the textarea by autofill or a previous session.
  const input = $("#source-uri");
  if (!input) return;
  const current = input.value.trim();
  if (current && !/^https?:\/\//i.test(current)) input.value = "";
  if (input.value.trim()) return;
  let startParam = "";
  try { startParam = decodeURIComponent(String(effectiveInitDataUnsafe()?.start_param || "")); } catch (_) { startParam = String(effectiveInitDataUnsafe()?.start_param || ""); }
  if (!startParam || !/^https?:\/\//i.test(startParam)) return;
  input.value = startParam;
  updateSourceDetection();
  scheduleSourceProbe();
}

function updateSourceDetection() {
  const node = $("#source-state");
  if (!node) return;
  const currentUri = $("#source-uri").value.trim();
  const detection = classifySource(currentUri);
  const uriChanged = state.sourceInputUri !== currentUri;
  if (uriChanged) {
    state.sourceInputUri = currentUri;
    state.sourceProbeRequestId += 1;
    state.sourceProbeController?.abort();
    state.sourceProbeController = null;
    $("#source-size").value = "";
    state.sourceProbeUri = "";
    if (state.sourceAutoDevice && $("#device").value === state.sourceAutoDevice) {
      $("#device").value = "";
      updateSummary();
    }
    state.sourceAutoDevice = null;
    state.sourceProbe = null;
  }
  state.sourceDetection = detection;
  updateSummary();
  node.classList.toggle("detected", Boolean(detection?.valid));
  node.classList.toggle("invalid", Boolean(detection && !detection.valid));
  node.classList.remove("probing", "analyzed", "preview-only", "probe-deferred", "probe-limited", "probe-failed", "probe-unavailable", "backend-offline");
  const marker = node.querySelector(".source-state-mark span");
  const facts = $("#source-facts");
  const factsHead = $("#source-facts-head");
  const probe = $("#probe-source");
  probe.disabled = false;
  probe.textContent = t("analyzeSource");
  if (!detection) {
    marker.textContent = "URL";
    $("#source-kicker").textContent = t("sourceIdleKicker");
    $("#source-state-title").textContent = t("sourceIdleTitle");
    $("#source-state-message").textContent = t("sourceIdleMessage");
    resetSourceFacts(null, "");
    facts.hidden = true; factsHead.hidden = true; probe.hidden = true; return;
  }
  if (!detection.valid) {
    marker.textContent = "?";
    $("#source-kicker").textContent = t("sourceInvalidKicker");
    $("#source-state-title").textContent = t("sourceInvalidTitle");
    $("#source-state-message").textContent = t("sourceInvalidMessage");
    resetSourceFacts(null, "");
    facts.hidden = true; factsHead.hidden = true; probe.hidden = true; return;
  }
  marker.textContent = detection.marker;
  $("#source-kicker").textContent = t("sourceDetectedKicker");
  $("#source-state-title").textContent = `${detection.provider} · ${detection.type}`;
  $("#source-state-message").textContent = t("deepProbeHint");
  resetSourceFacts(detection, currentUri);
  facts.hidden = false; factsHead.hidden = false;
  probe.hidden = detection.marker === "DRV";
  if (detection.device && [...$("#device").options].some((option) => option.value === detection.device)) {
    $("#device").value = detection.device;
    state.sourceAutoDevice = detection.device;
    updateSummary();
  }
  if (!$("#device").value) {
    $(".source-manual").open = true;
  }
  if (state.sourceProbeUri === currentUri && state.sourceProbe?.result) {
    const completeness = applyProbeResult(state.sourceProbe.result, currentUri, { announce: false });
    const previewOnly = state.sourceProbe.status === "preview-only";
    const coreComplete = completeness.requiredComplete === completeness.requiredTotal;
    setProbePresentation(previewOnly ? "preview-only" : coreComplete ? "analyzed" : "probe-limited", previewOnly ? "probeSignedPreviewOnly" : coreComplete ? "probeSuccess" : "probePartial");
    return;
  }
  if (!probe.hidden && !miniApiEndpoint) presentMissingApi();
}

function setProbePresentation(status, messageKey) {
  const node = $("#source-state");
  node.classList.remove("probing", "analyzed", "preview-only", "probe-deferred", "probe-limited", "probe-failed", "probe-unavailable", "backend-offline");
  node.classList.add(status);
  const kickerKey = status === "analyzed" ? "probeReadyKicker" : status === "preview-only" ? "probeLimitedKicker" : status === "probe-failed" ? "probeFailedKicker" : status === "probe-deferred" ? "probeDeferredKicker" : status === "probe-limited" ? "probeLimitedKicker" : "sourceDetectedKicker";
  $("#source-kicker").textContent = t(kickerKey);
  $("#source-state-message").textContent = t(messageKey);
}

async function probeSourceViaBackend(uri, signal) {
  const options = {
    method: "POST",
    body: JSON.stringify({ uri }),
    signal
  };
  if (effectiveInitData()) return apiRequest("/v1/sources/probe", options);
  const headers = new Headers({ "Content-Type": "application/json" });
  let response;
  try {
    response = await fetch(`${miniApiEndpoint}/v1/sources/probe`, { ...options, headers, cache: "no-store" });
  } catch (cause) {
    if (cause?.name === "AbortError") throw cause;
    const error = new Error(t("requestFailed"));
    error.connectionFailed = true;
    throw error;
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(payload.error || `HTTP ${response.status}`);
    error.code = payload.code || "";
    error.status = response.status;
    error.sourceRejected = response.status >= 400 && response.status < 500;
    throw error;
  }
  return payload;
}

const ZIP_METADATA_SUFFIXES = [
  "meta-inf/com/android/metadata",
  "payload_properties.txt",
  "android-info.txt"
];
const ZIP_MAX_METADATA_FILES = 8;
const ZIP_MAX_METADATA_FILE_BYTES = 2 * 1024 * 1024;
const ZIP_MAX_METADATA_TEXT_BYTES = 4 * 1024 * 1024;
const ZIP_MAX_METADATA_FIELDS = 256;
const ZIP_MAX_RANGE_BYTES = 8 * 1024 * 1024;
const ZIP_MAX_CLIENT_BYTES = 16 * 1024 * 1024;

function zipNumber(value, label) {
  const maximum = BigInt(Number.MAX_SAFE_INTEGER);
  if (typeof value === "bigint") {
    if (value < 0n || value > maximum) throw new Error(`${label} exceeds the browser ZIP limit`);
    return Number(value);
  }
  if (!Number.isSafeInteger(value) || value < 0) throw new Error(`${label} is invalid`);
  return value;
}

async function fetchProbeRange(session, start, end, signal) {
  if (!session?.url || !Number.isSafeInteger(start) || !Number.isSafeInteger(end) || end < start) {
    throw new Error("ROM range session is invalid");
  }
  const length = end - start + 1;
  if (length > ZIP_MAX_RANGE_BYTES) throw new Error("ROM ZIP range exceeds 8 MiB");
  const response = await fetch(session.url, {
    headers: { Range: `bytes=${start}-${end}` },
    cache: "no-store",
    signal
  });
  if (response.status !== 206) throw new Error(`ROM range returned HTTP ${response.status}`);
  const bytes = new Uint8Array(await response.arrayBuffer());
  if (bytes.byteLength !== length) throw new Error("ROM range length does not match the request");
  return bytes;
}

async function fetchProbeBytes(session, start, length, signal) {
  if (!Number.isSafeInteger(length) || length < 0 || length > ZIP_MAX_CLIENT_BYTES) {
    throw new Error("ROM ZIP metadata exceeds the 16 MiB inspection budget");
  }
  const chunks = [];
  let offset = 0;
  while (offset < length) {
    const chunkLength = Math.min(ZIP_MAX_RANGE_BYTES, length - offset);
    chunks.push(await fetchProbeRange(
      session,
      start + offset,
      start + offset + chunkLength - 1,
      signal
    ));
    offset += chunkLength;
  }
  const output = new Uint8Array(length);
  let outputOffset = 0;
  chunks.forEach((chunk) => {
    output.set(chunk, outputOffset);
    outputOffset += chunk.byteLength;
  });
  return output;
}

function findZipSignature(bytes, signature) {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  for (let offset = bytes.byteLength - 4; offset >= 0; offset -= 1) {
    if (view.getUint32(offset, true) === signature) return offset;
  }
  return -1;
}

function zip64Extra(extra, needs) {
  const view = new DataView(extra.buffer, extra.byteOffset, extra.byteLength);
  let offset = 0;
  while (offset + 4 <= extra.byteLength) {
    const id = view.getUint16(offset, true);
    const length = view.getUint16(offset + 2, true);
    const start = offset + 4;
    const end = start + length;
    if (end > extra.byteLength) throw new Error("ZIP extra field is truncated");
    if (id === 0x0001) {
      let cursor = start;
      const values = {};
      for (const name of ["uncompressedSize", "compressedSize", "localOffset", "disk"]) {
        if (!needs[name]) continue;
        const width = name === "disk" ? 4 : 8;
        if (cursor + width > end) throw new Error("ZIP64 extra field is truncated");
        values[name] = width === 8
          ? zipNumber(view.getBigUint64(cursor, true), `ZIP64 ${name}`)
          : view.getUint32(cursor, true);
        cursor += width;
      }
      return values;
    }
    offset = end;
  }
  return {};
}

async function zipDirectory(result, signal) {
  const size = zipNumber(Number(result?.sizeBytes), "ROM size");
  if (size < 22) throw new Error("ROM ZIP is too small");
  const session = result?.rangeSession;
  const tailLength = Math.min(size, 65557);
  const tailStart = size - tailLength;
  const tail = await fetchProbeBytes(session, tailStart, tailLength, signal);
  const eocdOffset = findZipSignature(tail, 0x06054b50);
  if (eocdOffset < 0 || eocdOffset + 22 > tail.byteLength) {
    throw new Error("ROM ZIP central directory was not found");
  }
  const view = new DataView(tail.buffer, tail.byteOffset, tail.byteLength);
  let entryCount = view.getUint16(eocdOffset + 10, true);
  let directorySize = view.getUint32(eocdOffset + 12, true);
  let directoryOffset = view.getUint32(eocdOffset + 16, true);
  if (entryCount === 0xffff || directorySize === 0xffffffff || directoryOffset === 0xffffffff) {
    const locatorOffset = findZipSignature(tail.slice(0, eocdOffset), 0x07064b50);
    if (locatorOffset < 0 || locatorOffset + 20 > tail.byteLength) {
      throw new Error("ROM ZIP64 locator was not found");
    }
    const zip64Offset = zipNumber(view.getBigUint64(locatorOffset + 8, true), "ZIP64 directory offset");
    const zip64Header = await fetchProbeBytes(session, zip64Offset, 56, signal);
    const zip64View = new DataView(zip64Header.buffer, zip64Header.byteOffset, zip64Header.byteLength);
    if (zip64View.getUint32(0, true) !== 0x06064b50) throw new Error("ROM ZIP64 directory is invalid");
    entryCount = zipNumber(zip64View.getBigUint64(32, true), "ZIP64 entry count");
    directorySize = zipNumber(zip64View.getBigUint64(40, true), "ZIP64 directory size");
    directoryOffset = zipNumber(zip64View.getBigUint64(48, true), "ZIP64 directory offset");
  }
  if (directorySize > ZIP_MAX_CLIENT_BYTES - tailLength) {
    throw new Error("ROM ZIP central directory exceeds the inspection budget");
  }
  if (directoryOffset + directorySize > size || entryCount > 1000000) {
    throw new Error("ROM ZIP central directory is invalid");
  }
  return {
    entries: entryCount,
    bytes: await fetchProbeBytes(session, directoryOffset, directorySize, signal)
  };
}

function metadataZipEntries(directory) {
  const bytes = directory.bytes;
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const decoder = new TextDecoder("utf-8", { fatal: false });
  const entries = [];
  let offset = 0;
  let parsed = 0;
  while (offset < bytes.byteLength && parsed < directory.entries) {
    if (offset + 46 > bytes.byteLength || view.getUint32(offset, true) !== 0x02014b50) {
      throw new Error("ROM ZIP central directory entry is invalid");
    }
    const flags = view.getUint16(offset + 8, true);
    const method = view.getUint16(offset + 10, true);
    let compressedSize = view.getUint32(offset + 20, true);
    let uncompressedSize = view.getUint32(offset + 24, true);
    const nameLength = view.getUint16(offset + 28, true);
    const extraLength = view.getUint16(offset + 30, true);
    const commentLength = view.getUint16(offset + 32, true);
    let localOffset = view.getUint32(offset + 42, true);
    const end = offset + 46 + nameLength + extraLength + commentLength;
    if (end > bytes.byteLength) throw new Error("ROM ZIP central directory is truncated");
    const name = decoder.decode(bytes.subarray(offset + 46, offset + 46 + nameLength));
    const extra = bytes.subarray(
      offset + 46 + nameLength,
      offset + 46 + nameLength + extraLength
    );
    const zip64 = zip64Extra(extra, {
      uncompressedSize: uncompressedSize === 0xffffffff,
      compressedSize: compressedSize === 0xffffffff,
      localOffset: localOffset === 0xffffffff,
      disk: view.getUint16(offset + 34, true) === 0xffff
    });
    uncompressedSize = zip64.uncompressedSize ?? uncompressedSize;
    compressedSize = zip64.compressedSize ?? compressedSize;
    localOffset = zip64.localOffset ?? localOffset;
    const normalized = name.replaceAll("\\", "/").toLowerCase();
    if (ZIP_METADATA_SUFFIXES.some((suffix) => normalized.endsWith(suffix))) {
      if (uncompressedSize <= ZIP_MAX_METADATA_FILE_BYTES) {
        entries.push({
          name,
          method,
          compressedSize,
          uncompressedSize,
          localOffset,
          encrypted: Boolean(flags & 1)
        });
        if (entries.length > ZIP_MAX_METADATA_FILES) {
          throw new Error("ROM ZIP exposes too many metadata files");
        }
      }
    }
    parsed += 1;
    offset = end;
  }
  return entries;
}

async function readMetadataZipEntry(session, entry, sourceSize, signal) {
  if (entry.encrypted) throw new Error("Encrypted ROM metadata is not supported");
  if (entry.compressedSize > ZIP_MAX_RANGE_BYTES) {
    throw new Error(`ROM metadata file is too large: ${entry.name}`);
  }
  // Metadata files are normally tiny. Prefetch the local header and first
  // 64 KiB together so the common case needs one network round-trip.
  const prefetchLength = Math.min(
    ZIP_MAX_RANGE_BYTES,
    zipNumber(Number(sourceSize), "ROM size") - entry.localOffset,
    Math.max(64 * 1024, 30 + entry.compressedSize)
  );
  if (prefetchLength < 30) throw new Error("ROM ZIP local header is truncated");
  const prefetched = await fetchProbeBytes(session, entry.localOffset, prefetchLength, signal);
  const header = prefetched.subarray(0, 30);
  const view = new DataView(header.buffer, header.byteOffset, header.byteLength);
  if (view.getUint32(0, true) !== 0x04034b50) throw new Error("ROM ZIP local header is invalid");
  const nameLength = view.getUint16(26, true);
  const extraLength = view.getUint16(28, true);
  const relativeDataOffset = 30 + nameLength + extraLength;
  let compressed;
  if (relativeDataOffset + entry.compressedSize <= prefetched.byteLength) {
    compressed = prefetched.subarray(relativeDataOffset, relativeDataOffset + entry.compressedSize);
  } else {
    const dataOffset = entry.localOffset + relativeDataOffset;
    compressed = await fetchProbeBytes(session, dataOffset, entry.compressedSize, signal);
  }
  let content;
  if (entry.method === 0) content = compressed;
  else if (entry.method === 8 && window.fflate?.inflateSync) content = window.fflate.inflateSync(compressed);
  else throw new Error(`Unsupported ROM metadata compression method: ${entry.method}`);
  if (content.byteLength !== entry.uncompressedSize || content.byteLength > ZIP_MAX_METADATA_FILE_BYTES) {
    throw new Error("ROM ZIP metadata file exceeds the inspection limit");
  }
  return content;
}

function firstMetadata(metadata, ...keys) {
  return keys.map((key) => metadata[key]).find(Boolean) || "";
}

function metadataAndroidVersion(metadata, version) {
  const explicit = firstMetadata(metadata, "android-version", "post-android-version");
  if (explicit) return explicit;
  const sdk = firstMetadata(metadata, "post-sdk-level", "sdk-level");
  const versions = { 36: "16", 35: "15", 34: "14", 33: "13", 32: "12L", 31: "12", 30: "11", 29: "10" };
  return versions[sdk] || String(version || "").match(/(?:^|_)(\d{2})(?:\.|_)/)?.[1] || "";
}

function metadataBuildDate(metadata) {
  const explicit = firstMetadata(metadata, "build-date", "post-build-date", "build-timestamp");
  if (explicit) return explicit.replace("T", " ").replace(/Z$/, "");
  let timestamp = Number(firstMetadata(metadata, "post-timestamp", "timestamp"));
  if (Number.isFinite(timestamp) && timestamp > 0) {
    if (timestamp > 10000000000) timestamp = Math.floor(timestamp / 1000);
    return new Date(timestamp * 1000).toISOString().replace("T", " ").slice(0, 19);
  }
  const otaBuild = firstMetadata(metadata, "ota-build");
  const match = otaBuild.match(/_(\d{12})(?:\D|$)/);
  if (!match) return "";
  const value = match[1];
  return `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6, 8)} ${value.slice(8, 10)}:${value.slice(10, 12)}:00`;
}

async function inspectProbeZipMetadata(result, signal) {
  if (
    !result?.rangeSession ||
    !Number.isSafeInteger(Number(result.sizeBytes)) ||
    Number(result.sizeBytes) <= 0 ||
    !String(result.filename || "").toLowerCase().endsWith(".zip")
  ) return result;
  const directory = await zipDirectory(result, signal);
  const entries = metadataZipEntries(directory);
  const metadata = {};
  let totalTextBytes = 0;
  const contents = new Array(entries.length);
  const failures = [];
  let nextEntry = 0;
  const readNext = async () => {
    while (nextEntry < entries.length) {
      const index = nextEntry;
      nextEntry += 1;
      try {
        contents[index] = await readMetadataZipEntry(
          result.rangeSession,
          entries[index],
          result.sizeBytes,
          signal
        );
      } catch (error) {
        if (signal?.aborted) throw error;
        failures.push(entries[index].name);
      }
    }
  };
  await Promise.all(Array.from({ length: Math.min(3, entries.length) }, readNext));
  for (const content of contents.filter(Boolean)) {
    totalTextBytes += content.byteLength;
    if (totalTextBytes > ZIP_MAX_METADATA_TEXT_BYTES) {
      throw new Error("ROM ZIP metadata exceeds the 4 MiB text limit");
    }
    new TextDecoder("utf-8", { fatal: false }).decode(content).split(/\r?\n/).forEach((line) => {
      const separator = line.indexOf("=");
      if (separator <= 0) return;
      const key = line.slice(0, separator).trim().toLowerCase().replaceAll("_", "-");
      if (!key || key.length > 128) return;
      metadata[key] = line.slice(separator + 1).trim().slice(0, 1024);
      if (Object.keys(metadata).length > ZIP_MAX_METADATA_FIELDS) {
        throw new Error("ROM ZIP metadata contains too many fields");
      }
    });
  }
  if (!Object.keys(metadata).length) {
    return {
      ...result,
      warning: failures.length
        ? "ROM ZIP metadata files could not be read"
        : "ROM ZIP does not expose recognized metadata files"
    };
  }
  const productName = firstMetadata(metadata, "oplus-product-name", "product-name");
  const device = firstMetadata(metadata, "pre-device", "product-name", "oplus-product-name");
  const version = firstMetadata(
    metadata,
    "oplus-version-name",
    "version-name",
    "post-build-incremental",
    "post-build"
  );
  return {
    ...result,
    productName,
    device,
    version,
    androidVersion: metadataAndroidVersion(metadata, version),
    securityPatch: firstMetadata(metadata, "post-security-patch-level"),
    buildDate: metadataBuildDate(metadata),
    otaType: firstMetadata(metadata, "ota-type"),
    deepInspected: true,
    warning: failures.length
      ? `${failures.length} ROM metadata file(s) could not be read`
      : null,
    metadata
  };
}

function normalizeDevice(value) {
  return String(value || "").toLocaleUpperCase().replace(/[^A-Z0-9]/g, "");
}

function matchCatalogDevice(result, detected, inferred, filename) {
  const versionProduct = String(result?.version || "").split("_", 1)[0];
  const candidates = [result?.productName, versionProduct, filename, result?.device, detected?.device, inferred?.device]
    .map(normalizeDevice).filter(Boolean);
  return state.catalog?.devices?.find((item) => {
    const product = normalizeDevice(item.product);
    return candidates.some((candidate) => candidate === product || candidate.startsWith(product) || candidate.includes(product));
  })?.product || "";
}

function selectModPackForVersion(version) {
  const match = String(version || "").match(/_(\d+\.\d+\.\d+)/);
  if (!match) return;
  const preferred = `ColorOS_${match[1]}`;
  if (state.catalog?.modVersions?.includes(preferred) && $("#mod-version").value !== preferred) {
    $("#mod-version").value = preferred;
    renderMods();
  }
}

function formatBytes(value) {
  let size = Number(value || 0);
  if (!Number.isFinite(size) || size <= 0) return "—";
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  let index = 0;
  while (size >= 1024 && index < units.length - 1) { size /= 1024; index += 1; }
  return `${size.toFixed(index ? 2 : 0)} ${units[index]}`;
}

function applyProbeResult(result, uri, { announce = true } = {}) {
  const detected = state.sourceDetection;
  const url = new URL(uri);
  const rawFilename = url.pathname.split("/").filter(Boolean).at(-1) || "";
  const localFilename = /\.(?:zip|ozip|bin)$/i.test(rawFilename) ? decodeURIComponent(rawFilename) : "—";
  const filename = result?.filename || localFilename;
  const host = result?.resolvedHost || result?.host || url.hostname;
  const inferred = filename !== "—" ? classifySource(`https://${host}/${encodeURIComponent(filename)}`) : null;
  const device = matchCatalogDevice(result, detected, inferred, filename);
  const product = result?.productName || String(result?.version || "").split("_", 1)[0] || device;
  const version = result?.version || detected.version || inferred?.version || "";
  const size = Number(result?.sizeBytes || 0);
  setSourceFact("source-provider", result?.provider || detected.provider);
  setSourceFact("source-host", host);
  setSourceFact("source-filename", filename);
  setSourceFact("source-product-detected", product);
  setSourceFact("source-device-detected", result?.device);
  setSourceFact("source-version-detected", version);
  setSourceFact("source-android-version", result?.androidVersion);
  setSourceFact("source-security-patch", result?.securityPatch);
  setSourceFact("source-build-date", result?.buildDate);
  setSourceFact("source-size-detected", size > 0 ? `${formatBytes(size)} · ${size.toLocaleString(state.language === "vi" ? "vi-VN" : "en-US")} bytes` : "");
  setSourceFact("source-ota-type", result?.otaType);
  setSourceFact("source-content-type", result?.contentType);
  setSourceFact("source-md5", result?.md5);
  setSourceFact("source-last-modified", result?.lastModified);
  setSourceFact("source-deep-inspection", result?.deepInspected ? t("deepInspected") : t("headersOnly"));
  if (Number.isSafeInteger(size) && size > 0) $("#source-size").value = String(size);
  if (device && [...$("#device").options].some((option) => option.value === device)) {
    $("#device").value = device;
    state.sourceAutoDevice = device;
    if (announce) toast(t("autoSelected", { device }));
  }
  selectModPackForVersion(version);
  state.sourceProbeUri = uri;
  const completeness = updateMetadataCompleteness();
  state.sourceProbe = { status: result?.cloudBuildReady === false ? "preview-only" : completeness.requiredComplete === completeness.requiredTotal ? "analyzed" : "partial", result };
  updateSummary();
  return completeness;
}

async function probeSourceInPlace() {
  const button = $("#probe-source");
  const uri = $("#source-uri").value.trim();
  if (!state.sourceDetection?.valid || !/^https?:\/\//i.test(uri)) throw new Error(t("invalidUrl"));
  if (!miniApiEndpoint) { presentMissingApi(); return; }
  state.sourceProbeController?.abort();
  const controller = new AbortController();
  state.sourceProbeController = controller;
  const requestId = ++state.sourceProbeRequestId;
  let timedOut = false;
  // Free control-plane hosts can require close to a minute to wake from an
  // idle cold start before the remote ZIP probe itself begins.
  const timeout = setTimeout(() => { timedOut = true; controller.abort(); }, 110000);
  button.disabled = true;
  button.textContent = t("probeAnalyzing");
  setProbePresentation("probing", "probeAnalyzing");
  try {
    let result = await probeSourceViaBackend(uri, controller.signal);
    try {
      result = await inspectProbeZipMetadata(result, controller.signal);
    } catch (inspectionError) {
      if (inspectionError?.name === "AbortError") throw inspectionError;
      result = {
        ...result,
        deepInspected: false,
        warning: inspectionError?.message || "ROM ZIP metadata is unavailable"
      };
    }
    if (requestId !== state.sourceProbeRequestId || uri !== $("#source-uri").value.trim()) return;
    const completeness = applyProbeResult(result, uri);
    const previewOnly = state.sourceProbe.status === "preview-only";
    const coreComplete = completeness.requiredComplete === completeness.requiredTotal;
    setProbePresentation(previewOnly ? "preview-only" : coreComplete ? "analyzed" : "probe-limited", previewOnly ? "probeSignedPreviewOnly" : coreComplete ? "probeSuccess" : "probePartial");
  } catch (error) {
    if (requestId !== state.sourceProbeRequestId || uri !== $("#source-uri").value.trim()) return;
    if (error?.name === "AbortError" && !timedOut) return;
    const sourceFailed = error?.sourceRejected && error?.status !== 429;
    const apiOffline = timedOut || error?.connectionFailed || navigator.onLine === false;
    const status = sourceFailed ? "probe-failed" : apiOffline ? "backend-offline" : "probe-deferred";
    const message = sourceFailed ? "probeFailed" : apiOffline ? "apiOfflineMessage" : "probeDeferred";
    state.sourceProbe = { status: sourceFailed ? "failed" : apiOffline ? "offline" : "deferred" };
    setProbePresentation(status, message);
    if (error?.code === "source_signed_url_expired") {
      $("#source-state-message").textContent = t("probeSignedExpired");
    }
    if (apiOffline) $("#source-kicker").textContent = t("apiOfflineKicker");
    toast(error?.code === "source_signed_url_expired" ? t("probeSignedExpired") : sourceFailed ? t("probeFailed") : apiOffline ? t("apiOfflineMessage") : t("probeDeferred"), true);
  } finally {
    clearTimeout(timeout);
    if (requestId === state.sourceProbeRequestId) {
      state.sourceProbeController = null;
      button.disabled = false;
      button.textContent = t("analyzeSource");
    }
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
  renderReleaseVersion();
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
    const copy = document.createElement("span"); copy.className = "device-copy"; copy.append(code, name);
    row.append(copy); return row;
  }));
  $("#catalog-mod-list").replaceChildren(...mods.map((name) => {
    const item = document.createElement("span"); item.textContent = name; return item;
  }));
  if (!devices.length && !mods.length) {
    const empty = document.createElement("span"); empty.className = "catalog-empty"; empty.textContent = t("noCatalogMatches");
    $("#catalog-mod-list").append(empty);
  }
  $("#device-count").textContent = String(devices.length);
  $("#catalog-mod-count").textContent = String(mods.length);
  const totalMods = Object.values(state.catalog.modsByVersion).reduce((total, names) => total + names.length, 0);
  $("#catalog-total").textContent = t("catalogSummary", { devices: state.catalog.devices.length, mods: totalMods });
  renderAdminReleaseEditor();
}

function renderAdminReleaseEditor() {
  const root = $("#catalog-release-admin");
  if (!root || !state.catalog) return;
  const admin = state.me?.role === "admin";
  root.hidden = !admin;
  if (!admin) return;
  const pack = $("#admin-release-pack");
  const selected = pack.value || $("#catalog-version").value || state.catalog.modVersions[0];
  options(pack, state.catalog.modVersions.map(value => ({ value, label: `${value} · ${state.catalog.modReleaseVersions[value] || value}` })), selected);
  $("#admin-release-label").value = state.catalog.modReleaseVersions[pack.value] || pack.value;
}

async function savePermanentReleaseVersion() {
  if (state.me?.role !== "admin") return;
  const pack = $("#admin-release-pack").value;
  const label = $("#admin-release-label").value.trim();
  if (!label || label.length > 64 || /[\\/\x00-\x1f]/.test(label)) throw new Error(t("invalidReleaseVersion"));
  const payload = await apiRequest("/v1/mod-release-versions", {
    method: "PUT", body: JSON.stringify({ modReleaseVersions: { [pack]: label } })
  });
  state.catalog.modReleaseVersions = { ...state.catalog.modReleaseVersions, ...(payload.modReleaseVersions || {}) };
  await refreshLiveReleaseVersions();
  renderAdminReleaseEditor();
  toast(`Đã lưu ${pack} thành ${label} cho mọi job sau.`);
}

function batchSelections(selector) { return $$(`${selector} input:checked`).map(input => input.value); }

function updateBatchSummary() {
  const count = batchSelections("#batch-devices").length * batchSelections("#batch-mod-versions").length;
  const editions = [$("#batch-lite").checked ? "Lite" : "", $("#batch-plus").checked ? "Plus" : ""].filter(Boolean).join(" + ");
  $("#batch-summary").textContent = `${count} cấu hình${editions ? ` · ${editions}` : ""}`;
}

function renderBatchChoices() {
  if (!state.catalog) return;
  $("#batch-devices").replaceChildren(...state.catalog.devices.map(item => {
    const label = document.createElement("label"); const input = document.createElement("input"); input.type = "checkbox"; input.value = item.product;
    const copy = document.createElement("span"); const name = document.createElement("b"); name.textContent = item.name; const code = document.createElement("small"); code.textContent = item.product;
    copy.append(name, code); label.append(input, copy); return label;
  }));
  $("#batch-mod-versions").replaceChildren(...state.catalog.modVersions.map(value => {
    const label = document.createElement("label"); const input = document.createElement("input"); input.type = "checkbox"; input.value = value;
    const copy = document.createElement("span"); const name = document.createElement("b"); name.textContent = value; const release = document.createElement("small"); release.textContent = state.catalog.modReleaseVersions[value] || value;
    copy.append(name, release); label.append(input, copy); return label;
  }));
  $("#batch-release-version").value = state.catalog.modReleaseVersions[$("#catalog-version").value] || "V5.0";
  updateBatchSummary();
}

function openBatchBuildPage() {
  if (state.me?.role !== "admin") return;
  renderBatchChoices();
  $("#system").classList.add("admin-batch-open"); $("#admin-batch-page").hidden = false;
  window.scrollTo({ top: 0, behavior: "instant" }); $("#admin-batch-back").focus({ preventScroll: true });
  loadLatestBatch().catch(() => {});
}

function closeBatchBuildPage() {
  clearTimeout(state.batchPollTimer); state.batchPollTimer = null;
  $("#system").classList.remove("admin-batch-open"); $("#admin-batch-page").hidden = true;
}

function renderBatch(payload) {
  $("#batch-status").textContent = `${payload.releaseVersion} · ${payload.status} · ${(payload.items || []).length} cấu hình`;
  $("#batch-items").replaceChildren(...(payload.items || []).map(item => {
    const row = document.createElement("article"); const head = document.createElement("div"); const title = document.createElement("strong"); title.textContent = `${item.device} · ${item.modVersion}`;
    const status = document.createElement("span"); status.textContent = `${item.status}${item.stage ? ` · ${item.stage}` : ""} · ${Math.round(Number(item.progress || 0) * 100)}%`; head.append(title, status);
    const detail = document.createElement("small"); detail.textContent = item.error || item.sourceVersion || "Đang chờ tìm ROM nguồn"; row.append(head, detail);
    if (Array.isArray(item.jobEvents) && item.jobEvents.length) {
      const log = document.createElement("details"); const summary = document.createElement("summary"); summary.textContent = `Log job · ${item.jobEvents.length} sự kiện`;
      const lines = document.createElement("div"); lines.className = "batch-job-log";
      lines.append(...item.jobEvents.slice().reverse().map(event => {
        const line = document.createElement("p"); const time = document.createElement("time"); time.textContent = formatDate(event.timestamp);
        const copy = document.createElement("span"); copy.textContent = event.message || event.error || event.warning || `${readableEventType(event.type)}${event.stage ? ` · ${readableEventStage(event.stage)}` : ""}`;
        line.append(time, copy); return line;
      }));
      log.append(summary, lines); row.append(log);
    }
    return row;
  }));
  $("#batch-events").replaceChildren(...(payload.events || []).slice().reverse().map(item => {
    const row = document.createElement("article"); const time = document.createElement("time"); time.textContent = formatDate(item.createdAt); const message = document.createElement("span"); message.textContent = item.message || item.eventType; row.append(time, message); return row;
  }));
  if (["succeeded", "partial", "failed", "cancelled"].includes(payload.status)) {
    localStorage.removeItem("wukong-batch-request");
    localStorage.removeItem("wukong-active-batch");
    state.activeBatchId = "";
  }
}

async function loadBatch() {
  if (!state.activeBatchId || state.me?.role !== "admin" || $("#admin-batch-page").hidden) return;
  clearTimeout(state.batchPollTimer);
  const payload = await apiRequest(`/v1/admin/batch-builds/${encodeURIComponent(state.activeBatchId)}`);
  renderBatch(payload);
  if (!["succeeded", "partial", "failed", "cancelled"].includes(payload.status)) state.batchPollTimer = setTimeout(() => loadBatch().catch(() => {}), 10000);
}

async function loadLatestBatch() {
  if (state.activeBatchId) return loadBatch();
  const payload = await apiRequest("/v1/admin/batch-builds");
  const latest = Array.isArray(payload.batches) ? payload.batches[0] : null;
  if (!latest?.batchId) return;
  state.activeBatchId = latest.batchId;
  return loadBatch();
}

async function startBatchBuild() {
  const devices = batchSelections("#batch-devices"), modVersions = batchSelections("#batch-mod-versions");
  const editions = [$("#batch-lite").checked ? "lite" : "", $("#batch-plus").checked ? "plus" : ""].filter(Boolean);
  if (!devices.length || !modVersions.length || !editions.length) throw new Error("Hãy chọn ít nhất một thiết bị, một nền MOD và một bản Lite/Plus.");
  const button = $("#start-batch-build"); button.disabled = true;
  try {
    const body = JSON.stringify({ devices, modVersions, editions, releaseVersion: $("#batch-release-version").value.trim() });
    let pending = null;
    try { pending = JSON.parse(localStorage.getItem("wukong-batch-request") || "null"); } catch (_) {}
    if (!pending || pending.body !== body || !pending.key) {
      pending = { body, key: crypto.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}` };
      localStorage.setItem("wukong-batch-request", JSON.stringify(pending));
    }
    const payload = await apiRequest("/v1/admin/batch-builds", { method: "POST", headers: { "Idempotency-Key": pending.key }, body });
    state.activeBatchId = payload.batchId;
    localStorage.setItem("wukong-active-batch", state.activeBatchId);
    pending.batchId = payload.batchId;
    localStorage.setItem("wukong-batch-request", JSON.stringify(pending));
    $("#batch-status").textContent = `${payload.releaseVersion} · ${payload.status} · ${payload.itemCount} cấu hình`;
    toast(`Đã tạo ${payload.itemCount} cấu hình batch build.`);
    loadBatch().catch(error => toast(`Batch đã được tạo; chưa tải được tiến độ: ${error.message}`, true));
  } finally { button.disabled = false; }
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
  const authenticated = Boolean(effectiveInitData() || activeSignedLaunchToken());
  const keyboardConnected = telegramTransportAvailable();
  const sessionAvailable = authenticated || keyboardConnected;
  const connected = miniApiAvailable();
  const connection = $("#telegram-state");
  const connectionText = connection?.querySelector("span");
  if (connectionText) {
    const stateKey = connected ? "connected" : sessionAvailable ? "apiSessionOnly" : "previewMode";
    connectionText.dataset.i18n = stateKey;
    connectionText.textContent = t(stateKey);
  }
  connection?.classList.toggle("preview", !connected);
  $("#telegram-health")?.classList.toggle("ok", connected);
  const authText = $("#telegram-auth-state");
  if (authText) {
    const stateKey = connected ? "authenticated" : sessionAvailable ? "apiUnavailableMessage" : "authenticatedPreview";
    authText.dataset.i18n = stateKey;
    authText.textContent = t(stateKey);
  }
}

function updatePipelineCount() {
  const all = $$("#steps input");
  const selected = all.filter((input) => input.checked).length;
  if ($("#pipeline-count")) $("#pipeline-count").textContent = `${selected}/${all.length}`;
}

function setMods(mode) {
  const defaults = new Set(defaultMods());
  $$("#mod-list input").forEach((input) => { input.checked = mode === "all" || (mode === "defaults" && defaults.has(input.value)); });
  if (mode !== "defaults") $("#preset").value = "custom";
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
  const selectedDevice = $("#device")?.value || "";
  const device = selectedDevice || "—";
  const preset = $("#preset")?.value || "plus";
  const runner = runnerLabel($("#execution")?.value || "github-auto");
  const release = selectedReleaseVersion();
  $("#route-label").textContent = runner;
  const summary = `${device} · ${release} / ${preset === "custom" ? t("custom") : preset.toUpperCase()} / ${runner}`;
  $("#launch-summary").textContent = summary;
  if ($("#mobile-launch-summary")) $("#mobile-launch-summary").textContent = summary;
  $("#mod-count").textContent = `${selectedMods().length} ${t("selected")}`;
  const currentUri = $("#source-uri")?.value?.trim() || "";
  const sourceDetection = classifySource(currentUri);
  const sourceReady = Boolean(sourceDetection?.valid);
  const apiReady = miniApiAvailable();
  const quotaReady = Boolean(
    state.me?.accessStatus === "approved"
    && (state.me?.unlimited || Number(state.me?.buildCredits || 0) > 0)
  );
  const sourceVerified = sourceDetection?.kind === "rclone"
    ? sourceReady
    : sourceReady && state.sourceProbeUri === currentUri && ["analyzed", "partial"].includes(state.sourceProbe?.status);
  const sourceNeedsRefresh = sourceReady && state.sourceProbeUri === currentUri && state.sourceProbe?.status === "preview-only";
  const runnerReady = Boolean($("#execution")?.value);
  const ready = sourceVerified && Boolean(selectedDevice) && runnerReady && apiReady && quotaReady;
  const completedChecks = [sourceVerified, Boolean(selectedDevice), runnerReady, apiReady && quotaReady].filter(Boolean).length;
  const docket = $(".dispatch-docket");
  docket?.classList.toggle("incomplete", !ready);
  const runtimeState = $("#runtime-pipeline-state");
  const runtimeDot = $("#runtime-pipeline-dot");
  if (runtimeState) runtimeState.textContent = t(ready ? "runtimeReady" : "runtimeWaiting");
  runtimeDot?.classList.toggle("waiting", !ready);
  runtimeDot?.classList.toggle("online", ready);
  if ($("#readiness-label")) $("#readiness-label").textContent = t(ready ? "readyLabel" : "incompleteLabel");
  if ($("#readiness-count")) $("#readiness-count").textContent = t("readinessProgress", { done: completedChecks });
  if ($("#launch-warning")) {
    const warningKey = ready ? "fallbackWarning" : !apiReady ? "apiRequiredHint" : !quotaReady ? "quotaRequiredHint" : sourceNeedsRefresh ? "probeSignedPreviewOnly" : sourceReady && !sourceVerified ? "sourceProbePendingHint" : sourceReady ? "chooseDeviceHint" : "completeSourceHint";
    $("#launch-warning").textContent = t(warningKey);
  }
  const recovery = $("#session-recovery");
  if (recovery) recovery.hidden = apiReady || !miniApiEndpoint;
  const connect = $("#connect-telegram");
  if (connect) {
    connect.disabled = state.pairingInFlight;
    connect.textContent = state.pairingInFlight ? t("pairingWaiting") : t("pairingButton");
  }
  updateChecklistItem("check-source", sourceVerified, "checklistSourceVerified", sourceNeedsRefresh ? "checklistSourceRefreshRequired" : sourceReady ? "checklistSourceProbePending" : "checklistSourcePending");
  updateChecklistItem("check-device", Boolean(selectedDevice), "checklistDeviceDone", "checklistDevicePending");
  updateChecklistItem("check-runner", runnerReady, "checklistRunnerDone", "checklistRunnerDone");
  updateChecklistItem("check-api", apiReady && quotaReady, "checklistApiDone", miniApiEndpoint ? "checklistApiAuthPending" : "checklistApiPending");
  if ($("#submit-recipe")) $("#submit-recipe").disabled = !ready;
  updateDeliveryStates();
  $$('[data-i18n="launch"], [data-i18n="finishSource"]').forEach((node) => {
    node.dataset.i18n = ready ? "launch" : "finishSource";
    node.textContent = t(ready ? "launch" : "finishSource");
  });
  $("#dispatch-fab")?.setAttribute("aria-label", t("fabBuild"));
}

function profileInitials(profile) {
  const label = String(profile?.displayName || profile?.username || profile?.telegramId || "WK").trim();
  const parts = label.split(/\s+/).filter(Boolean);
  return (parts.length > 1 ? `${parts[0][0]}${parts.at(-1)[0]}` : label.slice(0, 2)).toUpperCase();
}

function profileAvatar(profile, className = "") {
  const root = document.createElement("div");
  root.className = `profile-avatar ${className}`.trim();
  const fallback = document.createElement("span");
  fallback.textContent = profileInitials(profile);
  root.append(fallback);
  if (profile?.photoUrl) {
    const image = document.createElement("img");
    image.src = profile.photoUrl;
    image.alt = "";
    image.referrerPolicy = "no-referrer";
    image.addEventListener("error", () => image.remove(), { once: true });
    root.prepend(image);
  }
  const hue = [...String(profile?.telegramId || "wukong")].reduce((total, char) => total + char.charCodeAt(0), 0) % 360;
  root.style.setProperty("--avatar-hue", String(hue));
  return root;
}

function renderProfileTrigger(button, profile) {
  if (!button) return;
  button.hidden = !profile;
  if (!profile) return;
  const avatar = profileAvatar(profile);
  button.replaceChildren(...avatar.childNodes);
  button.style.setProperty("--avatar-hue", avatar.style.getPropertyValue("--avatar-hue"));
  if (profile.photoUrl) button.style.setProperty("--avatar-image", `url(${JSON.stringify(String(profile.photoUrl))})`);
  else button.style.removeProperty("--avatar-image");
  button.setAttribute("aria-label", t("openProfile"));
}

function profileValue(key, profile) {
  const values = {
    telegramId: profile.telegramId,
    username: profile.username ? `@${profile.username}` : "—",
    displayName: profile.displayName || "—",
    accessStatus: accessLabel(profile.accessStatus),
    role: t(profile.role === "admin" ? "roleAdmin" : "roleUser"),
    buildCredits: profile.unlimited ? t("unlimited") : String(profile.buildCredits || 0),
    unlimited: profile.unlimited ? t("yes") : t("no"),
    lifetimeGranted: String(profile.lifetimeGranted || 0),
    lifetimeUsed: String(profile.lifetimeUsed || 0),
    jobCount: String(profile.jobCount || 0),
    firstSeenAt: formatDate(profile.firstSeenAt),
    lastSeenAt: formatDate(profile.lastSeenAt),
    lastJobId: profile.lastJobId || "—",
    lastJobStatus: profile.lastJobStatus || "—",
    language: String(profile.language || "—").toUpperCase(),
    platform: profile.platform || "—",
    appVersion: profile.appVersion || "—",
    approvedAt: formatDate(profile.approvedAt),
    revokedAt: formatDate(profile.revokedAt),
    accessActor: profile.accessActor || "—",
    accessReason: profile.accessReason || "—",
    configuredAdmin: profile.configuredAdmin ? t("configuredAdminYes") : t("configuredAdminNo")
  };
  return values[key] ?? "—";
}

function profileLabel(key) {
  const labels = {
    telegramId: "Telegram ID", username: "Username", displayName: t("displayName"),
    accessStatus: t("profileStatus"), role: t("role"), buildCredits: t("allowance"),
    unlimited: t("unlimitedLabel"), lifetimeGranted: t("lifetimeGrantedLabel"), lifetimeUsed: t("lifetimeUsedLabel"),
    jobCount: t("jobCount"), firstSeenAt: t("firstAccess"), lastSeenAt: t("lastAccess"),
    lastJobId: t("lastJob"), lastJobStatus: t("lastJobStatusLabel"), language: t("languageLabel"),
    platform: t("platformLabel"), appVersion: t("appVersionLabel"), approvedAt: t("approvedAt"),
    revokedAt: t("revokedAt"), accessActor: t("accessActor"), accessReason: t("accessReason"),
    configuredAdmin: t("profileConfiguredAdmin")
  };
  return labels[key] || key;
}

function profileFact(key, profile) {
  const fact = document.createElement("div");
  fact.className = "profile-fact";
  const label = document.createElement("small");
  label.textContent = profileLabel(key);
  const value = document.createElement("strong");
  value.textContent = profileValue(key, profile);
  fact.append(label, value);
  return fact;
}

function profileGroup(titleKey, keys, profile) {
  const section = document.createElement("section");
  section.className = "profile-fact-group";
  const title = document.createElement("h2");
  title.textContent = t(titleKey);
  const facts = document.createElement("div");
  facts.className = "profile-fact-list";
  facts.append(...keys.map((key) => profileFact(key, profile)));
  section.append(title, facts);
  return section;
}

function profileHighlight(label, value, tone) {
  const node = document.createElement("div");
  node.className = `profile-highlight ${tone}`;
  const small = document.createElement("small");
  small.textContent = label;
  const strong = document.createElement("strong");
  strong.textContent = value;
  node.append(small, strong);
  return node;
}

function renderProfileView() {
  const profile = state.me;
  if (!profile) return;
  const avatarRoot = $("#profile-view-avatar");
  const avatar = profileAvatar(profile, "profile-avatar-hero");
  avatar.id = "profile-view-avatar";
  avatarRoot?.replaceWith(avatar);
  $("#profile-view-name").textContent = profile.displayName || profile.username || profile.telegramId;
  $("#profile-view-handle").textContent = profile.username ? `@${profile.username} · ${profile.telegramId}` : profile.telegramId;
  const scene = $("#profile-scene");
  scene?.style.setProperty("--profile-image", profile.photoUrl ? `url("${String(profile.photoUrl).replaceAll('"', '\\"')}")` : "none");
  scene?.style.setProperty("--avatar-hue", avatar.style.getPropertyValue("--avatar-hue"));

  const badgeRoot = $("#profile-view-badges");
  const access = document.createElement("span");
  access.className = `profile-badge ${profile.accessStatus || "pending"}`;
  access.textContent = accessLabel(profile.accessStatus);
  const role = document.createElement("span");
  role.className = "profile-badge";
  role.textContent = t(profile.role === "admin" ? "roleAdmin" : "roleUser");
  badgeRoot?.replaceChildren(access, role);

  $("#profile-highlights")?.replaceChildren(
    profileHighlight(t("profileBuilds"), profile.unlimited ? "∞" : String(profile.buildCredits || 0), "builds"),
    profileHighlight(t("profileJobs"), String(profile.jobCount || 0), "jobs"),
    profileHighlight(t("profileAccess"), accessLabel(profile.accessStatus), "access")
  );

  const groups = [
    ["profileIdentityGroup", ["telegramId", "username", "displayName", "role"]],
    ["profileAccessGroup", ["accessStatus", "buildCredits", "unlimited", "lifetimeGranted", "lifetimeUsed", "configuredAdmin"]],
    ["profileActivityGroup", ["jobCount", "firstSeenAt", "lastSeenAt", "lastJobId", "lastJobStatus", "approvedAt", "revokedAt"]],
    ["profileClientGroup", ["language", "platform", "appVersion", "accessActor", "accessReason"]]
  ];
  const grouped = new Set(groups.flatMap(([, keys]) => keys));
  const extra = Object.keys(profile).filter((key) => !grouped.has(key) && !["miniAppOpenCount", "photoUrl"].includes(key));
  const nodes = groups
    .map(([title, keys]) => profileGroup(title, keys.filter((key) => key in profile), profile))
    .filter((group) => group.querySelector(".profile-fact"));
  if (extra.length) nodes.push(profileGroup("profileMoreGroup", extra, profile));
  $("#profile-detail-grid")?.replaceChildren(...nodes);
}

function initializeApprovedWorkspace() {
  if (state.me?.accessStatus !== "approved") return;
  if (state.maintenance?.enabled && state.me?.role !== "admin") {
    renderAccessGate();
    return;
  }
  document.body.classList.remove("access-checking", "access-limited", "maintenance-limited");
  $("#access-gate").hidden = true;
  $("#maintenance-gate").hidden = true;
  if (state.workspaceLoaded) return;
  state.workspaceLoaded = true;
  navigate(location.hash.slice(1) || "build", false);
  loadCatalog().finally(() => requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: "auto" })));
  refreshLiveReleaseVersions().catch(() => {});
  loadJobs({ force: true }).catch(() => {});
}

function renderAccessGate() {
  const profile = state.me;
  const gate = $("#access-gate");
  if (!gate) return;
  const maintenanceGate = $("#maintenance-gate");
  const maintenanceLimited = Boolean(state.maintenance?.enabled && profile?.role !== "admin");
  if (maintenanceLimited) {
    document.body.classList.remove("access-checking", "access-limited");
    document.body.classList.add("maintenance-limited");
    gate.hidden = true;
    maintenanceGate.hidden = false;
    $("#maintenance-gate-message").textContent = state.maintenance.message || t("maintenanceGateTitle");
    clearTimeout(state.jobsPollTimer);
    clearTimeout(state.sourceProbeTimer);
    state.sourceProbeController?.abort();
    $$("dialog[open]").forEach((dialog) => dialog.close());
    clearTimeout(state.maintenancePollTimer);
    if (!document.hidden) state.maintenancePollTimer = setTimeout(() => {
      loadSession({ countOpen: false }).catch(() => renderAccessGate());
    }, 30000);
    return;
  }
  const wasLimited = document.body.classList.contains("maintenance-limited");
  clearTimeout(state.maintenancePollTimer);
  document.body.classList.remove("maintenance-limited");
  maintenanceGate.hidden = true;
  const approved = profile?.accessStatus === "approved";
  if (approved) {
    initializeApprovedWorkspace();
    if (wasLimited && state.workspaceLoaded) loadJobs().catch(() => {});
    return;
  }
  document.body.classList.remove("access-checking");
  document.body.classList.add("access-limited");
  gate.hidden = false;
  const status = profile?.accessStatus === "revoked" ? "Revoked" : profile ? "Pending" : "Connect";
  $("#access-kicker").textContent = t(`access${status}Kicker`);
  $("#access-title").textContent = t(`access${status}Title`);
  $("#access-message").textContent = t(`access${status}Message`);
  const facts = $("#access-profile");
  facts.hidden = !profile;
  if (profile) {
    $("#access-name").textContent = profile.displayName || "—";
    $("#access-username").textContent = profile.username ? `@${profile.username}` : "—";
    $("#access-id").textContent = profile.telegramId || "—";
    $("#access-meta").textContent = [
      profile.language ? profile.language.toUpperCase() : "",
      profile.platform || "",
      profile.appVersion ? `v${profile.appVersion}` : ""
    ].filter(Boolean).join(" · ") || "—";
    $("#access-avatar").replaceWith(profileAvatar(profile, "profile-avatar-large"));
    const avatar = $(".access-card .profile-avatar");
    if (avatar) avatar.id = "access-avatar";
  }
}

function renderMaintenanceAdmin() {
  const maintenance = state.maintenance || { enabled: false, message: "" };
  const enabled = Boolean(maintenance.enabled);
  const input = $("#maintenance-message-input");
  const toggle = $("#maintenance-toggle");
  const badge = $("#maintenance-state-badge");
  if (input && !state.maintenanceMessageDirty) {
    input.value = maintenance.message || "Hệ thống đang được bảo trì. Vui lòng quay lại sau.";
  }
  if (toggle) {
    toggle.classList.toggle("enabled", enabled);
    toggle.querySelector("span").textContent = t(enabled ? "disableMaintenance" : "enableMaintenance");
  }
  if (badge) {
    badge.classList.toggle("enabled", enabled);
    badge.textContent = enabled ? "BẢO TRÌ" : "ĐANG MỞ";
  }
  const status = $("#maintenance-admin-status");
  if (status) status.textContent = t(enabled ? "maintenanceClosedStatus" : "maintenanceOpenStatus");
}

function renderAccount() {
  const profile = state.me;
  renderProfileTrigger($("#dock-profile"), profile);
  renderProfileView();
  renderGreeting();
  scheduleGreeting();
  $("#user-admin").hidden = true;
  $("#admin-maintenance").hidden = true;
  $("#admin-batch-launch").hidden = true;
  $("#catalog-release-admin").hidden = true;
  if (!profile || profile.role !== "admin") closeAdminUserPage({ restoreFocus: false, scroll: false });
  if (!profile) return;
  const runtimeAllowance = $("#runtime-build-allowance");
  if (runtimeAllowance) {
    const values = {
      used: Number(profile.lifetimeUsed || 0),
      jobs: Number(profile.jobCount || 0)
    };
    runtimeAllowance.textContent = profile.unlimited
      ? t("allowanceUnlimitedSummary", values)
      : t("allowanceSummary", {
          ...values,
          remaining: String(Number(profile.buildCredits || 0))
        });
  }
  const admin = profile.role === "admin";
  $("#user-admin").hidden = !admin;
  $("#admin-maintenance").hidden = !admin;
  $("#admin-batch-launch").hidden = !admin;
  renderAdminReleaseEditor();
  renderMaintenanceAdmin();
  renderAccessGate();
}

async function loadSession({ countOpen = true } = {}) {
  if (!miniApiAvailable()) return null;
  const payload = await apiRequest(countOpen ? "/v1/session/open" : "/v1/me", {
    method: countOpen ? "POST" : "GET"
  });
  state.me = payload.user || null;
  state.maintenance = payload.maintenance || state.maintenance;
  renderAccount();
  updateSummary();
  if (state.me?.role === "admin") loadAdminUsers().catch(() => {});
  return state.me;
}

async function updateMaintenance() {
  if (state.me?.role !== "admin") return;
  const button = $("#maintenance-toggle");
  const enabled = !Boolean(state.maintenance?.enabled);
  const message = $("#maintenance-message-input").value.trim();
  if (!message) {
    toast(t("maintenanceMessage"), true);
    return;
  }
  button.disabled = true;
  try {
    const payload = await apiRequest("/v1/system/maintenance", {
      method: "PUT",
      body: JSON.stringify({ enabled, message })
    });
    state.maintenance = payload.maintenance;
    state.maintenanceMessageDirty = false;
    renderMaintenanceAdmin();
    toast(t(enabled ? "maintenanceEnabledToast" : "maintenanceDisabledToast"));
  } finally {
    button.disabled = false;
  }
}

function renderRomDevices() {
  const selected = state.romDevices.find((device) => device.id === $("#rom-device-filter").value);
  $("#rom-device-label").textContent = selected?.label || t("romDeviceChoose");
  const status = state.romDevicesStatus;
  $("#rom-devices-retry").hidden = status !== "error";
  const target = $("#rom-device-options");
  target.setAttribute("aria-busy", String(status === "loading"));
  target.replaceChildren();
  if (status !== "ready") {
    $("#rom-device-status").textContent = t(status === "error" ? "romDevicesError" : "romDevicesLoading");
    return;
  }
  const searchKey = (value) => String(value).toLocaleLowerCase().replace(/[\s_-]+/g, "");
  const query = searchKey($("#rom-device-search").value);
  const devices = state.romDevices.filter((device) => [device.id, device.label,
    ...device.regions.flatMap((region) => region.models)].some((value) => searchKey(value).includes(query)));
  $("#rom-device-status").textContent = devices.length ? t("romDevicesCount", { count: devices.length }) : t("romDevicesEmpty");
  const clear = document.createElement("button");
  clear.type = "button";
  clear.className = "rom-device-clear";
  clear.textContent = t("romDeviceClear");
  clear.addEventListener("click", () => chooseRomDevice(null));
  target.append(clear);
  const groups = new Map();
  devices.forEach((device) => {
    if (!groups.has(device.brand)) groups.set(device.brand, []);
    groups.get(device.brand).push(device);
  });
  groups.forEach((items, brand) => {
    const heading = document.createElement("h3");
    heading.textContent = `${brand} · ${items.length}`;
    target.append(heading);
    items.forEach((device) => {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.romDevice = device.id;
      button.setAttribute("aria-pressed", String(selected?.id === device.id));
      const label = document.createElement("span");
      label.textContent = device.label;
      const regions = document.createElement("small");
      regions.textContent = device.regions.map((region) => region.code).join(" · ");
      button.append(label, regions);
      button.addEventListener("click", () => chooseRomDevice(device));
      target.append(button);
    });
  });
}

async function loadRomDevices() {
  if (!privateApiAvailable() || ["loading", "ready"].includes(state.romDevicesStatus)) return;
  state.romDevicesStatus = "loading";
  renderRomDevices();
  try {
    const payload = await apiRequest("/v1/rom-catalog/devices");
    if (!Array.isArray(payload.devices)) throw new Error("Invalid device catalog");
    state.romDevices = payload.devices.filter((device) => ["oneplus", "oppo", "realme"].includes(String(device.brand).toLowerCase()));
    state.romDevicesStatus = "ready";
  } catch (_) {
    state.romDevicesStatus = "error";
  }
  renderRomDevices();
}

function chooseRomDevice(device) {
  $("#rom-device-filter").value = device?.id || "";
  const region = $("#rom-region-filter");
  const codes = device ? device.regions.map((entry) => entry.code) : ["CN", "EU", "GLO", "IN", "NA"];
  region.replaceChildren(new Option(t("romAllRegions"), ""), ...codes.map((code) => new Option(code, code)));
  region.options[0].dataset.i18n = "romAllRegions";
  $("#rom-device-picker").open = false;
  $("#rom-device-picker summary").focus();
  $("#rom-device-search").value = "";
  state.romCatalogRequestId += 1;
  state.romCatalogStatus = "idle";
  state.romCatalogReleases = [];
  resetRomResolved();
  renderRomVersions(false);
  $("#search-rom-catalog").disabled = false;
  renderRomDevices();
  renderRomCatalogResults();
  if (device) searchRomCatalog();
}

function resetRomResolved() {
  state.romResolveController?.abort();
  state.romResolveController = null;
  state.romResolved = null;
}

function filteredRomReleases() {
  const region = $("#rom-region-filter").value;
  return state.romCatalogReleases.filter((release) => !region || release.region === region);
}

function renderRomVersions(preserve = true) {
  const select = $("#rom-version-filter");
  const previous = preserve ? select.value : "";
  const releases = state.romCatalogStatus === "ready" ? filteredRomReleases() : [];
  select.replaceChildren(...releases.map((release) => new Option(`${release.version || release.otaVersion} · ${release.region}`, release.id)));
  select.disabled = !releases.length;
  if (!releases.length) select.add(new Option(t(state.romCatalogStatus === "loading" ? "romCatalogLoading" : state.romCatalogStatus === "ready" ? "romCatalogEmpty" : "romChooseDeviceFirst"), ""));
  else if (releases.some((release) => release.id === previous)) select.value = previous;
}

async function resolveRomRelease(release) {
  if (state.romResolved?.status === "loading") return;
  const controller = new AbortController();
  state.romResolveController = controller;
  let timedOut = false;
  const timeout = setTimeout(() => { timedOut = true; controller.abort(); }, 70_000);
  state.romResolved = { id: release.id, status: "loading" };
  renderRomCatalogResults();
  try {
    const payload = await apiRequest("/v1/sources/resolve", {
      method: "POST", body: JSON.stringify({ uri: release.sourceUrl }), signal: controller.signal
    });
    if (controller.signal.aborted || $("#rom-version-filter").value !== release.id) return;
    const url = new URL(payload.resolvedUrl);
    if (!["https:", "http:"].includes(url.protocol)) throw new Error("Invalid resolved link");
    state.romResolved = { id: release.id, status: "ready", url: url.toString(), expiresAt: payload.signedUrlExpiresAt };
  } catch (error) {
    if ((controller.signal.aborted && !timedOut) || $("#rom-version-filter").value !== release.id) return;
    state.romResolved = { id: release.id, status: "error" };
  } finally {
    clearTimeout(timeout);
    if (state.romResolveController === controller) {
      state.romResolveController = null;
      renderRomCatalogResults();
    }
  }
}

function renderRomCatalogResults() {
  const target = $("#rom-catalog-results");
  if (!target) return;
  const status = state.romCatalogStatus;
  target.setAttribute("aria-busy", String(status === "loading"));
  $("#rom-catalog-status").textContent = status === "ready"
    ? t("romCatalogCount", { count: filteredRomReleases().length })
    : status === "loading" ? t("romCatalogLoading") : "";
  if (status !== "ready") {
    const empty = document.createElement("div");
    empty.className = "rom-catalog-empty";
    const title = document.createElement("strong");
    title.textContent = t(status === "loading" ? "romCatalogLoading" : status === "error" ? "romCatalogRetry" : "romCatalogIdle");
    empty.append(title);
    if (status === "idle") {
      const hint = document.createElement("p");
      hint.textContent = t("romCatalogIdleHint");
      empty.append(hint);
    }
    target.replaceChildren(empty);
    return;
  }
  if (!filteredRomReleases().length) {
    const empty = document.createElement("p");
    empty.className = "rom-catalog-empty";
    empty.textContent = t("romCatalogEmpty");
    target.replaceChildren(empty);
    return;
  }
  target.replaceChildren(...filteredRomReleases().filter((release) => release.id === $("#rom-version-filter").value).map((release) => {
    const row = document.createElement("article");
    row.className = "rom-release";
    const copy = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = [release.device || release.model || "ROM", release.region].filter(Boolean).join(" · ");
    const version = document.createElement("p");
    version.className = "rom-release-version";
    version.textContent = release.version || release.otaVersion || "—";
    const meta = document.createElement("small");
    meta.textContent = [
      release.model,
      release.securityPatch ? `${t("securityPatch")}: ${release.securityPatch}` : "",
      Number(release.sizeBytes) > 0 ? formatBytes(release.sizeBytes) : ""
    ].filter(Boolean).join(" · ");
    copy.append(title, version, meta);
    const use = document.createElement("button");
    use.type = "button";
    use.dataset.romAction = "analyze";
    use.textContent = t("useRom");
    use.addEventListener("click", () => {
      const source = $("#source-uri");
      source.value = release.sourceUrl;
      source.dispatchEvent(new Event("input", { bubbles: true }));
      navigate("build");
      source.focus({ preventScroll: true });
      toast(t("romSelected"));
    });
    const actions = document.createElement("div");
    actions.className = "rom-release-actions";
    const copyLink = document.createElement("button");
    copyLink.type = "button";
    copyLink.dataset.romAction = "copy";
    copyLink.textContent = t("romCopyLink");
    copyLink.addEventListener("click", () => copyText(release.sourceUrl).then(() => toast(t("romLinkCopied"))).catch(() => toast(t("clipboardDenied"), true)));
    const resolve = document.createElement("button");
    resolve.type = "button";
    resolve.dataset.romAction = "resolve";
    const resolved = state.romResolved?.id === release.id ? state.romResolved : null;
    resolve.disabled = resolved?.status === "loading";
    resolve.textContent = t(resolve.disabled ? "romResolving" : "romResolve");
    resolve.addEventListener("click", () => resolveRomRelease(release));
    actions.append(copyLink, resolve, use);
    row.append(copy, actions);
    if (resolved?.status === "error") {
      const error = document.createElement("p");
      error.className = "rom-resolve-error";
      error.setAttribute("role", "alert");
      error.textContent = t("romResolveFailed");
      row.append(error);
    }
    if (resolved?.status === "ready") {
      const result = document.createElement("div");
      result.className = "rom-resolved-result";
      const label = document.createElement("label");
      label.textContent = t("romResolvedLabel");
      const link = document.createElement("textarea");
      link.className = "rom-resolved-url";
      link.readOnly = true;
      link.rows = 2;
      link.value = resolved.url;
      label.append(link);
      const hint = document.createElement("p");
      hint.textContent = t("romResolvedHint");
      const resolvedCopy = document.createElement("button");
      resolvedCopy.type = "button";
      resolvedCopy.dataset.romAction = "copy-resolved";
      resolvedCopy.textContent = t("romResolvedCopy");
      resolvedCopy.addEventListener("click", () => copyText(resolved.url).then(() => toast(t("romResolvedCopied"))).catch(() => { link.focus(); link.select(); toast(t("clipboardDenied"), true); }));
      result.append(label, hint, resolvedCopy);
      row.append(result);
    }
    return row;
  }));
  if (state.romCatalogTruncated) {
    const note = document.createElement("p");
    note.textContent = t("romVersionsTruncated");
    target.append(note);
  }
}

async function searchRomCatalog() {
  if (state.romCatalogStatus === "loading") return;
  const button = $("#search-rom-catalog");
  const params = new URLSearchParams({ latest: "0" });
  const filters = {
    device: $("#rom-device-filter").value.trim(),
    region: $("#rom-region-filter").value.trim()
  };
  if (!filters.device) {
    toast(t("romFilterRequired"), true);
    $("#rom-device-picker").open = true;
    $("#rom-device-search").focus();
    return;
  }
  Object.entries(filters).forEach(([key, value]) => {
    if (value) params.set(key, value);
  });
  button.disabled = true;
  const requestId = ++state.romCatalogRequestId;
  resetRomResolved();
  state.romCatalogStatus = "loading";
  renderRomVersions(false);
  renderRomCatalogResults();
  try {
    const payload = await apiRequest(`/v1/rom-catalog?${params.toString()}`);
    if (requestId !== state.romCatalogRequestId) return;
    state.romCatalogReleases = Array.isArray(payload.releases) ? payload.releases : [];
    state.romCatalogStatus = "ready";
    state.romCatalogTruncated = payload.truncated === true;
    renderRomVersions(false);
    renderRomCatalogResults();
  } catch (error) {
    if (requestId !== state.romCatalogRequestId) return;
    state.romCatalogReleases = [];
    state.romCatalogStatus = "error";
    renderRomVersions(false);
    renderRomCatalogResults();
  } finally {
    if (requestId === state.romCatalogRequestId) button.disabled = false;
  }
}

function selectLibraryTab(name, focus = false) {
  const rom = name === "rom";
  $("#rom-catalog-panel").hidden = !rom;
  $("#library-technical").hidden = rom;
  $$('[data-library-tab]').forEach((button) => {
    const selected = button.dataset.libraryTab === name;
    button.setAttribute("aria-selected", String(selected));
    button.tabIndex = selected ? 0 : -1;
    if (selected && focus) button.focus();
  });
}

function accessLabel(status) { return t(["pending", "approved", "revoked"].includes(status) ? status : "pending"); }

function currentActivityTitle(activity) {
  if (activity?.type === "build") return t("userBuildingRom");
  if (activity?.status === "searching") return t("userSearchingRom");
  if (activity?.status === "completed") return t("userRomSearchCompleted", { count: Number(activity.resultCount || 0) });
  return t("userRomSearchFailed");
}

function currentActivityLines(activity) {
  if (!activity) return [];
  if (activity.type === "build") {
    const device = activity.deviceName || catalogDeviceName(activity.productCode) || activity.productCode;
    return [
      [device, activity.productCode].filter(Boolean).join(" · "),
      [activity.preset, activity.modVersion].filter(Boolean).join(" · "),
      [activity.releaseVersion, `${Math.round(Number(activity.progress || 0) * 100)}%`, activity.stage].filter(Boolean).join(" · ")
    ].filter(Boolean);
  }
  const firstResult = Array.isArray(activity.results) ? activity.results[0] || {} : {};
  return [
    [activity.device || activity.model, activity.region].filter(Boolean).join(" · "),
    activity.latest ? t("romLatestOnly") : t("romAllVersions"),
    activity.status === "completed" ? firstResult.version || activity.version || "" : ""
  ].filter(Boolean);
}

function renderCurrentActivitySummary(user, compact = false) {
  const activities = Array.isArray(user.currentActivities) && user.currentActivities.length
    ? user.currentActivities
    : user.currentActivity ? [user.currentActivity] : [];
  const group = document.createElement(compact ? "span" : "section");
  group.className = "user-current-activities";
  if (!activities.length) {
    const section = document.createElement("span");
    section.className = "user-current-activity idle";
    const title = document.createElement("strong"); title.textContent = compact ? t("openCount", { count: user.miniAppOpenCount || 0 }) : t("noCurrentUserActivity");
    const detail = document.createElement("small"); detail.textContent = compact ? `${t("lastAccess")}: ${formatDate(user.lastSeenAt)}` : "";
    section.append(title, detail);
    group.append(section);
    return group;
  }
  activities.forEach((activity) => {
    const section = document.createElement("span");
  section.className = `user-current-activity ${activity?.type || "idle"} ${activity?.status || ""}`;
    const title = document.createElement("strong"); title.textContent = currentActivityTitle(activity);
    const status = document.createElement("i"); status.setAttribute("aria-hidden", "true");
    const heading = document.createElement("span"); heading.append(status, title);
    section.append(heading);
    currentActivityLines(activity).slice(0, 3).forEach((value) => {
      const line = document.createElement("small"); line.textContent = value; section.append(line);
    });
    if (!compact && activity.type === "build" && activity.jobId) {
      const open = document.createElement("button"); open.type = "button"; open.className = "secondary";
      open.textContent = t("openUserJob");
      open.addEventListener("click", () => openAdminJobPage({
        job_id: activity.jobId,
        status: activity.status,
        stage: activity.stage,
        progress: activity.progress,
        createdBy: user,
        recipe: {
          device: activity.productCode,
          build: {
            preset: activity.preset,
            modVersion: activity.modVersion,
            modReleaseVersion: activity.releaseVersion
          }
        }
      }));
      section.append(open);
    }
    group.append(section);
  });
  return group;
}

function renderAdminUsers() {
  const body = $("#user-table-body");
  if (!body) return;
  if (!state.adminUsers.length) {
    const empty = document.createElement("p"); empty.className = "user-empty"; empty.textContent = t("noUsers");
    body.replaceChildren(empty);
  } else body.replaceChildren(...state.adminUsers.map((user) => {
    const row = document.createElement("div"); row.className = "user-row"; row.setAttribute("role", "row");
    const identity = document.createElement("span"); identity.className = "user-identity";
    identity.append(profileAvatar(user, "profile-avatar-small"));
    const identityCopy = document.createElement("span");
    const name = document.createElement("strong"); name.textContent = user.displayName || (user.username ? `@${user.username}` : user.telegramId);
    const id = document.createElement("small"); id.textContent = `${user.telegramId}${user.username ? ` · @${user.username}` : ""}`;
    identityCopy.append(name, id); identity.append(identityCopy);
    const activity = renderCurrentActivitySummary(user, true);
    const quota = document.createElement("span"); quota.className = "user-quota";
    quota.textContent = user.unlimited ? t("unlimited") : `${user.buildCredits || 0} · ${t("jobsCount", { count: user.jobCount || 0 })}`;
    const status = document.createElement("span"); status.className = `access-badge ${user.accessStatus}`; status.textContent = accessLabel(user.accessStatus);
    const open = document.createElement("button"); open.type = "button"; open.className = "user-open"; open.dataset.userId = String(user.telegramId); open.textContent = "›"; open.setAttribute("aria-label", `${t("displayName")}: ${name.textContent}`);
    open.addEventListener("click", () => openAdminUser(user.telegramId).catch((error) => toast(error.message, true)));
    row.append(identity, activity, quota, status, open);
    return row;
  }));
  const start = state.adminUsersTotal ? state.adminUsersOffset + 1 : 0;
  const end = Math.min(state.adminUsersOffset + state.adminUsers.length, state.adminUsersTotal);
  $("#user-page-summary").textContent = `${start}–${end} / ${state.adminUsersTotal}`;
  const counts = state.adminUserStatusCounts;
  $("#user-total-count").textContent = String(counts.approved + counts.pending + counts.revoked);
  $("#user-approved-count").textContent = String(counts.approved);
  $("#user-pending-count").textContent = String(counts.pending);
  $("#user-revoked-count").textContent = String(counts.revoked);
  $("#user-prev").disabled = state.adminUsersOffset <= 0;
  $("#user-next").disabled = end >= state.adminUsersTotal;
}

async function loadAdminUsers({ reset = false } = {}) {
  if (state.me?.role !== "admin" || state.adminUsersLoading) return;
  if (reset) state.adminUsersOffset = 0;
  state.adminUsersLoading = true;
  try {
    const query = encodeURIComponent($("#user-search")?.value?.trim() || "");
    const status = encodeURIComponent($("#user-status")?.value || "");
    const quota = encodeURIComponent($("#user-quota-filter")?.value || "");
    const activity = encodeURIComponent($("#user-activity-filter")?.value || "");
    const sort = encodeURIComponent($("#user-sort")?.value || "lastSeenAt");
    const payload = await apiRequest(`/v1/admin/users?query=${query}&status=${status}&quota=${quota}&activity=${activity}&sort=${sort}&offset=${state.adminUsersOffset}&limit=25`);
    state.adminUsers = Array.isArray(payload.users) ? payload.users : [];
    state.adminUsersTotal = Number(payload.total || 0);
    const statusCounts = payload.statusCounts || {};
    state.adminUserStatusCounts = {
      approved: Number(statusCounts.approved || 0),
      pending: Number(statusCounts.pending || 0),
      revoked: Number(statusCounts.revoked || 0)
    };
    renderAdminUsers();
  } finally {
    state.adminUsersLoading = false;
    clearTimeout(state.adminUsersPollTimer);
    if (!document.hidden && state.me?.role === "admin" && document.body.dataset.view === "system") {
      state.adminUsersPollTimer = setTimeout(() => loadAdminUsers().catch(() => {}), 10000);
    }
  }
}

function detailFact(label, value) {
  const box = document.createElement("div"); const small = document.createElement("small"); const strong = document.createElement("strong");
  small.textContent = label; strong.textContent = value || "—"; box.append(small, strong); return box;
}

function adminAuditArticle(event) {
  const article = document.createElement("article");
  article.dataset.adminEventId = String(event.eventId || `${event.type || "event"}:${event.createdAt || ""}`);
  const name = document.createElement("strong"); name.textContent = event.type;
  const detail = document.createElement("small");
  detail.textContent = `${formatDate(event.createdAt)}${event.actorTelegramId ? ` · ${event.actorTelegramId}` : ""}${event.reason ? ` · ${event.reason}` : ""}`;
  article.append(name, detail);
  if (String(event.type || "").startsWith("rom_search_")) {
    article.classList.add("rom-search-audit");
    const details = event.details || {};
    name.textContent = t(event.type === "rom_search_started"
      ? "romSearchStartedLog"
      : event.type === "rom_search_completed"
        ? "romSearchCompletedLog"
        : "romSearchFailedLog");
    const filters = document.createElement("p");
    filters.textContent = `${t("romSearchFilters")}: ${[details.device || details.model, details.region, details.latest ? t("romLatestOnly") : t("romAllVersions")].filter(Boolean).join(" · ")}`;
    article.append(filters);
    if (Number.isFinite(Number(details.durationMs))) {
      const duration = document.createElement("small");
      duration.textContent = `${t("romSearchDuration")}: ${(Number(details.durationMs) / 1000).toFixed(2)}s`;
      article.append(duration);
    }
    const results = Array.isArray(details.results) ? details.results : [];
    if (event.type === "rom_search_completed") {
      const resultTitle = document.createElement("b");
      resultTitle.textContent = `${t("romSearchResults")}: ${Number(details.resultCount || results.length)}`;
      const list = document.createElement("ul");
      results.forEach((result) => {
        const item = document.createElement("li");
        item.textContent = [result.model, result.version, result.region].filter(Boolean).join(" · ");
        list.append(item);
      });
      article.append(resultTitle, list);
    }
    if (details.error) {
      const error = document.createElement("p"); error.className = "error"; error.textContent = String(details.error); article.append(error);
    }
  }
  return article;
}

function scheduleAdminUserActivityPoll() {
  clearTimeout(state.adminUserPollTimer);
  state.adminUserPollTimer = null;
  if (document.hidden || state.me?.role !== "admin" || !state.selectedAdminUserId || state.adminJobView) return;
  state.adminUserPollTimer = setTimeout(refreshAdminUserActivity, 10000);
}

async function refreshAdminUserActivity() {
  const telegramId = state.selectedAdminUserId;
  clearTimeout(state.adminUserPollTimer);
  state.adminUserPollTimer = null;
  if (!telegramId || document.hidden || state.adminJobView) return;
  try {
    const collected = [];
    let latestUser = null;
    let nextCursor = { ...state.adminUserEventCursor };
    for (let page = 0; page < 4; page += 1) {
      const query = new URLSearchParams({
        afterCreatedAt: nextCursor.createdAt,
        afterEventId: nextCursor.eventId
      });
      const payload = await apiRequest(`/v1/admin/users/${encodeURIComponent(telegramId)}/activity?${query}`);
      if (state.selectedAdminUserId !== telegramId || state.adminJobView) return;
      latestUser = payload.user;
      const events = Array.isArray(payload.events) ? payload.events : [];
      collected.push(...events);
      const consumed = events.at(-1);
      if (consumed?.createdAt) {
        nextCursor = {
          createdAt: String(consumed.createdAt),
          eventId: String(consumed.eventId || "")
        };
      }
      if (!payload.hasMore || !consumed) break;
    }
    if (!latestUser) return;
    const activity = renderCurrentActivitySummary(latestUser);
    activity.id = "admin-user-current-activity";
    $("#admin-user-current-activity")?.replaceWith(activity);
    const audit = $("#admin-user-audit-log");
    if (audit) {
      const existing = new Set([...audit.children].map((node) => node.dataset.adminEventId));
      const incoming = [...collected].reverse()
        .filter((event) => !existing.has(String(event.eventId || `${event.type || "event"}:${event.createdAt || ""}`)))
        .map(adminAuditArticle);
      if (incoming.length) audit.prepend(...incoming);
    }
    state.adminUserEventCursor = nextCursor;
  } catch (_) {
    // Keep the current snapshot and retry without interrupting the admin.
  } finally {
    if (state.selectedAdminUserId === telegramId) scheduleAdminUserActivityPoll();
  }
}

function closeAdminUserPage({ restoreFocus = true, scroll = true } = {}) {
  closeAdminJobPage({ restoreFocus: false, scroll: false, refreshUser: false });
  clearTimeout(state.adminUserPollTimer);
  state.adminUserPollTimer = null;
  const system = $("#system");
  const page = $("#admin-user-page");
  if (!system || !page) return;
  const telegramId = state.selectedAdminUserId;
  system.classList.remove("admin-user-open");
  page.hidden = true;
  state.selectedAdminUserId = "";
  state.adminUserEventCursor = { createdAt: "1970-01-01T00:00:00.000Z", eventId: "" };
  if (scroll) window.scrollTo({ top: state.adminUserReturnScrollY, behavior: prefersReducedMotion() ? "auto" : "smooth" });
  if (restoreFocus && telegramId) {
    requestAnimationFrame(() => $$(".user-open").find((button) => button.dataset.userId === String(telegramId))?.focus());
  }
}

function requestAdminAction(user, action) {
  if (action === "credit-add") return Promise.resolve({ reason: "admin grant" });
  const dialog = $("#admin-action-dialog");
  const form = $("#admin-action-form");
  const valueField = $("#admin-action-value-field");
  const valueInput = $("#admin-action-value");
  const reasonField = $("#admin-action-reason-field");
  const reasonInput = $("#admin-action-reason");
  const error = $("#admin-action-error");
  const confirm = $("#admin-action-confirm");
  const needsValue = ["credit-subtract", "credit-set"].includes(action);
  const needsReason = action === "revoke" || action === "credit-subtract" || (action === "unlimited" && user.unlimited);
  const allowsReason = needsReason || action === "approve" || action === "credit-set";
  $("#admin-action-title").textContent = t({
    approve: "approveUser", revoke: "revokeUser", "credit-subtract": "subtractCredit",
    "credit-set": "setCredit", unlimited: "toggleUnlimited"
  }[action]);
  $("#admin-action-message").textContent = t("adminActionMessage");
  valueField.hidden = !needsValue;
  reasonField.hidden = !allowsReason;
  valueInput.value = action === "credit-set" ? String(user.buildCredits || 0) : "1";
  reasonInput.value = action === "approve" ? "approved by admin" : "";
  error.hidden = true;
  confirm.classList.toggle("danger-confirm", action === "revoke");
  confirm.classList.toggle("primary", action !== "revoke");
  dialog.showModal();
  requestAnimationFrame(() => (needsValue ? valueInput : allowsReason ? reasonInput : confirm).focus());
  return new Promise((resolve) => {
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      form.onsubmit = null;
      resolve(value);
    };
    form.onsubmit = (event) => {
      event.preventDefault();
      if (event.submitter?.value === "cancel") { dialog.close("cancel"); return; }
      const rawValue = valueInput.value.trim();
      const valueValid = !needsValue || /^\d+$/.test(rawValue)
        && (action === "credit-set" || Number(rawValue) > 0);
      if (!valueValid) {
        error.textContent = t("actionValueInvalid");
        error.hidden = false;
        valueInput.focus();
        return;
      }
      const value = needsValue ? Number(rawValue) : undefined;
      const reasonRequired = needsReason || action === "credit-set" && value < Number(user.buildCredits || 0);
      const reason = reasonInput.value.trim();
      if (reasonRequired && !reason) {
        error.textContent = t("actionReasonRequired");
        error.hidden = false;
        reasonInput.focus();
        return;
      }
      dialog.close("confirm");
      finish({ value, reason });
    };
    dialog.addEventListener("close", () => finish(null), { once: true });
  });
}

async function runAdminUserAction(user, action) {
  const input = await requestAdminAction(user, action);
  if (!input) return;
  let path = action; let body = {};
  if (action === "approve" || action === "revoke") body.reason = input.reason;
  if (action === "credit-add") { path = "allowance"; body = { operation: "add", value: 1, reason: input.reason }; }
  if (action === "credit-subtract") { path = "allowance"; body = { operation: "add", value: -input.value, reason: input.reason }; }
  if (action === "credit-set") {
    path = "allowance";
    body = { operation: "set", value: input.value, reason: input.reason || "admin allocation" };
  }
  if (action === "unlimited") {
    path = "allowance";
    const next = !user.unlimited;
    body = { operation: "unlimited", unlimited: next, reason: input.reason || "admin enabled unlimited" };
  }
  await apiRequest(`/v1/admin/users/${encodeURIComponent(user.telegramId)}/${path}`, { method: "POST", body: JSON.stringify(body) });
  toast(t("userUpdated"));
  await loadAdminUsers({ reset: false });
  await openAdminUser(user.telegramId);
}

async function openAdminUser(telegramId) {
  clearTimeout(state.adminUserPollTimer);
  state.adminUserPollTimer = null;
  if (!$("#system")?.classList.contains("admin-user-open")) state.adminUserReturnScrollY = window.scrollY;
  const payload = await apiRequest(`/v1/admin/users/${encodeURIComponent(telegramId)}`);
  const user = payload.user; const events = Array.isArray(payload.events) ? payload.events : []; const jobs = Array.isArray(payload.jobs) ? payload.jobs : [];
  state.selectedAdminUserId = user.telegramId;
  state.adminUserEventCursor = events[0]?.createdAt
    ? { createdAt: String(events[0].createdAt), eventId: String(events[0].eventId || "") }
    : { createdAt: "1970-01-01T00:00:00.000Z", eventId: "" };
  const root = $("#user-detail-content");
  const header = document.createElement("header");
  header.className = "admin-user-hero";
  const titleBox = document.createElement("div"); titleBox.className = "user-detail-title"; titleBox.append(profileAvatar(user));
  const titleCopy = document.createElement("span"); const kicker = document.createElement("small"); kicker.textContent = `TELEGRAM ${user.telegramId}`; const title = document.createElement("h1"); title.id = "admin-user-page-title"; title.textContent = user.displayName || (user.username ? `@${user.username}` : user.telegramId); titleCopy.append(kicker, title); titleBox.append(titleCopy);
  const status = document.createElement("span"); status.className = `access-badge ${user.accessStatus}`; status.textContent = accessLabel(user.accessStatus); header.append(titleBox, status);
  const activityTitle = document.createElement("h3"); activityTitle.textContent = t("currentUserActivity");
  const currentActivity = renderCurrentActivitySummary(user);
  currentActivity.id = "admin-user-current-activity";
  const grid = document.createElement("div"); grid.className = "user-detail-grid";
  grid.append(
    detailFact(t("accessStatus"), accessLabel(user.accessStatus)), detailFact(t("allowance"), user.unlimited ? t("unlimited") : String(user.buildCredits || 0)),
    detailFact(t("firstAccess"), formatDate(user.firstSeenAt)), detailFact(t("lastAccess"), formatDate(user.lastSeenAt)),
    detailFact(t("activity"), `${t("openCount", { count: user.miniAppOpenCount || 0 })} · ${t("jobsCount", { count: user.jobCount || 0 })}`), detailFact(t("lastJob"), `${user.lastJobId || "—"} · ${user.lastJobStatus || "—"}`),
    detailFact("Username", user.username ? `@${user.username}` : "—"), detailFact(t("role"), user.role || "user"),
    detailFact(t("lifetime"), t("lifetimeSummary", { granted: user.lifetimeGranted || 0, used: user.lifetimeUsed || 0 })), detailFact(t("client"), [user.language, user.platform, user.appVersion].filter(Boolean).join(" · ")),
    detailFact(t("approvedAt"), formatDate(user.approvedAt)), detailFact(t("revokedAt"), formatDate(user.revokedAt)),
    detailFact(t("accessActor"), user.accessActor || "—"), detailFact(t("accessReason"), user.accessReason || "—")
  );
  const actions = document.createElement("div"); actions.className = "user-detail-actions";
  const definitions = user.accessStatus === "approved"
    ? [["credit-add", t("addCredit")], ["credit-subtract", t("subtractCredit")], ["credit-set", t("setCredit")], ["unlimited", t("toggleUnlimited")], ["revoke", t("revokeUser"), "danger"]]
    : [["approve", t("approveUser")]];
  definitions.forEach(([action, label, className]) => { const button = document.createElement("button"); button.type = "button"; button.textContent = label; if (className) button.className = className; button.disabled = Boolean(user.configuredAdmin); button.addEventListener("click", () => runAdminUserAction(user, action).catch((error) => toast(error.message, true))); actions.append(button); });
  const auditTitle = document.createElement("h3"); auditTitle.textContent = t("auditTitle");
  const audit = document.createElement("div"); audit.id = "admin-user-audit-log"; audit.className = "user-audit";
  audit.replaceChildren(...events.map(adminAuditArticle));
  let auditCursor = String(payload.eventsNextCursor || "");
  const loadMoreAudit = document.createElement("button");
  loadMoreAudit.type = "button";
  loadMoreAudit.className = "secondary";
  loadMoreAudit.textContent = t("loadMoreAudit");
  loadMoreAudit.hidden = !payload.eventsHasMore;
  loadMoreAudit.addEventListener("click", async () => {
    loadMoreAudit.disabled = true;
    try {
      const page = await apiRequest(`/v1/admin/users/${encodeURIComponent(user.telegramId)}/events?cursor=${encodeURIComponent(auditCursor)}&limit=100`);
      const nextEvents = Array.isArray(page.events) ? page.events : [];
      audit.append(...nextEvents.map(adminAuditArticle));
      auditCursor = String(page.nextCursor || "");
      loadMoreAudit.hidden = !page.hasMore;
    } catch (error) {
      toast(error.message, true);
    } finally {
      loadMoreAudit.disabled = false;
    }
  });
  const jobsTitle = document.createElement("h3"); jobsTitle.textContent = t("jobHistory");
  const jobHistory = document.createElement("div"); jobHistory.className = "user-audit";
  const historyEntry = (job) => {
    const article = document.createElement("article"); article.className = "user-job-entry";
    const copy = document.createElement("div");
    const name = document.createElement("strong"); name.textContent = jobMetadata(job).version || job.recipe?.device || job.job_id || job.jobId;
    const detail = document.createElement("small"); detail.textContent = `${statusLabel(job.status)} · ${jobProgress(job)}% · ${job.stage || "—"}\n${formatDate(job.created_at || job.createdAt)} · ${job.job_id || job.jobId}`;
    copy.append(name, detail);
    const open = document.createElement("button"); open.type = "button"; open.className = "secondary";
    open.dataset.openUserJob = job.job_id || job.jobId; open.textContent = t("openUserJob");
    open.addEventListener("click", () => openAdminJobPage({ ...job, createdBy: job.createdBy || user }));
    article.append(copy, open); return article;
  };
  jobHistory.replaceChildren(...jobs.map(historyEntry));
  let jobsCursor = String(payload.jobsNextCursor || "");
  const moreJobs = document.createElement("button"); moreJobs.type = "button"; moreJobs.className = "secondary";
  moreJobs.textContent = t("loadMoreUserJobs"); moreJobs.hidden = !payload.jobsHasMore;
  moreJobs.addEventListener("click", async () => {
    moreJobs.disabled = true;
    try {
      const page = await apiRequest(`/v1/admin/users/${encodeURIComponent(user.telegramId)}/jobs?cursor=${encodeURIComponent(jobsCursor)}`);
      jobHistory.append(...(page.jobs || []).map(historyEntry));
      jobsCursor = String(page.nextCursor || ""); moreJobs.hidden = !page.hasMore;
    } catch (error) { toast(error.message, true); }
    finally { moreJobs.disabled = false; }
  });
  root.replaceChildren(header, activityTitle, currentActivity, grid, actions, jobsTitle, jobHistory, moreJobs, auditTitle, audit, loadMoreAudit);
  $("#admin-user-page").hidden = false;
  $("#system").classList.add("admin-user-open");
  window.scrollTo({ top: 0, behavior: prefersReducedMotion() ? "auto" : "smooth" });
  requestAnimationFrame(() => $("#admin-user-back").focus());
  scheduleAdminUserActivityPoll();
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
  const source = { kind: detection.kind, uri };
  const size = positiveInteger($("#source-size"), "invalidSize");
  if (size) source.sizeBytes = size;
  return source;
}

function selectedReleaseVersion() {
  const version = $("#mod-version")?.value || "";
  return String(
    state.releaseVersionOverrides[version]
    || state.catalog?.modReleaseVersions?.[version]
    || version
    || "—"
  );
}

function renderReleaseVersion() {
  const label = selectedReleaseVersion();
  const display = $("#mod-release-version");
  const input = $("#mod-release-version-input");
  if (display) display.textContent = label;
  if (input) input.value = label === "—" ? "" : label;
}

async function saveReleaseVersion() {
  const version = $("#mod-version").value;
  const label = $("#mod-release-version-input").value.trim();
  if (!label || label.length > 64 || /[\\/\x00-\x1f]/.test(label)) throw new Error(t("invalidReleaseVersion"));
  const defaultLabel = String(state.catalog?.modReleaseVersions?.[version] || version);
  if (label === defaultLabel) delete state.releaseVersionOverrides[version];
  else state.releaseVersionOverrides[version] = label;
  renderReleaseVersion();
  updateSummary();
  toast(t("releaseVersionSaved"));
}

function sameStringList(left, right) {
  if (!Array.isArray(left) || !Array.isArray(right) || left.length !== right.length) return false;
  return left.every((value, index) => value === right[index]);
}

function normalizedDebloatPaths(value) {
  return String(value || "")
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function renderDebloatSummary() {
  const count = $("#debloat-path-count");
  const status = $("#debloat-path-state");
  if (count) count.textContent = t("debloatPathCount", { count: state.debloatPaths.length });
  if (status) status.textContent = t(state.debloatPathsCustomized ? "debloatCustomState" : "debloatDefaultState");
}

function openDebloatEditor() {
  const editor = $("#debloat-editor");
  const input = $("#debloat-paths");
  if (!editor || !input) return;
  input.value = state.debloatPaths.join("\n");
  editor.hidden = false;
  $("#edit-debloat-paths").hidden = true;
  requestAnimationFrame(() => input.focus({ preventScroll: true }));
}

function closeDebloatEditor() {
  const editor = $("#debloat-editor");
  if (editor) editor.hidden = true;
  $("#edit-debloat-paths").hidden = false;
}

function saveDebloatPaths() {
  state.debloatPaths = normalizedDebloatPaths($("#debloat-paths").value);
  state.debloatPathsCustomized = !sameStringList(
    state.debloatPaths,
    state.catalog?.defaultDebloatPaths || []
  );
  closeDebloatEditor();
  renderDebloatSummary();
  toast(t("debloatSaved"));
}

function resetJobDraft() {
  const source = $("#source-uri");
  if (source) {
    source.value = "";
    source.dispatchEvent(new Event("input", { bubbles: true }));
  }
  const size = $("#source-size");
  if (size) size.value = "";
  state.releaseVersionOverrides = {};
  state.debloatPaths = [...(state.catalog?.defaultDebloatPaths || [])];
  state.debloatPathsCustomized = false;
  closeDebloatEditor();
  renderDebloatSummary();
  renderReleaseVersion();
  try { localStorage.removeItem("wukong-recipe-draft"); } catch (_) {}
}

function buildRecipe() {
  if (!$("#device").value) throw new Error(t("deviceRequired"));
  const recipe = {
    schemaVersion: 1, task: "build", device: $("#device").value, source: sourceSpec(),
    execution: { target: $("#execution").value },
    storage: { remote: "wukong-gdrive", publishArtifact: $("#publish").checked }
  };
  recipe.build = {
      preset: $("#preset").value, modVersion: $("#mod-version").value, mods: selectedMods(),
      modReleaseVersion: selectedReleaseVersion(),
      enabledSteps: $$("#steps input:checked").map((input) => input.value),
      package: $("#package").checked, notifyTelegram: $("#notify").checked
    };
    // The shared default list is intentionally visible/editable in the Mini App.
    // Omitting an unchanged list is lossless: every runner resolves a missing
    // debloatPaths field from the same versioned config/debloat.json catalog.
    if (!sameStringList(state.debloatPaths, state.catalog.defaultDebloatPaths)) {
      recipe.build.debloatPaths = [...state.debloatPaths];
    }
  return recipe;
}

const terminalJobStatuses = new Set(["succeeded", "failed", "cancelled"]);
const eventTypeLabels = {
  vi: {
    submitted: "Đã tạo job", dispatched: "Đã gửi tới runner", github_run: "GitHub Actions",
    state: "Cập nhật trạng thái", running: "Runner đang xử lý", source: "ROM nguồn sẵn sàng",
    checkpoint: "Đã lưu checkpoint", upload_progress: "Đang tải artifact", artifacts: "Artifact hoàn tất",
    warning: "Cảnh báo", error: "Lỗi", cancelled: "Đã hủy job", resumed: "Tiếp tục từ checkpoint",
    plan: "Kế hoạch build", step: "Bước build", telegram_terminal_notified: "Đã gửi thông báo Telegram"
  },
  en: {
    submitted: "Job created", dispatched: "Sent to runner", github_run: "GitHub Actions",
    state: "Status update", running: "Runner processing", source: "Source ROM ready",
    checkpoint: "Checkpoint saved", upload_progress: "Uploading artifact", artifacts: "Artifacts ready",
    warning: "Warning", error: "Error", cancelled: "Job cancelled", resumed: "Resumed from checkpoint",
    plan: "Build plan", step: "Build step", telegram_terminal_notified: "Telegram notification sent"
  }
};
const eventStageLabels = {
  vi: { preflight: "Kiểm tra", download: "Tải ROM", build: "Build ROM", upload: "Tải lên", complete: "Hoàn tất", "github-actions": "GitHub Actions", "github-actions-running": "GitHub Actions" },
  en: { preflight: "Preflight", download: "ROM download", build: "ROM build", upload: "Upload", complete: "Complete", "github-actions": "GitHub Actions", "github-actions-running": "GitHub Actions" }
};

function readableEventType(value) {
  const key = String(value || "event");
  return eventTypeLabels[state.language]?.[key] || key.replaceAll("_", " ");
}

function readableEventStage(value) {
  const key = String(value || "");
  return eventStageLabels[state.language]?.[key] || eventTypeLabels[state.language]?.[key] || key.replaceAll("_", " ");
}

function readableStep(value) {
  const key = String(value || "");
  return pipelineLabels[state.language]?.[key] || key.replaceAll("_", " ") || t("events");
}

function readableStepStatus(value) {
  return t({ running: "eventRunning", success: "eventSucceeded", succeeded: "eventSucceeded", failed: "eventFailed" }[String(value || "").toLowerCase()] || "eventRunning");
}

function eventTitle(event) {
  if (event.type === "step" && event.step) return `${readableStep(event.step)} · ${readableStepStatus(event.status)}`;
  if (event.type === "plan") return `${readableEventType(event.type)} · ${(event.steps || []).length} ${t("eventSteps")}`;
  return readableEventType(event.type || event.status);
}

function formatEventValue(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (Array.isArray(value)) return value.map((item) => typeof item === "object" ? JSON.stringify(item) : String(item)).join(" · ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function eventDetailEntries(event) {
  const entries = [];
  const skip = new Set(["sequence", "jobId", "timestamp", "type", "traceback", "message", "error", "warning", "step", "stage", "status"]);
  Object.entries(event || {}).forEach(([key, value]) => {
    if (skip.has(key)) return;
    if (key === "details" && value && typeof value === "object" && !Array.isArray(value)) {
      Object.entries(value).forEach(([detailKey, detailValue]) => entries.push([detailKey, formatEventValue(detailValue)]));
    } else entries.push([key, formatEventValue(value)]);
  });
  return entries;
}

function statusLabel(status) {
  return t({
    queued: "stageQueued", preflight: "stagePreflight", downloading: "stageDownloading",
    running: "stageRunning", uploading: "stageUploading", succeeded: "pipelineComplete",
    failed: "pipelineFailed", cancelled: "cancel"
  }[status] || status);
}

function jobMetadata(job) {
  return {
    ...(job?.recipe?.source?.metadata || {}),
    ...(job?.rom_metadata || job?.romMetadata || {})
  };
}

function catalogDeviceName(product) {
  const normalized = String(product || "").trim().toLocaleUpperCase();
  if (!normalized) return "";
  return state.catalog?.devices?.find(
    (item) => String(item?.product || "").trim().toLocaleUpperCase() === normalized
  )?.name || "";
}

function jobProgress(job) {
  const value = Math.max(0, Math.min(1, Number(job?.progress || 0)));
  return Math.round(value * 100);
}

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : new Intl.DateTimeFormat(state.language === "vi" ? "vi-VN" : "en-GB", {
    dateStyle: "medium", timeStyle: "short"
  }).format(date);
}

function formatElapsed(job) {
  const start = new Date(job.created_at || job.createdAt || 0).getTime();
  const end = new Date(job.finished_at || job.finishedAt || Date.now()).getTime();
  if (!start || Number.isNaN(start) || Number.isNaN(end)) return "—";
  const seconds = Math.max(0, Math.floor((end - start) / 1000));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remaining = seconds % 60;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(remaining).padStart(2, "0")}`;
}

function jobFact(label, value) {
  const node = document.createElement("div");
  const name = document.createElement("small"); name.textContent = label;
  const content = document.createElement("strong"); content.textContent = value || "—";
  node.append(name, content);
  return node;
}

function artifactCloudUrl(artifact) {
  const candidate = String(artifact?.publicUrl || artifact?.public_url || "").trim();
  try {
    if (
      !candidate
      || candidate.includes("\\")
      || /\s|[\u0000-\u001f\u007f]/u.test(candidate)
      || /%(?![0-9a-f]{2})/iu.test(candidate)
    ) return "";
    const parsed = new URL(candidate);
    const hostname = parsed.hostname.toLowerCase();
    let miniApiOrigin = "";
    try { miniApiOrigin = new URL(miniApiEndpoint).origin; } catch (_) {}
    if (
      parsed.protocol !== "https:"
      || !hostname
      || hostname === "wukong-mini-api.onrender.com"
      || (miniApiOrigin && parsed.origin === miniApiOrigin)
    ) return "";
    return parsed.href;
  } catch (_) {
    return "";
  }
}

function artifactProvider(url) {
  const hostname = new URL(url).hostname.toLowerCase();
  if (hostname === "drive.google.com" || hostname.endsWith(".googleusercontent.com")) return "Google Drive";
  if (hostname === "1drv.ms" || hostname.endsWith(".onedrive.live.com")) return "OneDrive";
  if (hostname === "dropbox.com" || hostname.endsWith(".dropboxusercontent.com")) return "Dropbox";
  if (hostname === "mega.nz" || hostname.endsWith(".mega.nz")) return "MEGA";
  return hostname.replace(/^www\./, "");
}

function openArtifactUrl(url) {
  if (TelegramApp?.openLink) TelegramApp.openLink(url);
  else window.open(url, "_blank", "noopener,noreferrer");
}

function renderArtifacts(job) {
  const section = document.createElement("section"); section.className = "job-artifacts";
  const title = document.createElement("h3"); title.textContent = t("artifactsReady"); section.append(title);
  const artifacts = Array.isArray(job.artifacts) ? job.artifacts : [];
  if (!artifacts.length) {
    const empty = document.createElement("p"); empty.textContent = t("noArtifacts"); section.append(empty); return section;
  }
  artifacts.forEach((artifact, index) => {
    const card = document.createElement("article");
    const header = document.createElement("div");
    const name = document.createElement("strong"); name.textContent = artifact.name || "Artifact";
    const size = document.createElement("span"); size.textContent = formatBytes(artifact.size_bytes ?? artifact.sizeBytes);
    header.append(name, size);
    const sha = document.createElement("code"); sha.textContent = `SHA-256 ${artifact.sha256 || "—"}`;
    const cloudUrl = artifactCloudUrl(artifact);
    if (cloudUrl) {
      const providerName = artifactProvider(cloudUrl);
      const provider = document.createElement("small");
      provider.className = "artifact-provider";
      provider.textContent = providerName;
      const actions = document.createElement("div");
      actions.className = "job-artifact-actions";
      const open = document.createElement("button");
      open.type = "button";
      open.className = "artifact-open";
      open.dataset.jobFocus = `artifact-open-${index}`;
      open.textContent = t("openArtifactCloud", { provider: providerName });
      open.setAttribute("aria-label", `${open.textContent}: ${artifact.name || "Artifact"}`);
      open.addEventListener("click", () => openArtifactUrl(cloudUrl));
      const copy = document.createElement("button");
      copy.type = "button";
      copy.className = "artifact-copy";
      copy.dataset.jobFocus = `artifact-copy-${index}`;
      copy.textContent = t("copyArtifactLink");
      copy.setAttribute("aria-label", `${copy.textContent}: ${artifact.name || "Artifact"}`);
      copy.addEventListener("click", () => {
        copyText(cloudUrl)
          .then(() => toast(t("artifactLinkCopied")))
          .catch(() => toast(t("clipboardDenied"), true));
      });
      actions.append(open, copy);
      card.append(header, sha, provider, actions);
    } else {
      const uri = document.createElement("code"); uri.textContent = t("artifactLinkUnavailable");
      card.append(header, sha, uri);
    }
    section.append(card);
  });
  return section;
}

function renderEvents(events, expanded = false) {
  const section = document.createElement("section"); section.className = "job-events";
  if (expanded) section.classList.add("expanded");
  const heading = document.createElement("div"); heading.className = "job-events-heading";
  const title = document.createElement("h3"); title.textContent = expanded ? t("fullLogTitle") : t("eventTimeline");
  const previewCount = Math.min(events.length, 8);
  const count = document.createElement("span"); count.textContent = t("eventsPreview", { visible: expanded ? events.length : previewCount, total: events.length });
  heading.append(title, count); section.append(heading);
  const list = document.createElement("ol");
  if (!events.length) {
    const empty = document.createElement("li"); empty.textContent = t("noEvents"); list.append(empty);
  } else {
    let currentGroup = "";
    const visibleEvents = expanded ? events : events.slice(-8);
    visibleEvents.slice().reverse().forEach((event) => {
      const group = event.step ? readableStep(event.step) : readableEventStage(event.stage || event.status || event.type || t("events"));
      if (group !== currentGroup) {
        currentGroup = group;
        const divider = document.createElement("li"); divider.className = "event-group";
        divider.textContent = group; list.append(divider);
      }
      const item = document.createElement("li"); item.className = `event-${String(event.type || event.status || "info").replace(/[^a-z0-9_-]/gi, "")}`;
      const marker = document.createElement("span"); marker.className = "event-marker";
      const markerDot = document.createElement("i");
      const markerSequence = document.createElement("b"); markerSequence.textContent = String(event.sequence || "•").padStart(2, "0");
      marker.append(markerDot, markerSequence);
      const content = document.createElement("div"); content.className = "event-copy";
      const titleRow = document.createElement("div"); titleRow.className = "event-title-row";
      const eventTitleNode = document.createElement("strong"); eventTitleNode.textContent = eventTitle(event);
      const eventTime = document.createElement("time"); eventTime.dateTime = String(event.timestamp || ""); eventTime.textContent = formatDate(event.timestamp);
      titleRow.append(eventTitleNode, eventTime);
      const detail = document.createElement("p");
      const details = eventDetailEntries(event);
      const visible = event.message || event.error || event.warning || (event.type === "step" ? details.slice(0, 3).map(([key, value]) => `${key}: ${value}`).join(" · ") : "") || event.stage || event.status;
      detail.textContent = String(visible || readableEventStage(event.stage || event.status || event.type || ""));
      if (!detail.textContent) detail.hidden = true;
      content.append(titleRow, detail);
      if (expanded && details.length) {
        const data = document.createElement("dl"); data.className = "event-data";
        details.forEach(([key, value]) => {
          const row = document.createElement("div");
          const term = document.createElement("dt"); term.textContent = key.replaceAll(/([a-z])([A-Z])/g, "$1 $2").replaceAll("_", " ");
          const description = document.createElement("dd"); description.textContent = value;
          row.append(term, description); data.append(row);
        });
        content.append(data);
      }
      item.append(marker, content); list.append(item);
    });
  }
  section.append(list); return section;
}

function jobAction(label, action, job, danger = false) {
  const button = document.createElement("button"); button.type = "button"; button.textContent = label;
  button.dataset.jobFocus = `job-action-${action}`;
  if (danger) button.classList.add("danger");
  button.addEventListener("click", () => runJobAction(action, job.job_id || job.jobId).catch((error) => toast(error.message, true)));
  return button;
}

function openAdminJobPage(job) {
  if (state.me?.role !== "admin" || !state.selectedAdminUserId) return;
  clearTimeout(state.adminUserPollTimer);
  state.adminUserPollTimer = null;
  closeAdminJobPage({ restoreFocus: false, scroll: false, refreshUser: false });
  clearTimeout(state.jobsPollTimer);
  ++state.jobDetailRequestId;
  const view = {
    jobId: job.job_id || job.jobId, job, events: [], requestId: 0, timer: null,
    returnScrollY: window.scrollY, expandedConfigJobId: "", expandedLogJobId: "",
    jobEventsHasMore: false, unchangedPolls: 0, signature: ""
  };
  state.adminJobView = view;
  $("#system").classList.add("admin-job-open");
  $("#admin-job-page").hidden = false;
  renderActiveJob(job, [], view);
  const status = $("#admin-job-connection");
  status.classList.remove("error");
  if (status.textContent !== t("userJobLoading")) status.textContent = t("userJobLoading");
  window.scrollTo({ top: 0, behavior: "instant" });
  $("#admin-job-back").focus({ preventScroll: true });
  loadAdminJobDetail();
}

function closeAdminJobPage({ restoreFocus = true, scroll = true, refreshUser = true } = {}) {
  const view = state.adminJobView;
  if (!view) return;
  clearTimeout(view.timer);
  state.adminJobView = null;
  $("#system").classList.remove("admin-job-open");
  $("#admin-job-page").hidden = true;
  $("#admin-job-detail").replaceChildren();
  if (scroll) window.scrollTo({ top: view.returnScrollY, behavior: "instant" });
  if (restoreFocus) $$("[data-open-user-job]").find(button => button.dataset.openUserJob === view.jobId)?.focus({ preventScroll: true });
  scheduleJobsPoll(true);
  if (refreshUser && state.selectedAdminUserId && !document.hidden) {
    refreshAdminUserActivity();
  }
}

async function loadAdminJobDetail() {
  const view = state.adminJobView;
  if (!view || document.hidden || state.me?.role !== "admin") return;
  clearTimeout(view.timer);
  const requestId = ++view.requestId;
  const after = view.events.reduce((max, event) => Math.max(max, Number(event.sequence || 0)), 0);
  const status = $("#admin-job-connection");
  try {
    const payload = await apiRequest(`/v1/sync?jobId=${encodeURIComponent(view.jobId)}&after=${after}`);
    if (state.adminJobView !== view || requestId !== view.requestId) return;
    const job = payload.activeJob;
    if (!job || (job.job_id || job.jobId) !== view.jobId) {
      renderActiveJob(null, [], view);
      throw new Error(t("jobUnavailable"));
    }
    const incoming = Array.isArray(payload.events) ? payload.events : [];
    const unique = new Map([...view.events, ...incoming].map(event => [
      Number(event.sequence) > 0 ? `sequence:${event.sequence}` : JSON.stringify(event), event
    ]));
    view.events = [...unique.values()];
    view.job = job;
    view.jobEventsHasMore = incoming.length >= 500;
    const signature = JSON.stringify([job.status, job.stage, job.progress, job.updated_at || job.updatedAt, view.events.length]);
    view.unchangedPolls = signature === view.signature ? view.unchangedPolls + 1 : 0;
    view.signature = signature;
    renderActiveJob(job, view.events, view);
    if (status.textContent !== t("userJobSynced")) status.textContent = t("userJobSynced");
    status.classList.remove("error");
  } catch (error) {
    if (state.adminJobView !== view || requestId !== view.requestId) return;
    const message = error.connectionFailed ? t("jobsOffline") : error.message;
    if (status.textContent !== message) status.textContent = message;
    status.classList.add("error");
  } finally {
    if (state.adminJobView === view && requestId === view.requestId && !document.hidden) {
      const delay = terminalJobStatuses.has(view.job.status) || view.unchangedPolls >= 6 ? 30000 : view.unchangedPolls >= 3 ? 15000 : 10000;
      view.timer = setTimeout(loadAdminJobDetail, delay);
    }
  }
}

function openJob(job) {
  state.activeJobId = job.job_id || job.jobId;
  localStorage.setItem("wukong-active-job", state.activeJobId);
  ++state.jobDetailRequestId;
  state.activeEvents = [];
  state.activeEventsJobId = "";
  state.jobEventsHasMore = false;
  state.jobHistoryFilter = job.status === "succeeded" ? "succeeded" : terminalJobStatuses.has(job.status) ? "failed" : "active";
  if (!state.jobs.some(item => (item.job_id || item.jobId) === state.activeJobId)) state.jobs.unshift(job);
  renderActiveJob(job, []); renderJobHistory();
  loadJobDetail(state.activeJobId).catch((error) => toast(error.message, true));
}

function renderJobParameters(job, root, reader) {
  const id = job.job_id || job.jobId;
  const previous = root.querySelector(":scope > .job-config");
  const details = previous?.dataset.jobId === id ? previous : document.createElement("details");
  details.className = "job-config"; details.dataset.jobId = id;
  details.open = reader.expandedConfigJobId === id;
  if (!details.children.length) {
    details.append(document.createElement("summary"), document.createElement("p"), document.createElement("button"));
    details.addEventListener("toggle", () => { if (details.isConnected) reader.expandedConfigJobId = details.open ? id : ""; });
  }
  details.querySelector("summary").textContent = t("jobParameters");
  details.querySelector("p").textContent = t("jobParametersHint");
  const copy = details.querySelector("button"); copy.type = "button"; copy.className = "secondary"; copy.textContent = t("copyJobParameters");
  copy.onclick = () => copyText(JSON.stringify(job, null, 2)).then(() => toast(t("jobParametersCopied"))).catch(() => toast(t("clipboardDenied"), true));
  const { recipe, ...runtime } = job;
  for (const [key, value] of [["jobRecipeData", recipe || {}], ["jobRuntimeData", runtime]]) {
    let data = details.querySelector(`[data-parameters="${key}"]`);
    if (!data) {
      data = document.createElement("pre"); data.tabIndex = 0; data.dataset.parameters = key;
      details.append(document.createElement("h4"), data);
    }
    data.previousElementSibling.textContent = t(key);
    const text = JSON.stringify(value, null, 2);
    if (data.textContent !== text) {
      const { scrollTop, scrollLeft } = data;
      data.textContent = text;
      data.scrollTop = scrollTop; data.scrollLeft = scrollLeft;
    }
  }
  return details;
}

function renderActiveJob(job, events, inspection = null) {
  const root = inspection ? $("#admin-job-detail") : $("#active-job");
  const reader = inspection || state;
  if (!root) return;
  const focusedJobControl = root.contains(document.activeElement)
    ? document.activeElement.closest("[data-job-focus]")
    : null;
  const focusedJobControlKey = focusedJobControl?.dataset.jobFocus || "";
  if (!job) { root.hidden = true; root.replaceChildren(); delete root.dataset.jobId; return; }
  root.hidden = false;
  root.dataset.jobId = job.job_id || job.jobId;
  const metadata = jobMetadata(job);
  const header = document.createElement("header");
  const title = document.createElement("div");
  const kicker = document.createElement("small");
  kicker.textContent = t(terminalJobStatuses.has(job.status) ? "historicalJob" : "activeJob");
  const heading = document.createElement("h2"); heading.textContent = metadata.version || `${job.recipe?.device || "ROM"} · ${String(job.job_id || job.jobId).slice(0, 12)}`;
  title.append(kicker, heading);
  const badge = document.createElement("span"); badge.className = `job-status ${job.status}`; badge.textContent = statusLabel(job.status);
  header.append(title, badge);
  const creator = document.createElement("div"); creator.className = "job-creator";
  if (state.me?.role === "admin" && job.createdBy) {
    const user = job.createdBy;
    const text = document.createElement("div"); text.className = "job-creator-copy";
    const label = document.createElement("small"); label.textContent = t("jobCreator");
    const name = document.createElement("strong"); name.textContent = user.displayName || user.username || user.telegramId;
    const identity = document.createElement("span"); identity.textContent = [user.username ? `@${user.username}` : "", `ID ${user.telegramId}`].filter(Boolean).join(" · ");
    text.append(label, name, identity);
    const open = document.createElement("button"); open.type = "button"; open.className = "secondary"; open.textContent = t("viewJobUser");
    open.addEventListener("click", () => { navigate("system"); openAdminUser(user.telegramId).catch(error => toast(error.message, true)); });
    creator.append(profileAvatar(user), text);
    if (!inspection) creator.append(open);
  } else creator.hidden = true;
  const progress = document.createElement("div"); progress.className = "job-progress";
  const progressCopy = document.createElement("div");
  const stage = document.createElement("strong"); stage.textContent = job.stage || statusLabel(job.status);
  const percentage = document.createElement("b"); percentage.textContent = `${jobProgress(job)}%`;
  progressCopy.append(stage, percentage);
  const track = document.createElement("div"); const fill = document.createElement("i"); fill.style.width = `${jobProgress(job)}%`; track.append(fill);
  progress.append(progressCopy, track);
  const build = job.recipe?.build || {};
  const context = document.createElement("section"); context.className = "job-context";
  const contextTitle = document.createElement("div");
  const contextLabel = document.createElement("strong"); contextLabel.textContent = t("jobContext");
  const mods = document.createElement("div"); mods.className = "job-mod-grid";
  const selectedJobMods = build.mods || [];
  if (selectedJobMods.length) mods.append(...selectedJobMods.map((name) => {
    const chip = document.createElement("span"); chip.textContent = name; return chip;
  }));
  else { const empty = document.createElement("small"); empty.textContent = t("noModsSelected"); mods.append(empty); }
  contextTitle.append(contextLabel, mods);
  const contextCopy = document.createElement("div"); contextCopy.className = "job-release-context";
  const pack = document.createElement("small"); pack.textContent = build.modVersion || "—";
  const release = document.createElement("b"); release.textContent = build.modReleaseVersion || "—";
  const count = document.createElement("span"); count.textContent = `${(build.mods || []).length} ${t("selected")}`;
  contextCopy.append(pack, release, count);
  context.append(contextTitle, contextCopy);
  const upload = [...events].reverse().find((event) => event.type === "upload_progress");
  const uploadDetail = upload
    ? `${upload.fileName || "—"} · ${Math.max(0, Math.min(100, Math.round(Number(upload.percent) || 0)))}% · ${formatBytes(upload.bytes)} / ${formatBytes(upload.totalBytes)} · ${formatBytes(upload.speedBytesPerSecond)}/s${Number.isFinite(Number(upload.etaSeconds)) ? ` · ETA ${Math.max(0, Math.round(Number(upload.etaSeconds)))}s` : ""}`
    : "";
  const facts = document.createElement("div"); facts.className = "job-facts";
  const product = metadata.productName || job.recipe?.device;
  const factNodes = [
    jobFact("Job ID", job.job_id || job.jobId),
    jobFact(t("jobCreatedAt"), formatDate(job.created_at || job.createdAt)),
    jobFact(t("jobUpdatedAt"), formatDate(job.updated_at || job.updatedAt)),
    jobFact(t("deviceName"), catalogDeviceName(product)),
    jobFact(t("productCode"), product),
    jobFact(t("detectedDevice"), metadata.device),
    jobFact(t("androidVersion"), metadata.androidVersion),
    jobFact(t("securityPatch"), metadata.securityPatch),
    jobFact(t("buildDate"), metadata.buildDate),
    jobFact(t("runner"), job.runner),
    jobFact(t("elapsed"), formatElapsed(job)),
    jobFact(t("modConfiguration"), `${build.preset || "—"} / ${build.modVersion || "—"}`),
    jobFact(t("releaseVersion"), build.modReleaseVersion),
    jobFact(t("sourceSizeDetected"), formatBytes(job.recipe?.source?.sizeBytes))
  ];
  if (!terminalJobStatuses.has(job.status)) {
    factNodes.push(jobFact(t(job.status === "uploading" ? "uploadingNow" : "uploadSummary"), uploadDetail));
  }
  facts.append(...factNodes);
  const artifacts = renderArtifacts(job);
  const actions = document.createElement("div"); actions.className = "job-controls";
  const jobId = job.job_id || job.jobId;
  const logExpanded = reader.expandedLogJobId === jobId;
  const logButton = document.createElement("button"); logButton.type = "button"; logButton.className = "job-log-toggle";
  logButton.dataset.jobFocus = "log-toggle";
  logButton.textContent = t(logExpanded ? "hideFullLog" : "viewFullLog");
  logButton.setAttribute("aria-expanded", String(logExpanded));
  logButton.addEventListener("click", () => {
    reader.expandedLogJobId = logExpanded ? "" : jobId;
    renderActiveJob(job, events, inspection);
    if (!logExpanded) requestAnimationFrame(() => root.querySelector(".job-events")?.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block: "start" }));
  });
  actions.append(logButton);
  if (reader.jobEventsHasMore) {
    const more = document.createElement("button"); more.type = "button"; more.textContent = t("loadMoreJobEvents");
    more.dataset.jobFocus = "load-more-events";
    more.addEventListener("click", () => { more.disabled = true; (inspection ? loadAdminJobDetail() : loadJobDetail(jobId)).catch(error => toast(error.message, true)).finally(() => { more.disabled = false; }); });
    actions.append(more);
  }
  if (!inspection && !terminalJobStatuses.has(job.status)) actions.append(jobAction(t("cancel"), "cancel", job, true));
  if (!inspection && ["failed", "cancelled"].includes(job.status) && job.checkpoint) actions.append(jobAction(t("resume"), "resume", job));
  const config = state.me?.role === "admin" ? renderJobParameters(job, root, reader) : null;
  const before = [header, creator, progress, context, facts];
  const after = [artifacts, actions, renderEvents(events, logExpanded)];
  if (config?.parentElement === root) {
    // Keep the parameter reader attached so polling preserves focus and selection.
    for (const child of [...root.children]) if (child !== config) child.remove();
    config.before(...before); config.after(...after);
  } else root.replaceChildren(...before, ...(config ? [config] : []), ...after);
  if (focusedJobControlKey) {
    root.querySelector(`[data-job-focus="${focusedJobControlKey}"]`)?.focus({ preventScroll: true });
  }
}

function renderJobHistory() {
  const history = $("#job-history");
  const jobs = state.jobs;
  const grouped = {
    active: jobs.filter((job) => !terminalJobStatuses.has(job.status)),
    succeeded: jobs.filter((job) => job.status === "succeeded"),
    failed: jobs.filter((job) => ["failed", "cancelled"].includes(job.status))
  };
  if (!["active", "succeeded", "failed"].includes(state.jobHistoryFilter)) {
    state.jobHistoryFilter = ["active", "succeeded", "failed"].find((key) => grouped[key].length) || "active";
  }
  $$("[data-job-filter]").forEach((button) => {
    const selected = button.dataset.jobFilter === state.jobHistoryFilter;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-selected", String(selected));
  });
  for (const key of ["active", "succeeded", "failed"]) {
    const count = $(`#job-count-${key}`);
    if (count) count.textContent = String(grouped[key].length);
  }
  const visibleJobs = grouped[state.jobHistoryFilter] || [];
  $("#job-history-count").textContent = String(jobs.length);
  $("#job-empty").hidden = jobs.length > 0;
  history.hidden = jobs.length === 0;
  const cards = visibleJobs.map((job) => {
    const metadata = jobMetadata(job);
    const card = document.createElement("button"); card.type = "button"; card.className = "job-history-card";
    if ((job.job_id || job.jobId) === state.activeJobId) card.classList.add("selected");
    const header = document.createElement("div");
    const title = document.createElement("strong"); title.textContent = metadata.version || job.recipe?.device || "ROM build";
    const status = document.createElement("span"); status.className = `job-status ${job.status}`; status.textContent = statusLabel(job.status);
    header.append(title, status);
    const build = job.recipe?.build || {};
    const details = document.createElement("p"); details.textContent = `${job.recipe?.device || "—"} · ${build.modVersion || "—"} · ${build.modReleaseVersion || "—"} · ${jobProgress(job)}%`;
    const footer = document.createElement("small"); footer.textContent = `${String(job.job_id || job.jobId).slice(0, 12)} · ${formatDate(job.created_at || job.createdAt)}`;
    card.append(header, details, footer);
    if (state.me?.role === "admin" && job.createdBy) {
      const creator = document.createElement("p"); creator.className = "job-history-creator";
      creator.textContent = `${job.createdBy.displayName || job.createdBy.username || job.createdBy.telegramId} · ID ${job.createdBy.telegramId}`;
      card.append(creator);
    }
    card.addEventListener("click", () => {
      openJob(job);
    });
    return card;
  });
  if (!cards.length && jobs.length) {
    const empty = document.createElement("p");
    empty.className = "job-filter-empty";
    empty.textContent = t("noJobsInTab");
    history.replaceChildren(empty);
  } else history.replaceChildren(...cards);
}

function setJobsConnection(key, error = false) {
  const node = $("#jobs-connection"); if (!node) return;
  node.classList.toggle("error", error); node.classList.toggle("online", !error);
  node.querySelector("span").textContent = t(key);
}

async function loadJobDetail(jobId) {
  if (!jobId) return;
  const requestId = ++state.jobDetailRequestId;
  const sameJob = state.activeEventsJobId === jobId;
  const after = sameJob
    ? state.activeEvents.reduce((maximum, event) => Math.max(maximum, Number(event.sequence || 0)), 0)
    : 0;
  const payload = await apiRequest(
    `/v1/sync?jobId=${encodeURIComponent(jobId)}&after=${after}`
  );
  if (requestId !== state.jobDetailRequestId || state.activeJobId !== jobId) return;
  state.jobs = Array.isArray(payload.jobs) ? payload.jobs : state.jobs;
  const job = payload.activeJob
    || state.jobs.find((item) => (item.job_id || item.jobId) === jobId)
    || null;
  if (!job || (job.job_id || job.jobId) !== jobId) throw new Error(t("jobUnavailable"));
  const incoming = Array.isArray(payload.events) ? payload.events : [];
  state.jobEventsHasMore = incoming.length >= 500;
  const merged = sameJob ? [...state.activeEvents, ...incoming] : incoming;
  const unique = new Map();
  merged.forEach((event) => {
    const sequence = Number(event?.sequence || 0);
    const fallback = `${event?.timestamp || ""}|${event?.type || ""}|${JSON.stringify(event || {})}`;
    unique.set(sequence > 0 ? `sequence:${sequence}` : `event:${fallback}`, event);
  });
  state.activeEvents = [...unique.values()];
  state.activeEventsJobId = jobId;
  const index = state.jobs.findIndex((item) => (item.job_id || item.jobId) === jobId);
  if (index >= 0 && job) state.jobs[index] = job;
  else if (job) state.jobs.unshift(job);
  renderActiveJob(job, state.activeEvents); renderJobHistory();
}

function scheduleJobsPoll(active, changed = false) {
  clearTimeout(state.jobsPollTimer);
  if (document.hidden || !privateApiAvailable() || state.adminJobView) return;
  if (changed) state.jobsUnchangedPolls = 0;
  else state.jobsUnchangedPolls += 1;
  const delay = !active
    ? 30000
    : state.jobsUnchangedPolls >= 6
      ? 30000
      : state.jobsUnchangedPolls >= 3
        ? 15000
        : 10000;
  state.jobsPollTimer = setTimeout(() => loadJobs().catch(() => {}), delay);
}

async function loadJobs({ force = false } = {}) {
  if (state.adminJobView) return;
  if (state.jobsLoading && !force) return;
  if (!privateApiAvailable()) { setJobsConnection(state.me ? "quotaRequiredHint" : miniApiUnavailableMessageKey(), true); return; }
  state.jobsLoading = true;
  try {
    const requestedId = state.activeJobId;
    const selectionVersion = ++state.jobDetailRequestId;
    const sameJob = state.activeEventsJobId === requestedId;
    const after = sameJob
      ? state.activeEvents.reduce((maximum, event) => Math.max(maximum, Number(event.sequence || 0)), 0)
      : 0;
    const query = requestedId
      ? `?jobId=${encodeURIComponent(requestedId)}&after=${after}`
      : "";
    const payload = await apiRequest(`/v1/sync${query}`);
    if (selectionVersion !== state.jobDetailRequestId || requestedId !== state.activeJobId) { scheduleJobsPoll(true); return; }
    state.maintenance = payload.maintenance || state.maintenance;
    renderAccount();
    state.jobs = Array.isArray(payload.jobs) ? payload.jobs : [];
    if (requestedId && payload.activeJob && (payload.activeJob.job_id || payload.activeJob.jobId) === requestedId) {
      const index = state.jobs.findIndex(job => (job.job_id || job.jobId) === requestedId);
      if (index >= 0) state.jobs[index] = payload.activeJob;
      else state.jobs.unshift(payload.activeJob);
    }
    const running = state.jobs.find((job) => !terminalJobStatuses.has(job.status));
    const selectedExists = state.jobs.some((job) => (job.job_id || job.jobId) === state.activeJobId);
    if (requestedId && !selectedExists) { renderActiveJob(null, []); renderJobHistory(); throw new Error(t("jobUnavailable")); }
    if (!selectedExists) state.activeJobId = (running?.job_id || running?.jobId) || state.jobs[0]?.job_id || state.jobs[0]?.jobId || "";
    if (state.activeJobId) localStorage.setItem("wukong-active-job", state.activeJobId);
    else localStorage.removeItem("wukong-active-job");
    const activeJob = payload.activeJob
      && (payload.activeJob.job_id || payload.activeJob.jobId) === state.activeJobId
      ? payload.activeJob
      : state.jobs.find((job) => (job.job_id || job.jobId) === state.activeJobId) || null;
    const eventsSameJob = state.activeEventsJobId === state.activeJobId;
    const responseId = payload.activeJob?.job_id || payload.activeJob?.jobId;
    const incoming = responseId === state.activeJobId && Array.isArray(payload.events) ? payload.events : [];
    state.jobEventsHasMore = incoming.length >= 500;
    const merged = eventsSameJob ? [...state.activeEvents, ...incoming] : incoming;
    const unique = new Map();
    merged.forEach((event) => {
      const sequence = Number(event?.sequence || 0);
      const fallback = `${event?.timestamp || ""}|${event?.type || ""}|${JSON.stringify(event || {})}`;
      unique.set(sequence > 0 ? `sequence:${sequence}` : `event:${fallback}`, event);
    });
    state.activeEvents = [...unique.values()];
    state.activeEventsJobId = state.activeJobId;
    const nextSignature = JSON.stringify({
      jobs: state.jobs.map((job) => [
        job.job_id || job.jobId,
        job.status,
        job.stage,
        job.progress,
        job.updated_at || job.updatedAt
      ]),
      active: state.activeJobId,
      sequence: state.activeEvents.reduce(
        (maximum, event) => Math.max(maximum, Number(event.sequence || 0)),
        0
      )
    });
    const changed = nextSignature !== state.jobsSyncSignature;
    state.jobsSyncSignature = nextSignature;
    renderJobHistory();
    renderActiveJob(activeJob, state.activeEvents);
    setJobsConnection("jobsConnected");
    scheduleJobsPoll(Boolean(running), changed);
  } catch (error) {
    setJobsConnection("jobsOffline", true); scheduleJobsPoll(true, false); throw error;
  } finally {
    state.jobsLoading = false;
  }
}

async function runJobAction(action, jobId) {
  const job = await apiRequest(`/v1/jobs/${encodeURIComponent(jobId)}/${action}`, { method: "POST" });
  state.activeJobId = job.job_id || job.jobId; localStorage.setItem("wukong-active-job", state.activeJobId);
  await loadJobs({ force: true });
}

async function submitRecipe() {
  if (!miniApiAvailable()) throw new Error(t(miniApiUnavailableMessageKey()));
  const recipe = buildRecipe();
  const canonical = JSON.stringify(recipe);
  let pending = null;
  try { pending = JSON.parse(localStorage.getItem("wukong-submit-request") || "null"); } catch (_) {}
  if (!pending || pending.recipe !== canonical || !pending.key) {
    pending = { recipe: canonical, key: crypto.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}` };
    localStorage.setItem("wukong-submit-request", JSON.stringify(pending));
  }
  let job;
  try {
    job = await apiRequest("/v1/jobs", { method: "POST", headers: { "Idempotency-Key": pending.key }, body: canonical });
    localStorage.removeItem("wukong-submit-request");
  } catch (error) {
    if (!error.connectionFailed) localStorage.removeItem("wukong-submit-request");
    throw error;
  }
  state.activeJobId = job.job_id || job.jobId;
  localStorage.setItem("wukong-active-job", state.activeJobId);
  resetJobDraft();
  await apiRequest("/v1/drafts/source", { method: "DELETE" }).catch(() => {});
  await loadSession({ countOpen: false });
  toast(t("buildCreated")); navigate("jobs"); await loadJobs({ force: true });
}

function scheduleSourceProbe() {
  clearTimeout(state.sourceProbeTimer);
  const uri = $("#source-uri").value.trim();
  if (!miniApiEndpoint || !/^https?:\/\//i.test(uri) || !state.sourceDetection?.valid) return;
  if (state.sourceProbeUri === uri && state.sourceProbe?.result) return;
  state.sourceProbeTimer = setTimeout(() => probeSourceInPlace().catch(() => {}), 450);
}

async function loadCatalog() {
  try {
    const response = await fetch("./catalog.json", { cache: "no-cache" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const catalog = await response.json();
    if (catalog.schemaVersion !== 1 || !Array.isArray(catalog.devices) || !Array.isArray(catalog.modVersions)) throw new Error("Invalid catalog");
    state.catalog = catalog;
    state.catalog.modReleaseVersions ||= {};
    state.debloatPaths = Array.isArray(catalog.defaultDebloatPaths) ? [...catalog.defaultDebloatPaths] : [];
    state.debloatPathsCustomized = false;
    options($("#device"), [{ value: "", label: t("chooseDevice") }, ...catalog.devices.map((item) => ({ value: item.product, label: `${item.product} — ${item.name}` }))]);
    options($("#mod-version"), catalog.modVersions.map((value) => ({ value, label: `${value} · ${state.catalog.modReleaseVersions[value] || value}` })), catalog.modVersions.includes("ColorOS_16.0.9") ? "ColorOS_16.0.9" : catalog.modVersions.at(-1));
    options($("#catalog-version"), catalog.modVersions.map((value) => ({ value, label: `${value} · ${state.catalog.modReleaseVersions[value] || value}` })), catalog.modVersions.includes("ColorOS_16.0.9") ? "ColorOS_16.0.9" : catalog.modVersions.at(-1));
    if (privateApiAvailable()) await refreshLiveReleaseVersions();
    const count = Object.values(catalog.modsByVersion).reduce((total, names) => total + names.length, 0);
    $("#catalog-status").textContent = t("catalogReady", { mods: count, versions: catalog.modVersions.length });
    $("#catalog-status").closest("div").querySelector("i").classList.add("ok");
    renderPipelineSteps();
    renderMods();
    renderDebloatSummary();
    renderCatalog();
    updateSourceDetection();
    renderSelectedJob();
  } catch (error) {
    $("#catalog-status").textContent = t("catalogFailed");
    toast(t("catalogFailed"), true);
  }
}

async function refreshLiveReleaseVersions() {
  if (!state.catalog || !privateApiAvailable()) return;
  try {
    const selected = $("#mod-version").value;
    const live = await apiRequest("/v1/mod-release-versions");
    state.catalog.modReleaseVersions = { ...state.catalog.modReleaseVersions, ...(live.modReleaseVersions || {}) };
    options(
      $("#mod-version"),
      state.catalog.modVersions.map((value) => ({ value, label: `${value} · ${state.catalog.modReleaseVersions[value] || value}` })),
      selected,
    );
    const catalogSelected = $("#catalog-version").value || selected;
    options(
      $("#catalog-version"),
      state.catalog.modVersions.map((value) => ({ value, label: `${value} · ${state.catalog.modReleaseVersions[value] || value}` })),
      catalogSelected,
    );
    renderReleaseVersion();
    renderCatalog();
  } catch (_) { /* static labels remain usable while the authenticated API reconnects */ }
}

async function runQuickAction(action) {
  if (action === "diagnostics") {
    const payload = await apiRequest("/v1/diagnostics");
    const healthy = Boolean(payload.system || payload.runner || payload.cache);
    $("#telegram-health")?.classList.toggle("ok", healthy);
    toast(healthy ? t("jobsConnected") : t("requestFailed"), !healthy);
    return;
  }
  if (action === "cache") {
    const payload = await apiRequest("/v1/cache");
    toast(`${payload.entryCount ?? 0} cache · ${formatBytes(payload.totalBytes)}`);
    return;
  }
  if (action === "cache_clear") {
    openCacheClearDialog();
    return;
  }
  throw new Error(t("requestFailed"));
}

function openCacheClearDialog() {
  if (state.cacheClearPending) return;
  const dialog = $("#cache-clear-dialog");
  if (dialog && !dialog.open) dialog.showModal();
  TelegramApp?.HapticFeedback?.impactOccurred?.("medium");
}

async function performCacheClear() {
  if (state.cacheClearPending) return;
  const button = $("#cache-clear-confirm");
  state.cacheClearPending = true;
  if (button) {
    button.disabled = true;
    button.textContent = t("cacheClearing");
  }
  try {
    const payload = await apiRequest("/v1/cache/clear", { method: "POST" });
    $("#cache-clear-dialog")?.close();
    toast(t("cacheCleared", { count: payload.entryCount ?? 0 }));
  } catch (error) {
    toast(error.message, true);
  } finally {
    state.cacheClearPending = false;
    if (button) {
      button.disabled = false;
      button.textContent = t("confirmClearCache");
    }
  }
}

function bindEvents() {
  $("#language").addEventListener("click", () => { state.language = state.language === "vi" ? "en" : "vi"; localStorage.setItem("wukong-language", state.language); applyLanguage(); });
  $$('[data-nav]').forEach((button) => button.addEventListener("click", () => navigate(button.dataset.nav)));
  bindLiquidBottomTabs();
  $("#cache-clear-confirm")?.addEventListener("click", () => performCacheClear());
  $$("[data-theme-value]").forEach((button) => button.addEventListener("click", () => applyTheme(button.dataset.themeValue, true)));
  themeMedia?.addEventListener?.("change", handleSystemThemeChange);
  bindTelegramThemeEvents();
  window.addEventListener("scroll", updateMastheadScroll, { passive: true });
  let greetingResizeFrame = 0;
  window.addEventListener("resize", () => {
    cancelAnimationFrame(greetingResizeFrame);
    greetingResizeFrame = requestAnimationFrame(() => {
      updateGreetingOverflow();
      updateDockShellPath();
    });
  }, { passive: true });
  document.fonts?.ready?.then(updateGreetingOverflow).catch(() => {});
  $$('[data-action]').forEach((button) => button.addEventListener("click", () => {
    runQuickAction(button.dataset.action).catch((error) => toast(error.message, true));
  }));
  $("#recipe-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = event.submitter || event.currentTarget.querySelector('[type="submit"]');
    if (button) button.disabled = true;
    try { await submitRecipe(); } catch (error) { toast(error.message, true); }
    finally { if (button) button.disabled = false; }
  });
  $("#source-uri").addEventListener("input", () => { updateSourceDetection(); scheduleSourceProbe(); });
  $("#source-uri").addEventListener("paste", () => queueMicrotask(() => { updateSourceDetection(); scheduleSourceProbe(); }));
  $("#open-rom-catalog").addEventListener("click", () => {
    selectLibraryTab("rom");
    navigate("catalog");
    $("#rom-device-picker summary").focus();
  });
  $("#rom-catalog-form").addEventListener("submit", (event) => {
    event.preventDefault();
    searchRomCatalog();
  });
  $("#rom-device-search").addEventListener("input", renderRomDevices);
  $("#rom-region-filter").addEventListener("change", () => { resetRomResolved(); renderRomVersions(false); renderRomCatalogResults(); });
  $("#rom-version-filter").addEventListener("change", () => { resetRomResolved(); renderRomCatalogResults(); });
  $("#rom-device-search").addEventListener("keydown", (event) => {
    if (event.key === "Enter") { event.preventDefault(); $("[data-rom-device]")?.focus(); }
  });
  $("#rom-devices-retry").addEventListener("click", loadRomDevices);
  $("#rom-device-picker").addEventListener("toggle", () => {
    if ($("#rom-device-picker").open) loadRomDevices();
  });
  $("#rom-device-picker").addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    event.preventDefault();
    $("#rom-device-picker").open = false;
    $("#rom-device-picker summary").focus();
  });
  $$('[data-library-tab]').forEach((button) => {
    button.addEventListener("click", () => selectLibraryTab(button.dataset.libraryTab));
    button.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const name = event.key === "Home" ? "rom" : event.key === "End" ? "technical"
        : button.dataset.libraryTab === "rom" ? "technical" : "rom";
      selectLibraryTab(name, true);
    });
  });
  $("#paste-source").addEventListener("click", () => pasteSourceFromClipboard().catch((error) => toast(error.message, true)));
  $("#connect-telegram").addEventListener("click", () => connectTelegramSession());
  $("#refresh-access").addEventListener("click", () => {
    if (!miniApiAvailable()) { connectTelegramSession(); return; }
    loadSession({ countOpen: false }).catch((error) => toast(error.message, true));
  });
  $("#refresh-maintenance").addEventListener("click", () => {
    loadSession({ countOpen: false }).catch((error) => toast(error.message, true));
  });
  $("#maintenance-toggle").addEventListener("click", () => {
    updateMaintenance().catch((error) => toast(error.message, true));
  });
  $("#maintenance-message-input").addEventListener("input", () => { state.maintenanceMessageDirty = true; });
  $("#clear-source").addEventListener("click", clearSource);
  $("#probe-source").addEventListener("click", () => {
    clearTimeout(state.sourceProbeTimer);
    const probeButton = $("#probe-source");
    if (probeButton.dataset.connectTelegram) { connectTelegramSession(); return; }
    if (probeButton.dataset.closeApp) { closeTelegramApp(); return; }
    if (probeButton.dataset.openBot) { openTelegramBot(); return; }
    probeSourceInPlace().catch((error) => toast(error.message, true));
  });
  $("#select-defaults").addEventListener("click", () => setMods("defaults"));
  $("#select-all").addEventListener("click", () => setMods("all"));
  $("#clear-mods").addEventListener("click", () => setMods("none"));
  $("#mod-version").addEventListener("change", () => renderMods());
  $("#save-mod-release-version").addEventListener("click", () => saveReleaseVersion().catch((error) => toast(error.message, true)));
  $("#preset").addEventListener("change", () => renderMods());
  $("#execution").addEventListener("change", updateSummary);
  $("#device").addEventListener("change", updateSummary);
  $("#mod-list").addEventListener("change", (event) => {
    if (event.target.matches('input[type="checkbox"]')) $("#preset").value = "custom";
    updateSummary();
  });
  $("#mod-search").addEventListener("input", filterMods);
  $("#catalog-search").addEventListener("input", renderCatalog);
  $("#catalog-version").addEventListener("change", renderCatalog);
  $("#admin-release-pack").addEventListener("change", () => { $("#admin-release-label").value = state.catalog.modReleaseVersions[$("#admin-release-pack").value] || $("#admin-release-pack").value; });
  $("#save-admin-release").addEventListener("click", () => savePermanentReleaseVersion().catch(error => toast(error.message, true)));
  $("#open-batch-build").addEventListener("click", openBatchBuildPage);
  $("#admin-batch-back").addEventListener("click", closeBatchBuildPage);
  $("#start-batch-build").addEventListener("click", () => startBatchBuild().catch(error => toast(error.message, true)));
  $("#refresh-batch").addEventListener("click", () => loadBatch().catch(error => toast(error.message, true)));
  $("#batch-devices").addEventListener("change", updateBatchSummary);
  $("#batch-mod-versions").addEventListener("change", updateBatchSummary);
  $("#batch-lite").addEventListener("change", updateBatchSummary);
  $("#batch-plus").addEventListener("change", updateBatchSummary);
  $("#steps").addEventListener("change", updatePipelineCount);
  $("#edit-debloat-paths").addEventListener("click", openDebloatEditor);
  $("#save-debloat-paths").addEventListener("click", saveDebloatPaths);
  $("#cancel-debloat-paths").addEventListener("click", closeDebloatEditor);
  $$(".switches input").forEach((input) => input.addEventListener("change", () => {
    state.delivery[input.id] = input.checked ? "pending" : "skipped";
    updateSummary();
  }));
  $("#default-preset").value = state.defaultPreset;
  $("#preset").value = state.defaultPreset;
  $("#default-preset").addEventListener("change", (event) => {
    state.defaultPreset = event.target.value;
    localStorage.setItem("wukong-default-preset", state.defaultPreset);
    $("#preset").value = state.defaultPreset;
    renderMods();
  });
  $("#refresh-jobs").addEventListener("click", () => loadJobs({ force: true }).catch((error) => toast(error.message, true)));
  $$("[data-job-filter]").forEach((button) => button.addEventListener("click", () => {
    state.jobHistoryFilter = button.dataset.jobFilter;
    renderJobHistory();
  }));
  let userSearchTimer;
  $("#user-search").addEventListener("input", () => { clearTimeout(userSearchTimer); userSearchTimer = setTimeout(() => loadAdminUsers({ reset: true }).catch(() => {}), 250); });
  $("#user-status").addEventListener("change", () => loadAdminUsers({ reset: true }).catch(() => {}));
  $("#user-quota-filter").addEventListener("change", () => loadAdminUsers({ reset: true }).catch(() => {}));
  $("#user-activity-filter").addEventListener("change", () => loadAdminUsers({ reset: true }).catch(() => {}));
  $("#user-sort").addEventListener("change", () => loadAdminUsers({ reset: true }).catch(() => {}));
  $("#user-prev").addEventListener("click", () => { state.adminUsersOffset = Math.max(0, state.adminUsersOffset - 25); loadAdminUsers().catch(() => {}); });
  $("#user-next").addEventListener("click", () => { state.adminUsersOffset += 25; loadAdminUsers().catch(() => {}); });
  $("#add-user").addEventListener("click", () => $("#user-create-dialog").showModal());
  $("#admin-user-back").addEventListener("click", () => closeAdminUserPage());
  $("#admin-job-back").addEventListener("click", () => closeAdminJobPage());
  $("#refresh-admin-job").addEventListener("click", () => loadAdminJobDetail());
  $("#user-create-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await apiRequest("/v1/admin/users", {
        method: "POST",
        body: JSON.stringify({
          telegramId: $("#new-user-id").value.trim(),
          username: $("#new-user-username").value.trim(),
          displayName: $("#new-user-display-name").value.trim()
        })
      });
      $("#user-create-form").reset(); $("#user-create-dialog").close(); toast(t("userCreated"));
      await loadAdminUsers({ reset: true });
    } catch (error) { toast(error.message, true); }
  });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      clearTimeout(state.adminUsersPollTimer);
      clearTimeout(state.adminUserPollTimer);
      clearTimeout(state.adminJobView?.timer);
      clearTimeout(state.jobsPollTimer);
      clearTimeout(state.maintenancePollTimer);
      clearTimeout(state.batchPollTimer);
      state.batchPollTimer = null;
      clearInterval(state.greetingTimer);
    }
    else {
      if (state.adminJobView) loadAdminJobDetail();
      else if (state.selectedAdminUserId) refreshAdminUserActivity();
      if (document.body.dataset.view === "system" && !$("#admin-batch-page").hidden) loadLatestBatch().catch(() => {});
      scheduleGreeting();
      ensureAutomaticTelegramConnection();
      loadSession({ countOpen: false }).then(() => initializeApprovedWorkspace()).catch(() => {});
    }
  });
  $("#copy-source-metadata").addEventListener("click", () => copySourceMetadata().catch((error) => toast(error.message, true)));
  const docket = $(".dispatch-docket");
  const fab = $("#dispatch-fab");
  if (docket && fab && "IntersectionObserver" in window) {
    new IntersectionObserver(([entry]) => {
      state.docketInView = entry.isIntersecting;
      updateDispatchFab();
    }, { threshold: .18 }).observe(docket);
    fab.addEventListener("click", () => docket.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block: "center" }));
  }
}

function renderSessionDiagnostics() {
  const node = $("#session-diag");
  if (!node) return;
  if (activeSignedLaunchToken()) { node.textContent = t("sessionDiagLaunchToken"); return; }
  if (!TelegramApp && !effectiveInitData()) { node.textContent = t("sessionDiagNoLib"); return; }
  const rawDirect = String(TelegramApp?.initData || "");
  const fallback = !rawDirect ? effectiveInitData() : "";
  const chars = String(effectiveInitData() || "").length;
  if (!chars) { node.textContent = t("sessionDiagNoData"); return; }
  const via = fallback ? " (từ hash)" : "";
  node.textContent = t("sessionDiagOk", { platform: (TelegramApp?.platform || "?") + via, chars });
}

function activateTelegramApp() {
  try {
    TelegramApp.ready(); TelegramApp.expand();
    if (TelegramApp.isVersionAtLeast?.("7.7")) TelegramApp.disableVerticalSwipes?.();
    if (TelegramApp.isVersionAtLeast?.("6.1")) {
      TelegramApp.setHeaderColor?.("secondary_bg_color");
      TelegramApp.setBackgroundColor?.("secondary_bg_color");
    }
  } catch (_) {}
}

function ensureAutomaticTelegramConnection() {
  const insideTelegram = Boolean(TelegramApp?.platform && TelegramApp.platform !== "unknown");
  if (miniApiAvailable() || !miniApiEndpoint || !insideTelegram || state.pairingInFlight) return;
  const pairing = storedPairing();
  if (pairing) {
    state.pairingInFlight = true;
    updateSummary();
    pollTelegramPairing(pairing).catch(() => {
      state.pairingInFlight = false;
      updateSummary();
      toast(t("pairingFailed"), true);
    });
    return;
  }
  connectTelegramSession();
}

function startMiniApp() {
  applyTheme(state.theme);
  bindEvents();
  updateMastheadScroll();
  scheduleGreeting();
  restoreSourceDraft();
  window.WukongMiniApp = Object.freeze({ setDeliveryState });
  applyLanguage();
  history.scrollRestoration = "manual";
  renderSessionDiagnostics();
  ensureAutomaticTelegramConnection();
  if (miniApiAvailable()) {
    loadSession().then(() => {
      initializeApprovedWorkspace();
    }).catch((error) => toast(error.message, true));
  } else renderAccessGate();
}

if (TelegramApp) {
  activateTelegramApp();
  startMiniApp();
} else {
  // The official bridge failed to load before boot (blocked CDN, flaky
  // network inside the Telegram webview). Render the UI anyway, then inject
  // the bridge once more so a real session can still attach late.
  startMiniApp();
  const bridge = document.createElement("script");
  bridge.src = "https://telegram.org/js/telegram-web-app.js";
  bridge.async = true;
  bridge.addEventListener("load", () => {
    TelegramApp = (window.Telegram && window.Telegram.WebApp) || null;
    if (!TelegramApp) { renderSessionDiagnostics(); return; }
    activateTelegramApp();
    bindTelegramThemeEvents();
    applyTheme(state.theme);
    restoreSourceDraft();
    updateTelegramState();
    updateSourceDetection();
    scheduleSourceProbe();
    renderSessionDiagnostics();
    ensureAutomaticTelegramConnection();
    if (miniApiAvailable()) {
      loadSession({ countOpen: false }).then(() => initializeApprovedWorkspace()).catch(() => {});
    } else renderAccessGate();
  });
  bridge.addEventListener("error", renderSessionDiagnostics);
  document.head.append(bridge);
}
