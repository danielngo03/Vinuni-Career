import { api } from "./client";

export type InvitationStatus = "pending" | "accepted" | "declined" | "expired";

export interface JobInvitation {
  id: string;
  job_id: string;
  job_title: string;
  company_name: string;
  message: string | null;
  status: InvitationStatus;
  expires_at: string;
  responded_at: string | null;
  created_at: string;
}

export interface InviteRespondResult extends JobInvitation {
  apply_url?: string;
}

export interface SendInviteBody {
  student_id: string;
  message?: string;
}

export const invitationsApi = {
  /** Student: list own job invitations. */
  listMine(params: { status?: string } = {}): Promise<JobInvitation[]> {
    const qs = new URLSearchParams();
    if (params.status) qs.set("status", params.status);
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return api.get<JobInvitation[]>(`/student/invitations${suffix}`);
  },

  /** Student: get a single invitation. */
  getOne(invitationId: string): Promise<JobInvitation> {
    return api.get<JobInvitation>(`/student/invitations/${invitationId}`);
  },

  /** Student: respond to an invitation (accepted | declined). */
  respond(
    invitationId: string,
    response: "accepted" | "declined",
  ): Promise<InviteRespondResult> {
    return api.post<InviteRespondResult>(
      `/invitations/${invitationId}/respond`,
      { response },
    );
  },

  /** Partner: invite a student to apply to a specific job. */
  sendToStudent(jobId: string, body: SendInviteBody): Promise<JobInvitation> {
    return api.post<JobInvitation>(`/jobs/${jobId}/invitations`, body);
  },
};
