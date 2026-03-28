import type { Metadata } from "next";
import Link from "next/link";
import { withAuth } from "@workos-inc/authkit-nextjs";
import { SessionProvider } from "@/components/session-provider";
import { SignOutButton } from "@/components/sign-out-button";
import { OpsQueueBadge } from "@/components/ops-queue-badge";
import "./globals.css";

export const metadata: Metadata = {
  title: "OmniDrop AI",
  description: "AI-powered document ingestion and analytics",
};

const navItems = [
  { href: "/dashboard/c-suite", label: "Revenue Recovery" },
  { href: "/dashboard/ops", label: "Ops Queue" },
  { href: "/search", label: "Search" },
  { href: "/settings", label: "Settings" },
];

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user, organizationId } = await withAuth();

  const sessionUser = user
    ? {
        id: user.id,
        email: user.email,
        firstName: user.firstName ?? null,
        lastName: user.lastName ?? null,
        workosOrgId: organizationId ?? null,
        orgName: null,
      }
    : null;

  return (
    <html lang="en" suppressHydrationWarning>
      <body suppressHydrationWarning className="min-h-screen bg-gray-50">
        <SessionProvider user={sessionUser}>
          <nav className="border-b bg-white">
            <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3">
              <Link href="/dashboard" className="text-lg font-bold text-gray-900">
                OmniDrop AI
              </Link>
              <div className="flex items-center gap-6">
                {navItems.map((item) => (
                  <Link
                    key={item.href}
                    href={item.href}
                    className="inline-flex items-center text-sm text-gray-600 hover:text-gray-900"
                  >
                    {item.label}
                    {item.href === "/dashboard/ops" && <OpsQueueBadge />}
                  </Link>
                ))}
                <SignOutButton />
              </div>
            </div>
          </nav>
          <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
        </SessionProvider>
      </body>
    </html>
  );
}
