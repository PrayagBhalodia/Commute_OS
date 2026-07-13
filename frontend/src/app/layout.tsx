import type { Metadata } from "next";
import { Geist } from "next/font/google";
import "./globals.css";
import { AppSidebar } from "@/components/layout/AppSidebar";
import { MobileNavigation } from "@/components/layout/MobileNavigation";
import { TopHeader } from "@/components/layout/TopHeader";
import { Providers } from "./providers";

const geist = Geist({ subsets: ["latin"], variable: "--font-geist-sans" });

export const metadata: Metadata = {
  title: "Commute OS",
  description: "AI-first Journey Operating System prototype",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={geist.variable}>
        <Providers>
          <div className="min-h-screen lg:flex">
            <AppSidebar />
            <div className="min-w-0 flex-1 pb-16 lg:pb-0">
              <TopHeader />
              <main className="mx-auto w-full max-w-7xl px-4 py-6 lg:px-8">{children}</main>
            </div>
            <MobileNavigation />
          </div>
        </Providers>
      </body>
    </html>
  );
}
