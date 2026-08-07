import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "房间设计实验室 | House Design Lab",
  description: "逐房间查看、设计和验收室内空间方案与摄像机轨迹。",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
