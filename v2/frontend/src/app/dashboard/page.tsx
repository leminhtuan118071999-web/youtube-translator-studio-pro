import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { Studio } from "./studio";

export default async function DashboardPage() {
  const supabase = await createClient();
  const { data, error } = await supabase.auth.getClaims();
  if (error || !data?.claims?.sub) redirect("/login");
  return <Studio email={typeof data.claims.email === "string" ? data.claims.email : "Đã đăng nhập"} />;
}
