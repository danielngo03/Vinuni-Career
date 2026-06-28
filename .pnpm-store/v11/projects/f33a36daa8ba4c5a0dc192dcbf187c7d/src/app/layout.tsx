import type { Metadata } from "next";
import { Toaster } from "sonner";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "VinUni Career Platform",
    template: "%s · VinUni Career",
  },
  description:
    "Nền tảng kết nối sinh viên, doanh nghiệp và nhà trường bằng dữ liệu và AI có trách nhiệm.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="vi" suppressHydrationWarning>
      <body>
        {children}
        <Toaster richColors position="top-right" />
      </body>
    </html>
  );
}
