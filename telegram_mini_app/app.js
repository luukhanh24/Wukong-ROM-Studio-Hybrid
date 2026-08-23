let TelegramApp = window.Telegram && window.Telegram.WebApp;
const configuredMiniApiEndpoint = document.querySelector('meta[name="wukong-mini-api-endpoint"]')?.content?.trim() || "";
const miniApiEndpoint = configuredMiniApiEndpoint.startsWith("__") ? "" : configuredMiniApiEndpoint.replace(/\/$/, "");
const telegramBotUsername = (document.querySelector('meta[name="wukong-telegram-bot"]')?.content?.trim().replace(/^@/, "") || "");

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
function effectiveInitData() {
  const direct = String(TelegramApp?.initData || "");
  if (direct) return direct;
  return parseInitDataFromHash();
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
  probeDeferred: "Máy chủ đang bận phân tích ROM. Hãy thử lại sau ít phút.",
  probeDeferredKicker: "ĐANG CHỜ MÁY CHỦ"
});

Object.assign(translations.vi, {
  detectedProduct: "Product", detectedDevice: "Mã thiết bị", androidVersion: "Android", securityPatch: "Bản vá bảo mật", buildDate: "Ngày build", sourceSizeDetected: "Dung lượng", otaType: "Kiểu OTA", contentType: "Định dạng", lastModified: "Cập nhật máy chủ", deepInspection: "Kiểm tra ZIP",
  metadataTitle: "ROM METADATA", metadataCompleteness: "{complete}/{total} thông số", copyMetadata: "Sao chép thông số", metadataCopied: "Đã sao chép toàn bộ thông số ROM.", deepInspected: "Đã đọc metadata trong ZIP", headersOnly: "Chỉ đọc được header máy chủ",
  apiUnavailableKicker: "API CHƯA KẾT NỐI", apiUnavailableMessage: "Bản Mini App này chưa được gắn máy chủ API. Không thể đọc metadata sâu hoặc tạo job cho đến khi quản trị viên triển khai API.", apiUnavailableButton: "Chưa có máy chủ API", apiSessionOnly: "TELEGRAM · CHƯA CÓ API",
  apiAuthKicker: "CẦN PHIÊN TELEGRAM", apiAuthMessage: "Mở Mini App từ nút trong bot Telegram để xác thực rồi phân tích ROM.", apiAuthButton: "Mở từ bot Telegram", apiOfflineKicker: "MẤT KẾT NỐI API", apiOfflineMessage: "Không kết nối được máy chủ Mini App API. Link vẫn được giữ nguyên; hãy thử lại khi API hoạt động.",
  sessionDiagTitle: "Phiên Telegram", sessionDiagOk: "Thư viện Telegram đã nạp · nền {platform} · initData {chars} ký tự · phiên hợp lệ.", sessionDiagNoData: "Thư viện đã nạp nhưng initData trống → trang đang mở bằng link trực tiếp, không phải từ nút Mini App trong bot. Quay lại tab Studio và bấm “Mở từ bot Telegram”.", sessionDiagNoLib: "Không nạp được thư viện Telegram (telegram.org có thể bị chặn). Kiểm tra mạng rồi mở lại từ bot.",
  probePartial: "Nguồn ROM hoạt động nhưng metadata chưa đủ. Hãy kiểm tra link hoặc dùng trang OTA có metadata đầy đủ.", probeStale: "Đã bỏ kết quả cũ vì URL nguồn đã thay đổi.",
  checklistApi: "Mini App API", checklistApiDone: "Đã xác thực với máy chủ", checklistApiPending: "Chưa kết nối máy chủ", checklistApiAuthPending: "Cần mở từ bot Telegram", checklistSourceVerified: "Đã đọc metadata ROM", checklistSourceProbePending: "Đang chờ phân tích metadata", readinessProgress: "{done}/4 điều kiện", apiRequiredHint: "Mini App API chưa sẵn sàng nên chưa thể tạo job.", sourceProbePendingHint: "Hãy chờ phân tích metadata ROM hoàn tất.",
  jobsLoading: "Đang đồng bộ lịch sử job…", jobsConnected: "Đã đồng bộ · tự làm mới khi job đang chạy", jobsOffline: "Mất kết nối API · sẽ tự thử lại", jobHistoryKicker: "LỊCH SỬ", jobHistory: "Các lần chạy gần đây",
  noJobsTitle: "Chưa có job", noJobsMessage: "Tạo một cấu hình build; job sẽ được lưu và theo dõi tại đây.", newBuild: "Tạo build đầu tiên", buildCreated: "Đã tạo job và bắt đầu theo dõi trong Mini App.",
  activeJob: "JOB ĐANG CHẠY", eventTimeline: "Nhật ký trực tiếp", artifactsReady: "Artifact & link tải", noEvents: "Chưa có sự kiện mới.", noArtifacts: "Artifact sẽ xuất hiện sau khi build và upload hoàn tất.",
  retryJob: "Chạy lại", openActionsLog: "Mở log GitHub Actions", elapsed: "Thời gian", createdAt: "Khởi tạo", modConfiguration: "Cấu hình", autoSelected: "Đã tự chọn thiết bị {device} từ metadata ROM.", apiRequired: "Mini App API chưa được cấu hình. Hãy liên hệ quản trị viên.", requestFailed: "Không thể kết nối Mini App API."
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
  probeDeferred: "The server is busy analyzing ROMs. Try again in a moment.",
  probeDeferredKicker: "WAITING FOR SERVER"
});

Object.assign(translations.en, {
  detectedProduct: "Product", detectedDevice: "Device code", androidVersion: "Android", securityPatch: "Security patch", buildDate: "Build date", sourceSizeDetected: "Size", otaType: "OTA type", contentType: "Content type", lastModified: "Server modified", deepInspection: "ZIP inspection",
  metadataTitle: "ROM METADATA", metadataCompleteness: "{complete}/{total} fields", copyMetadata: "Copy metadata", metadataCopied: "All ROM metadata was copied.", deepInspected: "Metadata read from ZIP", headersOnly: "Server headers only",
  apiUnavailableKicker: "API NOT CONNECTED", apiUnavailableMessage: "This Mini App release is not bound to an API server. Deep metadata and job creation remain unavailable until the administrator deploys the API.", apiUnavailableButton: "API server unavailable", apiSessionOnly: "TELEGRAM · API OFFLINE",
  apiAuthKicker: "TELEGRAM SESSION REQUIRED", apiAuthMessage: "Open the Mini App from the Telegram bot button to authenticate and analyze the ROM.", apiAuthButton: "Open from Telegram bot", apiOfflineKicker: "API CONNECTION LOST", apiOfflineMessage: "The Mini App API could not be reached. The link is preserved; retry when the API is online.",
  sessionDiagTitle: "Telegram session", sessionDiagOk: "Telegram bridge loaded · platform {platform} · initData {chars} chars · session valid.", sessionDiagNoData: "Bridge loaded but initData is empty → this page was opened as a direct link, not from the bot's Mini App button. Go back to Studio and press “Open from Telegram bot”.", sessionDiagNoLib: "The Telegram bridge could not load (telegram.org may be blocked). Check the network and reopen from the bot.",
  probePartial: "The ROM source is reachable, but metadata is incomplete. Check the link or use an OTA page with complete metadata.", probeStale: "The old result was discarded because the source URL changed.",
  checklistApi: "Mini App API", checklistApiDone: "Authenticated with server", checklistApiPending: "API server not connected", checklistApiAuthPending: "Open from the Telegram bot", checklistSourceVerified: "ROM metadata inspected", checklistSourceProbePending: "Waiting for metadata analysis", readinessProgress: "{done}/4 checks", apiRequiredHint: "The Mini App API is not ready, so a job cannot be created.", sourceProbePendingHint: "Wait for ROM metadata analysis to finish.",
  jobsLoading: "Syncing job history…", jobsConnected: "Synced · active jobs refresh automatically", jobsOffline: "API connection lost · retrying automatically", jobHistoryKicker: "HISTORY", jobHistory: "Recent runs",
  noJobsTitle: "No jobs yet", noJobsMessage: "Create a build configuration; its progress and result will remain here.", newBuild: "Create first build", buildCreated: "Job created and now tracked inside the Mini App.",
  activeJob: "ACTIVE JOB", eventTimeline: "Live event log", artifactsReady: "Artifacts & downloads", noEvents: "No new events yet.", noArtifacts: "Artifacts appear after the build and upload finish.",
  retryJob: "Retry", openActionsLog: "Open GitHub Actions log", elapsed: "Elapsed", createdAt: "Created", modConfiguration: "Configuration", autoSelected: "Device {device} was selected from ROM metadata.", apiRequired: "The Mini App API is not configured. Contact the administrator.", requestFailed: "Could not reach the Mini App API."
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
  delivery: { package: "pending", publish: "pending", notify: "pending" },
  jobs: [],
  activeJobId: localStorage.getItem("wukong-active-job") || "",
  activeEvents: [],
  activeEventsJobId: "",
  jobsPollTimer: null,
  jobsLoading: false,
  sourceProbeTimer: null,
  sourceProbeUri: "",
  sourceInputUri: "",
  sourceProbeController: null,
  sourceProbeRequestId: 0
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
  renderJobHistory();
  const activeJob = state.jobs.find((job) => (job.job_id || job.jobId) === state.activeJobId);
  if (activeJob) renderActiveJob(activeJob, state.activeEvents);
  renderSessionDiagnostics();
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

function miniApiAvailable() {
  return Boolean(miniApiEndpoint && effectiveInitData());
}

function miniApiState() {
  if (!miniApiEndpoint) return "unconfigured";
  if (!effectiveInitData()) return "unauthenticated";
  return "ready";
}

async function apiRequest(path, options = {}) {
  if (!miniApiEndpoint) throw new Error(t("apiRequired"));
  const initData = effectiveInitData();
  if (!initData) throw new Error(t("telegramOnly"));
  const headers = new Headers(options.headers || {});
  headers.set("Authorization", `tma ${initData}`);
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
    const error = new Error(payload.error || `HTTP ${response.status}`);
    error.status = response.status;
    error.sourceRejected = response.status >= 400 && response.status < 500;
    throw error;
  }
  return payload;
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
  if (name === "jobs") loadJobs({ force: true }).catch(() => {});
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

const requiredSourceFactIds = sourceFactDefinitions
  .map(([id]) => id)
  .filter((id) => id !== "source-deep-inspection");

function setSourceFact(id, value) {
  const node = $(`#${id}`);
  if (!node) return;
  const text = String(value || "").trim();
  node.textContent = text || "—";
  node.dataset.empty = text && text !== "—" ? "false" : "true";
  node.title = text && text !== "—" ? text : "";
}

function updateMetadataCompleteness() {
  const complete = requiredSourceFactIds.filter((id) => {
    const value = $(`#${id}`)?.textContent?.trim();
    return value && value !== "—" && value !== "···";
  }).length;
  const total = requiredSourceFactIds.length;
  $("#source-metadata-count").textContent = t("metadataCompleteness", { complete, total });
  return { complete, total };
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

async function copySourceMetadata() {
  const text = sourceMetadataText();
  if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(text);
  else {
    const input = document.createElement("textarea"); input.value = text;
    input.style.position = "fixed"; input.style.opacity = "0"; input.style.pointerEvents = "none";
    document.body.append(input); input.select(); document.execCommand("copy"); input.remove();
  }
  toast(t("metadataCopied"));
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
  button.textContent = t(unconfigured ? "apiUnavailableButton" : insideTelegram ? "Đóng" : "apiAuthButton");
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
    button.dataset.closeApp = "1";
    delete button.dataset.openBot;
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
  node.classList.remove("probing", "analyzed", "probe-deferred", "probe-limited", "probe-failed", "probe-unavailable", "backend-offline");
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
    setProbePresentation(completeness.complete === completeness.total ? "analyzed" : "probe-limited", completeness.complete === completeness.total ? "probeSuccess" : "probePartial");
    return;
  }
  if (!probe.hidden && !miniApiAvailable()) presentMissingApi();
}

function setProbePresentation(status, messageKey) {
  const node = $("#source-state");
  node.classList.remove("probing", "analyzed", "probe-deferred", "probe-limited", "probe-failed", "probe-unavailable", "backend-offline");
  node.classList.add(status);
  const kickerKey = status === "analyzed" ? "probeReadyKicker" : status === "probe-failed" ? "probeFailedKicker" : status === "probe-deferred" ? "probeDeferredKicker" : status === "probe-limited" ? "probeLimitedKicker" : "sourceDetectedKicker";
  $("#source-kicker").textContent = t(kickerKey);
  $("#source-state-message").textContent = t(messageKey);
}

async function probeSourceViaBackend(uri, signal) {
  return apiRequest("/v1/sources/probe", {
    method: "POST",
    body: JSON.stringify({ uri }),
    signal
  });
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
  state.sourceProbe = { status: completeness.complete === completeness.total ? "analyzed" : "partial", result };
  updateSummary();
  return completeness;
}

async function probeSourceInPlace() {
  const button = $("#probe-source");
  const uri = $("#source-uri").value.trim();
  if (!state.sourceDetection?.valid || !/^https?:\/\//i.test(uri)) throw new Error(t("invalidUrl"));
  if (!miniApiAvailable()) { presentMissingApi(); return; }
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
    const result = await probeSourceViaBackend(uri, controller.signal);
    if (requestId !== state.sourceProbeRequestId || uri !== $("#source-uri").value.trim()) return;
    const completeness = applyProbeResult(result, uri);
    setProbePresentation(completeness.complete === completeness.total ? "analyzed" : "probe-limited", completeness.complete === completeness.total ? "probeSuccess" : "probePartial");
  } catch (error) {
    if (requestId !== state.sourceProbeRequestId || uri !== $("#source-uri").value.trim()) return;
    if (error?.name === "AbortError" && !timedOut) return;
    const sourceFailed = error?.sourceRejected && error?.status !== 429;
    const apiOffline = timedOut || error?.connectionFailed || navigator.onLine === false;
    const status = sourceFailed ? "probe-failed" : apiOffline ? "backend-offline" : "probe-deferred";
    const message = sourceFailed ? "probeFailed" : apiOffline ? "apiOfflineMessage" : "probeDeferred";
    state.sourceProbe = { status: sourceFailed ? "failed" : apiOffline ? "offline" : "deferred" };
    setProbePresentation(status, message);
    if (apiOffline) $("#source-kicker").textContent = t("apiOfflineKicker");
    toast(sourceFailed ? t("probeFailed") : apiOffline ? t("apiOfflineMessage") : error.message, true);
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
  const currentUri = $("#source-uri")?.value?.trim() || "";
  const sourceDetection = classifySource(currentUri);
  const sourceReady = Boolean(sourceDetection?.valid);
  const apiReady = miniApiAvailable();
  const sourceVerified = sourceDetection?.kind === "rclone"
    ? sourceReady
    : sourceReady && state.sourceProbeUri === currentUri && ["analyzed", "partial"].includes(state.sourceProbe?.status);
  const runnerReady = Boolean($("#execution")?.value);
  const ready = sourceVerified && Boolean(selectedDevice) && runnerReady && apiReady;
  const completedChecks = [sourceVerified, Boolean(selectedDevice), runnerReady, apiReady].filter(Boolean).length;
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
    const warningKey = ready ? "fallbackWarning" : !apiReady ? "apiRequiredHint" : sourceReady && !sourceVerified ? "sourceProbePendingHint" : sourceReady ? "chooseDeviceHint" : "completeSourceHint";
    $("#launch-warning").textContent = t(warningKey);
  }
  updateChecklistItem("check-source", sourceVerified, "checklistSourceVerified", sourceReady ? "checklistSourceProbePending" : "checklistSourcePending");
  updateChecklistItem("check-device", Boolean(selectedDevice), "checklistDeviceDone", "checklistDevicePending");
  updateChecklistItem("check-runner", runnerReady, "checklistRunnerDone", "checklistRunnerDone");
  updateChecklistItem("check-api", apiReady, "checklistApiDone", miniApiEndpoint ? "checklistApiAuthPending" : "checklistApiPending");
  if ($("#submit-recipe")) $("#submit-recipe").disabled = !ready;
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

function sameStringList(left, right) {
  if (!Array.isArray(left) || !Array.isArray(right) || left.length !== right.length) return false;
  return left.every((value, index) => value === right[index]);
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
    // The shared default list is intentionally visible/editable in the Mini App.
    // Omitting an unchanged list is lossless: every runner resolves a missing
    // debloatPaths field from the same versioned config/debloat.json catalog.
    if (paths.length && !sameStringList(paths, state.catalog.defaultDebloatPaths)) {
      recipe.build.debloatPaths = paths;
    }
  }
  return recipe;
}

const terminalJobStatuses = new Set(["succeeded", "failed", "cancelled"]);

function statusLabel(status) {
  return t({
    queued: "stageQueued", preflight: "stagePreflight", downloading: "stageDownloading",
    running: "stageRunning", uploading: "stageUploading", succeeded: "pipelineComplete",
    failed: "pipelineFailed", cancelled: "cancel"
  }[status] || status);
}

function jobMetadata(job) {
  return job?.recipe?.source?.metadata || {};
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

function renderArtifacts(job) {
  const section = document.createElement("section"); section.className = "job-artifacts";
  const title = document.createElement("h3"); title.textContent = t("artifactsReady"); section.append(title);
  const artifacts = Array.isArray(job.artifacts) ? job.artifacts : [];
  if (!artifacts.length) {
    const empty = document.createElement("p"); empty.textContent = t("noArtifacts"); section.append(empty); return section;
  }
  artifacts.forEach((artifact) => {
    const card = document.createElement("article");
    const header = document.createElement("div");
    const name = document.createElement("strong"); name.textContent = artifact.name || "Artifact";
    const size = document.createElement("span"); size.textContent = formatBytes(artifact.size_bytes ?? artifact.sizeBytes);
    header.append(name, size);
    const sha = document.createElement("code"); sha.textContent = `SHA-256 ${artifact.sha256 || "—"}`;
    const url = String(artifact.public_url || artifact.publicUrl || "");
    if (/^https:\/\//i.test(url)) {
      const link = document.createElement("a"); link.href = url; link.target = "_blank"; link.rel = "noopener noreferrer"; link.textContent = t("artifact");
      card.append(header, sha, link);
    } else {
      const uri = document.createElement("code"); uri.textContent = artifact.uri || "—";
      card.append(header, sha, uri);
    }
    section.append(card);
  });
  return section;
}

function renderEvents(events) {
  const section = document.createElement("section"); section.className = "job-events";
  const title = document.createElement("h3"); title.textContent = t("eventTimeline"); section.append(title);
  const list = document.createElement("ol");
  if (!events.length) {
    const empty = document.createElement("li"); empty.textContent = t("noEvents"); list.append(empty);
  } else {
    events.slice(-30).reverse().forEach((event) => {
      const item = document.createElement("li");
      const marker = document.createElement("b"); marker.textContent = String(event.sequence || "•").padStart(2, "0");
      const content = document.createElement("span");
      const eventTitle = document.createElement("strong"); eventTitle.textContent = event.type || "event";
      const detail = document.createElement("small");
      const visible = event.message || event.error || event.warning || event.stage || event.status || Object.entries(event)
        .filter(([key]) => !["sequence", "jobId", "timestamp", "type", "traceback"].includes(key))
        .map(([key, value]) => `${key}=${typeof value === "object" ? JSON.stringify(value) : value}`)
        .join(" · ");
      detail.textContent = `${formatDate(event.timestamp)}${visible ? ` · ${visible}` : ""}`;
      content.append(eventTitle, detail); item.append(marker, content); list.append(item);
    });
  }
  section.append(list); return section;
}

function jobAction(label, action, job, danger = false) {
  const button = document.createElement("button"); button.type = "button"; button.textContent = label;
  if (danger) button.classList.add("danger");
  button.addEventListener("click", () => runJobAction(action, job.job_id || job.jobId).catch((error) => toast(error.message, true)));
  return button;
}

function githubRunLink(job) {
  const runId = Number(job?.external_run_id ?? job?.externalRunId ?? 0);
  if (!Number.isSafeInteger(runId) || runId <= 0) return null;
  const link = document.createElement("a");
  link.href = `https://github.com/luukhanh24/Wukong-ROM-Studio-Hybrid/actions/runs/${runId}`;
  link.target = "_blank"; link.rel = "noopener noreferrer"; link.textContent = t("openActionsLog");
  return link;
}

function renderActiveJob(job, events) {
  const root = $("#active-job");
  if (!root) return;
  if (!job) { root.hidden = true; root.replaceChildren(); return; }
  root.hidden = false;
  const metadata = jobMetadata(job);
  const header = document.createElement("header");
  const title = document.createElement("div");
  const kicker = document.createElement("small"); kicker.textContent = t("activeJob");
  const heading = document.createElement("h2"); heading.textContent = metadata.version || `${job.recipe?.device || "ROM"} · ${String(job.job_id || job.jobId).slice(0, 12)}`;
  title.append(kicker, heading);
  const badge = document.createElement("span"); badge.className = `job-status ${job.status}`; badge.textContent = statusLabel(job.status);
  header.append(title, badge);
  const progress = document.createElement("div"); progress.className = "job-progress";
  const progressCopy = document.createElement("div");
  const stage = document.createElement("strong"); stage.textContent = job.stage || statusLabel(job.status);
  const percentage = document.createElement("b"); percentage.textContent = `${jobProgress(job)}%`;
  progressCopy.append(stage, percentage);
  const track = document.createElement("div"); const fill = document.createElement("i"); fill.style.width = `${jobProgress(job)}%`; track.append(fill);
  progress.append(progressCopy, track);
  const facts = document.createElement("div"); facts.className = "job-facts";
  facts.append(
    jobFact("Product", metadata.productName || job.recipe?.device),
    jobFact(t("androidVersion"), metadata.androidVersion),
    jobFact(t("securityPatch"), metadata.securityPatch),
    jobFact(t("buildDate"), metadata.buildDate),
    jobFact(t("runner"), job.runner),
    jobFact(t("elapsed"), formatElapsed(job)),
    jobFact(t("modConfiguration"), `${job.recipe?.build?.preset || "—"} / ${job.recipe?.build?.modVersion || "—"}`),
    jobFact(t("sourceSizeDetected"), formatBytes(job.recipe?.source?.sizeBytes))
  );
  const actions = document.createElement("div"); actions.className = "job-controls";
  if (!terminalJobStatuses.has(job.status)) actions.append(jobAction(t("cancel"), "cancel", job, true));
  if (["failed", "cancelled"].includes(job.status) && job.checkpoint) actions.append(jobAction(t("resume"), "resume", job));
  const runLink = githubRunLink(job); if (runLink) actions.append(runLink);
  root.replaceChildren(header, progress, facts, actions, renderEvents(events), renderArtifacts(job));
}

function renderJobHistory() {
  const history = $("#job-history");
  const jobs = state.jobs;
  $("#job-history-count").textContent = String(jobs.length);
  $("#job-empty").hidden = jobs.length > 0;
  history.hidden = jobs.length === 0;
  history.replaceChildren(...jobs.map((job) => {
    const metadata = jobMetadata(job);
    const card = document.createElement("button"); card.type = "button"; card.className = "job-history-card";
    if ((job.job_id || job.jobId) === state.activeJobId) card.classList.add("selected");
    const header = document.createElement("div");
    const title = document.createElement("strong"); title.textContent = metadata.version || job.recipe?.device || "ROM build";
    const status = document.createElement("span"); status.className = `job-status ${job.status}`; status.textContent = statusLabel(job.status);
    header.append(title, status);
    const details = document.createElement("p"); details.textContent = `${job.recipe?.device || "—"} · ${job.runner || "—"} · ${jobProgress(job)}%`;
    const footer = document.createElement("small"); footer.textContent = `${String(job.job_id || job.jobId).slice(0, 12)} · ${formatDate(job.created_at || job.createdAt)}`;
    card.append(header, details, footer);
    card.addEventListener("click", () => {
      state.activeJobId = job.job_id || job.jobId; localStorage.setItem("wukong-active-job", state.activeJobId);
      loadJobDetail(state.activeJobId).catch((error) => toast(error.message, true)); renderJobHistory();
    });
    return card;
  }));
}

function setJobsConnection(key, error = false) {
  const node = $("#jobs-connection"); if (!node) return;
  node.classList.toggle("error", error); node.classList.toggle("online", !error);
  node.querySelector("span").textContent = t(key);
}

async function loadJobDetail(jobId) {
  if (!jobId) return;
  const sameJob = state.activeEventsJobId === jobId;
  const after = sameJob
    ? state.activeEvents.reduce((maximum, event) => Math.max(maximum, Number(event.sequence || 0)), 0)
    : 0;
  const [job, eventsPayload] = await Promise.all([
    apiRequest(`/v1/jobs/${encodeURIComponent(jobId)}`),
    apiRequest(`/v1/jobs/${encodeURIComponent(jobId)}/events?after=${after}`)
  ]);
  const incoming = Array.isArray(eventsPayload.events) ? eventsPayload.events : [];
  const merged = sameJob ? [...state.activeEvents, ...incoming] : incoming;
  const unique = new Map();
  merged.forEach((event) => {
    const sequence = Number(event?.sequence || 0);
    const fallback = `${event?.timestamp || ""}|${event?.type || ""}|${JSON.stringify(event || {})}`;
    unique.set(sequence > 0 ? `sequence:${sequence}` : `event:${fallback}`, event);
  });
  state.activeEvents = [...unique.values()].slice(-100);
  state.activeEventsJobId = jobId;
  const index = state.jobs.findIndex((item) => (item.job_id || item.jobId) === jobId);
  if (index >= 0) state.jobs[index] = job;
  renderActiveJob(job, state.activeEvents); renderJobHistory();
}

function scheduleJobsPoll(active) {
  clearTimeout(state.jobsPollTimer);
  if (document.hidden || !miniApiAvailable()) return;
  state.jobsPollTimer = setTimeout(() => loadJobs().catch(() => {}), active ? 5000 : 30000);
}

async function loadJobs({ force = false } = {}) {
  if (state.jobsLoading && !force) return;
  if (!miniApiAvailable()) { setJobsConnection("apiRequired", true); return; }
  state.jobsLoading = true;
  try {
    const payload = await apiRequest("/v1/jobs");
    state.jobs = Array.isArray(payload.jobs) ? payload.jobs : [];
    const running = state.jobs.find((job) => !terminalJobStatuses.has(job.status));
    const selectedExists = state.jobs.some((job) => (job.job_id || job.jobId) === state.activeJobId);
    if (running) state.activeJobId = running.job_id || running.jobId;
    else if (!selectedExists) state.activeJobId = state.jobs[0]?.job_id || state.jobs[0]?.jobId || "";
    if (state.activeJobId) localStorage.setItem("wukong-active-job", state.activeJobId);
    else localStorage.removeItem("wukong-active-job");
    renderJobHistory();
    if (state.activeJobId) await loadJobDetail(state.activeJobId); else renderActiveJob(null, []);
    setJobsConnection("jobsConnected");
    scheduleJobsPoll(Boolean(running));
  } catch (error) {
    setJobsConnection("jobsOffline", true); scheduleJobsPoll(true); throw error;
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
  if (!miniApiAvailable()) throw new Error(t("apiRequired"));
  const recipe = buildRecipe();
  localStorage.setItem("wukong-recipe-draft", JSON.stringify(recipe));
  const job = await apiRequest("/v1/jobs", { method: "POST", body: JSON.stringify(recipe) });
  state.activeJobId = job.job_id || job.jobId;
  localStorage.setItem("wukong-active-job", state.activeJobId);
  toast(t("buildCreated")); navigate("jobs"); await loadJobs({ force: true });
}

function scheduleSourceProbe() {
  clearTimeout(state.sourceProbeTimer);
  const uri = $("#source-uri").value.trim();
  if (!miniApiAvailable() || !/^https?:\/\//i.test(uri) || !state.sourceDetection?.valid) return;
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

async function runQuickAction(action) {
  if (action === "diagnostics") {
    const payload = await apiRequest("/v1/diagnostics");
    const healthy = Boolean(payload.system || payload.runner || payload.cache);
    $("#telegram-health")?.classList.toggle("ok", healthy);
    toast(healthy ? t("jobsConnected") : t("requestFailed"), !healthy);
    return;
  }
  if (action === "cloud") {
    const payload = await apiRequest("/v1/cloud/library?category=artifacts");
    const root = $("#cloud-results");
    const entries = Array.isArray(payload.entries) ? payload.entries : [];
    root.hidden = false;
    const heading = document.createElement("h2"); heading.textContent = t("artifactsReady");
    const list = document.createElement("div");
    entries.slice(0, 50).forEach((entry) => {
      const item = document.createElement("article");
      const name = document.createElement("strong"); name.textContent = entry.name || entry.path || "Artifact";
      const details = document.createElement("small"); details.textContent = `${formatBytes(entry.sizeBytes)} · ${formatDate(entry.modifiedAt)}`;
      item.append(name, details); list.append(item);
    });
    if (!entries.length) { const empty = document.createElement("p"); empty.textContent = t("noArtifacts"); list.append(empty); }
    root.replaceChildren(heading, list);
    toast(`${entries.length} artifact`);
    return;
  }
  if (action === "cache") {
    const payload = await apiRequest("/v1/cache");
    toast(`${payload.entryCount ?? 0} cache · ${formatBytes(payload.totalBytes)}`);
    return;
  }
  if (action === "cache_clear") {
    const payload = await apiRequest("/v1/cache/clear", { method: "POST" });
    toast(`${payload.entryCount ?? 0} cache`);
    return;
  }
  throw new Error(t("requestFailed"));
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
  $("#probe-source").addEventListener("click", () => {
    clearTimeout(state.sourceProbeTimer);
    const probeButton = $("#probe-source");
    if (probeButton.dataset.closeApp) { closeTelegramApp(); return; }
    if (probeButton.dataset.openBot) { openTelegramBot(); return; }
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
  $("#refresh-jobs").addEventListener("click", () => loadJobs({ force: true }).catch((error) => toast(error.message, true)));
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) clearTimeout(state.jobsPollTimer);
    else loadJobs({ force: true }).catch(() => {});
  });
  $("#copy-source-metadata").addEventListener("click", () => copySourceMetadata().catch((error) => toast(error.message, true)));
  $$('input[name="task"]').forEach((input) => input.addEventListener("change", updateSummary));
}

function renderSessionDiagnostics() {
  const node = $("#session-diag");
  if (!node) return;
  if (!TelegramApp && !parseInitDataFromHash()) { node.textContent = t("sessionDiagNoLib"); return; }
  const rawDirect = String(TelegramApp?.initData || "");
  const fallback = !rawDirect ? parseInitDataFromHash() : "";
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

function startMiniApp() {
  bindEvents();
  restoreSourceDraft();
  window.WukongMiniApp = Object.freeze({ setDeliveryState });
  applyLanguage();
  navigate(location.hash.slice(1) || "build", false);
  loadCatalog();
  renderSessionDiagnostics();
  if (miniApiAvailable()) loadJobs().catch(() => {});
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
    restoreSourceDraft();
    updateTelegramState();
    updateSourceDetection();
    scheduleSourceProbe();
    renderSessionDiagnostics();
    loadJobs({ force: true }).catch(() => {});
  });
  bridge.addEventListener("error", renderSessionDiagnostics);
  document.head.append(bridge);
}
