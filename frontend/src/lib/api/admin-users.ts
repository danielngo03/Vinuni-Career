import { api } from "./client";

export interface AdminUserRow {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  email_verified: boolean;
  persona: string;
  org_id: string | null;
  created_at: string | null;
}

export interface AdminUsersPage {
  items: AdminUserRow[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface AdminUsersParams {
  persona?: string;
  q?: string;
  page?: number;
  page_size?: number;
}

export const adminUsersApi = {
  listUsers(params: AdminUsersParams = {}): Promise<AdminUsersPage> {
    const search = new URLSearchParams();
    if (params.persona) search.set("persona", params.persona);
    if (params.q) search.set("q", params.q);
    if (params.page) search.set("page", String(params.page));
    if (params.page_size) search.set("page_size", String(params.page_size));
    const qs = search.toString();
    return api.get(`/admin/users${qs ? `?${qs}` : ""}`);
  },

  suspendUser(userId: string): Promise<{ id: string; is_active: boolean }> {
    return api.post(`/admin/users/${userId}/suspend`, {});
  },

  unsuspendUser(userId: string): Promise<{ id: string; is_active: boolean }> {
    return api.post(`/admin/users/${userId}/unsuspend`, {});
  },
};
