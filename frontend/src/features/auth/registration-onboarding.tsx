"use client";

import {
  ArrowLeft,
  ArrowRight,
  Buildings,
  CheckCircle,
  FileArrowUp,
  GraduationCap,
  SpinnerGap,
} from "@phosphor-icons/react";
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

type RegistrationKind = "student" | "partner";
type ReferenceData = {
  universities: Array<{ id: string; name: string }>;
  majors: Array<{
    id: string;
    university_org_id: string;
    code: string;
    name: string;
  }>;
  industries: Array<{
    id: string;
    university_org_id: string;
    name_vi: string;
    name_en: string;
  }>;
};

const initialData = {
  fullName: "",
  email: "",
  password: "",
  passwordConfirmation: "",
  universityOrgId: "",
  studentCode: "",
  majorId: "",
  degreeLevel: "BACHELOR",
  enrollmentYear: String(new Date().getFullYear()),
  graduationYear: String(new Date().getFullYear() + 4),
  phone: "",
  companyName: "",
  taxCode: "",
  website: "",
  companySize: "11-50",
  foundedYear: "",
  headquarters: "",
  description: "",
  representativeName: "",
  representativeTitle: "",
  representativePhone: "",
  representativeEmail: "",
  industryIds: [] as string[],
  primaryIndustryId: "",
};

export function RegistrationOnboarding({
  locale,
  onComplete,
}: {
  locale: string;
  onComplete: (email: string) => void;
}) {
  const vi = locale === "vi";
  const [kind, setKind] = useState<RegistrationKind>("student");
  const [step, setStep] = useState(0);
  const [data, setData] = useState(initialData);
  const [reference, setReference] = useState<ReferenceData | null>(null);
  const [logo, setLogo] = useState<File | null>(null);
  const [license, setLicense] = useState<File | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [applicationId, setApplicationId] = useState("");

  useEffect(() => {
    fetch("/api/registrations/reference")
      .then(async (response) => {
        if (!response.ok) throw new Error("Reference data unavailable");
        return (await response.json()) as ReferenceData;
      })
      .then((body) => {
        setReference(body);
        if (body.universities[0]) {
          setData((current) => ({
            ...current,
            universityOrgId: current.universityOrgId || body.universities[0].id,
          }));
        }
      })
      .catch(() =>
        setError(
          vi
            ? "Không thể tải danh mục đăng ký. Vui lòng thử lại."
            : "Unable to load registration reference data.",
        ),
      );
  }, [vi]);

  const totalSteps = kind === "student" ? 3 : 4;
  const majors = useMemo(
    () =>
      reference?.majors.filter(
        (item) => item.university_org_id === data.universityOrgId,
      ) || [],
    [reference, data.universityOrgId],
  );
  const industries = useMemo(
    () =>
      reference?.industries.filter(
        (item) => item.university_org_id === data.universityOrgId,
      ) || [],
    [reference, data.universityOrgId],
  );

  function update<K extends keyof typeof initialData>(
    key: K,
    value: (typeof initialData)[K],
  ) {
    setData((current) => ({ ...current, [key]: value }));
    setError("");
  }

  function changeKind(nextKind: RegistrationKind) {
    setKind(nextKind);
    setStep(0);
    setError("");
    setApplicationId("");
  }

  function validateCurrentStep() {
    if (step === 0) {
      if (
        !data.fullName.trim() ||
        !data.email.includes("@") ||
        data.password.length < 8 ||
        data.password !== data.passwordConfirmation ||
        !data.universityOrgId
      ) {
        setError(
          vi
            ? "Vui lòng hoàn tất thông tin tài khoản và kiểm tra lại mật khẩu."
            : "Complete the account information and verify your passwords.",
        );
        return false;
      }
    }
    if (
      kind === "student" &&
      step === 1 &&
      (!data.studentCode || !data.majorId || !data.phone)
    ) {
      setError(
        vi
          ? "Vui lòng hoàn tất thông tin sinh viên."
          : "Complete the student information.",
      );
      return false;
    }
    if (
      kind === "partner" &&
      step === 1 &&
      (!data.companyName ||
        !data.taxCode ||
        !data.headquarters ||
        data.description.length < 20)
    ) {
      setError(
        vi
          ? "Vui lòng hoàn tất hồ sơ pháp nhân doanh nghiệp."
          : "Complete the company legal profile.",
      );
      return false;
    }
    if (
      kind === "partner" &&
      step === 2 &&
      (!data.representativeName ||
        !data.representativeTitle ||
        !data.representativePhone ||
        !data.representativeEmail ||
        !data.industryIds.length ||
        !data.primaryIndustryId ||
        !logo ||
        !license)
    ) {
      setError(
        vi
          ? "Vui lòng chọn ngành nghề, người đại diện và tải đủ hồ sơ."
          : "Choose industries, provide a representative, and upload both documents.",
      );
      return false;
    }
    return true;
  }

  async function submit() {
    if (!validateCurrentStep()) return;
    setPending(true);
    setError("");
    try {
      let response: Response;
      if (kind === "student") {
        response = await fetch("/api/registrations/student", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            university_org_id: data.universityOrgId,
            full_name: data.fullName,
            email: data.email,
            password: data.password,
            student_code: data.studentCode,
            major_id: data.majorId,
            degree_level: data.degreeLevel,
            enrollment_year: Number(data.enrollmentYear),
            expected_graduation_year: Number(data.graduationYear),
            phone_number: data.phone,
          }),
        });
      } else {
        const form = new FormData();
        const values: Record<string, string> = {
          university_org_id: data.universityOrgId,
          full_name: data.fullName,
          email: data.email,
          password: data.password,
          company_name: data.companyName,
          tax_code: data.taxCode,
          website: data.website,
          company_size: data.companySize,
          founded_year: data.foundedYear,
          headquarters_address: data.headquarters,
          company_description: data.description,
          representative_name: data.representativeName,
          representative_title: data.representativeTitle,
          representative_phone: data.representativePhone,
          representative_email: data.representativeEmail,
          industry_ids_json: JSON.stringify(data.industryIds),
          primary_industry_id: data.primaryIndustryId,
        };
        Object.entries(values).forEach(([key, value]) => {
          if (value) form.set(key, value);
        });
        form.set("logo", logo as File);
        form.set("business_license", license as File);
        response = await fetch("/api/registrations/partner", {
          method: "POST",
          body: form,
        });
      }
      const body = (await response.json()) as {
        id?: string;
        detail?: string;
        error?: { message?: string };
      };
      if (!response.ok) {
        throw new Error(
          body.detail ||
            body.error?.message ||
            (vi ? "Không thể gửi hồ sơ." : "Unable to submit the application."),
        );
      }
      setApplicationId(body.id || "");
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : vi
            ? "Không thể gửi hồ sơ."
            : "Unable to submit the application.",
      );
    } finally {
      setPending(false);
    }
  }

  if (applicationId) {
    return (
      <div className="py-3 text-center">
        <div className="mx-auto flex size-14 items-center justify-center rounded-full bg-emerald-50 text-emerald-600">
          <CheckCircle className="size-8" weight="fill" />
        </div>
        <h3 className="mt-5 text-xl font-semibold">
          {vi ? "Hồ sơ đã được gửi" : "Application submitted"}
        </h3>
        <p className="mx-auto mt-3 max-w-sm text-sm leading-6 text-muted">
          {vi
            ? "Nhà trường sẽ xác minh thông tin và gửi kết quả qua email. Bạn chỉ có thể truy cập workspace sau khi hồ sơ được duyệt."
            : "The university will verify your information and email the result. Workspace access starts only after approval."}
        </p>
        <p className="mt-4 rounded-xl bg-slate-50 px-4 py-3 font-mono text-xs text-slate-600">
          {vi ? "Mã hồ sơ" : "Application ID"}: {applicationId}
        </p>
        <Button
          type="button"
          variant="outline"
          className="mt-6 rounded-xl"
          onClick={() => onComplete(data.email)}
        >
          {vi ? "Quay lại đăng nhập" : "Return to sign in"}
        </Button>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-6 grid grid-cols-2 gap-3">
        <KindButton
          active={kind === "student"}
          icon={GraduationCap}
          title={vi ? "Sinh viên" : "Student"}
          description={vi ? "Xác minh hồ sơ học tập" : "Verify academic identity"}
          onClick={() => changeKind("student")}
        />
        <KindButton
          active={kind === "partner"}
          icon={Buildings}
          title={vi ? "Doanh nghiệp" : "Employer"}
          description={vi ? "Xác minh pháp nhân" : "Verify legal entity"}
          onClick={() => changeKind("partner")}
        />
      </div>

      <div className="mb-6 flex items-center gap-2">
        {Array.from({ length: totalSteps }, (_, index) => (
          <div
            key={index}
            className={cn(
              "h-1.5 flex-1 rounded-full",
              index <= step ? "bg-primary" : "bg-slate-200",
            )}
          />
        ))}
        <span className="ml-2 text-xs font-semibold text-muted">
          {step + 1}/{totalSteps}
        </span>
      </div>

      <div className="space-y-4">
        {step === 0 ? (
          <AccountStep
            vi={vi}
            data={data}
            universities={reference?.universities || []}
            update={update}
          />
        ) : null}
        {kind === "student" && step === 1 ? (
          <StudentStep vi={vi} data={data} majors={majors} update={update} />
        ) : null}
        {kind === "partner" && step === 1 ? (
          <CompanyStep vi={vi} data={data} update={update} />
        ) : null}
        {kind === "partner" && step === 2 ? (
          <PartnerVerificationStep
            vi={vi}
            data={data}
            industries={industries}
            update={update}
            logo={logo}
            license={license}
            setLogo={setLogo}
            setLicense={setLicense}
          />
        ) : null}
        {(kind === "student" && step === 2) ||
        (kind === "partner" && step === 3) ? (
          <ReviewStep vi={vi} kind={kind} data={data} />
        ) : null}
      </div>

      {error ? (
        <div className="mt-5 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      ) : null}

      <div className="mt-6 flex gap-3">
        {step > 0 ? (
          <Button
            type="button"
            variant="outline"
            className="rounded-xl"
            onClick={() => {
              setStep((current) => current - 1);
              setError("");
            }}
          >
            <ArrowLeft className="size-4" />
            {vi ? "Quay lại" : "Back"}
          </Button>
        ) : null}
        <Button
          type="button"
          className="ml-auto rounded-xl"
          disabled={pending || !reference}
          onClick={() => {
            if (!validateCurrentStep()) return;
            if (step === totalSteps - 1) {
              void submit();
            } else {
              setStep((current) => current + 1);
            }
          }}
        >
          {pending ? (
            <SpinnerGap className="size-4 animate-spin" />
          ) : step === totalSteps - 1 ? (
            <FileArrowUp className="size-4" />
          ) : (
            <ArrowRight className="size-4" />
          )}
          {step === totalSteps - 1
            ? vi
              ? "Gửi hồ sơ xét duyệt"
              : "Submit for review"
            : vi
              ? "Tiếp tục"
              : "Continue"}
        </Button>
      </div>
    </div>
  );
}

function KindButton({
  active,
  icon: Icon,
  title,
  description,
  onClick,
}: {
  active: boolean;
  icon: typeof GraduationCap;
  title: string;
  description: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "focus-ring cursor-pointer rounded-xl border p-3 text-left transition-colors",
        active
          ? "border-primary bg-blue-50 text-primary"
          : "hover:border-blue-200 hover:bg-slate-50",
      )}
    >
      <Icon className="size-5" weight={active ? "fill" : "regular"} />
      <p className="mt-2 text-sm font-semibold">{title}</p>
      <p className="mt-0.5 text-xs text-muted">{description}</p>
    </button>
  );
}

type Data = typeof initialData;
type Update = <K extends keyof Data>(key: K, value: Data[K]) => void;

function AccountStep({
  vi,
  data,
  universities,
  update,
}: {
  vi: boolean;
  data: Data;
  universities: ReferenceData["universities"];
  update: Update;
}) {
  return (
    <>
      <SectionTitle
        title={vi ? "Thông tin tài khoản" : "Account information"}
        description={
          vi
            ? "Email này sẽ nhận thông báo kết quả xét duyệt."
            : "Approval updates will be sent to this email."
        }
      />
      <TextField label={vi ? "Họ và tên" : "Full name"}>
        <Input value={data.fullName} onChange={(e) => update("fullName", e.target.value)} />
      </TextField>
      <TextField label="Email">
        <Input
          type="email"
          value={data.email}
          onChange={(e) => update("email", e.target.value)}
        />
      </TextField>
      <div className="grid gap-4 sm:grid-cols-2">
        <TextField label={vi ? "Mật khẩu" : "Password"}>
          <Input
            type="password"
            value={data.password}
            onChange={(e) => update("password", e.target.value)}
          />
        </TextField>
        <TextField label={vi ? "Xác nhận mật khẩu" : "Confirm password"}>
          <Input
            type="password"
            value={data.passwordConfirmation}
            onChange={(e) => update("passwordConfirmation", e.target.value)}
          />
        </TextField>
      </div>
      <TextField label={vi ? "Đơn vị xét duyệt" : "Reviewing university"}>
        <Select
          value={data.universityOrgId}
          onChange={(value) => {
            update("universityOrgId", value);
            update("majorId", "");
            update("industryIds", []);
            update("primaryIndustryId", "");
          }}
          options={universities.map((item) => ({ value: item.id, label: item.name }))}
        />
      </TextField>
    </>
  );
}

function StudentStep({
  vi,
  data,
  majors,
  update,
}: {
  vi: boolean;
  data: Data;
  majors: ReferenceData["majors"];
  update: Update;
}) {
  return (
    <>
      <SectionTitle
        title={vi ? "Thông tin sinh viên" : "Student information"}
        description={
          vi
            ? "Nhà trường sẽ đối chiếu với dữ liệu đào tạo."
            : "The university will match this against academic records."
        }
      />
      <div className="grid gap-4 sm:grid-cols-2">
        <TextField label={vi ? "Mã sinh viên" : "Student ID"}>
          <Input
            value={data.studentCode}
            onChange={(e) => update("studentCode", e.target.value)}
          />
        </TextField>
        <TextField label={vi ? "Số điện thoại" : "Phone number"}>
          <Input value={data.phone} onChange={(e) => update("phone", e.target.value)} />
        </TextField>
      </div>
      <TextField label={vi ? "Ngành học" : "Major"}>
        <Select
          value={data.majorId}
          onChange={(value) => update("majorId", value)}
          options={majors.map((item) => ({
            value: item.id,
            label: `${item.code} · ${item.name}`,
          }))}
          placeholder={vi ? "Chọn ngành học" : "Select a major"}
        />
      </TextField>
      <TextField label={vi ? "Bậc đào tạo" : "Degree level"}>
        <Select
          value={data.degreeLevel}
          onChange={(value) => update("degreeLevel", value)}
          options={[
            { value: "BACHELOR", label: vi ? "Cử nhân" : "Bachelor" },
            { value: "MASTER", label: vi ? "Thạc sĩ" : "Master" },
            { value: "PHD", label: vi ? "Tiến sĩ" : "PhD" },
            { value: "MD", label: "MD" },
          ]}
        />
      </TextField>
      <div className="grid gap-4 sm:grid-cols-2">
        <TextField label={vi ? "Năm nhập học" : "Enrollment year"}>
          <Input
            type="number"
            value={data.enrollmentYear}
            onChange={(e) => update("enrollmentYear", e.target.value)}
          />
        </TextField>
        <TextField label={vi ? "Năm tốt nghiệp dự kiến" : "Expected graduation"}>
          <Input
            type="number"
            value={data.graduationYear}
            onChange={(e) => update("graduationYear", e.target.value)}
          />
        </TextField>
      </div>
    </>
  );
}

function CompanyStep({ vi, data, update }: { vi: boolean; data: Data; update: Update }) {
  return (
    <>
      <SectionTitle
        title={vi ? "Hồ sơ doanh nghiệp" : "Company profile"}
        description={
          vi
            ? "Thông tin pháp nhân phải trùng với giấy đăng ký kinh doanh."
            : "Legal information must match the business registration."
        }
      />
      <TextField label={vi ? "Tên pháp lý doanh nghiệp" : "Legal company name"}>
        <Input
          value={data.companyName}
          onChange={(e) => update("companyName", e.target.value)}
        />
      </TextField>
      <div className="grid gap-4 sm:grid-cols-2">
        <TextField label={vi ? "Mã số thuế" : "Tax code"}>
          <Input value={data.taxCode} onChange={(e) => update("taxCode", e.target.value)} />
        </TextField>
        <TextField label={vi ? "Năm thành lập" : "Founded year"}>
          <Input
            type="number"
            value={data.foundedYear}
            onChange={(e) => update("foundedYear", e.target.value)}
          />
        </TextField>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <TextField label="Website">
          <Input
            type="url"
            value={data.website}
            onChange={(e) => update("website", e.target.value)}
          />
        </TextField>
        <TextField label={vi ? "Quy mô nhân sự" : "Company size"}>
          <Select
            value={data.companySize}
            onChange={(value) => update("companySize", value)}
            options={["1-10", "11-50", "51-200", "201-500", "501-1000", "1000+"].map(
              (value) => ({ value, label: value }),
            )}
          />
        </TextField>
      </div>
      <TextField label={vi ? "Địa chỉ trụ sở" : "Headquarters address"}>
        <Input
          value={data.headquarters}
          onChange={(e) => update("headquarters", e.target.value)}
        />
      </TextField>
      <TextField label={vi ? "Giới thiệu doanh nghiệp" : "Company description"}>
        <textarea
          value={data.description}
          onChange={(e) => update("description", e.target.value)}
          rows={3}
          className="focus-ring w-full rounded-xl border bg-white px-3 py-2.5 text-sm"
        />
      </TextField>
    </>
  );
}

function PartnerVerificationStep({
  vi,
  data,
  industries,
  update,
  logo,
  license,
  setLogo,
  setLicense,
}: {
  vi: boolean;
  data: Data;
  industries: ReferenceData["industries"];
  update: Update;
  logo: File | null;
  license: File | null;
  setLogo: (file: File | null) => void;
  setLicense: (file: File | null) => void;
}) {
  return (
    <>
      <SectionTitle
        title={vi ? "Người đại diện và xác minh" : "Representative and verification"}
        description={
          vi
            ? "Chỉ ngành nghề do nhà trường quản trị mới có thể được lựa chọn."
            : "Only university-managed industries can be selected."
        }
      />
      <div className="grid gap-4 sm:grid-cols-2">
        <TextField label={vi ? "Người đại diện" : "Representative name"}>
          <Input
            value={data.representativeName}
            onChange={(e) => update("representativeName", e.target.value)}
          />
        </TextField>
        <TextField label={vi ? "Chức danh" : "Job title"}>
          <Input
            value={data.representativeTitle}
            onChange={(e) => update("representativeTitle", e.target.value)}
          />
        </TextField>
        <TextField label={vi ? "Email người đại diện" : "Representative email"}>
          <Input
            type="email"
            value={data.representativeEmail}
            onChange={(e) => update("representativeEmail", e.target.value)}
          />
        </TextField>
        <TextField label={vi ? "Điện thoại" : "Phone"}>
          <Input
            value={data.representativePhone}
            onChange={(e) => update("representativePhone", e.target.value)}
          />
        </TextField>
      </div>
      <TextField label={vi ? "Ngành nghề hoạt động" : "Business industries"}>
        <div className="grid max-h-36 grid-cols-2 gap-2 overflow-y-auto rounded-xl border p-3">
          {industries.map((industry) => {
            const selected = data.industryIds.includes(industry.id);
            return (
              <label
                key={industry.id}
                className={cn(
                  "flex cursor-pointer items-center gap-2 rounded-lg px-2 py-2 text-xs",
                  selected ? "bg-blue-50 text-primary" : "hover:bg-slate-50",
                )}
              >
                <input
                  type="checkbox"
                  checked={selected}
                  onChange={() => {
                    const next = selected
                      ? data.industryIds.filter((id) => id !== industry.id)
                      : [...data.industryIds, industry.id];
                    update("industryIds", next);
                    if (selected && data.primaryIndustryId === industry.id) {
                      update("primaryIndustryId", "");
                    }
                  }}
                />
                {vi ? industry.name_vi : industry.name_en}
              </label>
            );
          })}
        </div>
      </TextField>
      <TextField label={vi ? "Ngành nghề chính" : "Primary industry"}>
        <Select
          value={data.primaryIndustryId}
          onChange={(value) => update("primaryIndustryId", value)}
          options={industries
            .filter((item) => data.industryIds.includes(item.id))
            .map((item) => ({
              value: item.id,
              label: vi ? item.name_vi : item.name_en,
            }))}
          placeholder={vi ? "Chọn ngành nghề chính" : "Select primary industry"}
        />
      </TextField>
      <div className="grid gap-4 sm:grid-cols-2">
        <FileField
          label={vi ? "Logo doanh nghiệp" : "Company logo"}
          accept="image/png,image/jpeg,image/webp"
          file={logo}
          onChange={setLogo}
        />
        <FileField
          label={vi ? "Giấy đăng ký kinh doanh" : "Business registration"}
          accept="application/pdf,image/png,image/jpeg"
          file={license}
          onChange={setLicense}
        />
      </div>
    </>
  );
}

function ReviewStep({
  vi,
  kind,
  data,
}: {
  vi: boolean;
  kind: RegistrationKind;
  data: Data;
}) {
  return (
    <>
      <SectionTitle
        title={vi ? "Kiểm tra và gửi hồ sơ" : "Review and submit"}
        description={
          vi
            ? "Hồ sơ sẽ được chuyển tới nhà trường để xác minh thủ công."
            : "The application will be sent to the university for manual verification."
        }
      />
      <div className="space-y-3 rounded-xl bg-slate-50 p-4 text-sm">
        <ReviewRow label={vi ? "Loại tài khoản" : "Account type"} value={kind} />
        <ReviewRow label={vi ? "Người đăng ký" : "Applicant"} value={data.fullName} />
        <ReviewRow label="Email" value={data.email} />
        <ReviewRow
          label={kind === "student" ? (vi ? "Mã sinh viên" : "Student ID") : vi ? "Doanh nghiệp" : "Company"}
          value={kind === "student" ? data.studentCode : data.companyName}
        />
      </div>
      <p className="text-xs leading-5 text-muted">
        {vi
          ? "Bằng việc gửi hồ sơ, bạn xác nhận thông tin là chính xác và đồng ý để nhà trường đối chiếu các tài liệu đã cung cấp."
          : "By submitting, you confirm the information is accurate and authorize the university to verify the provided documents."}
      </p>
    </>
  );
}

function SectionTitle({ title, description }: { title: string; description: string }) {
  return (
    <div className="mb-2">
      <h3 className="text-base font-semibold">{title}</h3>
      <p className="mt-1 text-xs leading-5 text-muted">{description}</p>
    </div>
  );
}

function TextField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-2 block text-sm font-semibold">{label}</span>
      {children}
    </label>
  );
}

function Select({
  value,
  onChange,
  options,
  placeholder,
}: {
  value: string;
  onChange: (value: string) => void;
  options: Array<{ value: string; label: string }>;
  placeholder?: string;
}) {
  return (
    <select
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className="focus-ring h-11 w-full rounded-xl border bg-white px-3 text-sm"
    >
      {placeholder ? <option value="">{placeholder}</option> : null}
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}

function FileField({
  label,
  accept,
  file,
  onChange,
}: {
  label: string;
  accept: string;
  file: File | null;
  onChange: (file: File | null) => void;
}) {
  return (
    <label className="focus-ring flex cursor-pointer flex-col items-center rounded-xl border border-dashed p-4 text-center hover:bg-slate-50">
      <FileArrowUp className="size-6 text-primary" />
      <span className="mt-2 text-xs font-semibold">{label}</span>
      <span className="mt-1 max-w-full truncate text-[11px] text-muted">
        {file?.name || "PDF, PNG, JPG · max 5MB"}
      </span>
      <input
        type="file"
        accept={accept}
        className="sr-only"
        onChange={(event) => onChange(event.target.files?.[0] || null)}
      />
    </label>
  );
}

function ReviewRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-muted">{label}</span>
      <span className="text-right font-semibold">{value}</span>
    </div>
  );
}
