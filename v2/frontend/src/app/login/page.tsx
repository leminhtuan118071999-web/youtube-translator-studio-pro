"use client";

import { type FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "signup" | "forgot">("login");
  const [message, setMessage] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(""); setMessage("");
    setLoading(true);

    try {
      const supabase = createClient();
      if (mode === "forgot") {
        const { error } = await supabase.auth.resetPasswordForEmail(email.trim(), {
          redirectTo: `${window.location.origin}/auth/callback?next=/reset-password`,
        });
        if (error) throw error;
        setMessage("Nếu email đã đăng ký, bạn sẽ nhận được liên kết đặt lại mật khẩu.");
        return;
      }
      if (mode === "signup") {
        const { data, error } = await supabase.auth.signUp({ email: email.trim(), password,
          options: { emailRedirectTo: `${window.location.origin}/auth/callback` },
        });
        if (error) throw error;
        if (!data.session) { setMessage("Hãy kiểm tra email để xác nhận tài khoản."); return; }
      } else {
        const { error } = await supabase.auth.signInWithPassword({ email: email.trim(), password });
        if (error) throw error;
      }

      router.replace("/dashboard");
      router.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Đăng nhập không thành công.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-wrap">
      <section className="auth-card">
        <div className="brand-mark">🎬</div>
        <p className="eyebrow">LMT CREATIVE WORKSPACE</p>
        <h1>LMT Studio Pro</h1>
        <p className="muted">Đăng nhập bằng tài khoản hiện tại của bạn.</p>

        <form onSubmit={handleSubmit} className="auth-form">
          <label htmlFor="email">Email</label>
          <input id="email" type="email" autoComplete="username" value={email}
            onChange={(event) => setEmail(event.target.value)} required />

          {mode !== "forgot" && <><label htmlFor="password">Mật khẩu</label>
          <input id="password" type="password" autoComplete="current-password" value={password}
            onChange={(event) => setPassword(event.target.value)} required minLength={mode === "signup" ? 8 : 1} /></>}

          {error && <p className="error-message" role="alert">{error}</p>}

          <button className="primary-button" type="submit" disabled={loading}>
            {loading ? "Đang xử lý..." : mode === "login" ? "Đăng nhập" : mode === "signup" ? "Tạo tài khoản" : "Gửi liên kết khôi phục"}
          </button>
        </form>
        {message && <p className="status-good" role="status">{message}</p>}
        <div className="toolbar">{(["login", "signup", "forgot"] as const).filter(m => m !== mode).map(m => <button className="ghost-button" disabled={loading} key={m} onClick={() => { setMode(m); setError(""); setMessage(""); }}>{m === "login" ? "Đăng nhập" : m === "signup" ? "Tạo tài khoản" : "Quên mật khẩu"}</button>)}</div>
        <p className="fine-print">V2 sử dụng cùng Supabase Auth; không tạo tài khoản trùng lặp.</p>
      </section>
    </main>
  );
}
