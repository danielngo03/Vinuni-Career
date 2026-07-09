"""Default notification template seed data (subject/body copy, vi + en).

Pure data, no logic. Extracted from ``template_seed.py`` so the copy content is
separate from the idempotent seeding logic. See ``template_seed.ensure_default_templates``
for how this is applied.
"""

from __future__ import annotations

DEFAULT_TEMPLATES: list[dict] = [
    {
        "key": "account.email_verification",
        "channel": "email",
        "variables_schema": {
            "allowed": ["name", "action_url", "email", "token", "otp_code", "ttl_minutes"],
            "required": ["otp_code", "action_url"],
        },
        "locales": {
            "vi": {
                "subject": "Mã xác minh email của bạn — VinUni Career",
                "body": (
                    "Cảm ơn bạn đã đăng ký VinUni Career Platform.\n\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "Mã xác minh của bạn:\n\n"
                    "  {{otp_code}}\n\n"
                    "━━━━━━━━━━━━━━━━━━━━\n\n"
                    "Mã có hiệu lực trong {{ttl_minutes}} phút.\n\n"
                    "Hoặc click vào liên kết bên dưới để xác minh tự động:\n"
                    "{{action_url}}\n\n"
                    "Nếu bạn không tạo tài khoản này, vui lòng bỏ qua email.\n\n"
                    "Trân trọng,\nVinUni Career Platform"
                ),
            },
            "en": {
                "subject": "Your email verification code — VinUni Career",
                "body": (
                    "Thanks for signing up for VinUni Career Platform.\n\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "Your verification code:\n\n"
                    "  {{otp_code}}\n\n"
                    "━━━━━━━━━━━━━━━━━━━━\n\n"
                    "The code is valid for {{ttl_minutes}} minutes.\n\n"
                    "Or click the link below to verify automatically:\n"
                    "{{action_url}}\n\n"
                    "If you didn't create this account, you can safely ignore this email.\n\n"
                    "Best regards,\nVinUni Career Platform"
                ),
            },
        },
    },
    {
        "key": "account.password_reset",
        "channel": "email",
        "variables_schema": {
            "allowed": ["name", "action_url", "email", "token", "otp_code", "ttl_minutes"],
            "required": ["action_url", "otp_code"],
        },
        "locales": {
            "vi": {
                "subject": "Đặt lại mật khẩu — VinUni Career",
                "body": (
                    "Chúng tôi nhận được yêu cầu đặt lại mật khẩu cho tài khoản của bạn.\n\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "Mã đặt lại mật khẩu:\n\n"
                    "  {{otp_code}}\n\n"
                    "━━━━━━━━━━━━━━━━━━━━\n\n"
                    "Bạn cũng có thể mở liên kết bên dưới để tạo mật khẩu mới:\n\n"
                    "{{action_url}}\n\n"
                    "Mã và liên kết chỉ dùng được một lần và sẽ hết hạn sau "
                    "{{ttl_minutes}} phút. Nếu bạn không yêu cầu, vui lòng bỏ qua email — "
                    "mật khẩu của bạn sẽ không "
                    "thay đổi.\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "Reset your password — VinUni Career",
                "body": (
                    "We received a request to reset the password for your account.\n\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "Password reset code:\n\n"
                    "  {{otp_code}}\n\n"
                    "━━━━━━━━━━━━━━━━━━━━\n\n"
                    "You can also open the link below to choose a new password:\n\n"
                    "{{action_url}}\n\n"
                    "This code and link can be used once and expire in {{ttl_minutes}} "
                    "minutes. If you did not request this, you can safely ignore this "
                    "email — your password will not change.\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        # OAuth account linking confirmation (E36 B-542/B-543). Sent whenever a
        # Google/Facebook identity is newly attached to this account (auto-link
        # for passwordless accounts, or explicit link-confirm after a password
        # challenge) so the owner has a durable record even if they didn't
        # initiate it from this device.
        "key": "account.oauth_linked",
        "channel": "email",
        "variables_schema": {
            "allowed": ["name", "email", "provider"],
            "required": ["email", "provider"],
        },
        "locales": {
            "vi": {
                "subject": "Đã liên kết tài khoản đăng nhập — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Tài khoản {{email}} của bạn vừa được liên kết để đăng nhập bằng "
                    "{{provider}}.\n\n"
                    "Nếu bạn không thực hiện thao tác này, vui lòng đổi mật khẩu ngay "
                    "và liên hệ VinUni Career Center.\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "Sign-in method linked — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "Your account {{email}} was just linked to sign in with "
                    "{{provider}}.\n\n"
                    "If you didn't do this, please change your password immediately "
                    "and contact VinUni Career Center.\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        # OAuth link-conflict notice. A sign-in attempt matched this account's
        # verified email via a provider that isn't linked yet; nothing was
        # changed unless the owner completed the explicit link-confirm flow.
        "key": "account.oauth_conflict",
        "channel": "email",
        "variables_schema": {
            "allowed": ["name", "email", "provider"],
            "required": ["email", "provider"],
        },
        "locales": {
            "vi": {
                "subject": "Có người thử đăng nhập bằng tài khoản của bạn — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Có người vừa thử đăng nhập vào VinUni Career bằng {{provider}} "
                    "sử dụng địa chỉ email {{email}} của bạn.\n\n"
                    "Chúng tôi CHƯA thực hiện bất kỳ thay đổi nào đối với tài khoản của "
                    "bạn — việc liên kết chỉ hoàn tất nếu chính bạn xác nhận bằng mật "
                    "khẩu. Nếu đây không phải là bạn, không cần làm gì thêm.\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "Someone tried signing in to your account — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "Someone just tried to sign in to VinUni Career with {{provider}} "
                    "using your email address {{email}}.\n\n"
                    "We have NOT made any changes to your account — linking only "
                    "completes if you confirm it yourself with your password. If this "
                    "wasn't you, no action is needed.\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        # Messaging new-message email (ADR-0012 §4). PII-safe: a masked sender label
        # + a neutral prompt + the internal deep link — NEVER the message body, never
        # the anonymous student's identity. ``action_url`` is an internal relative
        # path (allowed by the renderer's allowlist).
        "key": "message.received",
        "channel": "email",
        "variables_schema": {
            "allowed": ["name", "email", "sender_label", "action_url"],
            "required": ["sender_label"],
        },
        "locales": {
            "vi": {
                "subject": "Bạn có tin nhắn mới — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "{{sender_label}} đã gửi cho bạn một tin nhắn mới trên VinUni "
                    "Career. Mở liên kết bên dưới để xem và phản hồi:\n\n"
                    "{{action_url}}\n\n"
                    "Vì lý do bảo mật, nội dung tin nhắn không được hiển thị trong "
                    "email này.\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "You have a new message — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "{{sender_label}} sent you a new message on VinUni Career. Open "
                    "the link below to read and reply:\n\n"
                    "{{action_url}}\n\n"
                    "For your privacy, the message content is not shown in this "
                    "email.\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        # Message-request accepted email (Messaging V2). PII-safe: a MASKED
        # counterpart label + a neutral prompt + the internal deep link — never the
        # message body. Sent to the request INITIATOR when the other side accepts.
        "key": "message.request_accepted",
        "channel": "email",
        "variables_schema": {
            "allowed": ["name", "email", "counterpart_label", "action_url"],
            "required": ["counterpart_label"],
        },
        "locales": {
            "vi": {
                "subject": "Lời mời nhắn tin đã được chấp nhận — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "{{counterpart_label}} đã chấp nhận lời mời nhắn tin của bạn "
                    "trên VinUni Career. Bây giờ bạn có thể bắt đầu trò chuyện — mở "
                    "liên kết bên dưới:\n\n"
                    "{{action_url}}\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "Your message request was accepted — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "{{counterpart_label}} accepted your message request on VinUni "
                    "Career. You can now start the conversation — open the link "
                    "below:\n\n"
                    "{{action_url}}\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        "key": "partner.registration_received",
        "channel": "email",
        "variables_schema": {
            "allowed": ["name", "email", "company_name"],
            "required": ["name", "company_name"],
        },
        "locales": {
            "vi": {
                "subject": "Đã nhận hồ sơ đăng ký đối tác — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Chúng tôi đã nhận được hồ sơ đăng ký đối tác cho {{company_name}}. "
                    "Đội ngũ VinUni Career sẽ xem xét và phản hồi trong thời gian sớm "
                    "nhất.\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "We received your partner registration — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "We have received the partner registration for {{company_name}}. "
                    "The VinUni Career team will review it and get back to you "
                    "shortly.\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        "key": "partner.registration_approved",
        "channel": "email",
        "variables_schema": {
            "allowed": ["name", "email", "company_name", "token", "action_url"],
            "required": ["name", "company_name", "action_url"],
        },
        "locales": {
            "vi": {
                "subject": "Hồ sơ đối tác đã được duyệt — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Chúc mừng! Hồ sơ đối tác của {{company_name}} đã được phê duyệt. "
                    "Vui lòng kích hoạt tài khoản quản trị viên và đặt mật khẩu bằng "
                    "liên kết bên dưới:\n\n"
                    "{{action_url}}\n\n"
                    "Liên kết sẽ hết hạn sau 24 giờ.\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "Your partner account is approved — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "Congratulations! The partner registration for {{company_name}} "
                    "has been approved. Please activate your administrator account and "
                    "set a password using the link below:\n\n"
                    "{{action_url}}\n\n"
                    "This link expires in 24 hours.\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        "key": "partner.registration_rejected",
        "channel": "email",
        "variables_schema": {
            "allowed": ["name", "email", "company_name", "reason"],
            "required": ["name", "company_name", "reason"],
        },
        "locales": {
            "vi": {
                "subject": "Cập nhật về hồ sơ đăng ký đối tác — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Cảm ơn bạn đã quan tâm hợp tác cùng VinUni Career. Rất tiếc, hồ sơ "
                    "đăng ký của {{company_name}} chưa được chấp thuận ở thời điểm này.\n\n"
                    "Lý do: {{reason}}\n\n"
                    "Bạn có thể đăng ký lại sau khi bổ sung thông tin.\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "Update on your partner registration — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "Thank you for your interest in partnering with VinUni Career. "
                    "Unfortunately, the registration for {{company_name}} was not "
                    "approved at this time.\n\n"
                    "Reason: {{reason}}\n\n"
                    "You are welcome to register again with updated information.\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        "key": "org.member_invitation",
        "channel": "email",
        "variables_schema": {
            "allowed": ["email", "org_name", "token", "action_url"],
            "required": ["org_name", "action_url"],
        },
        "locales": {
            "vi": {
                "subject": "Bạn được mời tham gia tổ chức trên VinUni Career",
                "body": (
                    "Xin chào,\n\n"
                    "Bạn được mời tham gia {{org_name}} trên VinUni Career. Nhấn vào "
                    "liên kết bên dưới để chấp nhận lời mời:\n\n"
                    "{{action_url}}\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "You're invited to join an organization on VinUni Career",
                "body": (
                    "Hello,\n\n"
                    "You have been invited to join {{org_name}} on VinUni Career. "
                    "Click the link below to accept the invitation:\n\n"
                    "{{action_url}}\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        "key": "job.approved",
        "channel": "email",
        "variables_schema": {
            "allowed": ["name", "email", "job_title", "action_url"],
            "required": ["job_title", "action_url"],
        },
        "locales": {
            "vi": {
                "subject": "Tin tuyển dụng đã được duyệt — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Tin tuyển dụng \"{{job_title}}\" của bạn đã được duyệt và hiển thị "
                    "công khai trên VinUni Career. Bạn có thể xem tại:\n\n"
                    "{{action_url}}\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "Your job posting is approved — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "Your job posting \"{{job_title}}\" has been approved and is now "
                    "live publicly on VinUni Career. You can view it here:\n\n"
                    "{{action_url}}\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        "key": "job.rejected",
        "channel": "email",
        "variables_schema": {
            "allowed": ["name", "email", "job_title", "reason"],
            "required": ["job_title", "reason"],
        },
        "locales": {
            "vi": {
                "subject": "Cập nhật về tin tuyển dụng — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Rất tiếc, tin tuyển dụng \"{{job_title}}\" của bạn chưa được duyệt "
                    "ở thời điểm này.\n\n"
                    "Lý do: {{reason}}\n\n"
                    "Bạn có thể chỉnh sửa và gửi lại tin để được xem xét.\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "Update on your job posting — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "Unfortunately, your job posting \"{{job_title}}\" was not approved "
                    "at this time.\n\n"
                    "Reason: {{reason}}\n\n"
                    "You can edit and resubmit the posting for another review.\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        "key": "job.auto_closed",
        "channel": "email",
        "variables_schema": {
            "allowed": ["name", "email", "job_title"],
            "required": ["job_title"],
        },
        "locales": {
            "vi": {
                "subject": "Tin tuyển dụng đã đóng — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Tin tuyển dụng \"{{job_title}}\" của bạn đã tự động đóng do đã "
                    "qua hạn nộp hồ sơ và không còn hiển thị công khai.\n\n"
                    "Bạn có thể mở lại tin (sau khi cập nhật hạn nộp) trên VinUni "
                    "Career nếu vẫn muốn tuyển.\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "Your job posting was closed — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "Your job posting \"{{job_title}}\" was automatically closed "
                    "because its application deadline passed and is no longer public.\n\n"
                    "You can reopen it (after updating the deadline) on VinUni Career "
                    "if you are still hiring.\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        "key": "application.received",
        "channel": "email",
        "variables_schema": {
            "allowed": ["name", "email", "job_title", "applicant_label"],
            "required": ["job_title", "applicant_label"],
        },
        "locales": {
            "vi": {
                "subject": "Bạn có ứng viên mới — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Tin tuyển dụng \"{{job_title}}\" vừa nhận được hồ sơ ứng tuyển từ "
                    "{{applicant_label}}. Đăng nhập VinUni Career để xem chi tiết.\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "You have a new applicant — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "Your job posting \"{{job_title}}\" just received an application from "
                    "{{applicant_label}}. Sign in to VinUni Career to review it.\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        "key": "application.under_review",
        "channel": "email",
        "variables_schema": {
            "allowed": ["name", "email", "job_title"],
            "required": [],
        },
        "locales": {
            "vi": {
                "subject": "Hồ sơ của bạn đang được xem xét — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Hồ sơ ứng tuyển của bạn đang được nhà tuyển dụng xem xét. "
                    "Chúng tôi sẽ thông báo cho bạn khi có cập nhật mới.\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "Your application is under review — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "Your application is now being reviewed by the employer. "
                    "We'll let you know when there's an update.\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        "key": "application.stage_advanced",
        "channel": "email",
        "variables_schema": {
            "allowed": ["name", "email", "job_title"],
            "required": [],
        },
        "locales": {
            "vi": {
                "subject": "Hồ sơ của bạn đã chuyển sang vòng tiếp theo — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Tin tốt! Hồ sơ ứng tuyển của bạn đã được chuyển sang vòng tiếp "
                    "theo. Chúng tôi sẽ thông báo cho bạn khi có cập nhật mới.\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "Your application advanced to the next round — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "Good news! Your application has advanced to the next round. "
                    "We'll let you know when there's an update.\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        "key": "application.under_rereview",
        "channel": "email",
        "variables_schema": {
            "allowed": ["name", "email", "job_title"],
            "required": [],
        },
        "locales": {
            "vi": {
                "subject": "Hồ sơ của bạn đang được xem xét lại — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Hồ sơ ứng tuyển của bạn đang được nhà tuyển dụng xem xét lại. "
                    "Chúng tôi sẽ thông báo cho bạn khi có cập nhật mới.\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "Your application is being re-reviewed — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "Your application is being re-reviewed by the employer. "
                    "We'll let you know when there's an update.\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        "key": "application.rejected",
        "channel": "email",
        "variables_schema": {
            "allowed": ["name", "email", "job_title"],
            "required": [],
        },
        "locales": {
            "vi": {
                "subject": "Cập nhật hồ sơ ứng tuyển — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Cảm ơn bạn đã quan tâm. Lần này hồ sơ ứng tuyển của bạn chưa "
                    "phù hợp với vị trí. Đừng nản lòng — hãy tiếp tục khám phá các "
                    "cơ hội khác trên VinUni Career.\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "Application update — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "Thank you for your interest. Your application was not selected "
                    "for this role this time. Keep going — explore more opportunities "
                    "on VinUni Career.\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        "key": "application.interview_scheduled",
        "channel": "email",
        "variables_schema": {
            "allowed": [
                "name", "email", "job_title", "scheduled_at", "mode_label",
                "location_or_link",
            ],
            "required": [],
        },
        "locales": {
            "vi": {
                "subject": "Bạn có lịch phỏng vấn mới — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Bạn có buổi phỏng vấn cho vị trí “{{job_title}}”.\n"
                    "Thời gian: {{scheduled_at}}\n"
                    "Hình thức: {{mode_label}}\n"
                    "Địa điểm / liên kết: {{location_or_link}}\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "You have a new interview scheduled — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "You have an interview for “{{job_title}}”.\n"
                    "Time: {{scheduled_at}}\n"
                    "Mode: {{mode_label}}\n"
                    "Location / link: {{location_or_link}}\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        "key": "application.interview_rescheduled",
        "channel": "email",
        "variables_schema": {
            "allowed": [
                "name", "email", "job_title", "scheduled_at", "mode_label",
                "location_or_link",
            ],
            "required": [],
        },
        "locales": {
            "vi": {
                "subject": "Lịch phỏng vấn của bạn đã được cập nhật — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Buổi phỏng vấn cho vị trí “{{job_title}}” đã được cập nhật.\n"
                    "Thời gian mới: {{scheduled_at}}\n"
                    "Hình thức: {{mode_label}}\n"
                    "Địa điểm / liên kết: {{location_or_link}}\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "Your interview was rescheduled — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "Your interview for “{{job_title}}” was updated.\n"
                    "New time: {{scheduled_at}}\n"
                    "Mode: {{mode_label}}\n"
                    "Location / link: {{location_or_link}}\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        "key": "application.interview_cancelled",
        "channel": "email",
        "variables_schema": {
            "allowed": ["name", "email", "job_title", "scheduled_at", "mode_label"],
            "required": [],
        },
        "locales": {
            "vi": {
                "subject": "Lịch phỏng vấn của bạn đã bị hủy — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Buổi phỏng vấn cho vị trí “{{job_title}}” đã bị hủy. Chúng tôi "
                    "sẽ thông báo cho bạn nếu có lịch mới.\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "Your interview was cancelled — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "Your interview for “{{job_title}}” was cancelled. We'll let "
                    "you know if a new time is set.\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        "key": "application.interview_reminder",
        "channel": "email",
        "variables_schema": {
            "allowed": [
                "name", "email", "job_title", "scheduled_at", "mode_label",
                "location_or_link",
            ],
            "required": [],
        },
        "locales": {
            "vi": {
                "subject": "Nhắc lịch phỏng vấn sắp tới — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Nhắc bạn về buổi phỏng vấn sắp tới cho vị trí “{{job_title}}”.\n"
                    "Thời gian: {{scheduled_at}}\n"
                    "Hình thức: {{mode_label}}\n"
                    "Địa điểm / liên kết: {{location_or_link}}\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "Upcoming interview reminder — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "A reminder about your upcoming interview for “{{job_title}}”.\n"
                    "Time: {{scheduled_at}}\n"
                    "Mode: {{mode_label}}\n"
                    "Location / link: {{location_or_link}}\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        "key": "application.interview_assigned",
        "channel": "email",
        "variables_schema": {
            "allowed": ["name", "email", "job_title", "scheduled_at", "mode_label"],
            "required": [],
        },
        "locales": {
            "vi": {
                "subject": "Bạn được phân công phỏng vấn — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Bạn được phân công phỏng vấn cho vị trí “{{job_title}}”.\n"
                    "Thời gian: {{scheduled_at}}\n"
                    "Hình thức: {{mode_label}}\n\n"
                    "Đăng nhập VinUni Career để xem chi tiết.\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "You were assigned to an interview — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "You were assigned to interview for “{{job_title}}”.\n"
                    "Time: {{scheduled_at}}\n"
                    "Mode: {{mode_label}}\n\n"
                    "Sign in to VinUni Career for the details.\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        "key": "application.stage_sla_reminder",
        "channel": "email",
        # Partner-internal (pipeline owner/reviewer). No student-identity field.
        "variables_schema": {
            "allowed": [
                "name", "email", "job_title", "stage_name", "level_label",
                "deadline_label",
            ],
            "required": [],
        },
        "locales": {
            "vi": {
                "subject": "Nhắc hạn xử lý ứng viên — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Một ứng viên ở vòng “{{stage_name}}” cho vị trí “{{job_title}}” "
                    "{{level_label}} hạn xử lý ({{deadline_label}}).\n\n"
                    "Vui lòng đăng nhập VinUni Career để xem xét sớm.\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "Candidate review deadline reminder — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "A candidate at the “{{stage_name}}” stage for “{{job_title}}” "
                    "{{level_label}} its review deadline ({{deadline_label}}).\n\n"
                    "Please sign in to VinUni Career to take a look soon.\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        "key": "application.offer_received",
        "channel": "email",
        # NO salary variable — comp is never in a notification/email body (DATA_MODEL
        # §17); the candidate opens the platform to view comp.
        "variables_schema": {
            "allowed": [
                "name", "email", "job_title", "position_title", "company_name",
                "expiry_date",
            ],
            "required": [],
        },
        "locales": {
            "vi": {
                "subject": "Bạn nhận được một thư mời — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "{{company_name}} đã gửi cho bạn thư mời cho vị trí "
                    "“{{position_title}}”.\n"
                    "Vui lòng phản hồi trước: {{expiry_date}}\n\n"
                    "Đăng nhập VinUni Career để xem chi tiết và chấp nhận hoặc từ "
                    "chối.\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "You received an offer — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "{{company_name}} sent you an offer for “{{position_title}}”.\n"
                    "Please respond by: {{expiry_date}}\n\n"
                    "Sign in to VinUni Career to view the details and accept or "
                    "decline.\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        "key": "application.offer_expiring",
        "channel": "email",
        "variables_schema": {
            "allowed": [
                "name", "email", "job_title", "position_title", "company_name",
                "expiry_date",
            ],
            "required": [],
        },
        "locales": {
            "vi": {
                "subject": "Thư mời của bạn sắp hết hạn — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Thư mời cho vị trí “{{position_title}}” sẽ hết hạn vào "
                    "{{expiry_date}}.\n\n"
                    "Đăng nhập VinUni Career để phản hồi trước khi hết hạn.\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "Your offer is expiring soon — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "Your offer for “{{position_title}}” expires on "
                    "{{expiry_date}}.\n\n"
                    "Sign in to VinUni Career to respond before it expires.\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        "key": "application.offer_expired",
        "channel": "email",
        "variables_schema": {
            "allowed": [
                "name", "email", "job_title", "position_title", "company_name",
                "expiry_date",
            ],
            "required": [],
        },
        "locales": {
            "vi": {
                "subject": "Thư mời đã hết hạn — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Thư mời cho vị trí “{{position_title}}” đã hết hạn do quá thời "
                    "hạn phản hồi.\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "Your offer has expired — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "Your offer for “{{position_title}}” has expired because the "
                    "response deadline passed.\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        "key": "application.offer_rescinded",
        "channel": "email",
        "variables_schema": {
            "allowed": [
                "name", "email", "job_title", "position_title", "company_name",
                "expiry_date",
            ],
            "required": [],
        },
        "locales": {
            "vi": {
                "subject": "Cập nhật về thư mời của bạn — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Thư mời cho vị trí “{{position_title}}” đã được thu hồi. Chúng "
                    "tôi sẽ thông báo cho bạn nếu có cập nhật mới.\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "Update on your offer — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "The offer for “{{position_title}}” was withdrawn. We'll let you "
                    "know if there's an update.\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        "key": "application.reveal_requested",
        "channel": "email",
        "variables_schema": {
            "allowed": ["name", "email", "company_name"],
            "required": ["company_name"],
        },
        "locales": {
            "vi": {
                "subject": "Yêu cầu xem thông tin của bạn — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Công ty {{company_name}} muốn xem thông tin đầy đủ của bạn cho một "
                    "vị trí bạn đã ứng tuyển ẩn danh. Đăng nhập VinUni Career để xem lý "
                    "do và chấp nhận hoặc từ chối. Yêu cầu sẽ hết hạn sau 72 giờ.\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "A company requests your information — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "{{company_name}} would like to view your full information for a role "
                    "you applied to anonymously. Sign in to VinUni Career to see the "
                    "reason and accept or decline. The request expires in 72 hours.\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        "key": "application.reveal_responded",
        "channel": "email",
        "variables_schema": {
            "allowed": ["name", "email", "decision_label"],
            "required": ["decision_label"],
        },
        "locales": {
            "vi": {
                "subject": "Phản hồi yêu cầu xem thông tin — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Ứng viên đã phản hồi yêu cầu xem thông tin của bạn: {{decision_label}}. "
                    "Đăng nhập VinUni Career để xem chi tiết.\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "Response to your information request — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "The candidate responded to your information request: {{decision_label}}. "
                    "Sign in to VinUni Career to see the details.\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        "key": "account.password_changed",
        "channel": "email",
        "variables_schema": {
            "allowed": ["name", "email"],
            "required": ["name"],
        },
        "locales": {
            "vi": {
                "subject": "Mật khẩu của bạn đã được thay đổi — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Mật khẩu tài khoản của bạn vừa được thay đổi. Tất cả các phiên "
                    "đăng nhập khác đã được đăng xuất.\n\n"
                    "Nếu đây không phải là bạn, vui lòng đặt lại mật khẩu ngay và liên "
                    "hệ bộ phận hỗ trợ.\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "Your password was changed — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "The password for your account was just changed. All other active "
                    "sessions have been signed out.\n\n"
                    "If this wasn't you, reset your password immediately and contact "
                    "support.\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        "key": "event.registration_confirmed",
        "channel": "email",
        "variables_schema": {
            "allowed": ["name", "email", "event_title", "starts_at", "venue_or_format"],
            "required": ["event_title"],
        },
        "locales": {
            "vi": {
                "subject": "Đăng ký sự kiện thành công — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Bạn đã đăng ký thành công sự kiện “{{event_title}}”.\n"
                    "Thời gian bắt đầu: {{starts_at}}\n"
                    "Địa điểm / hình thức: {{venue_or_format}}\n\n"
                    "Xem trong mục “Sự kiện của tôi” trên VinUni Career.\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "You're registered — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "You're registered for “{{event_title}}”.\n"
                    "Starts: {{starts_at}}\n"
                    "Location / format: {{venue_or_format}}\n\n"
                    "Find it under “My events” on VinUni Career.\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        "key": "event.registration_waitlisted",
        "channel": "email",
        "variables_schema": {
            "allowed": ["name", "email", "event_title", "waitlist_position"],
            "required": ["event_title"],
        },
        "locales": {
            "vi": {
                "subject": "Bạn đang ở danh sách chờ — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Sự kiện “{{event_title}}” hiện đã đầy chỗ. Bạn đang ở vị trí "
                    "#{{waitlist_position}} trong danh sách chờ và sẽ được tự động "
                    "xác nhận nếu có chỗ trống.\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "You're on the waitlist — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "“{{event_title}}” is currently full. You're #{{waitlist_position}} "
                    "on the waitlist and will be confirmed automatically if a seat "
                    "opens up.\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        "key": "event.waitlist_promoted",
        "channel": "email",
        "variables_schema": {
            "allowed": ["name", "email", "event_title", "starts_at", "venue_or_format"],
            "required": ["event_title"],
        },
        "locales": {
            "vi": {
                "subject": "Bạn đã có chỗ tham dự — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Một chỗ vừa trống — bạn đã được xác nhận tham dự sự kiện "
                    "“{{event_title}}”.\n"
                    "Thời gian bắt đầu: {{starts_at}}\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "A seat opened up — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "A seat opened up — you're now registered for “{{event_title}}”.\n"
                    "Starts: {{starts_at}}\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        "key": "event.reminder",
        "channel": "email",
        "variables_schema": {
            "allowed": ["name", "email", "event_title", "starts_at", "venue_or_format"],
            "required": ["event_title"],
        },
        "locales": {
            "vi": {
                "subject": "Nhắc lịch sự kiện sắp diễn ra — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Nhắc bạn về sự kiện sắp diễn ra: “{{event_title}}”.\n"
                    "Thời gian bắt đầu: {{starts_at}}\n"
                    "Địa điểm / hình thức: {{venue_or_format}}\n\n"
                    "Với sự kiện trực tuyến, liên kết tham dự sẽ có trong ứng dụng.\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "Upcoming event reminder — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "A reminder about your upcoming event: “{{event_title}}”.\n"
                    "Starts: {{starts_at}}\n"
                    "Location / format: {{venue_or_format}}\n\n"
                    "For online events, the access link will be available in-app.\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        "key": "event.reminder_soon",
        "channel": "email",
        "variables_schema": {
            "allowed": ["name", "email", "event_title", "starts_at", "venue_or_format"],
            "required": ["event_title"],
        },
        "locales": {
            "vi": {
                "subject": "Sự kiện sắp bắt đầu trong 1 giờ — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Sự kiện “{{event_title}}” sắp bắt đầu trong khoảng 1 giờ nữa.\n"
                    "Thời gian bắt đầu: {{starts_at}}\n"
                    "Địa điểm / hình thức: {{venue_or_format}}\n\n"
                    "Với sự kiện trực tuyến, liên kết tham dự sẽ có trong ứng dụng.\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "Your event starts in about 1 hour — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "“{{event_title}}” starts in about 1 hour.\n"
                    "Starts: {{starts_at}}\n"
                    "Location / format: {{venue_or_format}}\n\n"
                    "For online events, the access link will be available in-app.\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        "key": "event.cancelled",
        "channel": "email",
        "variables_schema": {
            "allowed": ["name", "email", "event_title"],
            "required": ["event_title"],
        },
        "locales": {
            "vi": {
                "subject": "Sự kiện đã bị hủy — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Rất tiếc, ban tổ chức đã hủy sự kiện “{{event_title}}”. "
                    "Chúng tôi xin lỗi vì sự bất tiện này.\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "Event cancelled — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "Unfortunately, the organizer has cancelled “{{event_title}}”. "
                    "We're sorry for the inconvenience.\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        "key": "event.approved",
        "channel": "email",
        "variables_schema": {
            "allowed": ["name", "email", "event_title"],
            "required": ["event_title"],
        },
        "locales": {
            "vi": {
                "subject": "Sự kiện đã được duyệt — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Sự kiện “{{event_title}}” của bạn đã được duyệt và hiển thị "
                    "công khai trên VinUni Career.\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "Your event is approved — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "Your event “{{event_title}}” was approved and is now live "
                    "publicly on VinUni Career.\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        "key": "event.rejected",
        "channel": "email",
        "variables_schema": {
            "allowed": ["name", "email", "event_title", "reason"],
            "required": ["event_title", "reason"],
        },
        "locales": {
            "vi": {
                "subject": "Cập nhật về sự kiện — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Rất tiếc, sự kiện “{{event_title}}” chưa được duyệt ở thời "
                    "điểm này.\n\n"
                    "Lý do: {{reason}}\n\n"
                    "Bạn có thể chỉnh sửa và gửi lại để được xem xét.\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "Update on your event — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "Unfortunately, your event “{{event_title}}” was not approved at "
                    "this time.\n\n"
                    "Reason: {{reason}}\n\n"
                    "You can edit and resubmit it for another review.\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        "key": "advertising.submitted",
        "channel": "email",
        "variables_schema": {
            "allowed": ["name", "email", "company_name", "target_title"],
            "required": [],
        },
        "locales": {
            "vi": {
                "subject": "Yêu cầu quảng cáo mới chờ duyệt — VinUni Career",
                "body": (
                    "Xin chào,\n\n"
                    "Có một yêu cầu quảng cáo mới đang chờ duyệt trên VinUni Career. "
                    "Vui lòng đăng nhập để xem xét nội dung, nhãn công khai và chi "
                    "phí.\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "New advertising request pending review — VinUni Career",
                "body": (
                    "Hello,\n\n"
                    "A new advertising request is pending review on VinUni Career. "
                    "Please sign in to review the content, disclosure label, and "
                    "spend.\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        "key": "advertising.approved",
        "channel": "email",
        "variables_schema": {
            "allowed": ["name", "email"],
            "required": [],
        },
        "locales": {
            "vi": {
                "subject": "Yêu cầu quảng cáo đã được duyệt — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Yêu cầu quảng cáo của bạn đã được duyệt. Chiến dịch sẽ chạy "
                    "trong khung thời gian đã đặt sau khi thanh toán được ghi "
                    "nhận.\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "Your advertising request is approved — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "Your advertising request was approved. The campaign will run in "
                    "its scheduled window once payment is recorded.\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        "key": "advertising.rejected",
        "channel": "email",
        "variables_schema": {
            "allowed": ["name", "email", "reason"],
            "required": ["reason"],
        },
        "locales": {
            "vi": {
                "subject": "Cập nhật về yêu cầu quảng cáo — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Rất tiếc, yêu cầu quảng cáo của bạn chưa được duyệt ở thời "
                    "điểm này.\n\n"
                    "Lý do: {{reason}}\n\n"
                    "Bạn có thể chỉnh sửa và gửi lại để được xem xét.\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "Update on your advertising request — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "Unfortunately, your advertising request was not approved at "
                    "this time.\n\n"
                    "Reason: {{reason}}\n\n"
                    "You can edit and resubmit it for another review.\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        "key": "advertising.payment_recorded",
        "channel": "email",
        # No payment reference / amount in the body (spend stays admin-only).
        "variables_schema": {
            "allowed": ["name", "email"],
            "required": [],
        },
        "locales": {
            "vi": {
                "subject": "Đã ghi nhận thanh toán quảng cáo — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Chúng tôi đã ghi nhận thanh toán cho chiến dịch quảng cáo của "
                    "bạn. Chiến dịch sẽ chạy đúng khung thời gian đã đặt.\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "Advertising payment recorded — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "We've recorded the payment for your advertising campaign. It "
                    "will run in its scheduled window.\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        "key": "advertising.live",
        "channel": "email",
        "variables_schema": {
            "allowed": ["name", "email"],
            "required": [],
        },
        "locales": {
            "vi": {
                "subject": "Chiến dịch quảng cáo đang chạy — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Chiến dịch quảng cáo của bạn đang chạy. Nội dung được tài trợ "
                    "luôn hiển thị kèm nhãn công khai bắt buộc.\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "Your advertising campaign is live — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "Your advertising campaign is now live. Sponsored content always "
                    "carries the mandatory public disclosure label.\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        "key": "advertising.ending",
        "channel": "email",
        "variables_schema": {
            "allowed": ["name", "email"],
            "required": [],
        },
        "locales": {
            "vi": {
                "subject": "Chiến dịch quảng cáo sắp kết thúc — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Chiến dịch quảng cáo của bạn sẽ kết thúc trong vòng 24 giờ "
                    "tới.\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "Your advertising campaign is ending soon — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "Your advertising campaign will end within the next 24 hours.\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    # ----------------------------------------------------- billing (ADR-0010)
    # No amount / payment reference in any body (revenue stays admin-only).
    {
        "key": "billing.payment_recorded",
        "channel": "email",
        "variables_schema": {"allowed": ["name", "email"], "required": []},
        "locales": {
            "vi": {
                "subject": "Đã ghi nhận thanh toán gói đăng ký — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Chúng tôi đã ghi nhận thanh toán cho gói đăng ký của bạn. Gói "
                    "dịch vụ của bạn đã được kích hoạt.\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "Subscription payment recorded — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "We've recorded the payment for your subscription. Your plan is "
                    "now active.\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        "key": "billing.active",
        "channel": "email",
        "variables_schema": {"allowed": ["name", "email"], "required": []},
        "locales": {
            "vi": {
                "subject": "Gói đăng ký đang hiệu lực — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Gói đăng ký của bạn đã được kích hoạt. Đăng nhập VinUni Career "
                    "để xem quyền lợi và ngày hết hạn.\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "Your subscription is active — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "Your subscription is now active. Sign in to VinUni Career to "
                    "see what it grants and its expiry.\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        "key": "billing.expiring",
        "channel": "email",
        "variables_schema": {"allowed": ["name", "email"], "required": []},
        "locales": {
            "vi": {
                "subject": "Gói đăng ký sắp hết hạn — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Gói đăng ký của bạn sẽ hết hạn trong vòng 7 ngày tới. Hãy gia "
                    "hạn để giữ các quyền lợi nâng cao.\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "Your subscription is expiring soon — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "Your subscription will expire within the next 7 days. Renew to "
                    "keep your upgraded benefits.\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        "key": "billing.expired",
        "channel": "email",
        "variables_schema": {"allowed": ["name", "email"], "required": []},
        "locales": {
            "vi": {
                "subject": "Gói đăng ký đã hết hạn — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Gói đăng ký của bạn đã hết hạn và tài khoản đã trở về gói mặc "
                    "định. Bạn có thể đăng ký lại bất kỳ lúc nào.\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "Your subscription has expired — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "Your subscription has expired and your account reverted to the "
                    "default plan. You can subscribe again anytime.\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        "key": "billing.cancelled",
        "channel": "email",
        "variables_schema": {"allowed": ["name", "email"], "required": []},
        "locales": {
            "vi": {
                "subject": "Gói đăng ký đã được hủy — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Gói đăng ký của bạn đã được hủy và tài khoản đã trở về gói mặc "
                    "định.\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "Your subscription was cancelled — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "Your subscription was cancelled and your account reverted to "
                    "the default plan.\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        "key": "student.weekly_job_digest",
        "channel": "email",
        "variables_schema": {
            "allowed": ["name", "email", "job_count", "job_lines", "url"],
            "required": [],
        },
        "locales": {
            "vi": {
                "subject": "{{job_count}} cơ hội việc làm mới tuần này — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Đây là {{job_count}} cơ hội việc làm mới nhất tuần này trên VinUni Career:\n\n"
                    "{{job_lines}}\n\n"
                    "Xem toàn bộ tin tuyển dụng tại: {{url}}\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "{{job_count}} new opportunities this week — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "Here are the latest {{job_count}} opportunities this week on "
                    "VinUni Career:\n\n"
                    "{{job_lines}}\n\n"
                    "Browse all openings at: {{url}}\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    {
        "key": "job.alert_matches",
        "channel": "email",
        "variables_schema": {
            "allowed": ["alert_name", "match_count", "first_job_title", "url"],
            "required": [],
        },
        "locales": {
            "vi": {
                "subject": "Viec lam moi phu hop voi thong bao {{alert_name}} — VinUni Career",
                "body": (
                    "Chao ban,\n\n"
                    "Co {{match_count}} viec lam moi khop voi thong bao {{alert_name}} cua ban.\n"
                    "Xem ngay tai: {{url}}\n\n"
                    "Tran trong,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "New jobs match your alert {{alert_name}} — VinUni Career",
                "body": (
                    "Hi,\n\n"
                    "{{match_count}} new job(s) match your alert {{alert_name}}.\n"
                    "View them at: {{url}}\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    # ── Onboarding: student email verification ───────────────────────────────
    {
        "key": "account.student_email_verification",
        "channel": "email",
        "variables_schema": {
            "allowed": ["name", "otp_code", "ttl_minutes", "email", "action_url", "token"],
            "required": ["name", "otp_code"],
        },
        "locales": {
            "vi": {
                "subject": "Xác minh email sinh viên của bạn — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Để xác minh tư cách sinh viên, vui lòng nhập mã OTP bên dưới "
                    "vào ứng dụng VinUni Career:\n\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "Mã xác minh sinh viên:\n\n"
                    "  {{otp_code}}\n\n"
                    "━━━━━━━━━━━━━━━━━━━━\n\n"
                    "Mã có hiệu lực trong {{ttl_minutes}} phút.\n"
                    "Nếu bạn không yêu cầu điều này, vui lòng bỏ qua email.\n\n"
                    "Trân trọng,\nVinUni Career Platform"
                ),
            },
            "en": {
                "subject": "Verify your student email — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "To verify your student status, please enter the OTP below in "
                    "the VinUni Career app:\n\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "Student verification code:\n\n"
                    "  {{otp_code}}\n\n"
                    "━━━━━━━━━━━━━━━━━━━━\n\n"
                    "The code is valid for {{ttl_minutes}} minutes.\n"
                    "If you didn't request this, you can safely ignore this email.\n\n"
                    "Best regards,\nVinUni Career Platform"
                ),
            },
        },
    },
    # ── Onboarding: employer application received ────────────────────────────
    {
        "key": "onboarding.employer_application_received",
        "channel": "email",
        "variables_schema": {
            "allowed": ["name", "company_name", "email"],
            "required": ["name", "company_name"],
        },
        "locales": {
            "vi": {
                "subject": "Chúng tôi đã nhận được hồ sơ doanh nghiệp của bạn — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Cảm ơn bạn đã đăng ký tài khoản nhà tuyển dụng cho {{company_name}} "
                    "trên VinUni Career Platform.\n\n"
                    "Hồ sơ của bạn đang được xem xét bởi đội ngũ VinUni Career. "
                    "Thông thường quá trình này mất 1–3 ngày làm việc.\n\n"
                    "Chúng tôi sẽ thông báo cho bạn qua email khi có kết quả.\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "We received your employer application — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "Thank you for registering an employer account for {{company_name}} "
                    "on VinUni Career Platform.\n\n"
                    "Your application is currently under review by the VinUni Career team. "
                    "This typically takes 1–3 business days.\n\n"
                    "We will notify you via email once a decision has been made.\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    # ── Onboarding: employer approved ────────────────────────────────────────
    {
        "key": "onboarding.employer_approved",
        "channel": "email",
        "variables_schema": {
            "allowed": ["name", "company_name", "action_url", "email"],
            "required": ["name", "company_name", "action_url"],
        },
        "locales": {
            "vi": {
                "subject": "Tài khoản nhà tuyển dụng đã được duyệt — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Chúc mừng! Tài khoản nhà tuyển dụng của {{company_name}} đã được "
                    "VinUni Career phê duyệt.\n\n"
                    "Bạn có thể đăng nhập và bắt đầu đăng tin tuyển dụng ngay tại:\n"
                    "{{action_url}}\n\n"
                    "Chúc bạn tìm được ứng viên phù hợp!\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "Your employer account has been approved — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "Congratulations! The employer account for {{company_name}} has been "
                    "approved by VinUni Career.\n\n"
                    "You can log in and start posting jobs at:\n"
                    "{{action_url}}\n\n"
                    "We look forward to helping you find great candidates!\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    # ── Onboarding: employer rejected ────────────────────────────────────────
    {
        "key": "onboarding.employer_rejected",
        "channel": "email",
        "variables_schema": {
            "allowed": ["name", "company_name", "reason", "action_url", "email"],
            "required": ["name", "company_name"],
        },
        "locales": {
            "vi": {
                "subject": "Hồ sơ doanh nghiệp chưa được chấp thuận — VinUni Career",
                "body": (
                    "Chào {{name}},\n\n"
                    "Rất tiếc, hồ sơ đăng ký nhà tuyển dụng của {{company_name}} chưa "
                    "được chấp thuận lần này.\n\n"
                    "Lý do: {{reason}}\n\n"
                    "Bạn có thể cập nhật hồ sơ và nộp lại tại:\n"
                    "{{action_url}}\n\n"
                    "Nếu bạn có thắc mắc, vui lòng liên hệ với chúng tôi qua email "
                    "career@vinuni.edu.vn.\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "Your employer application was not approved — VinUni Career",
                "body": (
                    "Hi {{name}},\n\n"
                    "Unfortunately, the employer registration for {{company_name}} was "
                    "not approved at this time.\n\n"
                    "Reason: {{reason}}\n\n"
                    "You may update your application and resubmit at:\n"
                    "{{action_url}}\n\n"
                    "If you have questions, please contact us at career@vinuni.edu.vn.\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
    # ── Onboarding: welcome job seeker ───────────────────────────────────────
    {
        "key": "onboarding.welcome_job_seeker",
        "channel": "email",
        "variables_schema": {
            "allowed": ["name", "action_url", "email"],
            "required": ["name", "action_url"],
        },
        "locales": {
            "vi": {
                "subject": "Chào mừng đến VinUni Career — Bắt đầu hành trình sự nghiệp!",
                "body": (
                    "Chào {{name}},\n\n"
                    "Chào mừng bạn đến với VinUni Career Platform! 🎉\n\n"
                    "Tài khoản của bạn đã được thiết lập xong. Dưới đây là một vài điều "
                    "bạn có thể làm ngay:\n\n"
                    "  • Hoàn thiện hồ sơ CV của bạn\n"
                    "  • Khám phá các cơ hội việc làm phù hợp\n"
                    "  • Bật thông báo khi có việc làm mới\n\n"
                    "Bắt đầu ngay tại:\n{{action_url}}\n\n"
                    "Chúc bạn thành công!\n\n"
                    "Trân trọng,\nVinUni Career Center"
                ),
            },
            "en": {
                "subject": "Welcome to VinUni Career — Start your journey!",
                "body": (
                    "Hi {{name}},\n\n"
                    "Welcome to VinUni Career Platform! 🎉\n\n"
                    "Your account is all set. Here are a few things you can do right away:\n\n"
                    "  • Complete your CV profile\n"
                    "  • Explore matching job opportunities\n"
                    "  • Enable job alerts for new postings\n\n"
                    "Get started at:\n{{action_url}}\n\n"
                    "Best of luck!\n\n"
                    "Best regards,\nVinUni Career Center"
                ),
            },
        },
    },
]
