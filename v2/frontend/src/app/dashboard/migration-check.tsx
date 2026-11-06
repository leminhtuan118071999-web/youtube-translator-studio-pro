"use client";

import { useState } from "react";
import { createClient } from "@/lib/supabase/client";

type MigrationReport = {
  legacy_state_found?: boolean;
  ready_for_import?: boolean;
  session_count?: number;
  saved_session_count?: number;
  provider_setting_count?: number;
  sessions_with_character_image_manifest?: number;
  sessions_with_video_forms?: number;
  encryption_verified?: boolean;
  errors?: string[];
  warnings?: string[];
  message?: string;
};

export function MigrationCheck() {
  const [report, setReport] = useState<MigrationReport | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function runDryRun() {
    setLoading(true);
    setError("");
    setReport(null);

    try {
      const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "");
      if (!baseUrl) throw new Error("Chưa cấu hình địa chỉ V2 API.");

      const supabase = createClient();
      const { data, error: sessionError } = await supabase.auth.getSession();
      if (sessionError) throw sessionError;
      const token = data.session?.access_token;
      if (!token) throw new Error("Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại.");

      const response = await fetch(`${baseUrl}/v1/migration/legacy/dry-run`, {
        method: "GET",
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });

      const body = await response.json();
      if (!response.ok) {
        throw new Error(typeof body.detail === "string" ? body.detail : "Không thể kiểm tra dữ liệu V1.");
      }
      setReport(body as MigrationReport);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Không thể kết nối máy chủ V2.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="migration-panel" aria-live="polite">
      <div className="migration-copy">
        <p className="eyebrow">DATA CONTINUITY</p>
        <h2>Kiểm tra dữ liệu V1</h2>
        <p className="muted">Kiểm tra số phiên và khả năng giải mã cấu hình API trước khi chuyển dữ liệu. Thao tác này chỉ đọc, không thay đổi V1.</p>
      </div>
      <button className="secondary-button" onClick={runDryRun} disabled={loading}>
        {loading ? "Đang kiểm tra..." : "Chạy kiểm tra tương thích"}
      </button>

      {error && <p className="error-message migration-message" role="alert">{error}</p>}

      {report && (
        <div className="migration-result">
          <div className="migration-result-head">
            <strong>{report.legacy_state_found ? "Đã tìm thấy dữ liệu V1" : "Không có bản ghi V1"}</strong>
            <span className={report.ready_for_import ? "status-good" : "status-warning"}>
              {report.ready_for_import ? "Đạt kiểm tra sơ bộ" : "Chưa đủ điều kiện chuyển"}
            </span>
          </div>
          <div className="migration-stats">
            <div><strong>{report.session_count ?? 0}</strong><span>Phiên làm việc</span></div>
            <div><strong>{report.saved_session_count ?? 0}</strong><span>Phiên đã lưu</span></div>
            <div><strong>{report.provider_setting_count ?? 0}</strong><span>Thiết lập API</span></div>
            <div><strong>{report.sessions_with_character_image_manifest ?? 0}</strong><span>Phiên có manifest ảnh</span></div>
          </div>
          <p className="migration-encryption">
            Mã hóa API: <strong>{report.encryption_verified ? "Đã xác minh" : "Chưa xác minh"}</strong>
          </p>
          {report.errors?.length ? <p className="error-message migration-message">Lỗi kiểm tra: {report.errors.join(", ")}</p> : null}
          {report.warnings?.length ? <p className="muted migration-message">Cảnh báo: {report.warnings.join(", ")}</p> : null}
          {report.message && <p className="muted migration-message">{report.message}</p>}
        </div>
      )}
    </section>
  );
}
