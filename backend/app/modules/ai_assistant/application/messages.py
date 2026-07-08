"""User-facing message catalog for the AI assistant (vi/en).

Only *user-facing* assistant output is localized here — the deterministic
fast-path/agent replies, tool-result formatters, confirmation summaries, and
safety refusals that the student/partner actually reads. LLM system/developer
prompts, task instructions, and guardrail text stay English and live under
``app.ai.prompts`` / ``app.ai.safety`` (they are not routed through this
catalog).

Design:
- ``vi`` is the default and MUST stay byte-identical to the historical hardcoded
  Vietnamese so no existing behaviour or test changes for the default locale.
- ``en`` is a faithful translation of the same message.
- ``assistant_message(key, locale, **params)`` looks up the message, falls back
  to ``vi`` when the locale is unknown/unsupported, and ``.format(**params)``s
  any interpolation placeholders.

Every message is a plain string with optional ``{named}`` placeholders. Keep the
placeholder names identical across ``vi`` and ``en`` so callers stay locale
agnostic.
"""

from __future__ import annotations

from typing import Final

DEFAULT_LOCALE: Final[str] = "vi"
_SUPPORTED: Final[frozenset[str]] = frozenset({"vi", "en"})


def normalize_locale(locale: str | None) -> str:
    """Coerce an arbitrary locale hint to a supported catalog locale.

    Accepts ``None``, region-tagged (``en-US``), or unknown values and always
    returns one of the supported locales, defaulting to ``vi`` (so callers can
    pass a raw ``Accept-Language`` fragment safely).
    """
    if not locale:
        return DEFAULT_LOCALE
    base = locale.split(",")[0].split("-")[0].strip().lower()
    return base if base in _SUPPORTED else DEFAULT_LOCALE


# --------------------------------------------------------------------------- #
# Catalog                                                                     #
#                                                                             #
# Keyed by stable string ids grouped by source module. ``vi`` first (default) #
# then ``en``. Do NOT add LLM prompt / guardrail text here.                   #
# --------------------------------------------------------------------------- #

_MESSAGES: Final[dict[str, dict[str, str]]] = {
    # ---- chat_service (top-level orchestrator) ---------------------------- #
    "chat.cannot_process": {
        "vi": "Tôi không thể xử lý tin nhắn này. Vui lòng thử lại.",
        "en": "I couldn't process this message. Please try again.",
    },
    "chat.generic_error": {
        "vi": "Tôi gặp sự cố khi xử lý yêu cầu này. Vui lòng thử lại.",
        "en": "I ran into a problem handling this request. Please try again.",
    },
    "chat.preparing_tool": {
        "vi": "Đang chuẩn bị thực hiện: {tool_name}",
        "en": "Preparing to run: {tool_name}",
    },
    # ---- response_formatter ---------------------------------------------- #
    "formatter.ai_unavailable": {
        "vi": (
            "Xin lỗi, trợ lý AI tạm thời không khả dụng. "
            "Vui lòng thử lại sau hoặc dùng thanh tìm kiếm để khám phá cơ hội việc làm."
        ),
        "en": (
            "Sorry, the AI assistant is temporarily unavailable. "
            "Please try again later, or use the search bar to explore job opportunities."
        ),
    },
    "formatter.greeting": {
        "vi": (
            "Xin chào! Mình là trợ lý hướng nghiệp của VinUni. "
            "Bạn có thể hỏi mình về việc làm phù hợp, CV, đơn ứng tuyển, "
            "sự kiện tuyển dụng, mức lương hoặc định hướng nghề nghiệp."
        ),
        "en": (
            "Hi! I'm VinUni's career assistant. "
            "You can ask me about matching jobs, your CV, applications, "
            "recruitment events, salary, or career direction."
        ),
    },
    "formatter.stripped_tool_call_fallback": {
        "vi": "Mình đang tra cứu dữ liệu hệ thống. Vui lòng thử lại với câu hỏi cụ thể hơn.",
        "en": "I'm looking up platform data. Please try again with a more specific question.",
    },
    # ---- tool_loop (confirmation summaries) ------------------------------ #
    "confirm.pending_generic": {
        "vi": "Đang chờ xác nhận để thực hiện {tool_name}{reason}",
        "en": "Waiting for confirmation to run {tool_name}{reason}",
    },
    "confirm.result.save_job": {
        "vi": "Đã lưu việc làm này vào danh sách của bạn.",
        "en": "This job has been saved to your list.",
    },
    "confirm.result.apply_job": {
        "vi": "Đã nộp đơn ứng tuyển. Bạn có thể theo dõi trạng thái trong **Đơn ứng tuyển**.",
        "en": "Your application has been submitted. You can track its status in **Applications**.",
    },
    "confirm.result.move_candidate_stage": {
        "vi": "Đã cập nhật trạng thái ứng viên.",
        "en": "The candidate stage has been updated.",
    },
    "confirm.result.generic": {
        "vi": "Đã thực hiện thao tác.",
        "en": "The action has been completed.",
    },
    "confirm.error.apply_no_cv": {
        "vi": "Bạn chưa có CV để nộp đơn. Hãy tạo hoặc upload CV trong **CV Studio** trước.",
        "en": "You don't have a CV to apply with yet. Create or upload one in **CV Studio** first.",
    },
    "confirm.error.apply_already_applied": {
        "vi": (
            "Bạn đã ứng tuyển vị trí này rồi. "
            "Hãy kiểm tra trạng thái trong **Đơn ứng tuyển**."
        ),
        "en": (
            "You've already applied to this position. "
            "Check its status in **Applications**."
        ),
    },
    "confirm.error.apply_generic": {
        "vi": (
            "Mình chưa nộp đơn được lúc này. "
            "Bạn có thể mở trang việc làm và nhấn **Ứng tuyển**."
        ),
        "en": (
            "I couldn't submit the application right now. "
            "You can open the job page and click **Apply**."
        ),
    },
    "confirm.error.save_generic": {
        "vi": "Mình chưa lưu được việc làm này. Bạn có thể mở trang việc làm và nhấn nút lưu.",
        "en": "I couldn't save this job. You can open the job page and click the save button.",
    },
    "confirm.error.generic": {
        "vi": "Mình chưa thực hiện được thao tác này. Vui lòng thử lại.",
        "en": "I couldn't complete this action. Please try again.",
    },
    # ---- planner (deterministic agent replies) --------------------------- #
    "planner.out_of_scope": {
        "vi": (
            "Mình chỉ hỗ trợ các nội dung liên quan đến VinUni Career Platform, tài khoản, "
            "cài đặt hệ thống, tìm việc, CV, ứng tuyển, phỏng vấn, sự kiện tuyển dụng, "
            "mức lương và định hướng nghề nghiệp. Mình không tra cứu internet/nguồn ngoài; "
            "bạn có thể hỏi mình về một thao tác trong hệ thống hoặc một cơ hội việc làm nhé."
        ),
        "en": (
            "I only help with topics related to the VinUni Career Platform: your account, "
            "system settings, job search, CVs, applications, interviews, recruitment events, "
            "salary, and career direction. I don't browse the internet or external sources; "
            "you can ask me about an action in the platform or a job opportunity."
        ),
    },
    "planner.external_source": {
        "vi": (
            "Mình không tìm được trên {source} và cũng không tra cứu internet/nguồn ngoài. "
            "Chatbot này chỉ dùng dữ liệu trong **VinUni Career Platform**: việc làm đang mở, "
            "CV của bạn, đơn ứng tuyển, sự kiện, công ty/review nội bộ và knowledge base hệ thống. "
            "Bạn có thể hỏi: “tìm việc trong hệ thống VinUni Career cho data analyst ở Hà Nội” "
            "hoặc “gợi ý job phù hợp với CV của tôi”."
        ),
        "en": (
            "I couldn't find it on {source}, and I don't browse the internet or external sources. "
            "This assistant only uses data inside the **VinUni Career Platform**: open jobs, "
            "your CVs, applications, events, internal companies/reviews, and the platform "
            "knowledge base. You can ask: “find jobs in the VinUni Career Platform for a data "
            "analyst in Hanoi” or “suggest jobs that match my CV”."
        ),
    },
    "planner.capability": {
        "vi": (
            "Mình là chatbot cho student/người tìm việc trong **VinUni Career Platform**. "
            "Mình có thể tìm job/internship nội bộ, gợi ý job theo CV, xem CV/đơn ứng tuyển/"
            "lịch phỏng vấn/sự kiện, so CV với JD, tra review công ty nội bộ, benchmark lương "
            "và hướng dẫn bước tiếp theo. Mình không tìm trên Google, LinkedIn hay internet; "
            "mọi câu trả lời phải dựa trên dữ liệu trong hệ thống hoặc thông tin bạn cung cấp."
        ),
        "en": (
            "I'm the assistant for students/job seekers on the **VinUni Career Platform**. "
            "I can find internal jobs/internships, suggest jobs from your CV, review your "
            "CVs/applications/interview schedule/events, compare a CV with a JD, look up "
            "internal company reviews, benchmark salary, and guide your next step. I don't "
            "search Google, LinkedIn, or the internet; every answer is based on platform data "
            "or the information you provide."
        ),
    },
    "planner.data_boundary": {
        "vi": (
            "Nguồn của mình chỉ là **VinUni Career Platform**: job đang mở, CV của bạn, "
            "đơn ứng tuyển, lịch phỏng vấn, sự kiện, công ty/review nội bộ, salary benchmark "
            "và knowledge base của hệ thống. Mình không browse internet, Google, LinkedIn "
            "hay website ngoài; nếu bạn muốn, mình có thể tìm cơ hội tương ứng trong hệ thống."
        ),
        "en": (
            "My only source is the **VinUni Career Platform**: open jobs, your CVs, "
            "applications, interview schedule, events, internal companies/reviews, salary "
            "benchmarks, and the platform knowledge base. I don't browse the internet, Google, "
            "LinkedIn, or external websites; if you'd like, I can find matching opportunities "
            "inside the platform."
        ),
    },
    "planner.withdraw_application": {
        "vi": (
            "Mình chưa thể rút/hủy đơn trực tiếp qua chat. Bạn hãy mở **Đơn ứng tuyển**, "
            "chọn đúng đơn rồi dùng thao tác rút/hủy nếu hệ thống cho phép. Nếu chưa chắc nên rút, "
            "mình có thể giúp bạn xem lại trạng thái đơn và cân nhắc bước tiếp theo."
        ),
        "en": (
            "I can't withdraw or cancel an application directly through chat. Open "
            "**Applications**, pick the right one, and use the withdraw/cancel action if the "
            "system allows it. If you're unsure whether to withdraw, I can help you review the "
            "application's status and weigh your next step."
        ),
    },
    "planner.application_navigation": {
        "vi": (
            "Mình chưa chỉnh sửa đơn ứng tuyển trực tiếp qua chat. Bạn hãy vào **Đơn ứng tuyển**, "
            "mở đúng đơn và dùng các thao tác hệ thống cho phép. Nếu cần kiểm tra trạng thái hoặc "
            "quyết định nên làm gì tiếp, mình có thể xem danh sách đơn của bạn trong hệ thống."
        ),
        "en": (
            "I can't edit an application directly through chat. Go to **Applications**, open the "
            "right one, and use the actions the system allows. If you need to check status or "
            "decide what to do next, I can review your list of applications in the platform."
        ),
    },
    "planner.cv_nav.upload_create": {
        "vi": (
            "Bạn có thể upload hoặc tạo CV trong **CV Studio**. Sau khi có CV trong hệ thống, "
            "mình có thể xem danh sách CV, gợi ý job phù hợp hoặc so CV với một JD cụ thể."
        ),
        "en": (
            "You can upload or create a CV in **CV Studio**. Once you have a CV in the platform, "
            "I can list your CVs, suggest matching jobs, or compare a CV with a specific JD."
        ),
    },
    "planner.cv_nav.delete": {
        "vi": (
            "Mình chưa xóa CV trực tiếp qua chat. Bạn hãy vào **CV Studio**, chọn CV cần xóa "
            "và dùng menu thao tác của CV đó. Mình vẫn có thể liệt kê CV hiện có để bạn chọn đúng."
        ),
        "en": (
            "I can't delete a CV directly through chat. Go to **CV Studio**, pick the CV to "
            "delete, and use that CV's action menu. I can still list your existing CVs so you "
            "pick the right one."
        ),
    },
    "planner.cv_nav.download": {
        "vi": (
            "Bạn có thể tải CV xuống trong **CV Studio** từ menu của từng CV. Nếu muốn biết "
            "nên dùng CV nào để apply, hãy nói “gợi ý job phù hợp với CV của tôi”."
        ),
        "en": (
            "You can download a CV in **CV Studio** from each CV's menu. If you want to know "
            "which CV to apply with, say “suggest jobs that match my CV”."
        ),
    },
    "planner.cv_nav.edit": {
        "vi": (
            "Mình không sửa trực tiếp file/CV qua chat. Bạn hãy vào **CV Studio** để chỉnh "
            "nội dung, đổi tên hoặc quản lý phiên bản CV. Mình có thể hỗ trợ phần AI như: "
            "gợi ý cải thiện CV, kiểm tra CV cần bổ sung gì, hoặc so CV với một JD/job cụ thể."
        ),
        "en": (
            "I can't edit a CV file directly through chat. Go to **CV Studio** to edit content, "
            "rename, or manage CV versions. I can help with the AI side: suggest CV "
            "improvements, check what your CV is missing, or compare a CV with a specific "
            "JD/job."
        ),
    },
    "planner.cv_nav.default": {
        "vi": (
            "Các thao tác quản lý CV nằm trong **CV Studio**. Mình có thể xem CV hiện có, "
            "gợi ý job theo CV hoặc so CV với một JD/job cụ thể trong hệ thống."
        ),
        "en": (
            "CV management actions live in **CV Studio**. I can review your existing CVs, "
            "suggest jobs from your CV, or compare a CV with a specific JD/job in the platform."
        ),
    },
    "planner.save_job_needs_selection": {
        "vi": (
            "Mình có thể lưu job cho bạn sau khi xác định đúng tin tuyển dụng trong hệ thống. "
            "Hãy tìm job trước hoặc nói rõ “lưu job thứ 2”; thao tác lưu sẽ cần bạn xác nhận."
        ),
        "en": (
            "I can save a job for you once we've pinned down the right listing in the platform. "
            "Search for a job first or say “save the 2nd job”; the save action will need your "
            "confirmation."
        ),
    },
    "planner.unsave_job": {
        "vi": (
            "Mình chưa bỏ lưu/xóa job khỏi danh sách đã lưu trực tiếp qua chat. Bạn hãy vào "
            "**Việc làm đã lưu** hoặc mở trang job rồi bấm bỏ lưu. Mình có thể hiển thị danh sách "
            "job đã lưu để bạn chọn đúng tin."
        ),
        "en": (
            "I can't unsave or remove a job from your saved list directly through chat. Go to "
            "**Saved Jobs** or open the job page and click unsave. I can show your saved jobs so "
            "you pick the right listing."
        ),
    },
    "planner.event_action.cancel": {
        "vi": (
            "Mình chưa hủy đăng ký sự kiện trực tiếp qua chat. Bạn hãy vào **Sự kiện** hoặc "
            "**Sự kiện đã đăng ký**, mở đúng sự kiện và dùng nút hủy nếu hệ thống cho phép."
        ),
        "en": (
            "I can't cancel an event registration directly through chat. Go to **Events** or "
            "**Registered Events**, open the right event, and use the cancel button if the "
            "system allows it."
        ),
    },
    "planner.event_action.register": {
        "vi": (
            "Mình chưa đăng ký sự kiện trực tiếp qua chat. Bạn hãy mở trang "
            "**Sự kiện**, chọn sự kiện "
            "phù hợp và bấm đăng ký. Mình có thể tìm sự kiện trong hệ thống hoặc xem các sự kiện "
            "bạn đã đăng ký."
        ),
        "en": (
            "I can't register for an event directly through chat. Open the **Events** page, pick "
            "a suitable event, and click register. I can find events in the platform or review "
            "the events you've registered for."
        ),
    },
    "planner.interview_action": {
        "vi": (
            "Mình chưa xác nhận, hủy hoặc đổi lịch phỏng vấn trực tiếp qua chat. Bạn hãy mở "
            "**Đơn ứng tuyển** hoặc lịch phỏng vấn trong hệ thống để thao tác. Mình có thể xem "
            "lịch phỏng vấn sắp tới hoặc bắt đầu mock interview để bạn luyện tập."
        ),
        "en": (
            "I can't confirm, cancel, or reschedule an interview directly through chat. Open "
            "**Applications** or the interview schedule in the platform to do that. I can show "
            "your upcoming interviews or start a mock interview for practice."
        ),
    },
    "planner.alert_action": {
        "vi": (
            "Mình chưa {action} job alert trực tiếp qua chat. Bạn hãy vào **Thông báo việc làm** "
            "hoặc **Cài đặt thông báo** để quản lý alert. Mình có thể xem các job alert hiện có "
            "và tìm việc phù hợp ngay trong hệ thống."
        ),
        "en": (
            "I can't {action} a job alert directly through chat. Go to **Job Alerts** or "
            "**Notification Settings** to manage alerts. I can review your existing job alerts "
            "and find matching jobs right in the platform."
        ),
    },
    "planner.alert_action.manage": {"vi": "quản lý", "en": "manage"},
    "planner.alert_action.create": {"vi": "tạo/bật", "en": "create/enable"},
    "planner.alert_action.edit": {"vi": "sửa/tắt/xóa", "en": "edit/disable/delete"},
    "planner.offer_action": {
        "vi": (
            "Mình chưa chấp nhận, từ chối, ký hoặc nộp phản hồi offer/hợp đồng qua chat. "
            "Bạn nên mở đúng offer trong **Đơn ứng tuyển** và thao tác trong hệ thống sau khi "
            "đọc kỹ lương, probation, benefit, deadline và điều kiện làm việc. Mình có thể giúp "
            "bạn kiểm tra checklist hoặc tra benchmark lương trước khi quyết định."
        ),
        "en": (
            "I can't accept, decline, sign, or submit a response to an offer/contract through "
            "chat. Open the specific offer in **Applications** and act in the platform after "
            "carefully reading the salary, probation, benefits, deadline, and working "
            "conditions. I can help you go through a checklist or look up a salary benchmark "
            "before you decide."
        ),
    },
    "planner.scam_or_safety": {
        "vi": (
            "Nếu một job hoặc nhà tuyển dụng yêu cầu chuyển khoản, đặt cọc, nộp phí ứng tuyển, "
            "gửi giấy tờ nhạy cảm ngoài quy trình, hoặc có dấu hiệu quấy rối/phân biệt đối xử, "
            "bạn nên dừng trao đổi và báo cáo trong hệ thống hoặc liên hệ Career Office. "
            "Mình có thể giúp bạn kiểm tra lại job/công ty trong dữ liệu nội bộ nếu bạn gửi tên "
            "hoặc mở job đó trong VinUni Career."
        ),
        "en": (
            "If a job or employer asks for a bank transfer, deposit, application fee, sensitive "
            "documents outside the normal process, or shows signs of harassment/discrimination, "
            "you should stop the conversation and report it in the platform or contact the "
            "Career Office. I can help you re-check the job/company in internal data if you send "
            "the name or open that job in VinUni Career."
        ),
    },
    "planner.domain_clarification": {
        "vi": (
            "Mình hiểu đây là câu hỏi liên quan đến quá trình tìm việc, nhưng cần bạn nói rõ hơn "
            "để trả lời chính xác bằng dữ liệu hệ thống. Bạn có thể hỏi theo một hướng cụ thể như: "
            "“tìm internship data ở Hà Nội”, “gợi ý job phù hợp với CV của tôi”, "
            "“đơn ứng tuyển của tôi sao rồi”, hoặc “so CV với job thứ 1”."
        ),
        "en": (
            "I can tell this is about your job search, but I need a bit more detail to answer "
            "precisely with platform data. You can ask in a specific direction, e.g. “find a "
            "data internship in Hanoi”, “suggest jobs that match my CV”, “how are my "
            "applications doing”, or “compare my CV with job #1”."
        ),
    },
    "planner.support.contact": {
        "vi": (
            "Bạn có thể liên hệ admin/cố vấn qua mục **Tin nhắn** hoặc **Trợ giúp** "
            "trong hệ thống. Nếu đang ở workspace, hãy bấm biểu tượng chat hoặc avatar "
            "góc phải rồi chọn **Hỗ trợ**. Với lỗi tài khoản khẩn cấp, hãy gửi kèm email "
            "đăng ký và ảnh chụp màn hình để đội hỗ trợ kiểm tra nhanh hơn."
        ),
        "en": (
            "You can reach an admin/advisor through **Messages** or **Help** in the platform. "
            "If you're in the workspace, click the chat icon or the avatar at the top right, "
            "then choose **Support**. For urgent account issues, include your registered email "
            "and a screenshot so the support team can check faster."
        ),
    },
    "planner.support.theme": {
        "vi": (
            "Bạn có thể đổi theme/giao diện tại **Cài đặt** → **Ngôn ngữ & khu vực** "
            "→ **Giao diện**. Chọn Sáng, Tối hoặc Theo hệ thống. Nếu đang ở workspace, "
            "hãy bấm avatar góc phải rồi vào **Cài đặt**."
        ),
        "en": (
            "You can change the theme/appearance under **Settings** → **Language & region** "
            "→ **Appearance**. Choose Light, Dark, or System. If you're in the workspace, click "
            "the avatar at the top right and open **Settings**."
        ),
    },
    "planner.support.account": {
        "vi": (
            "Nếu tài khoản gặp vấn đề, hãy dùng **Quên mật khẩu** ở màn hình đăng nhập "
            "hoặc vào **Cài đặt** → **Bảo mật** khi còn đăng nhập được. Nếu tài khoản bị "
            "khóa hoặc email chưa xác thực, hãy liên hệ bộ phận hỗ trợ VinUni Career Platform."
        ),
        "en": (
            "If your account has issues, use **Forgot password** on the login screen, or go to "
            "**Settings** → **Security** while you're still signed in. If your account is locked "
            "or your email isn't verified, contact VinUni Career Platform support."
        ),
    },
    "planner.support.settings": {
        "vi": (
            "Các thiết lập hệ thống nằm trong **Cài đặt**: ngôn ngữ/giao diện, thông báo, "
            "bảo mật tài khoản, gói sử dụng và quyền/role. Một số mục chỉ hiện nếu tài khoản "
            "của bạn có quyền student, partner hoặc university tương ứng."
        ),
        "en": (
            "System settings live under **Settings**: language/appearance, notifications, "
            "account security, your plan, and permissions/roles. Some items only appear if your "
            "account has the corresponding student, partner, or university permissions."
        ),
    },
    "planner.cover_letter": {
        "vi": (
            "Mình có thể giúp bạn dựng thư ứng tuyển theo cấu trúc 4 đoạn: "
            "1) vị trí và lý do quan tâm, 2) 2–3 bằng chứng năng lực khớp JD, "
            "3) vì sao bạn hợp công ty/đội nhóm, 4) lời kết và CTA lịch sự. "
            "Bạn gửi JD hoặc nói “viết cover letter cho job thứ 1” để mình cá nhân hóa hơn."
        ),
        "en": (
            "I can help you build a cover letter in 4 paragraphs: "
            "1) the role and why you're interested, 2) 2–3 pieces of evidence matching the JD, "
            "3) why you fit the company/team, 4) a polite closing and CTA. "
            "Send the JD or say “write a cover letter for job #1” so I can personalize it more."
        ),
    },
    "planner.portfolio": {
        "vi": (
            "Portfolio/GitHub/LinkedIn nên chứng minh năng lực bằng bằng chứng cụ thể: "
            "3–5 dự án tốt nhất, vai trò của bạn, tech/skill dùng, kết quả đo được, "
            "link demo hoặc repo sạch README. Nếu bạn đang apply, hãy ưu tiên dự án khớp JD "
            "và đưa 1–2 project mạnh nhất lên đầu CV."
        ),
        "en": (
            "Your portfolio/GitHub/LinkedIn should prove your ability with concrete evidence: "
            "3–5 best projects, your role, the tech/skills used, measurable results, and a demo "
            "link or a clean repo with a README. If you're applying, prioritize projects that "
            "match the JD and put your 1–2 strongest projects at the top of your CV."
        ),
    },
    "planner.offer": {
        "vi": (
            "Với offer/hợp đồng, bạn nên kiểm tra 5 điểm: lương gross/net, probation, "
            "benefit, điều kiện làm việc, và deadline phản hồi. Nếu muốn thương lượng, "
            "hãy nêu mức mong muốn bằng dữ liệu thị trường và lý do năng lực; mình có thể "
            "tra benchmark lương nếu bạn cho biết role và số năm kinh nghiệm."
        ),
        "en": (
            "For an offer/contract, check 5 things: gross/net salary, probation, benefits, "
            "working conditions, and the response deadline. If you want to negotiate, state your "
            "target using market data and your capability rationale; I can look up a salary "
            "benchmark if you tell me the role and years of experience."
        ),
    },
    "planner.rejection": {
        "vi": (
            "Bị từ chối không có nghĩa là hồ sơ của bạn kém; thường là lệch timing, fit hoặc "
            "mức cạnh tranh. Bước tốt nhất là xem lại JD, so CV với yêu cầu, ghi lại câu hỏi "
            "phỏng vấn khó, rồi apply thêm 3–5 vị trí tương tự. Bạn có thể hỏi “gợi ý job phù hợp” "
            "hoặc “so CV với job đó” để mình giúp cụ thể hơn."
        ),
        "en": (
            "A rejection doesn't mean your profile is weak; it's usually about timing, fit, or "
            "competition. The best next step is to review the JD, compare your CV with the "
            "requirements, note the hard interview questions, then apply to 3–5 more similar "
            "roles. You can ask “suggest matching jobs” or “compare my CV with that job” so I "
            "can help more specifically."
        ),
    },
    "planner.first_job": {
        "vi": (
            "Nếu bạn chưa có kinh nghiệm, hãy nhắm internship/fresher và dùng dự án, coursework, "
            "club, research hoặc volunteer làm bằng chứng. CV nên đặt kỹ năng + dự án liên quan "
            "lên cao, mỗi bullet có hành động và kết quả. Mình có thể tìm internship phù hợp hoặc "
            "gợi ý job dựa trên CV của bạn."
        ),
        "en": (
            "If you don't have experience yet, target internships/fresher roles and use "
            "projects, coursework, clubs, research, or volunteering as evidence. Put relevant "
            "skills + projects high on your CV, with each bullet showing an action and a result. "
            "I can find suitable internships or suggest jobs based on your CV."
        ),
    },
    # ---- planner: external source labels (interpolated into planner.external_source)
    "planner.external_source_label.external_website": {
        "vi": "website ngoài hệ thống",
        "en": "an external website",
    },
    "planner.external_source_label.internet": {
        "vi": "internet",
        "en": "the internet",
    },
    "planner.external_source_label.external_default": {
        "vi": "nguồn ngoài hệ thống",
        "en": "an external source",
    },
    # ---- formatters (tool-result rendering) ------------------------------ #
    "fmt.tool.generic_ok": {
        "vi": "Mình đã tra cứu dữ liệu hệ thống và sẵn sàng hỗ trợ bước tiếp theo.",
        "en": "I've looked up platform data and I'm ready to help with the next step.",
    },
    "fmt.fail.no_specific_job": {
        "vi": "Mình chưa xác định được job cụ thể. Bạn hãy mở/tìm job trước rồi nói “job đó” nhé.",
        "en": (
            "I couldn't identify a specific job. Please open/find a job first, then say "
            "“that job”."
        ),
    },
    "fmt.fail.recommend_jobs": {
        "vi": (
            "Mình chưa tạo được gợi ý việc làm lúc này. "
            "Bạn có thể mở trang **Việc làm** để duyệt các tin mới."
        ),
        "en": (
            "I couldn't generate job suggestions right now. "
            "You can open the **Jobs** page to browse new listings."
        ),
    },
    "fmt.fail.cvs_with_reason": {
        "vi": (
            "Mình chưa tải được thư viện CV lúc này. Bạn hãy kiểm tra lại trong "
            "**CV Studio**; khi đã có CV, hãy chọn một JD/job cụ thể để hệ thống "
            "so CV, kỹ năng thiếu và keyword cần bổ sung."
        ),
        "en": (
            "I couldn't load your CV library right now. Please check again in "
            "**CV Studio**; once you have a CV, pick a specific JD/job so the system can compare "
            "the CV, missing skills, and keywords to add."
        ),
    },
    "fmt.fail.cvs": {
        "vi": "Mình chưa tải được thư viện CV. Bạn thử mở **CV Studio** hoặc tải lại trang nhé.",
        "en": "I couldn't load your CV library. Try opening **CV Studio** or reloading the page.",
    },
    "fmt.fail.applications": {
        "vi": "Mình chưa tải được đơn ứng tuyển. Bạn có thể kiểm tra trong **Đơn ứng tuyển**.",
        "en": "I couldn't load your applications. You can check them in **Applications**.",
    },
    "fmt.fail.skill_gap": {
        "vi": (
            "Mình chưa phân tích được độ phù hợp. "
            "Hãy chắc chắn bạn đã có CV và job cụ thể trong hệ thống."
        ),
        "en": (
            "I couldn't analyze the fit. "
            "Make sure you have a CV and a specific job in the platform."
        ),
    },
    "fmt.fail.generic": {
        "vi": "Mình chưa lấy được dữ liệu hệ thống lúc này. Vui lòng thử lại sau.",
        "en": "I couldn't retrieve platform data right now. Please try again later.",
    },
    # ---- formatters: salary ---------------------------------------------- #
    "fmt.salary.no_benchmark": {
        "vi": "Hiện chưa có benchmark lương đủ tin cậy cho vị trí này.",
        "en": "There isn't a reliable salary benchmark for this position yet.",
    },
    "fmt.salary.with_url": {
        "vi": "{note}\nBạn có thể xem thêm tin đang mở tại {search_url}.",
        "en": "{note}\nYou can see more open listings at {search_url}.",
    },
    "fmt.salary.heading": {
        "vi": "Benchmark lương tham khảo cho {role}:",
        "en": "Reference salary benchmark for {role}:",
    },
    "fmt.salary.tier": {
        "vi": "- {years} năm kinh nghiệm: {min}–{max} {currency}",
        "en": "- {years} years of experience: {min}–{max} {currency}",
    },
    "fmt.salary.footer": {
        "vi": (
            "Đây là khoảng tham khảo; thực tế phụ thuộc công ty, level, kỹ năng và phỏng vấn."
        ),
        "en": (
            "This is a reference range; the actual figure depends on the company, level, "
            "skills, and interview."
        ),
    },
    # ---- formatters: jobs ------------------------------------------------ #
    "fmt.jobs.empty": {
        "vi": (
            "Mình chưa thấy việc làm phù hợp trong dữ liệu hiện tại. "
            "Bạn có thể thử từ khóa khác trên trang **Việc làm**."
        ),
        "en": (
            "I don't see matching jobs in the current data. "
            "You can try different keywords on the **Jobs** page."
        ),
    },
    "fmt.jobs.heading.recommend_platform_only": {
        "vi": "{reason}\nMình sẽ gợi ý việc làm bằng dữ liệu nội bộ:",
        "en": "{reason}\nI'll suggest jobs using internal data:",
    },
    "fmt.jobs.heading.recommend_apply": {
        "vi": (
            "Bạn muốn ứng tuyển, nên mình cần chọn đúng vị trí trước. "
            "Một số việc làm phù hợp với hồ sơ của bạn:"
        ),
        "en": (
            "You'd like to apply, so I need to pick the right position first. "
            "Some jobs that match your profile:"
        ),
    },
    "fmt.jobs.heading.recommend": {
        "vi": "Một số việc làm phù hợp với hồ sơ của bạn:",
        "en": "Some jobs that match your profile:",
    },
    "fmt.jobs.heading.saved": {
        "vi": "Các việc làm bạn đã lưu:",
        "en": "Jobs you've saved:",
    },
    "fmt.jobs.heading.partner": {
        "vi": "Các job đang quản lý:",
        "en": "Jobs you manage:",
    },
    "fmt.jobs.heading.search_platform_only": {
        "vi": "{reason}\nMình tìm thấy các việc làm trong hệ thống:",
        "en": "{reason}\nI found these jobs in the platform:",
    },
    "fmt.jobs.heading.search": {
        "vi": "Mình tìm thấy các việc làm sau:",
        "en": "I found these jobs:",
    },
    "fmt.jobs.item_title_fallback": {
        "vi": "Vị trí tuyển dụng",
        "en": "Job position",
    },
    "fmt.jobs.footer": {
        "vi": (
            "Bạn có thể nói “xem chi tiết job thứ 2”, “so CV với job đó”, "
            "hoặc “apply job thứ 2”."
        ),
        "en": (
            "You can say “show details of the 2nd job”, “compare my CV with that job”, "
            "or “apply to the 2nd job”."
        ),
    },
    # ---- formatters: job detail ------------------------------------------ #
    "fmt.job_detail.title_fallback": {
        "vi": "Vị trí tuyển dụng",
        "en": "Job position",
    },
    "fmt.job_detail.employment": {
        "vi": "- Hình thức: {employment_type} · {location_type}",
        "en": "- Type: {employment_type} · {location_type}",
    },
    "fmt.job_detail.salary": {
        "vi": "- Lương: {salary_min}–{salary_max} {currency}",
        "en": "- Salary: {salary_min}–{salary_max} {currency}",
    },
    "fmt.job_detail.skills": {
        "vi": "- Kỹ năng chính: {skills}",
        "en": "- Key skills: {skills}",
    },
    "fmt.job_detail.deadline": {
        "vi": "- Hạn ứng tuyển: {deadline}",
        "en": "- Application deadline: {deadline}",
    },
    "fmt.job_detail.view": {
        "vi": "Xem chi tiết: {url}",
        "en": "View details: {url}",
    },
    # ---- formatters: skill gap ------------------------------------------- #
    "fmt.skill_gap.heading": {
        "vi": "Độ phù hợp giữa CV **{cv_title}** và job **{job_title}**: {score}/100.",
        "en": "Fit between CV **{cv_title}** and job **{job_title}**: {score}/100.",
    },
    "fmt.skill_gap.job_fallback": {
        "vi": "này",
        "en": "this",
    },
    "fmt.skill_gap.matched": {
        "vi": "Kỹ năng đã khớp: {skills}.",
        "en": "Matched skills: {skills}.",
    },
    "fmt.skill_gap.gaps": {
        "vi": "Nên bổ sung/tô rõ: {gaps}.",
        "en": "Consider adding/highlighting: {gaps}.",
    },
    "fmt.skill_gap.view_jd": {
        "vi": "Bạn có thể xem lại JD tại {url}.",
        "en": "You can review the JD at {url}.",
    },
    # ---- formatters: CVs ------------------------------------------------- #
    "fmt.cvs.empty_with_reason": {
        "vi": (
            "Bạn chưa có CV nào trong hệ thống. Hãy upload CV vào **CV Studio** trước; "
            "sau đó chọn một JD/job cụ thể để mình phân tích độ phù hợp, kỹ năng thiếu "
            "và keyword nên bổ sung."
        ),
        "en": (
            "You don't have any CV in the platform yet. Upload a CV into **CV Studio** first; "
            "then pick a specific JD/job so I can analyze the fit, missing skills, and keywords "
            "to add."
        ),
    },
    "fmt.cvs.empty": {
        "vi": (
            "Bạn chưa có CV nào trong hệ thống. "
            "Hãy vào **CV Studio** để upload CV hoặc tạo CV từ mẫu."
        ),
        "en": (
            "You don't have any CV in the platform yet. "
            "Go to **CV Studio** to upload a CV or create one from a template."
        ),
    },
    "fmt.cvs.heading_with_reason": {
        "vi": (
            "Mình đã tìm thấy CV của bạn. Để check CV thật chính xác, "
            "hãy chọn một JD/job cụ thể để hệ thống so kỹ năng, keyword và độ phù hợp."
        ),
        "en": (
            "I found your CVs. To check a CV precisely, "
            "pick a specific JD/job so the system can compare skills, keywords, and fit."
        ),
    },
    "fmt.cvs.count": {
        "vi": "Bạn đang có {total} CV trong thư viện.",
        "en": "You have {total} CV(s) in your library.",
    },
    "fmt.cvs.heading_no_count": {
        "vi": "CV hiện có trong thư viện của bạn:",
        "en": "CVs currently in your library:",
    },
    "fmt.cvs.list_heading": {
        "vi": "Danh sách CV hiện có:",
        "en": "Your current CV list:",
    },
    "fmt.cvs.item_title_fallback": {
        "vi": "Untitled CV",
        "en": "Untitled CV",
    },
    "fmt.cvs.footer_with_reason": {
        "vi": "Bạn có thể hỏi: “CV này nên apply JD nào?” hoặc “so CV với job thứ 1”.",
        "en": "You can ask: “which JD should I apply this CV to?” or “compare my CV with job #1”.",
    },
    # ---- formatters: applications ---------------------------------------- #
    "fmt.applications.empty": {
        "vi": (
            "Bạn chưa có đơn ứng tuyển nào. "
            "Khi ứng tuyển, trạng thái sẽ nằm trong **Đơn ứng tuyển**."
        ),
        "en": (
            "You don't have any applications yet. "
            "Once you apply, the status will appear in **Applications**."
        ),
    },
    "fmt.applications.heading": {
        "vi": "Các đơn ứng tuyển gần đây của bạn:",
        "en": "Your recent applications:",
    },
    "fmt.applications.job_fallback": {
        "vi": "Vị trí",
        "en": "Position",
    },
    # ---- formatters: events ---------------------------------------------- #
    "fmt.events.empty": {
        "vi": "Mình chưa thấy sự kiện phù hợp. Bạn có thể xem thêm ở trang **Sự kiện**.",
        "en": "I don't see matching events. You can see more on the **Events** page.",
    },
    "fmt.events.heading.registered": {
        "vi": "Sự kiện bạn đã đăng ký:",
        "en": "Events you've registered for:",
    },
    "fmt.events.heading.search": {
        "vi": "Một số sự kiện phù hợp:",
        "en": "Some matching events:",
    },
    "fmt.events.item_title_fallback": {
        "vi": "Sự kiện",
        "en": "Event",
    },
    # ---- formatters: companies ------------------------------------------- #
    "fmt.companies.empty_platform_only": {
        "vi": (
            "{reason}\nMình chưa tìm thấy công ty phù hợp trong dữ liệu nội bộ. "
            "Bạn có thể thử tên công ty khác trong trang **Công ty**."
        ),
        "en": (
            "{reason}\nI couldn't find a matching company in internal data. "
            "You can try a different company name on the **Companies** page."
        ),
    },
    "fmt.companies.empty": {
        "vi": (
            "Mình chưa tìm thấy công ty phù hợp. "
            "Bạn có thể thử từ khóa khác trong trang **Công ty**."
        ),
        "en": (
            "I couldn't find a matching company. "
            "You can try different keywords on the **Companies** page."
        ),
    },
    "fmt.companies.heading_platform_only": {
        "vi": "{reason}\nMột số công ty phù hợp trong hệ thống:",
        "en": "{reason}\nSome matching companies in the platform:",
    },
    "fmt.companies.heading": {
        "vi": "Một số công ty phù hợp:",
        "en": "Some matching companies:",
    },
    "fmt.companies.item_name_fallback": {
        "vi": "Công ty",
        "en": "Company",
    },
    "fmt.companies.item_open_roles": {
        "vi": "{count} vị trí mở",
        "en": "{count} open role(s)",
    },
    "fmt.companies.footer": {
        "vi": "Bạn có thể hỏi “review công ty thứ 1” hoặc “chi tiết công ty đó”.",
        "en": "You can ask “review the 1st company” or “details of that company”.",
    },
    # ---- formatters: company detail -------------------------------------- #
    "fmt.company_detail.name_fallback": {
        "vi": "Thông tin công ty",
        "en": "Company information",
    },
    "fmt.company_detail.industry_size": {
        "vi": "- Ngành/quy mô: {industry} · {size}",
        "en": "- Industry/size: {industry} · {size}",
    },
    "fmt.company_detail.hq": {
        "vi": "- Trụ sở: {city}",
        "en": "- Headquarters: {city}",
    },
    "fmt.company_detail.open_roles": {
        "vi": "- Vị trí đang mở: {count}",
        "en": "- Open positions: {count}",
    },
    "fmt.company_detail.rating": {
        "vi": "- Đánh giá: {rating} ({review_count} review)",
        "en": "- Rating: {rating} ({review_count} review(s))",
    },
    "fmt.company_detail.page": {
        "vi": "Trang công ty: {url}",
        "en": "Company page: {url}",
    },
    # ---- formatters: company reviews ------------------------------------- #
    "fmt.company_reviews.heading": {
        "vi": "Tóm tắt review công ty:",
        "en": "Company review summary:",
    },
    "fmt.company_reviews.overall": {
        "vi": "- Điểm tổng quan: {overall_avg} từ {review_count} review",
        "en": "- Overall score: {overall_avg} from {review_count} review(s)",
    },
    "fmt.company_reviews.empty": {
        "vi": "Chưa có review công khai đủ dữ liệu cho công ty này.",
        "en": "There aren't enough public reviews for this company yet.",
    },
    "fmt.company_reviews.view_more": {
        "vi": "Xem thêm: {url}",
        "en": "See more: {url}",
    },
    # ---- formatters: profile (identity-only) ----------------------------- #
    "fmt.profile.open_to_work": {
        "vi": (
            "Hồ sơ của bạn đang bật trạng thái “Sẵn sàng tìm việc”, nên nhà tuyển dụng "
            "có thể thấy bạn đang tìm cơ hội. Nội dung sự nghiệp của bạn nằm trong CV — "
            "hãy hỏi “gợi ý job phù hợp” hoặc “so CV với job thứ 1” để đi tiếp."
        ),
        "en": (
            "Your profile is set to “Open to work”, so recruiters can see you're looking "
            "for opportunities. Your career details live in your CVs — ask “suggest "
            "matching jobs” or “compare my CV with job #1” to continue."
        ),
    },
    "fmt.profile.not_open_to_work": {
        "vi": (
            "Hồ sơ của bạn đang tắt trạng thái “Sẵn sàng tìm việc”. Bật nó lên ở phần Hồ sơ "
            "nếu bạn muốn nhà tuyển dụng biết bạn đang tìm cơ hội. Nội dung sự nghiệp của bạn "
            "nằm trong CV — vào /student/cv để tạo hoặc cập nhật CV."
        ),
        "en": (
            "Your profile is not set to “Open to work”. Turn it on in your Profile if you'd "
            "like recruiters to know you're looking. Your career details live in your CVs — "
            "go to /student/cv to create or update a CV."
        ),
    },
    # ---- formatters: interviews ------------------------------------------ #
    "fmt.interviews.empty": {
        "vi": "Bạn chưa có lịch phỏng vấn sắp tới trong hệ thống.",
        "en": "You don't have any upcoming interviews in the platform.",
    },
    "fmt.interviews.heading": {
        "vi": "Lịch phỏng vấn sắp tới:",
        "en": "Upcoming interviews:",
    },
    "fmt.interviews.job_fallback": {
        "vi": "Vị trí",
        "en": "Position",
    },
    # ---- formatters: alerts ---------------------------------------------- #
    "fmt.alerts.empty": {
        "vi": (
            "Bạn chưa có job alert nào. Hãy tạo alert ở **Thông báo việc làm** để nhận tin phù hợp."
        ),
        "en": (
            "You don't have any job alerts. Create one in **Job Alerts** to receive matching "
            "listings."
        ),
    },
    "fmt.alerts.heading": {
        "vi": "Job alerts đang bật:",
        "en": "Active job alerts:",
    },
    "fmt.alerts.item_name_fallback": {
        "vi": "Alert",
        "en": "Alert",
    },
    "fmt.alerts.any_keyword": {
        "vi": "mọi từ khóa",
        "en": "all keywords",
    },
    # ---- formatters: partner pipeline ------------------------------------ #
    "fmt.partner_pipeline.heading": {
        "vi": "Pipeline hiện có {active} ứng viên đang active trên {jobs} job.",
        "en": "The pipeline currently has {active} active candidate(s) across {jobs} job(s).",
    },
    "fmt.partner_pipeline.item_job_fallback": {
        "vi": "Job",
        "en": "Job",
    },
    "fmt.partner_pipeline.item": {
        "vi": "- {title} · {active} active",
        "en": "- {title} · {active} active",
    },
    # ---- formatters: career advice --------------------------------------- #
    "fmt.career.fallback_overview": {
        "vi": "Lộ trình {role} đang có nhu cầu trên thị trường.",
        "en": "The {role} track is in demand in the market.",
    },
    "fmt.career.role_fallback": {
        "vi": "nghề nghiệp",
        "en": "career",
    },
    "fmt.career.skills": {
        "vi": "Kỹ năng nên tập trung: {skills}.",
        "en": "Skills to focus on: {skills}.",
    },
    "fmt.career.growth_path": {
        "vi": "Lộ trình thường gặp: {path}.",
        "en": "A common growth path: {path}.",
    },
    "fmt.career.search_url": {
        "vi": "Bạn có thể xem việc liên quan tại {url}.",
        "en": "You can see related jobs at {url}.",
    },
    # ---- formatters: interview sim --------------------------------------- #
    "fmt.interview_sim.opening": {
        "vi": "Mình có thể bắt đầu luyện phỏng vấn với câu hỏi này:\n{question}",
        "en": "I can start the mock interview with this question:\n{question}",
    },
    "fmt.interview_sim.tip": {
        "vi": "Gợi ý trả lời: {tip}",
        "en": "Answer tip: {tip}",
    },
    "fmt.interview_sim.unavailable": {
        "vi": (
            "Mình chưa tạo được phiên luyện phỏng vấn lúc này. "
            "Bạn thử nêu rõ role hoặc job muốn luyện nhé."
        ),
        "en": (
            "I couldn't start a mock interview session right now. "
            "Try specifying the role or job you want to practice for."
        ),
    },
    # ---- safety: policy refusals ----------------------------------------- #
    "safety.refuse.harmful": {
        "vi": (
            "Tôi không thể hỗ trợ yêu cầu này. Nếu bạn đang gặp khó khăn, "
            "vui lòng liên hệ đường dây hỗ trợ sức khỏe tâm thần hoặc tư vấn viên nhà trường."
        ),
        "en": (
            "I can't help with this request. If you're going through a hard time, "
            "please contact a mental-health support line or a university counselor."
        ),
    },
    "safety.refuse.boundary_probe": {
        "vi": (
            "Xin lỗi, tôi không thể chia sẻ thông tin về cấu hình nội bộ, "
            "nhà cung cấp, hay hướng dẫn hệ thống. "
            "Tôi có thể giúp bạn tìm việc làm, chuẩn bị CV, hoặc luyện phỏng vấn nhé?"
        ),
        "en": (
            "Sorry, I can't share information about internal configuration, "
            "providers, or system instructions. "
            "I can help you find jobs, prepare a CV, or practice interviews instead?"
        ),
    },
    "safety.refuse.external_source": {
        "vi": (
            "Mình không thể tra cứu internet hoặc nguồn ngoài hệ thống. "
            "Mình chỉ dùng dữ liệu trong VinUni Career Platform như việc làm, CV, "
            "đơn ứng tuyển, sự kiện, công ty và knowledge base nội bộ."
        ),
        "en": (
            "I can't look up the internet or external sources. "
            "I only use data inside the VinUni Career Platform, such as jobs, CVs, "
            "applications, events, companies, and the internal knowledge base."
        ),
    },
    "safety.refuse.generic": {
        "vi": "Tôi không thể xử lý yêu cầu này.",
        "en": "I can't handle this request.",
    },
}


def assistant_message(key: str, locale: str | None = DEFAULT_LOCALE, **params: object) -> str:
    """Return the localized, formatted user-facing message for ``key``.

    Unknown/unsupported locales fall back to ``vi`` (keeping the historical
    Vietnamese output byte-identical). A missing ``key`` is a programming error
    and raises ``KeyError`` so it surfaces in tests, not to users.
    """
    entry = _MESSAGES[key]
    loc = normalize_locale(locale)
    template = entry.get(loc) or entry[DEFAULT_LOCALE]
    if params:
        return template.format(**params)
    return template
