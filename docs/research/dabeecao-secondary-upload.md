# Khảo sát DC Cloud làm nơi upload thứ hai

Ngày khảo sát: 2026-08-30  
Phạm vi: đọc endpoint công khai, nguồn chính thức và trạng thái hiển thị read-only của phiên Brave đã đăng nhập qua extension; không upload, không tạo credential và không thay đổi tài khoản.

## Kết luận

**Có thể tích hợp về mặt kỹ thuật, nhưng hiện chỉ nên xem là một mirror phụ “best effort”, chưa phải bản backup hoặc kênh phát hành thứ hai đáng tin cậy.**

`cloud.dabeecao.org` là một instance Cloudreve v4. Cloudreve có REST API cho upload theo phiên/chunk, tạo URL tải và tạo share; instance cũng có endpoint quản lý tài khoản WebDAV. Phiên Brave đã đăng nhập hiển thị `1.2 TB / 4.0 TB`, tức còn khoảng `2.8 TB` theo số làm tròn trên giao diện, và cho phép mở luồng tạo WebDAV account. Tuy nhiên kích thước file tối đa, storage policy, quyền share/direct-link, thời hạn link, giới hạn băng thông và chính sách lưu giữ không được công khai hoặc chưa được xác nhận. [Cấu hình public của instance](https://cloud.dabeecao.org/api/v4/site/config/basic), [API upload Cloudreve](https://docs.cloudreve.org/en/api/upload), [router chính thức Cloudreve](https://github.com/cloudreve/cloudreve/blob/master/routers/router.go)

Khuyến nghị cho Wukong ROM Studio:

1. Giữ Google Drive là nơi phát hành chính.
2. Nếu tài khoản có WebDAV, dùng một **WebDAV device account riêng** làm credential cho `rclone`; đây là đường upload ít thay đổi nhất với kiến trúc hiện tại, nhưng vẫn phải tách bước tạo public link khỏi `rclone link`.
3. Chỉ bật mirror sau khi kiểm tra quota và thử upload/download một artifact nhỏ, xác minh SHA-256, link chia sẻ và hành vi hết hạn.
4. Mirror phải **không làm job build thất bại** khi DC Cloud lỗi; ghi trạng thái mirror riêng và luôn giữ URL Google Drive làm URL chính.

## Điều đã xác nhận trên chính instance

| Hạng mục | Kết quả | Nguồn chính thức |
|---|---|---|
| Danh tính | Trang tự nhận là `DC Cloud`; public config trả về title này và anonymous group. | [Trang chủ](https://cloud.dabeecao.org/), [basic config](https://cloud.dabeecao.org/api/v4/site/config/basic) |
| Họ phần mềm | Frontend đang dùng API base `/api/v4`, trùng API Cloudreve v4; source/router Cloudreve định nghĩa các route upload, file URL, share và WebDAV tương ứng. | [Bundle đang triển khai](https://cloud.dabeecao.org/assets/index-BDKOyYQX.js), [Cloudreve API overview](https://docs.cloudreve.org/en/api/overview), [router Cloudreve](https://github.com/cloudreve/cloudreve/blob/master/routers/router.go) |
| Điều khoản và privacy | Instance công bố chính xác URL ToS và Privacy trong public login config. | [login config](https://cloud.dabeecao.org/api/v4/site/config/login), [ToS](https://dabeecao.org/terms-of-service.html), [Privacy](https://dabeecao.org/privacy-policy.html) |
| Batch UI | `max_batch_size` hiện là `3000`; đây là giới hạn số mục của thao tác batch trong explorer, **không phải** quota hay max file size. | [explorer config](https://cloud.dabeecao.org/api/v4/site/config/explorer) |
| Dung lượng tài khoản | UI của phiên Brave đã đăng nhập hiển thị `1.2 TB / 4.0 TB` (xấp xỉ `2.8 TB` còn trống theo số làm tròn). Khi gọi công khai, `GET /api/v4/user/capacity` trả JSON `code: 401` / `Login required`. Cloudreve thường trả HTTP 200 và đặt lỗi trong trường `code`, nên không được chỉ dựa vào HTTP status. | Quan sát read-only ngày 2026-08-30; [capacity endpoint](https://cloud.dabeecao.org/api/v4/user/capacity), [quy ước response](https://docs.cloudreve.org/en/api/overview) |
| Share | Không thể xác định quyền của tài khoản công khai. `GET /api/v4/share` yêu cầu đăng nhập. | [share endpoint](https://cloud.dabeecao.org/api/v4/share), [router Cloudreve](https://github.com/cloudreve/cloudreve/blob/master/routers/router.go) |
| WebDAV | Tài khoản đã đăng nhập mở được `Connect & Mount` và hộp `Create WebDAV account`, nên quyền tạo WebDAV account hiện có trên UI. Có thể giới hạn relative root folder và bật read-only/block dotfiles/reverse proxy. Bảng hiện `No records`, và khảo sát không tạo account mới. | Quan sát read-only ngày 2026-08-30; [DAV endpoint](https://cloud.dabeecao.org/api/v4/devices/dav), [router Cloudreve](https://github.com/cloudreve/cloudreve/blob/master/routers/router.go) |
| Status/SLA | Không tìm thấy status page riêng hoặc SLA công khai từ site/config/ToS. Việc không tìm thấy không chứng minh dịch vụ không có giám sát nội bộ. | [Trang chủ](https://cloud.dabeecao.org/), [ToS](https://dabeecao.org/terms-of-service.html) |

## Các cách tích hợp khả dụng

### 1. REST API Cloudreve — đầy đủ nhất

Cloudreve mô tả upload gồm ba pha: tạo upload session, upload các chunk theo storage policy, rồi complete nếu provider yêu cầu. Session trả về `session_id`, `chunk_size`, upload URL/credential, thời hạn, concurrency và thông tin mã hóa. Vì các giá trị này phụ thuộc policy, client không nên hard-code kích thước chunk hay giả định backend là S3/local. [Tài liệu upload](https://docs.cloudreve.org/en/api/upload)

Các route liên quan trong source chính thức gồm:

- `PUT /api/v4/file/upload` — tạo upload session.
- `POST /api/v4/file/upload/:sessionId/:index` — gửi dữ liệu chunk khi upload đi qua Cloudreve.
- `DELETE /api/v4/file/upload` — hủy upload session.
- `POST /api/v4/file/url` — lấy URL preview/download của file.
- `PUT /api/v4/share` — tạo share; `GET /api/v4/share/info/:id` — đọc thông tin share.

Nguồn: [router Cloudreve](https://github.com/cloudreve/cloudreve/blob/master/routers/router.go), [API overview](https://docs.cloudreve.org/en/api/overview).

Ưu điểm là có thể lấy progress, chunking và link sau upload. Nhược điểm là cần triển khai đúng state machine theo từng storage policy, xử lý token refresh, retry/idempotency, session expiry và completion callback. Đây không phải một endpoint `multipart/form-data` đơn giản. [Tài liệu upload](https://docs.cloudreve.org/en/api/upload)

### 2. WebDAV qua rclone — phù hợp nhất với repo hiện tại nếu được cấp quyền

Cloudreve hỗ trợ WebDAV trên mọi storage policy. Tài liệu chính thức lưu ý WebDAV upload phải relay qua Cloudreve, là single-stream, không chunking và hỗ trợ file lớn kém hơn desktop client. Điều này cần được kiểm thử với artifact ROM thực tế trước khi chọn làm đường upload production. [So sánh desktop/WebDAV](https://docs.cloudreve.org/en/usage/desktop-client)

Repo hiện đã đóng gói upload artifact qua `RcloneStorageAdapter`: adapter dùng `rclone copyto`, tạo metadata SHA-256, rồi gọi `rclone link`. Vì vậy một rclone remote kiểu WebDAV có thể tái sử dụng phần copy/progress, nhưng **không thể coi adapter hiện tại là dùng được nguyên trạng**: khả năng của `rclone link` phụ thuộc backend, còn WebDAV thường chỉ cung cấp giao thức file chứ không chuẩn hóa thao tác tạo public share. Cần cho phép upload thành công dù backend không hỗ trợ `link`, sau đó gọi Cloudreve share/file-URL API riêng nếu cần URL công khai. [Tài liệu rclone WebDAV](https://rclone.org/webdav/), [tài liệu rclone link](https://rclone.org/commands/rclone_link/). Xem thêm [wukong/adapters.py](../../wukong/adapters.py) và [wukong/executor.py](../../wukong/executor.py).

Không nên dùng mật khẩu đăng nhập chính cho CI. Nếu UI của tài khoản cho phép, tạo một WebDAV device account riêng, giới hạn quyền/thư mục nếu có, lưu credential trong secret store và có quy trình revoke/rotate.

### 3. OAuth/API token — phù hợp hơn khi cần tính năng share/direct link

Cloudreve dùng `Authorization: Bearer <AccessToken>` và hỗ trợ refresh token. OAuth 2.0 authorization-code flow là phương án được tài liệu khuyến nghị cho ứng dụng truy cập thay người dùng; cần admin đăng ký OAuth app và chọn scope. [Tài liệu authentication](https://docs.cloudreve.org/en/api/auth)

Không nên sao chép access/refresh token từ localStorage của phiên Brave vào repo hoặc GitHub Actions: refresh token là credential dài hạn và tài liệu yêu cầu lưu token an toàn. Nếu operator không cấp OAuth app, WebDAV device account riêng là lựa chọn dễ thu hồi hơn; nếu cả hai đều không có thì phải cân nhắc một tài khoản tích hợp riêng thay vì tái sử dụng phiên trình duyệt. [Tài liệu authentication](https://docs.cloudreve.org/en/api/auth)

## Share và direct download

Cloudreve hỗ trợ hai khái niệm khác nhau:

- API file URL sinh URL preview/download từ file (`POST /api/v4/file/url`).
- API share tạo một đối tượng share (`PUT /api/v4/share`), có thể dùng làm link công khai tùy quyền và cấu hình.

Nguồn route: [router Cloudreve](https://github.com/cloudreve/cloudreve/blob/master/routers/router.go).

Độ bền của direct URL phụ thuộc storage policy và chế độ public/private/redirect. Tài liệu Cloudreve cho thấy khả năng direct link dài hạn khác nhau giữa local, remote node, OneDrive và các provider S3/OSS/COS/OBS; do đó không được giả định URL trả về sẽ vĩnh viễn. [So sánh storage policy](https://docs.cloudreve.org/en/usage/storage/)

Trước khi nối vào nút tải artifact của Wukong cần xác nhận bằng tài khoản:

- account có permission tạo share/direct link;
- link có yêu cầu đăng nhập hay không;
- có thời hạn, password, download count hoặc traffic limit không;
- URL là ổn định hay signed/temporary;
- hỗ trợ HTTP `HEAD`, redirect và `Range` theo nhu cầu download;
- xóa/đổi tên file có làm link hỏng hay không.

## Giới hạn và retention chưa thể xác nhận

Các thông tin sau **không xuất hiện** trong public config, ToS hoặc Privacy và cần kiểm tra bằng phiên đăng nhập/read-only hoặc hỏi operator:

- giới hạn kích thước mỗi file, loại file, chunk size/concurrency và upload-session TTL;
- giới hạn băng thông, số request, tốc độ upload/download;
- quyền WebDAV, remote download, share và direct link của user group;
- retention của file, recycle bin, tài khoản không hoạt động và thời gian báo trước khi xóa;
- backup/restore của operator, RPO/RTO, SLA/uptime và data export khi dịch vụ dừng;
- thời hạn và tính ổn định của public/share/direct link.

Endpoint cần kiểm tra sau khi người dùng cho phép thao tác đăng nhập read-only: [capacity](https://cloud.dabeecao.org/api/v4/user/capacity), [share](https://cloud.dabeecao.org/api/v4/share), [WebDAV accounts](https://cloud.dabeecao.org/api/v4/devices/dav).

## Rủi ro điều khoản, bảo mật và vận hành

- ToS cấm nội dung bất hợp pháp/gây hại, can thiệp dịch vụ và phát tán malware; operator có quyền tạm ngừng hoặc chấm dứt truy cập khi vi phạm hoặc gây hại hệ thống. Artifact ROM/mod cần được rà soát quyền phân phối và tuyệt đối không chứa malware. [ToS](https://dabeecao.org/terms-of-service.html)
- ToS yêu cầu chủ tài khoản tự bảo vệ tài khoản/mật khẩu. Credential tích hợp phải nằm trong secret store, không nằm trong recipe, manifest, log hoặc rclone config được commit. [ToS](https://dabeecao.org/terms-of-service.html)
- Privacy nói dịch vụ có thể thu thập thông tin định danh/liên hệ, lịch sử/hành vi sử dụng, IP, trình duyệt và thiết bị; dữ liệu có thể được chia sẻ khi có đồng ý, nghĩa vụ pháp lý hoặc với nhà cung cấp dịch vụ đáng tin cậy. Không nên upload secret, signing key hay dữ liệu người dùng vào mirror. [Privacy](https://dabeecao.org/privacy-policy.html)
- ToS/Privacy không cam kết SLA, backup, retention, notice period hay khả năng phục hồi. Vì thế DC Cloud không nên là bản sao duy nhất hoặc nguồn duy nhất cấp URL tải. [ToS](https://dabeecao.org/terms-of-service.html), [Privacy](https://dabeecao.org/privacy-policy.html)
- Cloudreve có thể mã hóa file nếu operator bật policy encryption, nhưng trạng thái này không được xác nhận công khai cho tài khoản/storage policy của instance. Không được coi dữ liệu đã mã hóa chỉ vì frontend có hiển thị trạng thái encryption. [File encryption](https://docs.cloudreve.org/en/usage/file-encryption), [explorer config](https://cloud.dabeecao.org/api/v4/site/config/explorer)

## Gate đề xuất trước khi triển khai

Chỉ triển khai sau khi hoàn tất các gate sau:

1. Ghi lại quota/free space, max file size và quyền của account từ UI hoặc API đã đăng nhập.
2. Tạo credential tích hợp riêng (ưu tiên WebDAV device account; OAuth app nếu cần share API), xác nhận revoke/rotate.
3. Upload file thử không nhạy cảm, tải lại, kiểm SHA-256 và đo thời gian/tốc độ.
4. Tạo share/direct link thử và kiểm tra bằng cửa sổ không đăng nhập, `HEAD`, redirect, `Range` và thời hạn.
5. Xác nhận quy tắc retention/backup/SLA với operator bằng văn bản nếu mirror được dùng cho production.
6. Thiết kế mirror ở chế độ best effort: Google Drive thành công vẫn hoàn thành job; lỗi DC Cloud tạo warning/retry riêng.
7. Lưu cả URI nội bộ và URL public theo provider; không thay URL Google Drive cho tới khi link DC Cloud vượt qua kiểm thử độ bền.
8. Có cleanup policy và đối chiếu định kỳ bằng SHA-256 để tránh quota đầy hoặc mirror âm thầm thiếu file.

## Quyết định đề xuất

**Go cho một PoC nhỏ, No-Go cho production/durable backup ở thời điểm khảo sát.**

PoC nên bắt đầu bằng rclone + WebDAV nếu account có quyền, vì đây là đường **truyền file** gần nhất với `RcloneStorageAdapter` hiện tại; adapter vẫn cần bỏ giả định mọi remote đều hỗ trợ `rclone link`. Chọn REST API khi cần chunking/progress tốt hơn hoặc cần tự động tạo share/direct link; khi đó phải triển khai token lifecycle và state machine upload chính thức của Cloudreve. Dù chọn đường nào, DC Cloud vẫn là secondary best-effort cho tới khi quota, retention, SLA và độ bền của link được xác nhận.
