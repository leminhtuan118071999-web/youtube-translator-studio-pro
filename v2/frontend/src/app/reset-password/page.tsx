"use client";
import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";

export default function ResetPassword() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError("");
    try {
      const { error } = await createClient().auth.updateUser({ password });
      if (error) throw error;
      router.replace("/dashboard"); router.refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "Không đổi được mật khẩu."); }
    finally { setBusy(false); }
  }
  return <main className="auth-wrap"><section className="auth-card"><h1>Đặt mật khẩu mới</h1><form className="auth-form" onSubmit={submit}><label htmlFor="new-password">Mật khẩu mới</label><input id="new-password" type="password" autoComplete="new-password" minLength={8} required value={password} onChange={e => setPassword(e.target.value)} />{error && <p role="alert" className="error-message">{error}</p>}<button disabled={busy} className="primary-button">Lưu mật khẩu</button></form></section></main>;
}
