# Phương án upload native Cloudreve khi không có quyền DNS

Ngày khảo sát: 2026-08-31  
Phạm vi: Cloudreve `4.18.0`; chỉ đối chiếu tài liệu, source, release và security advisory chính thức của Cloudreve. Không dùng cookie phiên Brave, không trích token hiện có và không thay đổi tài khoản.

## Kết luận

**Có một phương án khả thi không cần quyền DNS/Cloudflare: thay WebDAV bằng REST uploader native của Cloudreve.** Native uploader tạo một upload session rồi gửi file theo chunk; với storage policy local/relay, mỗi request chỉ mang một chunk nên tránh giới hạn request-body của Cloudflare áp lên một lệnh WebDAV `PUT` 7.89 GiB. Cloudreve cũng tự trả `chunk_size`, số luồng, URL upload, credential tạm và thời hạn; client không được hard-code các giá trị này. [Tài liệu upload v4](https://github.com/cloudreve/docs/blob/v4/en/api/upload.md), [source `CreateUploadSession` 4.18.0](https://github.com/cloudreve/cloudreve/blob/0bb0ab833571d380153edd3529e01a7957b8b4ce/service/explorer/upload.go)

Tuy nhiên, **WebDAV device account không phải credential REST**. Source chỉ dùng device account qua HTTP Basic trong middleware WebDAV; các route `/api/v4/file/*` yêu cầu JWT bearer token và scope `Files.Read`/`Files.Write`. Vì user thường không thể tự đăng ký OAuth application, đường khả thi là bootstrap một lần bằng password login (và CAPTCHA/OTP nếu instance yêu cầu), rồi lưu **refresh token** trong GitHub Secret. Đây là thay đổi so với giả định cũ “không API login/CAPTCHA” và phải được chấp nhận như một rủi ro bảo mật riêng. [Tài liệu auth v4](https://github.com/cloudreve/docs/blob/v4/en/api/auth.md), [router 4.18.0](https://github.com/cloudreve/cloudreve/blob/0bb0ab833571d380153edd3529e01a7957b8b4ce/routers/router.go), [middleware WebDAV 4.18.0](https://github.com/cloudreve/cloudreve/blob/0bb0ab833571d380153edd3529e01a7957b8b4ce/middleware/auth.go)

Khuyến nghị: triển khai một adapter REST native độc lập, giữ Drive là primary và DC Cloud là best-effort. Không dùng password của tài khoản trong GitHub Actions; chỉ nhập password ở bước bootstrap cục bộ, sau đó Actions dùng refresh token.

## Authentication phù hợp cho GitHub Actions

### Các lựa chọn được Cloudreve hỗ trợ

| Cách | User thường tự làm được? | Phù hợp CI? | Nhận xét |
|---|---:|---:|---|
| OAuth 2.0 authorization code + PKCE + `offline_access` | Không, vì admin phải đăng ký OAuth app | Tốt nhất | Có thể giới hạn scope còn `Files.Write` (bao hàm read theo source) và refresh token. Đây là cách tài liệu chính thức khuyến nghị. |
| Password login một lần, lưu refresh token | Có, nếu tài khoản có password | Có điều kiện | Token login built-in không mang OAuth client/scope nên trên 4.18 nó có quyền của toàn phiên user, rộng hơn nhu cầu mirror. Không lưu password trong GitHub. |
| Password login ở mỗi workflow | Có | Không khuyến nghị | CAPTCHA có thể bật theo cấu hình site; 2FA tạo session 600 giây và cần OTP. Không ổn định/headless. |
| WebDAV device account | Có trên instance hiện tại | Không dùng được cho REST | Chỉ xác thực WebDAV; không đổi thành JWT/API token. |
| Tự ký JWT bằng site master key | Không | Cấm dùng production | Tài liệu ghi rõ chỉ dành cho local debugging và không được tiết lộ master key. |

OAuth cần admin tạo client, redirect URI và scope. Refresh token chỉ được cấp khi request có `offline_access`; endpoint refresh là `POST /api/v4/session/token/refresh`. Nếu OAuth không khả dụng, built-in password login vẫn trả access/refresh token pair; source 4.18 phát token built-in không gắn `ClientID` hay scope, nên middleware scope bỏ qua kiểm tra chi tiết. [Auth v4](https://github.com/cloudreve/docs/blob/v4/en/api/auth.md), [JWT implementation 4.18.0](https://github.com/cloudreve/cloudreve/blob/0bb0ab833571d380153edd3529e01a7957b8b4ce/pkg/auth/jwt.go), [login implementation 4.18.0](https://github.com/cloudreve/cloudreve/blob/0bb0ab833571d380153edd3529e01a7957b8b4ce/service/user/login.go)

Kiểm tra instance hiện tại cho thấy password login đang khả dụng, CAPTCHA login không được yêu cầu cho user này và 2FA đang tắt. Đây là trạng thái vận hành hiện tại, không phải cam kết lâu dài: admin có thể bật CAPTCHA, còn user có thể bật 2FA sau này. Source route xác nhận CAPTCHA được áp có điều kiện, password login có 2FA thì trả session trung gian 600 giây và phải gọi `/api/v4/session/token/2fa` với OTP trước khi nhận token pair. [Router auth 4.18.0](https://github.com/cloudreve/cloudreve/blob/0bb0ab833571d380153edd3529e01a7957b8b4ce/routers/router.go), [2FA implementation 4.18.0](https://github.com/cloudreve/cloudreve/blob/0bb0ab833571d380153edd3529e01a7957b8b4ce/service/user/login.go)

### Mô hình credential đề xuất

1. Chạy tool bootstrap **trên máy user**, hỏi password qua stdin; giải CAPTCHA/OTP tương tác nếu server yêu cầu.
2. Chỉ ghi refresh token vào GitHub Secret, ví dụ `WUKONG_DCCLOUD_REFRESH_TOKEN`; không ghi password, access token, cookie hay response JSON vào log.
3. Mỗi job gọi refresh endpoint để lấy access token ngắn hạn; mask cả token cũ và token mới trước mọi log.
4. Refresh response trả một token pair mới. Workflow nên dùng access token mới trong run hiện tại; việc tự cập nhật GitHub Secret cần credential GitHub có quyền ghi secret và làm tăng rủi ro, nên phiên bản đầu có thể giữ refresh token bootstrap cho tới gần hạn rồi rotate thủ công. Source 4.18 không revoke token cũ chỉ vì đã refresh, nhưng điều này là chi tiết implementation, không nên coi là cam kết API vĩnh viễn. [Auth refresh](https://github.com/cloudreve/docs/blob/v4/en/api/auth.md), [JWT refresh source](https://github.com/cloudreve/cloudreve/blob/0bb0ab833571d380153edd3529e01a7957b8b4ce/pkg/auth/jwt.go)

## Luồng upload chunked

1. Gọi `PUT /api/v4/file/upload` với URI staging, `size`, `last_modified`, MIME type và policy nếu cần.
2. Tôn trọng response `session_id`, `chunk_size`, `expires`, `storage_policy.chunk_concurrency`, `upload_urls`, `credential`, `complete_url` và callback secret.
3. Chia file đúng `chunk_size`; chunk cuối có kích thước phần dư. Với local/relay, gửi `POST /api/v4/file/upload/{sessionId}/{index}` và `Content-Length` chính xác. Với remote/S3/OneDrive/provider khác, upload theo URL/credential và completion flow mà session trả về.
4. Local/remote/upyun hoàn tất tự động; các provider khác có bước complete/callback khác nhau. Không được giả định DC Cloud đang dùng local policy nếu chưa đọc session live.
5. Sau completion, list/get file theo URI để xác minh tên và kích thước; checksum end-to-end vẫn cần tải lại hoặc một checksum do storage/provider đáng tin trả về.

Cloudreve 4.18.0 sửa lỗi local upload khi bật parallel chunks. Source 4.18 kiểm tra chính xác `Content-Length`, ghi chunk theo offset, theo dõi các index đã nhận và chỉ complete khi đủ mọi chunk. [Release 4.18.0](https://github.com/cloudreve/cloudreve/releases/tag/4.18.0), [upload controller 4.18.0](https://github.com/cloudreve/cloudreve/blob/0bb0ab833571d380153edd3529e01a7957b8b4ce/service/explorer/upload.go), [upload manager 4.18.0](https://github.com/cloudreve/cloudreve/blob/0bb0ab833571d380153edd3529e01a7957b8b4ce/pkg/filemanager/manager/upload.go)

## Resume và idempotency

- Trong cùng session, retry cùng một chunk index là có thể: local upload dùng overwrite ở đúng offset; tracker 4.18 lưu index trong map nên việc ghi nhận trùng là no-op và không complete lần hai.
- Resume chỉ hợp lệ trước `expires`. Session nằm trong KV/cache server và bị xóa khi complete/cancel; khi session hết hạn, API trả lỗi session expired.
- Reference web client lưu toàn bộ session và `chunkProgress` ở `localStorage`, khóa theo tên + thư mục đích + size + policy, rồi bỏ cache khi session hết hạn hoặc upload xong. Điều này chứng minh resume là trách nhiệm của client, không có route công khai để hỏi server “chunk nào đã xong”. [Frontend đúng submodule của 4.18.0: base uploader](https://github.com/cloudreve/frontend/blob/083484109f15e361bc92330ec0318fe758d43d72/src/component/Uploader/core/uploader/base.ts), [resume helper](https://github.com/cloudreve/frontend/blob/083484109f15e361bc92330ec0318fe758d43d72/src/component/Uploader/core/utils/helper.ts)
- Không nên lưu session response thô vào GitHub artifact/log vì nó có pre-signed URL, callback secret hoặc credential tạm. Trong một workflow run, giữ checkpoint trong file tạm có permission hẹp và xóa cuối job. Giữa các workflow run, phương án an toàn nhất của v1 là tạo session mới, không cố phục hồi session cũ.
- Idempotency cấp artifact phải dựa trên URI đích xác định + sidecar metadata chứa SHA-256. Trước upload, nếu file cuối và sidecar đã tồn tại, size và SHA khớp thì trả `available`; nếu không khớp thì upload vào staging mới, không ghi đè file public ngay.

## Final move và metadata

Luồng đề xuất giữ nguyên mô hình staging nhưng thực hiện bằng file API:

1. Upload ZIP vào `cloudreve://my/WukongROM/_staging/{job_id}/{artifact}`.
2. Upload sidecar JSON nhỏ chứa SHA-256, size, job id và schema version vào cùng staging.
3. List staging và xác minh ZIP + sidecar đều hoàn tất; nếu cần kiểm chứng byte thật, tải lại ZIP và hash trước khi publish.
4. Gọi `POST /api/v4/file/move` để chuyển các URI staging sang folder `WukongROM/ROM/{release}/{edition}`.
5. Chỉ sau khi ZIP đã ở đích mới move/upload sidecar cuối cùng như commit marker.

Routes `move`, `rename`, `PATCH metadata`, list và upload đều yêu cầu `Files.Write`/`Files.Read`. Create-upload-session chấp nhận `metadata`, nhưng source chỉ cho phép các namespace metadata đã biết; một checksum tùy ý không phải contract API ổn định. Sidecar JSON vì thế bền hơn việc phụ thuộc vào metadata key nội bộ. [Router file API 4.18.0](https://github.com/cloudreve/cloudreve/blob/0bb0ab833571d380153edd3529e01a7957b8b4ce/routers/router.go), [metadata validation 4.18.0](https://github.com/cloudreve/cloudreve/blob/0bb0ab833571d380153edd3529e01a7957b8b4ce/pkg/filemanager/manager/metadata.go)

Move trong Cloudreve là thao tác filesystem/index của ứng dụng, không phải WebDAV `MOVE` xuyên Cloudflare; tuy nhiên tính atomic của việc move nhiều mục không được tài liệu API cam kết. Vì vậy sidecar cuối cùng phải là dấu hiệu `available`, và repair phải chấp nhận trạng thái ZIP đã move nhưng sidecar chưa move.

## Rủi ro và quyết định

- Refresh token built-in là credential dài hạn, có quyền rộng trên tài khoản. Nếu secret repo bị lộ, kẻ tấn công có thể đọc/ghi/xóa file trong phạm vi account, không chỉ `WukongROM`.
- Đổi email/password hoặc sign-out/revoke có thể làm refresh token hết hiệu lực; TTL do operator cấu hình. Cần preflight refresh và cảnh báo trước hạn.
- Session/URL/credential phụ thuộc storage policy; adapter phải dispatch theo `policy_type`, không chỉ implement local.
- Upload native giảm body size mỗi request nhưng vẫn đi qua Cloudflare và origin; cần retry từng chunk với exponential backoff, timeout hữu hạn và giới hạn concurrency theo server.
- 4.18.0 release ghi có sửa nhiều security vulnerabilities và một lỗi parallel local upload. Instance cần giữ ít nhất 4.18.0 và tiếp tục cập nhật bản vá; advisory scoped-root WebDAV trước 4.16.1 vẫn là lý do không hạ phiên bản. [Release 4.18.0](https://github.com/cloudreve/cloudreve/releases/tag/4.18.0), [GHSA-w5fv-7x5q-g8qp](https://github.com/cloudreve/cloudreve/security/advisories/GHSA-w5fv-7x5q-g8qp)

**Quyết định đề xuất: Go cho PoC REST native bằng refresh token bootstrap một lần; chưa bật production cho tới khi upload 10 MB, 100 MB, 1 GB và ROM 7.89 GiB đều tải lại đúng SHA-256.** Nếu user không chấp nhận lưu refresh token có quyền rộng trong GitHub Secret thì không còn đường tự động ổn định nào chỉ với quyền user: WebDAV lớn vẫn bị proxy, OAuth cần admin, còn browser/manual upload không đáp ứng mirror CI.

## Gate triển khai

1. User chấp nhận thay đổi policy: cho phép API login **chỉ ở bootstrap cục bộ** và lưu refresh token vào GitHub Secret.
2. Tool bootstrap không in token/password; hỗ trợ CAPTCHA/OTP nhưng instance hiện tại không yêu cầu hai bước này.
3. Adapter implement token refresh, upload state machine theo policy, retry chunk và cleanup session.
4. Không persist pre-signed URL/callback secret; không đưa REST URI/token/stderr vào API công khai, Telegram hay GitHub Summary.
5. PoC checksum đủ bốn cỡ file; kiểm anonymous share chỉ đọc như kế hoạch cũ.
6. Chỉ sau ba build liên tiếp thành công mới đặt mirror flag `true`; lỗi mirror vẫn không làm Drive/build thất bại.
