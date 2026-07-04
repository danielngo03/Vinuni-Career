import { api, apiUpload } from "./client";

export type OnboardingRole = "job_seeker" | "employer";
export type SeekerType = "student" | "professional" | "fresh_graduate";
export type OnboardingStep =
  | "role_select"
  | "seeker_type"
  | "seeker_profile"
  | "student_verify"
  | "employer_info"
  | "employer_docs"
  | "pending"
  | "complete";

export type AiDocStatus = "pending" | "passed" | "tampered" | "manual_review";
export type EmployerRequestStatus = "pending_review" | "approved" | "rejected";

export interface OnboardingStatus {
  current_step: OnboardingStep;
  role: OnboardingRole | null;
  seeker_type: SeekerType | null;
  is_complete: boolean;
  email_verified: boolean;
  student_verification_status: string | null;
  employer_doc_status: AiDocStatus | null;
  employer_request_status: EmployerRequestStatus | null;
}

export interface SeekerProfilePayload {
  // Professional
  title?: string;
  company?: string;
  industry?: string;
  years_experience?: number;
  // Fresh graduate
  university?: string;
  major?: string;
  graduation_year?: number;
}

export const onboardingApi = {
  getStatus(): Promise<OnboardingStatus> {
    return api.get<OnboardingStatus>("/onboarding/status");
  },

  setRole(role: OnboardingRole): Promise<{ current_step: OnboardingStep; role: OnboardingRole }> {
    return api.post("/onboarding/role", { role });
  },

  setSeekerType(seeker_type: SeekerType): Promise<{ current_step: OnboardingStep; seeker_type: SeekerType }> {
    return api.post("/onboarding/seeker-type", { seeker_type });
  },

  saveSeekerProfile(data: SeekerProfilePayload): Promise<{ current_step: OnboardingStep; is_complete: boolean }> {
    return api.post("/onboarding/seeker-profile", data);
  },

  requestStudentVerify(data: {
    university_name: string;
    student_id_number: string;
    student_email: string;
  }): Promise<{ status: string; student_email: string }> {
    return api.post("/onboarding/student-verify/request", data);
  },

  confirmStudentVerify(data: {
    otp_code: string;
    id_card_image?: File | null;
  }): Promise<{ current_step: OnboardingStep }> {
    const form = new FormData();
    form.append("otp_code", data.otp_code);
    if (data.id_card_image) {
      form.append("id_card_image", data.id_card_image);
    }
    return apiUpload("/onboarding/student-verify/confirm", form);
  },

  saveEmployerInfo(data: {
    company_name: string;
    industry?: string;
    company_size?: string;
    address?: string;
    registrant_role?: string;
  }): Promise<{ current_step: OnboardingStep }> {
    return api.post("/onboarding/employer-info", data);
  },

  submitEmployerDocs(data: {
    document: File;
    tax_id?: string;
  }): Promise<{ status: string; ai_doc_status: AiDocStatus }> {
    const form = new FormData();
    form.append("document", data.document);
    if (data.tax_id) form.append("tax_id", data.tax_id);
    return apiUpload("/onboarding/employer-docs", form);
  },

  getEmployerDocStatus(): Promise<{
    ai_doc_status: AiDocStatus;
    request_status: EmployerRequestStatus;
    tax_id_verified: boolean;
  }> {
    return api.get("/onboarding/employer-docs/status");
  },
};
