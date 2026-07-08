"""Server-side in-app message catalog (vi + en).

This is the bilingual title/body source for the in-app Notification Center feed.
It is deliberately small and product-owned: each ``notif_type`` maps to a friendly
``title`` + ``body`` template per locale plus the notification-preference
``category`` used for in-app channel gating.

Why a code catalog (and not the admin template builder): the in-app feed must
always render a safe, localized title/body even before any org has authored a
template. The later-phase admin template builder (``notification_templates`` with
``channel='in_app'``) can supersede an entry here by key; until then this catalog
is the source of truth (``docs/NOTIFICATIONS_COMMUNICATIONS_SPEC.md`` §4/§7).

Hard rules honored here:
- No provider/model/token/internal codes — only friendly, localized copy.
- No raw PII beyond what the recipient is entitled to. Partner-facing rows use an
  anonymous candidate handle (``applicant_label``), never the student's name/email.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.modules.users.domain.preferences import is_mandatory

DEFAULT_LOCALE = "vi"
_SUPPORTED_LOCALES = frozenset({"vi", "en"})


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    category: str
    title: dict[str, str]
    body: dict[str, str]


# notif_type -> localized title/body + preference category.
CATALOG: dict[str, CatalogEntry] = {
    "recruitment.reveal_requested": CatalogEntry(
        category="application_status",
        title={
            "vi": "Yêu cầu tiết lộ danh tính",
            "en": "Identity reveal requested",
        },
        body={
            "vi": "{company_name} muốn xem thông tin liên hệ của bạn cho đơn ứng "
            "tuyển ẩn danh. Bạn có thể chấp nhận hoặc từ chối.",
            "en": "{company_name} asked to view your contact details for your "
            "anonymous application. You can accept or decline.",
        },
    ),
    "recruitment.reveal_responded": CatalogEntry(
        category="application_status",
        title={
            "vi": "Phản hồi yêu cầu tiết lộ",
            "en": "Reveal request answered",
        },
        body={
            "vi": "Ứng viên đã {decision_label} yêu cầu tiết lộ danh tính của bạn.",
            "en": "The candidate {decision_label} your identity-reveal request.",
        },
    ),
    "recruitment.application_under_review": CatalogEntry(
        category="application_status",
        title={
            "vi": "Hồ sơ của bạn đang được xem xét",
            "en": "Your application is under review",
        },
        body={
            "vi": "Hồ sơ ứng tuyển của bạn đang được nhà tuyển dụng xem xét. "
            "Chúng tôi sẽ thông báo khi có cập nhật mới.",
            "en": "Your application is now being reviewed by the employer. "
            "We'll let you know when there's an update.",
        },
    ),
    "recruitment.application_stage_advanced": CatalogEntry(
        category="application_status",
        title={
            "vi": "Hồ sơ của bạn đã chuyển sang vòng tiếp theo",
            "en": "Your application advanced to the next round",
        },
        body={
            # Neutral + generic (ADR-0004 §4): never carries the internal stage
            # name, required action, or any partner-side code.
            "vi": "Tin tốt! Hồ sơ ứng tuyển của bạn đã được chuyển sang vòng tiếp "
            "theo. Chúng tôi sẽ thông báo khi có cập nhật mới.",
            "en": "Good news! Your application has advanced to the next round. "
            "We'll let you know when there's an update.",
        },
    ),
    "recruitment.application_under_rereview": CatalogEntry(
        category="application_status",
        title={
            "vi": "Hồ sơ của bạn đang được xem xét lại",
            "en": "Your application is being re-reviewed",
        },
        body={
            # Neutral (ADR-0004 §4): the rollback reason is partner-internal and is
            # NEVER surfaced to the student.
            "vi": "Hồ sơ ứng tuyển của bạn đang được nhà tuyển dụng xem xét lại. "
            "Chúng tôi sẽ thông báo khi có cập nhật mới.",
            "en": "Your application is being re-reviewed by the employer. "
            "We'll let you know when there's an update.",
        },
    ),
    "recruitment.application_rejected": CatalogEntry(
        category="application_status",
        title={
            "vi": "Cập nhật hồ sơ ứng tuyển",
            "en": "Application update",
        },
        body={
            "vi": "Hồ sơ ứng tuyển của bạn chưa phù hợp với vị trí này lần này. "
            "Đừng nản lòng — hãy tiếp tục khám phá các cơ hội khác trên VinUni Career.",
            "en": "Your application was not selected for this role this time. "
            "Keep going — explore more opportunities on VinUni Career.",
        },
    ),
    "recruitment.interview_scheduled": CatalogEntry(
        category="interview",
        title={
            "vi": "Bạn có lịch phỏng vấn mới",
            "en": "You have a new interview scheduled",
        },
        body={
            # Identity-safe (to the student about their OWN interview): time + mode
            # only. Never carries assignee identities (PRD §7.6).
            "vi": "Bạn có buổi phỏng vấn cho “{job_title}” vào {scheduled_at} "
            "({mode_label}). Xem chi tiết trong hồ sơ ứng tuyển.",
            "en": "You have an interview for “{job_title}” on {scheduled_at} "
            "({mode_label}). See the details in your application.",
        },
    ),
    "recruitment.interview_rescheduled": CatalogEntry(
        category="interview",
        title={
            "vi": "Lịch phỏng vấn của bạn đã được cập nhật",
            "en": "Your interview was rescheduled",
        },
        body={
            "vi": "Buổi phỏng vấn cho “{job_title}” đã được dời sang {scheduled_at} "
            "({mode_label}). Xem chi tiết trong hồ sơ ứng tuyển.",
            "en": "Your interview for “{job_title}” was moved to {scheduled_at} "
            "({mode_label}). See the details in your application.",
        },
    ),
    "recruitment.interview_cancelled": CatalogEntry(
        category="interview",
        title={
            "vi": "Lịch phỏng vấn của bạn đã bị hủy",
            "en": "Your interview was cancelled",
        },
        body={
            "vi": "Buổi phỏng vấn cho “{job_title}” đã bị hủy. Chúng tôi sẽ thông "
            "báo nếu có lịch mới.",
            "en": "Your interview for “{job_title}” was cancelled. We'll let you "
            "know if a new time is set.",
        },
    ),
    "recruitment.interview_reminder": CatalogEntry(
        category="interview",
        title={
            "vi": "Nhắc lịch phỏng vấn sắp tới",
            "en": "Upcoming interview reminder",
        },
        body={
            "vi": "Nhắc bạn: buổi phỏng vấn cho “{job_title}” diễn ra vào "
            "{scheduled_at} ({mode_label}).",
            "en": "Reminder: your interview for “{job_title}” is on {scheduled_at} "
            "({mode_label}).",
        },
    ),
    "recruitment.interview_assigned": CatalogEntry(
        category="interview",
        title={
            "vi": "Bạn được phân công phỏng vấn",
            "en": "You were assigned to an interview",
        },
        body={
            "vi": "Bạn được phân công phỏng vấn cho “{job_title}” vào {scheduled_at} "
            "({mode_label}).",
            "en": "You were assigned to interview for “{job_title}” on "
            "{scheduled_at} ({mode_label}).",
        },
    ),
    "recruitment.interview_reminder_assignee": CatalogEntry(
        category="interview",
        title={
            "vi": "Nhắc lịch phỏng vấn bạn phụ trách",
            "en": "Reminder: interview you are assigned to",
        },
        body={
            "vi": "Nhắc bạn: buổi phỏng vấn cho “{job_title}” diễn ra vào "
            "{scheduled_at} ({mode_label}).",
            "en": "Reminder: the interview for “{job_title}” is on {scheduled_at} "
            "({mode_label}).",
        },
    ),
    "recruitment.offer_received": CatalogEntry(
        category="application_status",
        title={
            "vi": "Bạn nhận được một thư mời",
            "en": "You received an offer",
        },
        body={
            # NO salary in the body (DATA_MODEL §17) — the student opens the platform
            # to view comp.
            "vi": "{company_name} đã gửi cho bạn thư mời cho vị trí “{position_title}”. "
            "Vui lòng phản hồi trước {expiry_date}. Mở VinUni Career để xem chi tiết.",
            "en": "{company_name} sent you an offer for “{position_title}”. Please "
            "respond by {expiry_date}. Open VinUni Career to view the details.",
        },
    ),
    "recruitment.offer_expiring": CatalogEntry(
        category="application_status",
        title={
            "vi": "Thư mời của bạn sắp hết hạn",
            "en": "Your offer is expiring soon",
        },
        body={
            "vi": "Thư mời cho vị trí “{position_title}” sẽ hết hạn vào {expiry_date}. "
            "Mở VinUni Career để phản hồi.",
            "en": "Your offer for “{position_title}” expires on {expiry_date}. Open "
            "VinUni Career to respond.",
        },
    ),
    "recruitment.offer_expired": CatalogEntry(
        category="application_status",
        title={
            "vi": "Thư mời đã hết hạn",
            "en": "The offer has expired",
        },
        body={
            "vi": "Thư mời cho vị trí “{position_title}” đã hết hạn.",
            "en": "The offer for “{position_title}” has expired.",
        },
    ),
    "recruitment.offer_accepted": CatalogEntry(
        category="application_status",
        title={
            "vi": "Ứng viên đã chấp nhận thư mời",
            "en": "Candidate accepted the offer",
        },
        body={
            # Partner-internal feed; NO salary.
            "vi": "Ứng viên đã chấp nhận thư mời cho vị trí “{position_title}”.",
            "en": "The candidate accepted the offer for “{position_title}”.",
        },
    ),
    "recruitment.offer_declined": CatalogEntry(
        category="application_status",
        title={
            "vi": "Ứng viên đã từ chối thư mời",
            "en": "Candidate declined the offer",
        },
        body={
            # Partner-internal feed; the candidate's reason is shown to the partner only.
            "vi": "Ứng viên đã từ chối thư mời cho vị trí “{position_title}”.",
            "en": "The candidate declined the offer for “{position_title}”.",
        },
    ),
    "recruitment.offer_rescinded": CatalogEntry(
        category="application_status",
        title={
            "vi": "Thư mời đã được thu hồi",
            "en": "The offer was withdrawn",
        },
        body={
            "vi": "Thư mời cho vị trí “{position_title}” đã được thu hồi. Chúng tôi sẽ "
            "thông báo nếu có cập nhật mới.",
            "en": "The offer for “{position_title}” was withdrawn. We'll let you know "
            "if there's an update.",
        },
    ),
    "recruitment.application_received": CatalogEntry(
        category="application_status",
        title={
            "vi": "Hồ sơ ứng tuyển mới",
            "en": "New application received",
        },
        body={
            "vi": "{applicant_label} vừa ứng tuyển vào vị trí “{job_title}”.",
            "en": "{applicant_label} just applied to “{job_title}”.",
        },
    ),
    "recruitment.pipeline_sla_reminder": CatalogEntry(
        category="application_status",
        title={
            "vi": "Nhắc hạn xử lý ứng viên",
            "en": "Candidate review deadline reminder",
        },
        body={
            # Partner-internal (pipeline owner/reviewer). Never carries the
            # student's identity — the reveal handshake stays the only path.
            "vi": "Một ứng viên ở vòng “{stage_name}” cho “{job_title}” "
            "{level_label} hạn xử lý ({deadline_label}). Vui lòng xem xét sớm.",
            "en": "A candidate at the “{stage_name}” stage for “{job_title}” "
            "{level_label} its review deadline ({deadline_label}). Please take "
            "a look soon.",
        },
    ),
    "opportunities.job_approved": CatalogEntry(
        category="job_moderation",
        title={
            "vi": "Tin tuyển dụng đã được duyệt",
            "en": "Job posting approved",
        },
        body={
            "vi": "Tin tuyển dụng “{job_title}” đã được duyệt và hiển thị công khai.",
            "en": "Your job posting “{job_title}” was approved and is now live.",
        },
    ),
    "opportunities.job_rejected": CatalogEntry(
        category="job_moderation",
        title={
            "vi": "Tin tuyển dụng chưa được duyệt",
            "en": "Job posting needs changes",
        },
        body={
            "vi": "Tin tuyển dụng “{job_title}” chưa được duyệt. Lý do: {reason}",
            "en": "Your job posting “{job_title}” was not approved. Reason: {reason}",
        },
    ),
    "opportunities.job_auto_closed": CatalogEntry(
        category="job_moderation",
        title={
            "vi": "Tin tuyển dụng đã đóng",
            "en": "Job posting closed",
        },
        body={
            "vi": "Tin tuyển dụng “{job_title}” đã tự động đóng do hết hạn nộp hồ sơ.",
            "en": "Your job posting “{job_title}” was automatically closed because "
            "its application deadline passed.",
        },
    ),
    "opportunities.event_registration_confirmed": CatalogEntry(
        category="event",
        title={
            "vi": "Đăng ký sự kiện thành công",
            "en": "Event registration confirmed",
        },
        body={
            "vi": "Bạn đã đăng ký thành công sự kiện “{event_title}”. Xem trong "
            "“Sự kiện của tôi”.",
            "en": "You're registered for “{event_title}”. See it under “My events”.",
        },
    ),
    "opportunities.event_waitlisted": CatalogEntry(
        category="event",
        title={
            "vi": "Bạn đang ở danh sách chờ",
            "en": "You're on the waitlist",
        },
        body={
            "vi": "Sự kiện “{event_title}” đã đầy. Bạn đang ở vị trí "
            "#{waitlist_position} trong danh sách chờ.",
            "en": "“{event_title}” is full. You're #{waitlist_position} on the "
            "waitlist.",
        },
    ),
    "opportunities.event_waitlist_promoted": CatalogEntry(
        category="event",
        title={
            "vi": "Bạn đã có chỗ tham dự",
            "en": "A seat opened up",
        },
        body={
            "vi": "Một chỗ vừa trống — bạn đã được xác nhận tham dự sự kiện "
            "“{event_title}”.",
            "en": "A seat opened up — you're now registered for “{event_title}”.",
        },
    ),
    "opportunities.saved_job_deadline": CatalogEntry(
        # Student re-engagement (spec §3: "Job deadline reminders and saved-job
        # closure"). PII-safe: job title + deadline only, no other-candidate data.
        category="job_deadline",
        title={
            "vi": "Công việc bạn đã lưu sắp hết hạn nộp hồ sơ",
            "en": "A job you saved is closing soon",
        },
        body={
            "vi": "“{job_title}” bạn đã lưu sẽ hết hạn nhận hồ sơ vào {deadline_label}. "
            "Ứng tuyển trước khi hết hạn để không bỏ lỡ cơ hội.",
            "en": "“{job_title}” that you saved closes for applications on "
            "{deadline_label}. Apply before the deadline so you don't miss out.",
        },
    ),
    "opportunities.event_reminder": CatalogEntry(
        category="event",
        title={
            "vi": "Nhắc lịch sự kiện sắp diễn ra",
            "en": "Upcoming event reminder",
        },
        body={
            "vi": "Nhắc bạn: sự kiện “{event_title}” sẽ sớm diễn ra. Mở VinUni "
            "Career để xem chi tiết.",
            "en": "Reminder: “{event_title}” is coming up soon. Open VinUni Career "
            "for the details.",
        },
    ),
    "opportunities.event_reminder_soon": CatalogEntry(
        category="event",
        title={
            "vi": "Sự kiện bắt đầu trong 1 giờ",
            "en": "Event starts in 1 hour",
        },
        body={
            "vi": "Sự kiện “{event_title}” sắp bắt đầu trong khoảng 1 giờ nữa.",
            "en": "“{event_title}” starts in about 1 hour.",
        },
    ),
    "opportunities.event_cancelled": CatalogEntry(
        category="event",
        title={
            "vi": "Sự kiện đã bị hủy",
            "en": "Event cancelled",
        },
        body={
            "vi": "Ban tổ chức đã hủy sự kiện “{event_title}”. Chúng tôi xin lỗi vì "
            "sự bất tiện này.",
            "en": "The organizer has cancelled “{event_title}”. We're sorry for the "
            "inconvenience.",
        },
    ),
    "opportunities.event_approved": CatalogEntry(
        category="event",
        title={
            "vi": "Sự kiện đã được duyệt",
            "en": "Event approved",
        },
        body={
            "vi": "Sự kiện “{event_title}” đã được duyệt và hiển thị công khai.",
            "en": "Your event “{event_title}” was approved and is now live.",
        },
    ),
    "opportunities.event_rejected": CatalogEntry(
        category="event",
        title={
            "vi": "Sự kiện chưa được duyệt",
            "en": "Event needs changes",
        },
        body={
            "vi": "Sự kiện “{event_title}” chưa được duyệt. Lý do: {reason}",
            "en": "Your event “{event_title}” was not approved. Reason: {reason}",
        },
    ),
    "advertising.approved": CatalogEntry(
        category="advertising",
        title={
            "vi": "Yêu cầu quảng cáo đã được duyệt",
            "en": "Advertising request approved",
        },
        body={
            "vi": "Yêu cầu quảng cáo của bạn đã được duyệt. Chiến dịch sẽ chạy "
            "trong khoảng thời gian đã đặt sau khi thanh toán được ghi nhận.",
            "en": "Your advertising request was approved. The campaign will run in "
            "its scheduled window once payment is recorded.",
        },
    ),
    "advertising.rejected": CatalogEntry(
        category="advertising",
        title={
            "vi": "Yêu cầu quảng cáo chưa được duyệt",
            "en": "Advertising request needs changes",
        },
        body={
            "vi": "Yêu cầu quảng cáo của bạn chưa được duyệt. Lý do: {reason}",
            "en": "Your advertising request was not approved. Reason: {reason}",
        },
    ),
    "advertising.payment_recorded": CatalogEntry(
        category="advertising",
        title={
            "vi": "Đã ghi nhận thanh toán quảng cáo",
            "en": "Advertising payment recorded",
        },
        body={
            "vi": "Chúng tôi đã ghi nhận thanh toán cho chiến dịch quảng cáo của "
            "bạn. Chiến dịch sẽ chạy đúng khung thời gian đã đặt.",
            "en": "We've recorded the payment for your advertising campaign. It "
            "will run in its scheduled window.",
        },
    ),
    "advertising.live": CatalogEntry(
        category="advertising",
        title={
            "vi": "Chiến dịch quảng cáo đang chạy",
            "en": "Advertising campaign is live",
        },
        body={
            "vi": "Chiến dịch quảng cáo của bạn đang chạy. Nội dung được tài trợ "
            "luôn hiển thị kèm nhãn công khai bắt buộc.",
            "en": "Your advertising campaign is now live. Sponsored content always "
            "carries the mandatory public disclosure label.",
        },
    ),
    "advertising.ending": CatalogEntry(
        category="advertising",
        title={
            "vi": "Chiến dịch quảng cáo sắp kết thúc",
            "en": "Advertising campaign ending soon",
        },
        body={
            "vi": "Chiến dịch quảng cáo của bạn sẽ kết thúc trong vòng 24 giờ tới.",
            "en": "Your advertising campaign will end within the next 24 hours.",
        },
    ),
    "billing.payment_recorded": CatalogEntry(
        category="billing",
        title={
            "vi": "Đã ghi nhận thanh toán gói đăng ký",
            "en": "Subscription payment recorded",
        },
        body={
            # No amount / payment reference in the body (PII-safe; admin-only spend).
            "vi": "Chúng tôi đã ghi nhận thanh toán cho gói đăng ký của bạn. Gói "
            "dịch vụ của bạn đã được kích hoạt.",
            "en": "We've recorded the payment for your subscription. Your plan is "
            "now active.",
        },
    ),
    "billing.active": CatalogEntry(
        category="billing",
        title={
            "vi": "Gói đăng ký đang hiệu lực",
            "en": "Your subscription is active",
        },
        body={
            "vi": "Gói đăng ký của bạn đã được kích hoạt. Bạn có thể xem quyền lợi "
            "và ngày hết hạn trong mục Gói dịch vụ.",
            "en": "Your subscription is now active. You can see what it grants and "
            "its expiry under Billing.",
        },
    ),
    "billing.expiring": CatalogEntry(
        category="billing",
        title={
            "vi": "Gói đăng ký sắp hết hạn",
            "en": "Your subscription is expiring soon",
        },
        body={
            "vi": "Gói đăng ký của bạn sẽ hết hạn trong vòng 7 ngày tới. Hãy gia "
            "hạn để giữ các quyền lợi nâng cao.",
            "en": "Your subscription will expire within the next 7 days. Renew to "
            "keep your upgraded benefits.",
        },
    ),
    "billing.expired": CatalogEntry(
        category="billing",
        title={
            "vi": "Gói đăng ký đã hết hạn",
            "en": "Your subscription has expired",
        },
        body={
            "vi": "Gói đăng ký của bạn đã hết hạn. Tài khoản của bạn đã trở về gói "
            "mặc định. Bạn có thể đăng ký lại bất kỳ lúc nào.",
            "en": "Your subscription has expired. Your account reverted to the "
            "default plan. You can subscribe again anytime.",
        },
    ),
    "billing.cancelled": CatalogEntry(
        category="billing",
        title={
            "vi": "Gói đăng ký đã được hủy",
            "en": "Your subscription was cancelled",
        },
        body={
            "vi": "Gói đăng ký của bạn đã được hủy. Tài khoản của bạn đã trở về gói "
            "mặc định.",
            "en": "Your subscription was cancelled. Your account reverted to the "
            "default plan.",
        },
    ),
    "message.received": CatalogEntry(
        category="message",
        title={
            "vi": "Bạn có tin nhắn mới",
            "en": "You have a new message",
        },
        body={
            # PII-safe (ADR-0012 §4): a MASKED sender label + a neutral "new message"
            # only — NEVER the message body, never the anonymous student's identity.
            "vi": "{sender_label} đã gửi cho bạn một tin nhắn mới. Mở VinUni Career "
            "để xem.",
            "en": "{sender_label} sent you a new message. Open VinUni Career to read "
            "it.",
        },
    ),
    "message.flagged": CatalogEntry(
        category="message",
        title={
            "vi": "Một cuộc trò chuyện đã được báo cáo",
            "en": "A conversation was reported",
        },
        body={
            # Moderation alert to university staff; no content, just a review prompt.
            "vi": "Một người dùng đã báo cáo một cuộc trò chuyện. Vui lòng xem xét.",
            "en": "A user reported a conversation. Please review it.",
        },
    ),
    "organization.partner_approved": CatalogEntry(
        category="application_lifecycle",
        title={
            "vi": "Tài khoản đối tác đã được duyệt",
            "en": "Partner account approved",
        },
        body={
            "vi": "Đăng ký đối tác của {company_name} đã được duyệt. Hãy kích hoạt "
            "tài khoản để bắt đầu.",
            "en": "The partner registration for {company_name} was approved. "
            "Activate your account to get started.",
        },
    ),
    "organization.partner_rejected": CatalogEntry(
        category="application_lifecycle",
        title={
            "vi": "Đăng ký đối tác chưa được duyệt",
            "en": "Partner registration declined",
        },
        body={
            "vi": "Đăng ký đối tác của {company_name} chưa được duyệt. Lý do: {reason}",
            "en": "The partner registration for {company_name} was declined. "
            "Reason: {reason}",
        },
    ),
    "recruitment.job_invitation_received": CatalogEntry(
        category="application_lifecycle",
        title={
            "vi": "Bạn được mời ứng tuyển",
            "en": "You've been invited to apply",
        },
        body={
            "vi": "{company_name} mời bạn ứng tuyển vào vị trí {job_title}.",
            "en": "{company_name} invited you to apply for {job_title}.",
        },
    ),
    "recruitment.job_invitation_accepted": CatalogEntry(
        category="application_lifecycle",
        title={
            "vi": "Ứng viên đã chấp nhận lời mời",
            "en": "Candidate accepted your invitation",
        },
        body={
            "vi": "Một ứng viên đã chấp nhận lời mời ứng tuyển vị trí {job_title}.",
            "en": "A candidate accepted your invitation to apply for {job_title}.",
        },
    ),
}


class _SafeDict(dict):
    """``str.format_map`` helper: unknown placeholders render as empty strings.

    Keeps a missing variable from raising and from leaking a raw ``{placeholder}``
    token into user-facing copy.
    """

    def __missing__(self, key: str) -> str:  # noqa: D401
        return ""


def normalize_locale(locale: str | None) -> str:
    return locale if locale in _SUPPORTED_LOCALES else DEFAULT_LOCALE


def category_for(notif_type: str) -> str | None:
    entry = CATALOG.get(notif_type)
    return entry.category if entry else None


def is_mandatory_type(notif_type: str) -> bool:
    category = category_for(notif_type)
    return bool(category and is_mandatory(category))


def render(
    notif_type: str, *, locale: str | None, variables: dict[str, object] | None
) -> tuple[str, str]:
    """Return ``(title, body)`` for ``notif_type`` in the requested locale.

    Falls back to the default locale, then to the notif_type itself only if no
    entry exists at all (defensive — every wired event has a catalog entry).
    """

    loc = normalize_locale(locale)
    entry = CATALOG.get(notif_type)
    if entry is None:
        # Should never happen for wired events; never expose a raw enum as copy.
        return (notif_type, "")
    safe_vars = _SafeDict({k: ("" if v is None else str(v)) for k, v in (variables or {}).items()})
    title = entry.title.get(loc, entry.title[DEFAULT_LOCALE])
    body = entry.body.get(loc, entry.body[DEFAULT_LOCALE])
    return (title.format_map(safe_vars), body.format_map(safe_vars))
