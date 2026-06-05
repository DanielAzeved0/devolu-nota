import { ProtectedLayout } from "@/components/protected-layout";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return <ProtectedLayout>{children}</ProtectedLayout>;
}
