

export const runtime = {};

import { mergeEvents, eventCursor } from "../lib/log-buffer.js";

import { requestJson, RequestScopes } from "../lib/http.js";

const requestScopes = new RequestScopes();

runtime.TelegramApp = window.Telegram && window.Telegram.WebApp;

const configuredMiniApiEndpoint = document.querySelector('meta[name="wukong-mini-api-endpoint"]')?.content?.trim() || "";

const miniApiEndpoint = configuredMiniApiEndpoint.startsWith("__") ? "" : configuredMiniApiEndpoint.replace(/\/$/, "");

const telegramBotUsername = (document.querySelector('meta[name="wukong-telegram-bot"]')?.content?.trim().replace(/^@/, "") || "");

const publicRomCatalogEndpoint = "https://roms.danielspringer.at/api/ota.php";

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

runtime.signedTelegramLaunchToken = consumeSignedLaunchToken();

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
runtime.cachedTelegramInitData = parseInitDataFromHash();

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
  dcCloudRepair: "Repair DC Cloud mirror",
  dcCloudRepairHint: "Upload lại ZIP lên DC Cloud nếu lần mirror trước bị lỗi.",
  dcCloudRepairQueued: "Đã đưa yêu cầu repair DC Cloud vào hàng đợi.",
  dcCloudRepairFailed: "Không thể bắt đầu repair DC Cloud."
});

Object.assign(translations.en, {
  dcCloudRepair: "Repair DC Cloud mirror",
  dcCloudRepairHint: "Re-upload the ZIP to DC Cloud when the previous mirror failed.",
  dcCloudRepairQueued: "DC Cloud repair has been queued.",
  dcCloudRepairFailed: "Could not start DC Cloud repair."
});

Object.assign(translations.vi, {
  buildTitle: "Wukong Studio", buildIntro: "Cấu hình, khởi chạy và theo dõi ROM ngay trong Mini App.",
  releaseVersion: "Phiên bản phát hành", releaseVersionHint: "Nhãn hiển thị cùng MOD pack trong mỗi job.", saveReleaseVersion: "Lưu nhãn", invalidReleaseVersion: "Nhãn dài 1–64 ký tự, an toàn cho tên file và không kết thúc bằng dấu chấm hoặc khoảng trắng.", releaseVersionSaved: "Đã lưu nhãn phát hành.", jobContext: "Ngữ cảnh job", uploadingNow: "Đang upload", uploadSummary: "Upload gần nhất", noModsSelected: "Không có MOD tùy chọn",
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
  jobsLoading: "Đang đồng bộ lịch sử job…", jobsConnected: "Đã đồng bộ · tự làm mới job và DC Cloud mirror", jobsOffline: "Mất kết nối API · sẽ tự thử lại", jobHistoryKicker: "LỊCH SỬ", jobHistory: "Các lần chạy gần đây", jobHistoryToday: "Hôm nay", jobHistoryYesterday: "Hôm qua", jobSearch: "Tìm lịch sử job", jobPresetFilter: "Preset", jobModFilter: "MOD version", jobDateFrom: "Từ ngày", jobDateTo: "Đến ngày", allJobs: "Tất cả", clearJobFilters: "Xóa bộ lọc", jobPageSummary: "{from}–{to} / {total} job", jobPrevious: "Trước", jobNext: "Sau", jobPage: "Trang {page}", jobFilterEmpty: "Không có job phù hợp với bộ lọc.", jobHistoryLoading: "Đang tải lịch sử…",
  noJobsTitle: "Chưa có job", noJobsMessage: "Tạo một cấu hình build; job sẽ được lưu và theo dõi tại đây.", newBuild: "Tạo build đầu tiên", buildCreated: "Đã tạo job và bắt đầu theo dõi trong Mini App.",
  activeJob: "JOB ĐANG CHẠY", eventTimeline: "Nhật ký trực tiếp", eventsPreview: "{visible} thẻ / {total} cập nhật", uploadUpdates: "{count} lần cập nhật đã gộp", uploadTransferred: "Đã tải", uploadSpeed: "Tốc độ", uploadEta: "Còn lại", uploadComplete: "Hoàn tất", viewFullLog: "Xem toàn bộ nhật ký", hideFullLog: "Thu gọn nhật ký", fullLogTitle: "Toàn bộ nhật ký build", eventRunning: "Đang thực hiện", eventSucceeded: "Đã hoàn tất", eventFailed: "Thất bại", eventSteps: "bước", eventDetails: "Thông số chi tiết", finishBuild: "Hoàn tất cấu hình build", artifactsReady: "Artifact & link tải", noEvents: "Chưa có sự kiện mới.", noArtifacts: "Artifact sẽ xuất hiện sau khi build và upload hoàn tất.",
  retryJob: "Chạy lại", openActionsLog: "Mở log GitHub Actions", elapsed: "Thời gian", createdAt: "Khởi tạo", modConfiguration: "Cấu hình", autoSelected: "Đã tự chọn thiết bị {device} từ metadata ROM.", apiRequired: "Mini App API chưa được cấu hình. Hãy liên hệ quản trị viên.", requestFailed: "Không thể kết nối Mini App API.",
  openArtifactCloud: "Mở trên {provider}", downloadArtifactCloud: "Tải xuống từ {provider}", copyArtifactLink: "Sao chép link tải", artifactLinkCopied: "Đã sao chép link tải.", artifactLinkUnavailable: "Link cloud chưa sẵn sàng.", dcCloudMirror: "DC Cloud mirror", dcCloudMirrorPending: "DC Cloud mirror đang upload…", dcCloudMirrorFailed: "DC Cloud mirror chưa sẵn sàng", dcCloudMirrorRepairing: "DC Cloud mirror đang repair…"
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
  releaseVersion: "Release version", releaseVersionHint: "This label follows the MOD pack into every job.", saveReleaseVersion: "Save label", invalidReleaseVersion: "Use 1–64 filename-safe characters; do not end with a period or space.", releaseVersionSaved: "Release label saved.", jobContext: "Job context", uploadingNow: "Uploading now", uploadSummary: "Latest upload", noModsSelected: "No optional MODs",
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
  jobsLoading: "Syncing job history…", jobsConnected: "Synced · jobs and DC Cloud mirrors refresh automatically", jobsOffline: "API connection lost · retrying automatically", jobHistoryKicker: "HISTORY", jobHistory: "Recent runs", jobHistoryToday: "Today", jobHistoryYesterday: "Yesterday", jobSearch: "Search job history", jobPresetFilter: "Preset", jobModFilter: "MOD version", jobDateFrom: "From date", jobDateTo: "To date", allJobs: "All", clearJobFilters: "Clear filters", jobPageSummary: "{from}–{to} / {total} jobs", jobPrevious: "Previous", jobNext: "Next", jobPage: "Page {page}", jobFilterEmpty: "No jobs match these filters.", jobHistoryLoading: "Loading history…",
  noJobsTitle: "No jobs yet", noJobsMessage: "Create a build configuration; its progress and result will remain here.", newBuild: "Create first build", buildCreated: "Job created and now tracked inside the Mini App.",
  activeJob: "ACTIVE JOB", eventTimeline: "Live event log", eventsPreview: "{visible} cards / {total} updates", uploadUpdates: "{count} updates collapsed", uploadTransferred: "Transferred", uploadSpeed: "Speed", uploadEta: "Remaining", uploadComplete: "Complete", viewFullLog: "View full log", hideFullLog: "Collapse log", fullLogTitle: "Complete build log", eventRunning: "In progress", eventSucceeded: "Completed", eventFailed: "Failed", eventSteps: "steps", eventDetails: "Detailed data", finishBuild: "Complete build configuration", artifactsReady: "Artifacts & downloads", noEvents: "No new events yet.", noArtifacts: "Artifacts appear after the build and upload finish.",
  retryJob: "Retry", openActionsLog: "Open GitHub Actions log", elapsed: "Elapsed", createdAt: "Created", modConfiguration: "Configuration", autoSelected: "Device {device} was selected from ROM metadata.", apiRequired: "The Mini App API is not configured. Contact the administrator.", requestFailed: "Could not reach the Mini App API.",
  openArtifactCloud: "Open in {provider}", downloadArtifactCloud: "Download from {provider}", copyArtifactLink: "Copy download link", artifactLinkCopied: "Download link copied.", artifactLinkUnavailable: "The cloud link is not ready yet.", dcCloudMirror: "DC Cloud mirror", dcCloudMirrorPending: "DC Cloud mirror is uploading…", dcCloudMirrorFailed: "DC Cloud mirror is not ready", dcCloudMirrorRepairing: "DC Cloud mirror is being repaired…"
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
  romDevicesRetry: "Tải lại danh sách", romDevicesEmpty: "Không có thiết bị phù hợp.", romDevicesCount: "{count} thiết bị", romDevicesPublic: "Danh sách OTA công khai · {count} thiết bị", romDevicesLocal: "Danh sách thiết bị build · {count} thiết bị",
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
  romDevicesRetry: "Reload devices", romDevicesEmpty: "No matching devices.", romDevicesCount: "{count} devices", romDevicesPublic: "Public OTA list · {count} devices", romDevicesLocal: "Build device list · {count} devices",
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

Object.assign(translations.vi, {
  presetLabelsTitle: "Tên bản build", presetLabelsHint: "Đổi tên hiển thị và tên file cho Lite, Plus hoặc Custom. Mã preset nội bộ vẫn giữ nguyên.",
  presetLabelLite: "Tên Lite", presetLabelPlus: "Tên Plus", presetLabelCustom: "Tên Custom", savePresetLabels: "Lưu vĩnh viễn",
  invalidPresetLabel: "Tên bản build dài 1–64 ký tự, không chứa ký tự đặc biệt của tên file và không kết thúc bằng dấu chấm hoặc khoảng trắng.", presetLabelsSaved: "Đã lưu tên bản build cho các job sau.",
  customPresetJobTitle: "Tên bản Custom", customPresetJobHint: "Đổi Custom thành tên riêng như Limited; chỉ áp dụng cho job hiện tại.",
  applyCustomPresetJob: "Áp dụng cho job", customPresetJobSaved: "Đã áp dụng tên bản Custom cho job hiện tại.",
  releaseVersionPlaceholder: "Ví dụ: V5.1"
});

Object.assign(translations.en, {
  openUserJob: "View job", jobCreator: "Created by", jobParameters: "All job parameters", loadMoreUserJobs: "Load older jobs",
  jobParametersHint: "Read-only · Saved configuration and actual state. Credentials and temporary signed source ROM links are hidden.",
  jobRecipeData: "Requested configuration", jobRuntimeData: "State and results", copyJobParameters: "Copy parameters",
  jobParametersCopied: "Job parameters copied.", jobUnavailable: "Could not open this job. Refresh or select another job.",
  jobCreatedAt: "Created", jobUpdatedAt: "Updated", loadMoreJobEvents: "Load more events", viewJobUser: "Open user profile"
});

Object.assign(translations.en, {
  presetLabelsTitle: "Build names", presetLabelsHint: "Rename the display name and filename for Lite, Plus or Custom. Internal preset keys stay unchanged.",
  presetLabelLite: "Lite name", presetLabelPlus: "Plus name", presetLabelCustom: "Custom name", savePresetLabels: "Save permanently",
  invalidPresetLabel: "The build name must be 1–64 characters, contain no filename-reserved characters, and not end with a dot or space.", presetLabelsSaved: "Build names saved for future jobs.",
  customPresetJobTitle: "Custom build name", customPresetJobHint: "Rename Custom to a job-specific name such as Limited; this applies only to the current job.",
  applyCustomPresetJob: "Apply to job", customPresetJobSaved: "Custom build name applied to the current job.",
  releaseVersionPlaceholder: "Example: V5.1"
});

Object.assign(translations.vi, {
  jobSearchPlaceholder: "Job ID / thiết bị / phiên bản / user",
  jobModPlaceholder: "ColorOS_16.0.10"
});

Object.assign(translations.en, {
  jobSearchPlaceholder: "Job ID / device / version / user",
  jobModPlaceholder: "ColorOS_16.0.10"
});

Object.assign(translations.vi, { requestTimedOut: "Yêu cầu quá thời gian chờ. Hãy thử lại.", confirmingJob: "Đang xác nhận job. Dùng nút Xác nhận lại để kiểm tra cùng yêu cầu; cấu hình đã gửi được giữ nguyên.", confirmAgain: "Xác nhận lại", metadataDetails: "Thông tin chi tiết", advancedBuild: "Tùy chọn nâng cao", latestUpdate: "Cập nhật gần nhất", previousEvents: "Trang nhật ký trước", nextEvents: "Trang nhật ký tiếp", logPage: "Trang nhật ký {page}" });

Object.assign(translations.en, { requestTimedOut: "The request timed out. Please retry.", confirmingJob: "Confirming your job. Use Confirm again to check the same request; the submitted configuration is preserved.", confirmAgain: "Confirm again", metadataDetails: "Technical details", advancedBuild: "Advanced options", latestUpdate: "Last updated", previousEvents: "Previous log page", nextEvents: "Next log page", logPage: "Log page {page}" });

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
  jobHistoryFilter: "active",
  jobHistoryPage: 1,
  jobHistoryPageSize: 20,
  jobHistoryTotal: 0,
  jobHistoryTotalPages: 1,
  jobHistoryStatusCounts: { active: 0, succeeded: 0, failed: 0 },
  jobHistoryRequestId: 0,
  jobHistoryLoading: false,
  sourceProbeTimer: null,
  sourceProbeUri: "",
  sourceInputUri: "",
  sourceProbeController: null,
  sourceProbeRequestId: 0,
  pairingPollTimer: null,
  pairingPollAttempt: 0,
  pairingInFlight: false,
  docketInView: true,
  presetLabels: { lite: "Lite", plus: "Plus", custom: "Custom" },
  customPresetLabelOverride: "",
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
  romDevicesSource: "remote",
  romDevicesError: "",
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
  workspaceLoaded: false,
  submitInFlight: false
};

function workspacePollingAllowed() {
  return document.hidden !== true && (typeof navigator === "undefined" || navigator.onLine !== false);
}

function t(key, values = {}) {
  let value = translations[state.language][key] || translations.vi[key] || key;
  for (const [name, replacement] of Object.entries(values)) value = value.replace(`{${name}}`, replacement);
  return value;
}

const themeMedia = window.matchMedia?.("(prefers-color-scheme: dark)");

runtime.telegramThemeEventsBoundTo = null;

const liquidSlots = [0, 1, 2, 3, 4];

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

const romDeviceBrands = new Set(["oneplus", "oppo", "realme"]);

const romDeviceWords = { OP: "OnePlus", PRO: "Pro", ULTRA: "Ultra", ACE: "Ace", FIND: "Find", RENO: "Reno", NORD: "Nord", PAD: "Pad", OPEN: "Open", TURBO: "Turbo", LITE: "Lite", RACING: "Racing", GO: "Go", REALME: "Realme" };

const terminalJobStatuses = new Set(["succeeded", "failed", "cancelled"]);

const eventTypeLabels = {
  vi: {
    submitted: "Đã tạo job", dispatched: "Đã gửi tới runner", github_run: "GitHub Actions",
    state: "Cập nhật trạng thái", running: "Runner đang xử lý", source: "ROM nguồn sẵn sàng",
    checkpoint: "Đã lưu checkpoint", upload_progress: "Đang tải artifact", artifacts: "Artifact hoàn tất",
    warning: "Cảnh báo", mirror_upload_failed: "DC Cloud mirror thất bại", mirror_available: "DC Cloud mirror sẵn sàng", error: "Lỗi", cancelled: "Đã hủy job", resumed: "Tiếp tục từ checkpoint",
    plan: "Kế hoạch build", step: "Bước build", telegram_terminal_notified: "Đã gửi thông báo Telegram"
  },
  en: {
    submitted: "Job created", dispatched: "Sent to runner", github_run: "GitHub Actions",
    state: "Status update", running: "Runner processing", source: "Source ROM ready",
    checkpoint: "Checkpoint saved", upload_progress: "Uploading artifact", artifacts: "Artifacts ready",
    warning: "Warning", mirror_upload_failed: "DC Cloud mirror failed", mirror_available: "DC Cloud mirror ready", error: "Error", cancelled: "Job cancelled", resumed: "Resumed from checkpoint",
    plan: "Build plan", step: "Build step", telegram_terminal_notified: "Telegram notification sent"
  }
};

const eventStageLabels = {
  vi: { preflight: "Kiểm tra", download: "Tải ROM", build: "Build ROM", upload: "Tải lên", complete: "Hoàn tất", "github-actions": "GitHub Actions", "github-actions-running": "GitHub Actions" },
  en: { preflight: "Preflight", download: "ROM download", build: "ROM build", upload: "Upload", complete: "Complete", "github-actions": "GitHub Actions", "github-actions-running": "GitHub Actions" }
};

export { mergeEvents, eventCursor, requestJson, RequestScopes, requestScopes, configuredMiniApiEndpoint, miniApiEndpoint, telegramBotUsername, publicRomCatalogEndpoint, validSignedLaunchToken, consumeSignedLaunchToken, parseInitDataFromHash, translations, pipelineLabels, $, $$, state, t, themeMedia, liquidSlots, sourceFactDefinitions, completenessSourceFactIds, requiredSourceFactIds, ZIP_METADATA_SUFFIXES, ZIP_MAX_METADATA_FILES, ZIP_MAX_METADATA_FILE_BYTES, ZIP_MAX_METADATA_TEXT_BYTES, ZIP_MAX_METADATA_FIELDS, ZIP_MAX_RANGE_BYTES, ZIP_MAX_CLIENT_BYTES, romDeviceBrands, romDeviceWords, terminalJobStatuses, eventTypeLabels, eventStageLabels, workspacePollingAllowed };

Object.assign(translations.vi, { reviewBuild: "Kiểm tra và build", selectionSummary: "{mods} MOD · {steps} bước pipeline", keyboardEditing: "Đang nhập cấu hình", syncSnapshot: "Dữ liệu lúc {time}", recipeHint: "Chọn preset và nền MOD. Tùy chỉnh thêm khi cần." });
Object.assign(translations.en, { reviewBuild: "Review and build", selectionSummary: "{mods} MODs · {steps} pipeline steps", keyboardEditing: "Editing configuration", syncSnapshot: "Snapshot at {time}", recipeHint: "Choose a preset and MOD base. Fine-tune options when needed." });
