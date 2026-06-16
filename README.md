# Starter Code Template — Cohort 2 (AI20K Build)

Đây là template khởi tạo trống (Starter Code) dành cho các kho lưu trữ (repository) của các nhóm thuộc **Cohort 2 - AI20K Build**. Dự án đã được cấu hình sẵn các hook để tự động ghi lại lịch sử sử dụng AI (AI usage logging hooks) cho các công cụ phổ biến như: Claude Code, Cursor, Codex, Gemini CLI, Antigravity (IDE), và GitHub Copilot.

## Cấu trúc thư mục

```
├── scripts/
│   ├── _pyrun.sh             # Trình chạy Python đa nền tảng (bash)
│   ├── _pyrun.cmd            # Trình chạy Python đa nền tảng (Windows cmd)
│   ├── setup_hooks.sh        # Script cài đặt git hook một lần (POSIX / macOS)
│   ├── setup_hooks.ps1       # Script cài đặt git hook một lần (Windows PowerShell)
│   ├── log_hook.py           # Bộ xử lý ghi log cho các công cụ AI (Claude / Cursor / Codex / Gemini / Copilot)
│   ├── log_antigravity.py    # Bộ tự động quét log từ Antigravity
│   ├── log_manual.py         # Bộ ghi log thủ công cho ChatGPT hoặc các công cụ nền web
│   └── submit_log.py         # Tự động gửi log lên hệ thống grading khi thực hiện git push
├── .agents/                  # Các quy tắc (rules) và luồng công việc (workflows) của Antigravity
├── .claude/ .codex/ .cursor/ .gemini/ .github/hooks/   # Các file cấu hình hook cho từng công cụ AI
├── .env.example              # File cấu hình mẫu môi trường
├── JOURNAL.md                # Nhật ký hàng tuần — chặng đường sản phẩm và bài học kinh nghiệm
├── WORKLOG.md                # Nhật ký công việc, quyết định kỹ thuật, phân chia nhiệm vụ
└── README.md                 # Tài liệu hướng dẫn dự án (file này)
```

## Bắt đầu cài đặt (Getting Started)

### 1. Clone dự án và cài đặt pre-push hook

**Dành cho Linux / macOS / Git Bash:**
```bash
git clone <repo-url>
cd <repo>
bash scripts/setup_hooks.sh
```

**Dành cho Windows PowerShell:**
```powershell
git clone <repo-url>
cd <repo>
powershell -ExecutionPolicy Bypass -File scripts\setup_hooks.ps1
```

### 2. Cấu hình môi trường (.env)

Tạo file `.env` từ file mẫu:
```bash
cp .env.example .env       # macOS / Linux / Git Bash
# copy .env.example .env   # Windows cmd
```

Sau đó, mở file `.env` và điền đầy đủ thông tin `AI_LOG_SERVER` và `AI_LOG_API_KEY` (được cung cấp bởi giảng viên khóa học).

### 3. Phát triển dự án của bạn

Đây là một template trống để bắt đầu dự án — bạn có thể chọn bất kỳ ngôn ngữ hay framework nào bạn muốn. Hệ thống ghi log (hooks) không phụ thuộc vào ngôn ngữ lập trình của dự án; hệ thống chỉ yêu cầu có sẵn **Python 3** trên máy của bạn (chấp nhận bất kỳ lệnh nào như `python3`, `python`, hoặc `py`).

---

## Nhật ký hàng tuần (Weekly Journal)

Cập nhật **[JOURNAL.md](./JOURNAL.md)** vào cuối mỗi tuần học:

- Các tính năng đã phát triển thành công.
- Các công cụ AI đã sử dụng và cách chúng hỗ trợ bạn.
- Vấn đề khó khăn nhất trong tuần và cách bạn giải quyết nó.
- Những điểm bạn muốn làm khác đi nếu được làm lại.
- Kế hoạch phát triển cho tuần tiếp theo.

> **QUAN TRỌNG:** File `JOURNAL.md` phải được cập nhật trước mỗi lần tạo Pull Request (PR) — đây là minh chứng học tập và tiêu chí đánh giá cho khóa học của bạn.

---

## Nhật ký công việc (Worklog)

Cập nhật **[WORKLOG.md](./WORKLOG.md)** bất cứ khi nào nhóm của bạn đưa ra quyết định kỹ thuật hoặc thay đổi hướng đi:

- **Quyết định kỹ thuật**: Tại sao lại chọn cách tiếp cận này thay vì các lựa chọn thay thế khác?
- **Phân chia nhiệm vụ**: Ai làm gì, thời hạn hoàn thành khi nào.
- **Thảo luận ý tưởng (Brainstorming)**: Các giải pháp đã cân nhắc, ưu điểm / nhược điểm, kết luận cuối cùng.
- **Lỗi quan trọng (Bugs)**: Nguyên nhân gốc rễ và cách khắc phục.

---

## Cơ chế ghi nhận log sử dụng AI (AI Logging)

Các prompt và lượt gọi công cụ của bạn sẽ **tự động được ghi nhận và gửi đi** khi bạn sử dụng bất kỳ công cụ AI nào được hỗ trợ (Claude Code, Cursor, Codex, Gemini, Antigravity, Copilot). Bạn không cần thực hiện thêm bước thủ công nào sau khi đã chạy lệnh `setup_hooks`.

### Ghi nhận log thủ công (Dành cho ChatGPT hoặc các công cụ Web khác)

Nếu bạn sử dụng ChatGPT hoặc các công cụ AI khác trên giao diện web, hãy chạy lệnh dưới đây để ghi nhận lịch sử thủ công:

**Dành cho macOS / Linux (POSIX):**
```bash
bash scripts/_pyrun.sh scripts/log_manual.py --tool chatgpt --prompt "<mô tả chi tiết những gì bạn đã làm>"
```

**Dành cho Windows:**
```cmd
scripts\_pyrun.cmd scripts\log_manual.py --tool chatgpt --prompt "<mô tả chi tiết những gì bạn đã làm>"
```

### Yêu cầu về môi trường chạy Python

Hệ thống hooks yêu cầu cài đặt sẵn ít nhất một trong các lệnh: `python3`, `python`, hoặc `py` trong biến môi trường PATH của hệ điều hành.

| Hệ điều hành | Hướng dẫn cài đặt khuyến nghị |
|---|---|
| **Windows** | Tải Python 3 từ [python.org](https://www.python.org/downloads/) — khi cài đặt tích hợp sẵn cả `python` và launcher `py` vào PATH. |
| **Ubuntu / Debian** | Chạy `sudo apt install python3` (hầu hết đã được cài sẵn). |
| **macOS** | Chạy `brew install python3` hoặc sử dụng Python 3 đi kèm của hệ thống. |

Trình bao bọc `scripts/_pyrun.*` sẽ tự động phát hiện phiên bản Python đang có trên hệ thống của bạn — bạn không cần thiết lập cấu hình alias hoặc chỉnh sửa đường dẫn thủ công.

---

## Cải tiến hệ thống AI Log trong repository này

Để hỗ trợ quy trình làm việc thuận tiện hơn cho học sinh trong các môi trường Workspace phức tạp, repository này đã được cập nhật thêm các tính năng:

1. **Bộ lọc thông minh theo đường dẫn (Path-based filtering) cho Antigravity**:
   - Khác với phiên bản gốc chỉ dựa vào thư mục chạy lệnh (`Cwd`) dễ gây ra lỗi lẫn lộn hoặc kéo theo các prompt của các bài Lab khác khi bạn mở một Workspace cha chung (ví dụ thư mục `Vinuni/` chứa nhiều lab).
   - Hệ thống mới sẽ kiểm tra đệ quy tất cả các đường dẫn file được thao tác trong cuộc hội thoại. Chỉ khi cuộc hội thoại thực sự có tương tác với các file/thư mục nằm trong `Build/C2-App-037`, hệ thống mới ghi log và gửi đi.

2. **Khả năng chạy độc lập không phụ thuộc thư viện ngoài (`python-dotenv`)**:
   - Script gửi log (`submit_log.py`) đã được bổ sung bộ phân tích thủ công file `.env` dự phòng.
   - Nhờ vậy, ngay cả khi máy bạn chưa cài đặt thư viện `python-dotenv` (một lỗi phổ biến gây bỏ sót log mà không cảnh báo rõ), hệ thống vẫn tự động đọc được API Key từ `.env` và gửi log lên server chấm điểm thành công.
