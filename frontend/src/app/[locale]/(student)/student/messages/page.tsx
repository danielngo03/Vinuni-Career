import { MessagingScreen } from "@/components/messaging/messaging-screen";

export default async function StudentMessagesPage({
  searchParams,
}: {
  searchParams: Promise<{ thread?: string }>;
}) {
  const { thread } = await searchParams;
  return <MessagingScreen initialThreadId={thread} />;
}
