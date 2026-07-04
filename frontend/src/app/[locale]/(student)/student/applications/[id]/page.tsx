import { StudentApplicationDetail } from "@/components/applications/student-application-detail";

export default async function StudentApplicationDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <StudentApplicationDetail id={id} />;
}
