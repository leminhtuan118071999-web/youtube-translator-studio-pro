"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { autoTranslationReady } from "@/lib/auto-translation";
import { createClient } from "@/lib/supabase/client";
import { SignOutButton } from "./sign-out-button";

type Data = Record<string, unknown>;
type Session = { id: string; name: string; revision: number; status: string; data: Data; updated_at: string };
type Summary = Omit<Session, "data">;
type Job = { id: string; session_id: string | null; job_type: string; status: string; progress: number; stage: string; error: string; attempts: number };
type Provider = { base_url: string; model: string; kind: string; auth?: string };
type Config = { values: Record<string, string>; configured_keys: string[]; version: number };
const tabs = ["Nội dung", "Lời kể", "YouTube SEO", "Tác vụ", "Cấu hình API", "AI33"];
const languages = [
  "Tiếng Ba Lan",
  "Tiếng Anh",
  "Tiếng Pháp",
  "Tiếng Đức",
  "Tiếng Tây Ban Nha",
  "Tiếng Ý",
  "Tiếng Bồ Đào Nha",
  "Tiếng Hà Lan",
  "Tiếng Thụy Điển",
  "Tiếng Na Uy",
  "Tiếng Đan Mạch",
  "Tiếng Phần Lan",
  "Tiếng Iceland",
  "Tiếng Séc",
  "Tiếng Slovakia",
  "Tiếng Hungary",
  "Tiếng Romania",
  "Tiếng Bulgaria",
  "Tiếng Hy Lạp",
  "Tiếng Croatia",
  "Tiếng Serbia",
  "Tiếng Slovenia",
  "Tiếng Bosnia",
  "Tiếng Albania",
  "Tiếng Lithuania",
  "Tiếng Latvia",
  "Tiếng Estonia",
  "Tiếng Ukraine",
  "Tiếng Nga",
  "Tiếng Belarus",
  "Tiếng Thổ Nhĩ Kỳ",
  "Tiếng Ireland",
  "Tiếng Malta",
  "Tiếng Catalan",
  "Tiếng Basque",
  "Tiếng Wales",
  "Tiếng Luxembourg",
  "Tiếng Macedonia",
  "Tiếng Việt",
  "Tiếng Nhật",
  "Tiếng Hàn"
].map(value => ({ label: value, value }));
const active = (job: Job) => ["queued", "running", "retry_wait"].includes(job.status);
const jobNames: Record<string, string> = { full: "Dịch lời kể và SEO", translation: "Dịch lời kể và SEO", seo: "Dịch tiêu đề, mô tả và tạo tag", forms: "Tạo form 8 giây", characters: "Tạo hồ sơ nhân vật", images: "Tạo ảnh tham chiếu" };
const statusNames: Record<string, string> = { queued: "Đang chờ", running: "Đang xử lý", retry_wait: "Đang chờ thử lại", succeeded: "Hoàn thành", completed: "Hoàn thành", failed: "Có lỗi", cancelled: "Đã hủy", draft: "Bản nháp", ready: "Sẵn sàng", processing: "Đang xử lý", interrupted: "Đã gián đoạn" };
const jobPercent = (job: Job) => Math.max(0, Math.min(100, Math.round(job.progress)));
const latestJob = (jobs: Job[], sid: string) => jobs.find(j => j.session_id === sid && active(j)) ?? jobs.find(j => j.session_id === sid);
const str = (value: unknown) => typeof value === "string" ? value : "";

async function api<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "");
  if (!base) throw new Error("Chưa cấu hình địa chỉ V2 API.");
  const { data } = await createClient().auth.getSession();
  if (!data.session) throw new Error("Phiên đăng nhập hết hạn. Hãy đăng nhập lại.");
  const response = await fetch(base + "/v1" + path, {
    method, cache: "no-store", headers: { Authorization: `Bearer ${data.session.access_token}`, "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (response.status === 204) return undefined as T;
  const result = await response.json();
  if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "Yêu cầu chưa thành công. Kiểm tra dữ liệu hoặc kết nối máy chủ.");
  return result as T;
}

export function Studio({ email }: { email: string }) {
  const [sessions, setSessions] = useState<Summary[]>([]);
  const [selected, setSelected] = useState<Session | null>(null);
  const [draft, setDraft] = useState<Data>({});
  const [name, setName] = useState("");
  const [dirty, setDirty] = useState(false);
  const [autoTranslation, setAutoTranslation] = useState<{ sid: string; language: string } | null>(null);
  const dirtyRef = useRef(false);
  const selectedRef = useRef<string | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [healthy, setHealthy] = useState(false);
  const [tab, setTab] = useState("Nội dung");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [providers, setProviders] = useState<Record<string, Provider>>({});
  const [config, setConfig] = useState<Config>({ values: {}, configured_keys: [], version: 0 });
  const [changes, setChanges] = useState<Record<string, string>>({});
  const [models, setModels] = useState<string[]>([]);
  const request = useRef<{ key: string; id: string } | null>(null);
  const sessionCache = useRef(new Map<string, Session>());
  const refreshing = useRef<Promise<void> | null>(null);
  const busyRef = useRef(false);
  const activeJobsRef = useRef(false);

  function accept(session: Session) {
    sessionCache.current.set(session.id, session);
    setAutoTranslation(null);
    selectedRef.current = session.id;
    setSelected(session); setDraft(session.data); setName(session.name);
    dirtyRef.current = false; setDirty(false);
  }
  const refresh = useCallback((): Promise<void> => {
    if (refreshing.current) return refreshing.current;
    const sid = selectedRef.current;
    const cached = sid ? sessionCache.current.get(sid) : undefined;
    const query = sid ? `?sid=${sid}&revision=${cached?.revision ?? -1}` : "";
    const task = api<{ sessions: Summary[]; jobs: Job[]; healthy: boolean; selected: Session | null }>(`/dashboard${query}`).then(result => {
      setSessions(result.sessions); setJobs(result.jobs); setHealthy(result.healthy);
      activeJobsRef.current = result.jobs.some(active);
      if (result.selected && sid === selectedRef.current && !dirtyRef.current
          && result.selected.revision >= (sessionCache.current.get(sid!)?.revision ?? -1)) {
        sessionCache.current.set(result.selected.id, result.selected);
        setSelected(result.selected); setDraft(result.selected.data); setName(result.selected.name);
      }
    }).finally(() => { refreshing.current = null; });
    refreshing.current = task;
    return task;
  }, []);
  useEffect(() => {
    let mounted = true;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try { if (!document.hidden) await refresh(); }
      catch (e) { if (mounted) setError(e instanceof Error ? e.message : "Không tải được dữ liệu."); }
      if (mounted) timer = setTimeout(poll, document.hidden ? 60000 : activeJobsRef.current ? 5000 : 15000);
    }
    void poll();
    void Promise.all([api<Record<string, Provider>>("/providers"), api<Config>("/settings")])
      .then(([p, c]) => { if (mounted) { setProviders(p); setConfig(c); } })
      .catch(e => { if (mounted) setError(e.message); });
    const visible = () => { if (!document.hidden) { clearTimeout(timer); void poll(); } };
    document.addEventListener("visibilitychange", visible);
    return () => { mounted = false; clearTimeout(timer); document.removeEventListener("visibilitychange", visible); };
  }, [refresh]);
  useEffect(() => {
    const protect = (e: BeforeUnloadEvent) => { if (dirtyRef.current) e.preventDefault(); };
    window.addEventListener("beforeunload", protect);
    return () => window.removeEventListener("beforeunload", protect);
  }, []);

  async function action(task: () => Promise<void>) {
    if (busyRef.current) return;
    busyRef.current = true; setBusy(true); setError(""); setNotice("");
    try { await task(); } catch (e) { setError(e instanceof Error ? e.message : "Không thực hiện được yêu cầu."); }
    finally { busyRef.current = false; setBusy(false); }
  }
  function change(key: string, value: unknown) {
    setDraft(old => key === "url" && old.url !== value
      ? { ...old, url: value, source: "", title: "", description: "" }
      : { ...old, [key]: value }); dirtyRef.current = true; setDirty(true);
  }
  async function open(sid: string) {
    if (dirtyRef.current) { setError("Hãy lưu thay đổi trước khi chuyển phiên."); return; }
    selectedRef.current = sid;
    const cached = sessionCache.current.get(sid);
    if (cached) { accept(cached); void refresh().catch(e => setError(e.message)); return; }
    const row = await api<Session>(`/sessions/${sid}?view=studio`);
    if (selectedRef.current === sid) accept(row);
  }
  async function save(): Promise<Session> {
    if (!selected) throw new Error("Hãy chọn hoặc tạo phiên.");
    if (!dirtyRef.current) return selected;
    const payload = {
      name, revision: selected.revision,
      source: str(draft.source), url: str(draft.url), title: str(draft.title), description: str(draft.description),
      language: str(draft.language) || "Tiếng Việt", style: str(draft.style) || "Hoạt hình 2D",
      duration_seconds: typeof draft.duration_seconds === "number" ? draft.duration_seconds : null,
      translated: str(draft.translated),
    };
    const row = await api<Session>(`/sessions/${selected.id}`, "PUT", payload);
    accept(row); return row;
  }
  async function run(kind: string) {
    const row = await save();
    const key = `${row.id}:${row.revision}:${kind}`;
    if (request.current?.key !== key) request.current = { key, id: crypto.randomUUID() };
    await api(`/sessions/${row.id}/jobs`, "POST", { kind, revision: row.revision, request_id: request.current.id });
    request.current = null;
    setNotice(`Đã giao tác vụ: ${jobNames[kind] || kind}. Các bước khác chỉ chạy khi bạn yêu cầu.`); await refresh();
  }
  async function editArtifact(field: string, value: string, extra: Record<string, unknown> = {}) {
    if (!selected) return;
    const row = await save();
    accept(await api<Session>(`/sessions/${row.id}/artifact`, "PUT", { field, value, revision: row.revision, ...extra }));
    await refresh(); setNotice("Đã lưu nội dung chỉnh sửa.");
  }
  async function download(format: string) {
    if (!selected) return;
    const { data } = await createClient().auth.getSession();
    const endpoint = format === "jpg" ? "thumbnail" : format === "zip" ? "images.zip" : `export?format=${format}`;
    const response = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/v1/sessions/${selected.id}/${endpoint}`, { headers: { Authorization: `Bearer ${data.session?.access_token}` } });
    if (!response.ok) throw new Error("Chưa xuất được nội dung. Kiểm tra form hoặc kết nối.");
    const url = URL.createObjectURL(await response.blob());
    const a = document.createElement("a"); a.href = url; a.download = `lmt-${selected.id}.${format}`; a.click(); URL.revokeObjectURL(url);
  }
  const provider = changes.api_provider ?? config.values.api_provider ?? "Groq";
  const pref = (key: string, fallback = "") => changes[key] ?? config.values[key] ?? fallback;
  const setPref = (key: string, value: string) => setChanges(old => ({ ...old, [key]: value }));
  const selectedJob = selected ? latestJob(jobs, selected.id) : undefined;
  const running = selectedJob ? active(selectedJob) : false;
  useEffect(() => {
    if (!autoTranslationReady({ request: autoTranslation, sessionId: selected?.id, language: draft.language,
      url: str(draft.url), busy, running, healthy })) return;
    const timer = setTimeout(() => {
      setAutoTranslation(null);
      void action(async () => { await run("full"); setTab("Lời kể"); });
    }, 700);
    return () => clearTimeout(timer);
  }, [autoTranslation, selected?.id, selected?.revision, draft, name, busy, running, healthy]);
  const stale = (key: string) => draft[key] === true ? <p className="status-warning">Nội dung này được tạo từ đầu vào cũ. Hãy tạo lại để khớp với phiên hiện tại.</p> : null;
  const generate = (label: string, kind: string) => <button className="primary-button" disabled={busy || !selected || running || !healthy} onClick={() => void action(() => run(kind))}>{label}</button>;

  return <main className="app-shell studio-shell">
    <aside className="sidebar">
      <div className="sidebar-brand"><span>🎬</span><strong>LMT Studio Pro</strong><small>V2</small></div>
      <button className="primary-button" disabled={busy || dirty} onClick={() => void action(async () => {
        accept(await api<Session>("/sessions", "POST", {})); setTab("Nội dung"); await refresh();
      })}>＋ Phiên mới</button>
      <button className="ghost-button danger" disabled={busy || !sessions.length} onClick={() => void action(async () => {
        if (!window.confirm("Xóa TẤT CẢ phiên V2 của tài khoản, của tài khoản? Các tác vụ đang chạy sẽ bị hủy; nội dung chưa lưu cũng bị xóa. Không thể hoàn tác từ ứng dụng.")) return;
        setAutoTranslation(null);
        await api("/sessions", "DELETE");
        selectedRef.current = null; dirtyRef.current = false; request.current = null;
        setSelected(null); setDraft({}); setName(""); setDirty(false); sessionCache.current.clear();
        await refresh(); setNotice("Đã xóa tất cả phiên V2 và hủy tác vụ liên quan.");
      })}>Xóa tất cả phiên</button>
      <div className="session-list">{sessions.map(s => {
        const job = latestJob(jobs, s.id);
        return <button disabled={busy} className={`session-item ${selected?.id === s.id ? "active" : ""}`} key={s.id} onClick={() => void action(() => open(s.id))}>
          <span>◫ {s.name}</span>
          <small>{job ? `${statusNames[job.status] || job.status} · ${jobPercent(job)}%` : statusNames[s.status] || s.status}</small>
          {job && <><small>{jobNames[job.job_type] || job.job_type}</small><progress aria-label={`Tiến trình phiên ${s.name}`} value={jobPercent(job)} max={100} /><small className="session-stage" title={job.error || job.stage}>{job.error || job.stage}</small></>}
        </button>;
      })}{!sessions.length && <p className="muted">Tạo phiên mới để bắt đầu.</p>}</div>
      <div className="sidebar-footer"><span className="online-dot" style={{ background: healthy ? "var(--green)" : "#ffc46b" }} />{healthy ? "Worker sẵn sàng" : "Worker chưa kết nối"}</div>
    </aside>
    <section className="main-area">
      <header className="topbar"><div><span className="eyebrow">CREATIVE WORKSPACE</span><h1>{selected?.name || "Không gian sáng tạo"}</h1></div>
        <div className="account-menu"><strong>{email}</strong><SignOutButton /></div></header>
      {busy && <p className="status-warning" role="status" aria-live="polite">Đang xử lý yêu cầu…</p>}
      <nav className="studio-tabs" aria-label="Chức năng">{tabs.map(t => <button key={t} className={t === tab ? "active" : ""} onClick={() => setTab(t)}>{t}</button>)}</nav>
      {error && <p className="error-message" role="alert">{error}<button className="ghost-button" onClick={() => void action(async () => { dirtyRef.current = false; setDirty(false); await refresh(); })}>Tải lại dữ liệu đã lưu</button></p>}
      {notice && <p className="status-good" role="status">{notice}</p>}
      {selected && selectedJob && <section className={`session-progress ${selectedJob.status === "failed" ? "has-error" : ""}`} aria-label={`Tiến trình phiên ${selected.name}`}>
        <div role="status" aria-live="polite" aria-atomic="true"><strong>{selected.name} · {jobNames[selectedJob.job_type] || selectedJob.job_type}</strong><p>{statusNames[selectedJob.status] || selectedJob.status} · {jobPercent(selectedJob)}% — {selectedJob.stage}</p>
          {selectedJob.status === "queued" && <p className="muted">{healthy ? "Đang chờ worker nhận tác vụ." : "Đang chờ kết nối worker. Hãy mở worker trên máy Mac."}</p>}
          {selectedJob.status === "retry_wait" && <p className="muted">Worker sẽ tự thử lại từ phần đã lưu.</p>}
          {selectedJob.error && <p className="error-message">{selectedJob.error}</p>}
        </div><progress aria-label={`Mức hoàn thành phiên ${selected.name}`} value={jobPercent(selectedJob)} max={100} />
      </section>}
      {dirty && <div className="save-banner"><span>Có thay đổi chưa lưu. Lưu sẽ hủy tác vụ đang chạy của phiên.</span><button disabled={busy} className="secondary-button" onClick={() => void action(async () => { await save(); setNotice("Đã lưu trên máy chủ."); })}>Lưu thay đổi</button></div>}
      {!healthy && <p className="muted worker-hint">Worker chưa sẵn sàng. Bạn vẫn có thể chuẩn bị và lưu nội dung; nút tạo sẽ mở khi worker kết nối.</p>}
      {!selected && !["Cấu hình API", "Tác vụ", "AI33"].includes(tab) && <section className="welcome-panel"><div><p className="eyebrow">BẮT ĐẦU SÁNG TẠO</p><h2>Dịch lời kể và nội dung YouTube.</h2><p className="muted">Tạo phiên mới hoặc mở phiên đã lưu ở thanh bên. Cấu hình API của bạn được mã hóa trên máy chủ.</p></div><div className="welcome-icon">✦</div></section>}
      {selected && tab === "Nội dung" && <section className="editor-panel">
        <div className="form-grid"><label>Tên phiên<input disabled={busy} value={name} onChange={e => { setName(e.target.value); dirtyRef.current = true; setDirty(true); }} /></label>
          <ChoiceField key={`${selected.id}:language`} label="Ngôn ngữ đích" options={languages} value={typeof draft.language === "string" ? draft.language : "Tiếng Việt"} disabled={busy || running} maxLength={80} onChange={value => {
            change("language", value); setAutoTranslation({ sid: selected.id, language: value });
            setNotice("Đã chọn ngôn ngữ. Khi link YouTube hợp lệ và worker kết nối, app tự dịch lời kể và YouTube SEO.");
          }} />
          <label>Link YouTube<input disabled={busy} value={str(draft.url)} onChange={e => change("url", e.target.value)} placeholder="https://www.youtube.com/watch?v=…" /></label>
        </div>
        <Thumbnail url={str(draft.url)} download={() => void action(() => download("jpg"))} />
        <p className="muted">Nhập link YouTube rồi chọn ngôn ngữ đích: app tự lấy phụ đề và dịch thành lời kể cùng YouTube SEO. Bạn không cần nhập tiêu đề, mô tả hoặc phụ đề nguồn.</p>
        <div className="toolbar">{generate("Dịch lời kể và YouTube SEO", "full")}<button className="ghost-button" disabled={busy} onClick={() => void action(() => download("json"))}>Xuất phiên JSON</button>
          <button className="ghost-button danger" disabled={busy} onClick={() => void action(async () => { if (!window.confirm("Xóa phiên này và hủy mọi tác vụ đang chạy?")) return; await api(`/sessions/${selected.id}`, "DELETE"); selectedRef.current = null; setSelected(null); dirtyRef.current = false; setDirty(false); await refresh(); })}>Xóa phiên</button></div>
      </section>}
      {selected && tab === "Lời kể" && <section className="editor-panel">{stale("translation_stale")}<h2>Bản dịch cho giọng đọc AI</h2><p className="muted">Một người dẫn chuyện, lời kể gián tiếp, số viết bằng chữ theo ngôn ngữ đích.</p>
        <textarea disabled={busy} rows={22} value={str(draft.translated)} onChange={e => change("translated", e.target.value)} />
        <div className="toolbar">{generate("Dịch lại và cập nhật SEO", "translation")}<button className="ghost-button" onClick={() => void action(async () => { await navigator.clipboard.writeText(str(draft.translated)); setNotice("Đã copy lời kể."); })}>Copy lời kể</button></div></section>}
      {selected && tab === "YouTube SEO" && <section className="editor-panel">{stale("seo_stale")}<p className="muted">Tiêu đề và mô tả được dịch sát nghĩa khi có bản gốc. Nếu không có mô tả gốc, mô tả sẽ được viết theo bản dịch lời kể. Có thể thêm emoji phù hợp để dễ đọc và hấp dẫn hơn; thẻ tag được tối ưu riêng.</p>{!str(draft.title).trim() && <p className="muted">Chưa có tiêu đề gốc: tiêu đề sẽ được tạo theo nội dung câu chuyện.</p>}{!str(draft.description).trim() && <p className="muted">Không có mô tả gốc: tự tạo mô tả theo bản dịch lời kể, kèm emoji phù hợp.</p>}<div className="toolbar"><h2>Tiêu đề video</h2><CopyButton key={`${selected.id}:title`} text={str(draft.new_title)} label="tiêu đề" /></div><pre>{str(draft.new_title) || "Tiêu đề chưa được tạo"}</pre><p className="muted">{str(draft.new_title).length}/100 ký tự</p><div className="toolbar"><h2>Mô tả video</h2><CopyButton key={`${selected.id}:description`} text={str(draft.new_description)} label="mô tả" /></div><pre>{str(draft.new_description) || "Mô tả chưa được tạo"}</pre><div className="toolbar"><h2>Thẻ tag</h2><CopyButton key={`${selected.id}:tags`} text={str(draft.seo_tags)} label="thẻ tag" /></div><pre>{str(draft.seo_tags)}</pre><div className="toolbar">{(["new_title", "new_description", "seo_tags"] as const).map(field => <button disabled={busy} key={field} className="ghost-button" onClick={() => { const value = window.prompt(field === "new_title" ? "Tiêu đề mới (tối đa 100 ký tự)" : field === "new_description" ? "Mô tả mới" : "Thẻ tag", str(draft[field])); if (value !== null) void action(() => editArtifact(field, value)); }}>Sửa {field === "new_title" ? "tiêu đề" : field === "new_description" ? "mô tả" : "tag"}</button>)}</div>{generate("Dịch lại tiêu đề, mô tả và tạo tag", "seo")}</section>}
      {tab === "Tác vụ" && <section className="editor-panel"><h2>Hàng đợi trên máy chủ</h2><p className="muted">Checkpoint giữ lại khi worker khởi động lại. Tiếp tục job lỗi dùng đầu vào ban đầu; sửa nội dung rồi tạo job mới nếu muốn thay đổi.</p>{jobs.length === 0 && <p className="muted">Chưa có tác vụ.</p>}{jobs.map(job => <article className="job-card" key={job.id}><div className="toolbar"><strong>{sessions.find(s => s.id === job.session_id)?.name || "Phiên đã xóa"} · {jobNames[job.job_type] || job.job_type}</strong><span className="status-pill">{statusNames[job.status] || job.status} · lần {job.attempts}</span></div><p>{job.stage}</p><progress aria-label={`Tiến trình ${jobNames[job.job_type] || job.job_type}`} value={jobPercent(job)} max={100} /><small>{jobPercent(job)}% · {job.id.slice(0, 8)}</small>{job.error && <p className="error-message">{job.error}</p>}<div className="toolbar">{active(job) && <button disabled={busy} className="ghost-button" onClick={() => void action(async () => { await api(`/jobs/${job.id}/cancel`, "POST"); await refresh(); })}>Hủy tác vụ</button>}{job.status === "failed" && job.session_id && <button disabled={busy || !healthy} className="secondary-button" onClick={() => void action(async () => { await api(`/jobs/${job.id}/retry`, "POST"); await refresh(); })}>Tiếp tục từ checkpoint</button>}</div></article>)}</section>}
      {tab === "Cấu hình API" && <section className="editor-panel"><h2>Nhà cung cấp AI</h2><p className="muted">API key đã lưu được giữ trên máy chủ. Để trống ô key sẽ giữ key hiện tại; dùng “Xóa key” khi cần.</p>
        <label>Nền tảng<select disabled={busy} value={provider} onChange={e => { setPref("api_provider", e.target.value); setModels([]); }}>{Object.keys(providers).map(p => <option key={p}>{p}</option>)}</select></label>
        <label>API key {config.configured_keys.includes(`api_key_${provider}`) && <small className="status-good">Đã lưu</small>}<input disabled={busy} type="password" autoComplete="new-password" value={changes[`api_key_${provider}`] ?? ""} onChange={e => { const value = e.target.value; setChanges(old => { const next = { ...old }; if (value) next[`api_key_${provider}`] = value; else delete next[`api_key_${provider}`]; return next; }); }} placeholder="Nhập key mới nếu muốn thay đổi" /></label>
        <button className="ghost-button" onClick={() => setPref(`api_key_${provider}`, "")}>Xóa key đã lưu khi lưu cấu hình</button>
        <div className="form-grid"><label>Base URL<input disabled={busy} value={pref(`api_base_${provider}`, providers[provider]?.base_url)} onChange={e => setPref(`api_base_${provider}`, e.target.value)} /></label><label>Model<input disabled={busy} list="models" value={pref(`api_model_id_${provider}`, providers[provider]?.model)} onChange={e => setPref(`api_model_id_${provider}`, e.target.value)} /><datalist id="models">{models.map(m => <option key={m}>{m}</option>)}</datalist></label></div>
        <details><summary>Tùy chọn API tương thích</summary><label>Giao thức<select value={pref(`api_format_${provider}`, "chat")} onChange={e => setPref(`api_format_${provider}`, e.target.value)}><option value="chat">OpenAI Chat Completions</option><option value="anthropic">Anthropic Messages</option></select></label><label>Xác thực<select value={pref(`api_auth_mode_${provider}`, providers[provider]?.auth || "bearer")} onChange={e => setPref(`api_auth_mode_${provider}`, e.target.value)}><option value="bearer">Bearer token</option><option value="api_key">API key</option></select></label></details>
        {[['image_api_key_input', 'OpenAI Images API key'], ['supadata_api_key_input', 'Supadata API key (dự phòng phụ đề đang có)']].map(([key, label]) => <label key={key}>{label} {config.configured_keys.includes(key) && <small className="status-good">Đã lưu</small>}<input disabled={busy} type="password" autoComplete="new-password" value={changes[key] ?? ""} placeholder="Giữ key hiện tại nếu để trống" onChange={e => { const value = e.target.value; setChanges(old => { const next = { ...old }; if (value) next[key] = value; else delete next[key]; return next; }); }} /><button type="button" className="ghost-button" onClick={() => setPref(key, "")}>Xóa key khi lưu</button></label>)}
        <div className="toolbar"><button disabled={busy} className="primary-button" onClick={() => void action(async () => { const values = { ...changes, api_provider: provider, [`api_base_${provider}`]: pref(`api_base_${provider}`, providers[provider]?.base_url), [`api_model_id_${provider}`]: pref(`api_model_id_${provider}`, providers[provider]?.model) }; setConfig(await api("/settings", "PUT", { values, version: config.version })); setChanges({}); setNotice("Đã mã hóa và lưu cấu hình."); })}>Lưu cấu hình</button><button disabled={busy || Object.keys(changes).length > 0} className="ghost-button" onClick={() => void action(async () => { await api("/providers/test", "POST"); setNotice("Kết nối API thành công."); })}>Kiểm tra API đã lưu</button><button disabled={busy || Object.keys(changes).length > 0} className="ghost-button" onClick={() => void action(async () => setModels(await api<string[]>("/providers/models", "POST")))}>Quét model</button></div></section>}
      {tab === "AI33" && <section className="editor-panel"><h2>AI33 / OpenSpeaker</h2><p className="muted">Tác vụ LMT tiếp tục trên worker khi bạn dùng AI33.</p><a className="secondary-button" href="https://ai33.pro/app" target="_blank" rel="noreferrer">Mở AI33 ↗</a><iframe title="AI33" src="https://ai33.pro/app" className="ai33-frame" referrerPolicy="no-referrer" /></section>}
    </section>
  </main>;
}

function ChoiceField({ label, options, value, disabled, maxLength, onChange }: {
  label: string; options: { label: string; value: string }[]; value: string;
  disabled: boolean; maxLength: number; onChange: (value: string) => void;
}) {
  const [custom, setCustom] = useState(false);
  const isCustom = custom || !options.some(option => option.value === value);
  return <div className="choice-field"><label>{label}<select disabled={disabled} value={isCustom ? "__custom__" : value} onChange={e => {
    const next = e.target.value;
    setCustom(next === "__custom__");
    if (next !== "__custom__") onChange(next);
  }}>{options.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}<option value="__custom__">Khác — tự nhập…</option></select></label>
    {isCustom && <label>{label} tùy chỉnh<input disabled={disabled} maxLength={maxLength} value={value} onChange={e => onChange(e.target.value)} placeholder={`Nhập ${label.toLowerCase()}…`} /></label>}
  </div>;
}

function CopyButton({ text, label }: { text: string; label: string }) {
  const [state, setState] = useState<"idle" | "copying" | "copied" | "error">("idle");
  const latest = useRef(text);
  latest.current = text;
  useEffect(() => { setState("idle"); }, [text]);
  async function copy() {
    setState("copying");
    try {
      await navigator.clipboard.writeText(text);
      if (latest.current === text) setState("copied");
    } catch {
      if (latest.current === text) setState("error");
    }
  }
  return <div><button type="button" className="ghost-button" disabled={!text.trim() || state === "copying"}
    aria-label={`Copy ${label}`} onClick={() => void copy()}>
    {state === "copied" ? "✓ Đã copy" : state === "copying" ? "Đang copy…" : `Copy ${label}`}
  </button><span role="status" aria-live="polite" className={state === "error" ? "error-message" : "status-good"}>
    {state === "copied" ? ` Đã copy ${label}` : state === "error" ? " Không copy được. Hãy cho phép trình duyệt sao chép và thử lại." : ""}
  </span></div>;
}

function Thumbnail({ url, download }: { url: string; download: () => void }) {
  const id = /(?:v=|youtu\.be\/|\/shorts\/|\/live\/)([\w-]{11})/.exec(url)?.[1];
  if (!id) return null;
  return <div className="thumbnail-preview"><img src={`https://i.ytimg.com/vi/${id}/hqdefault.jpg`} alt="Thumbnail gốc YouTube" /><button className="secondary-button" onClick={download}>Tải thumbnail gốc</button></div>;
}
