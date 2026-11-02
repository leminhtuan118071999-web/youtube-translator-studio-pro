import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { SignOutButton } from "./sign-out-button";
import { MigrationCheck } from "./migration-check";

const modules = [
  { icon: "🌍", title: "YouTube Translator", description: "Lấy phụ đề, dịch thuật và chuyển thành lời kể audio.", status: "Đang xây dựng" },
  { icon: "✍️", title: "YouTube SEO", description: "Tiêu đề, mô tả, tags và tối ưu nội dung.", status: "Đang xây dựng" },
  { icon: "🎬", title: "Video Form Studio", description: "Tự phân tích và tạo form video 8 giây.", status: "Đang xây dựng" },
  { icon: "🧑‍🎨", title: "Character Studio", description: "Hồ sơ nhân vật, ảnh tham chiếu và continuity.", status: "Đang xây dựng" },
  { icon: "⚙️", title: "Task Manager", description: "Hàng đợi nền, checkpoint và tự khôi phục.", status: "Đang xây dựng" },
  { icon: "🔑", title: "AI Providers", description: "Quản lý nhà cung cấp và cấu hình API an toàn.", status: "Đang xây dựng" },
];

export default async function DashboardPage() {
  const supabase = await createClient();
  const { data, error } = await supabase.auth.getClaims();

  if (error || !data?.claims?.sub) redirect("/login");

  const email = typeof data.claims.email === "string" ? data.claims.email : "Tài khoản đã đăng nhập";
  const uid = String(data.claims.sub);

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand"><span>🎬</span><strong>LMT Studio Pro</strong><small>V2</small></div>
        <div className="nav-label">WORKSPACE</div>
        <a className="nav-item active" href="/dashboard">◫ <span>Tổng quan</span></a>
        <div className="nav-label">STUDIO</div>
        {modules.map((item) => <div className="nav-item disabled" key={item.title}>{item.icon} <span>{item.title}</span></div>)}
        <div className="sidebar-footer">
          <span className="online-dot" /> V2 Foundation
        </div>
      </aside>

      <section className="main-area">
        <header className="topbar">
          <div><span className="eyebrow">WORKSPACE / OVERVIEW</span><h1>Dashboard</h1></div>
          <div className="account-menu"><div><strong>{email}</strong><span>UID: {uid.slice(0, 8)}…</span></div><SignOutButton /></div>
        </header>

        <section className="welcome-panel">
          <div>
            <p className="eyebrow">AI VIDEO & STORYTELLING STUDIO</p>
            <h2>Chào mừng trở lại.</h2>
            <p className="muted">Nền tảng sản xuất nội dung của bạn đang được xây dựng lại trên kiến trúc V2.</p>
          </div>
          <div className="welcome-icon">✦</div>
        </section>

        <MigrationCheck />

        <div className="section-heading"><div><h2>Không gian sáng tạo</h2><p className="muted">Các phân hệ sẽ được mở dần sau khi hoàn tất kiểm thử.</p></div><span className="status-pill">Foundation</span></div>
        <section className="module-grid">
          {modules.map((item) => (
            <article className="module-card" key={item.title}>
              <div className="module-icon">{item.icon}</div>
              <h3>{item.title}</h3>
              <p>{item.description}</p>
              <span className="module-status">{item.status}</span>
            </article>
          ))}
        </section>
      </section>
    </main>
  );
}
