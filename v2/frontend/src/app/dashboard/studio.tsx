"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { SignOutButton } from "./sign-out-button";
import { MigrationCheck } from "./migration-check";

type Data = Record<string, unknown>;
type Session = { id: string; name: string; revision: number; status: string; data: Data; updated_at: string };
type Summary = Omit<Session, "data">;
type Job = { id: string; session_id: string | null; job_type: string; status: string; progress: number; stage: string; error: string; attempts: number };
type Provider = { base_url: string; model: string; kind: string; auth?: string };
type Config = { values: Record<string, string>; configured_keys: string[]; version: number };
const tabs = ["Nội dung", "Lời kể", "YouTube SEO", "Form 8 giây", "Nhân vật", "Tác vụ", "Cấu hình API", "Chuyển dữ liệu", "AI33"];
const active = (job: Job) => ["queued", "running", "retry_wait"].includes(job.status);
const jobNames: Record<string, string> = { full: "Dịch lời kể và SEO", translation: "Dịch lời kể và SEO", seo: "Dịch tiêu đề, mô tả và tạo tag", forms: "Tạo form 8 giây", characters: "Tạo hồ sơ nhân vật", images: "Tạo ảnh tham chiếu" };
const statusNames: Record<string, string> = { queued: "Đang chờ", running: "Đang xử lý", retry_wait: "Đang chờ thử lại", succeeded: "Hoàn thành", completed: "Hoàn thành", failed: "Có lỗi", cancelled: "Đã hủy", draft: "Bản nháp", ready: "Sẵn sàng", processing: "Đang xử lý", interrupted: "Đã gián đoạn" };
const jobPercent = (job: Job) => Math.max(0, Math.min(100, Math.round(job.progress)));
const latestJob = (jobs: Job[], sid: string) => jobs.find(j => j.session_id === sid && active(j)) ?? jobs.find(j => j.session_id === sid);
const str = (value: unknown) => typeof value === "string" ? value : "";
const pretty = (value: unknown) => { try { return JSON.stringify(typeof value === "string" ? JSON.parse(value) : value, null, 2); } catch { return str(value); } };

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
  const [images, setImages] = useState<{ name: string; url: string }[]>([]);
  const request = useRef<{ key: string; id: string } | null>(null);
  const [search, setSearch] = useState("");

  function accept(session: Session) {
    selectedRef.current = session.id;
    setSelected(session); setDraft(session.data); setName(session.name);
    dirtyRef.current = false; setDirty(false); setImages([]);
  }
  const refresh = useCallback(async () => {
    const [list, queue, worker] = await Promise.all([
      api<Summary[]>("/sessions"), api<Job[]>("/jobs"), api<{ healthy: boolean }>("/worker"),
    ]);
    setSessions(list); setJobs(queue); setHealthy(worker.healthy);
    const sid = selectedRef.current;
    if (sid && !dirtyRef.current) {
      const row = await api<Session>(`/sessions/${sid}`);
      if (sid === selectedRef.current && !dirtyRef.current) {
        setSelected(row); setDraft(row.data); setName(row.name);
      }
    }
  }, []);
  useEffect(() => {
    let mounted = true;
    void Promise.all([refresh(), api<Record<string, Provider>>("/providers"), api<Config>("/settings")])
      .then(([, p, c]) => { if (mounted) { setProviders(p); setConfig(c); } })
      .catch(e => { if (mounted) setError(e.message); });
    const timer = setInterval(() => { void refresh().catch(e => { if (mounted) setError(e.message); }); }, 5000);
    return () => { mounted = false; clearInterval(timer); };
  }, [refresh]);
  useEffect(() => {
    const protect = (e: BeforeUnloadEvent) => { if (dirtyRef.current) e.preventDefault(); };
    window.addEventListener("beforeunload", protect);
    return () => window.removeEventListener("beforeunload", protect);
  }, []);

  async function action(task: () => Promise<void>) {
    setBusy(true); setError(""); setNotice("");
    try { await task(); } catch (e) { setError(e instanceof Error ? e.message : "Không thực hiện được yêu cầu."); }
    finally { setBusy(false); }
  }
  function change(key: string, value: unknown) {
    setDraft(old => ({ ...old, [key]: value })); dirtyRef.current = true; setDirty(true);
  }
  async function open(sid: string) {
    if (dirtyRef.current) { setError("Hãy lưu thay đổi trước khi chuyển phiên."); return; }
    selectedRef.current = sid;
    const row = await api<Session>(`/sessions/${sid}`);
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
    accept(row); await refresh(); return row;
  }
  async function run(kind: string) {
    const row = await save();
    const key = `${row.id}:${row.revision}:${kind}`;
    if (request.current?.key !== key) request.current = { key, id: crypto.randomUUID() };
    await api(`/sessions/${row.id}/jobs`, "POST", { kind, revision: row.revision, request_id: request.current.id });
    request.current = null;
    setNotice("Đã giao tác vụ. Worker sẽ tiếp tục khi bạn đóng trình duyệt."); await refresh();
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
  const stale = (key: string) => draft[key] === true ? <p className="status-warning">Nội dung này được tạo từ đầu vào cũ. Hãy tạo lại để khớp với phiên hiện tại.</p> : null;
  const generate = (label: string, kind: string) => <button className="primary-button" disabled={busy || !selected || running || !healthy} onClick={() => void action(() => run(kind))}>{label}</button>;

  return <main className="app-shell studio-shell">
    <aside className="sidebar">
      <div className="sidebar-brand"><span>🎬</span><strong>LMT Studio Pro</strong><small>V2</small></div>
      <button className="primary-button" disabled={busy || dirty} onClick={() => void action(async () => {
        accept(await api<Session>("/sessions", "POST", {})); setTab("Nội dung"); await refresh();
      })}>＋ Phiên mới</button>
      <input className="session-search" aria-label="Tìm phiên" placeholder="Tìm phiên làm việc…" value={search} onChange={e => setSearch(e.target.value)} />
      <div className="session-list">{sessions.filter(s => s.name.toLowerCase().includes(search.toLowerCase())).map(s => {
        const job = latestJob(jobs, s.id);
        return <button disabled={busy} className={`session-item ${selected?.id === s.id ? "active" : ""}`} key={s.id} onClick={() => void action(() => open(s.id))}>
          <span>◫ {s.name}</span>
          <small>{job ? `${statusNames[job.status] || job.status} · ${jobPercent(job)}%` : statusNames[s.status] || s.status}</small>
          {job && <><small>{jobNames[job.job_type] || job.job_type}</small><progress aria-label={`Tiến trình phiên ${s.name}`} value={jobPercent(job)} max={100} /><small className="session-stage" title={job.error || job.stage}>{job.error || job.stage}</small></>}
        </button>;
      })}{!sessions.length && <p className="muted">Tạo phiên mới hoặc chuyển dữ liệu V1.</p>}</div>
      <div className="sidebar-footer"><span className="online-dot" style={{ background: healthy ? "var(--green)" : "#ffc46b" }} />{healthy ? "Worker sẵn sàng" : "Worker chưa kết nối"}</div>
    </aside>
    <section className="main-area">
      <header className="topbar"><div><span className="eyebrow">CREATIVE WORKSPACE</span><h1>{selected?.name || "Không gian sáng tạo"}</h1></div>
        <div className="account-menu"><strong>{email}</strong><SignOutButton /></div></header>
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
      {!selected && !["Cấu hình API", "Chuyển dữ liệu", "Tác vụ", "AI33"].includes(tab) && <section className="welcome-panel"><div><p className="eyebrow">BẮT ĐẦU SÁNG TẠO</p><h2>Từ câu chuyện đến từng khung hình.</h2><p className="muted">Tạo phiên mới hoặc mở “Chuyển dữ liệu” để lấy lại phiên V1. Cấu hình API của bạn được mã hóa trên máy chủ.</p></div><div className="welcome-icon">✦</div></section>}
      {selected && tab === "Nội dung" && <section className="editor-panel">
        <div className="form-grid"><label>Tên phiên<input disabled={busy} value={name} onChange={e => { setName(e.target.value); dirtyRef.current = true; setDirty(true); }} /></label>
          <label>Ngôn ngữ đích<input disabled={busy} value={str(draft.language)} onChange={e => change("language", e.target.value)} /></label>
          <label>Link YouTube<input disabled={busy} value={str(draft.url)} onChange={e => change("url", e.target.value)} placeholder="https://www.youtube.com/watch?v=…" /></label>
          <label>Phong cách<input disabled={busy} value={str(draft.style)} onChange={e => change("style", e.target.value)} /></label>
          <label>Tiêu đề gốc<input disabled={busy} value={str(draft.title)} onChange={e => change("title", e.target.value)} /></label>
          <label>Mô tả gốc<input disabled={busy} value={str(draft.description)} onChange={e => change("description", e.target.value)} /></label></div>
        <Thumbnail url={str(draft.url)} download={() => void action(() => download("jpg"))} />
        <label>Nội dung gốc / phụ đề<textarea disabled={busy} rows={15} value={str(draft.source)} onChange={e => change("source", e.target.value)} placeholder="Dán toàn bộ nội dung cần dịch, hoặc nhập link YouTube ở trên." /></label>
        <div className="toolbar"><label className="file-label">Nhập TXT / SRT<input disabled={busy} type="file" accept=".txt,.srt,.vtt" onChange={e => { const f = e.target.files?.[0]; if (f) void action(async () => { if (f.size > 1400000) throw new Error("Tệp quá lớn."); change("source", await f.text()); }); }} /></label><span className="muted">{str(draft.source).length.toLocaleString()} ký tự</span></div>
        <div className="toolbar">{generate("Tạo bản dịch lời kể và SEO", "full")}<button className="ghost-button" disabled={busy} onClick={() => void action(() => download("json"))}>Xuất phiên JSON</button>
          <button className="ghost-button danger" disabled={busy} onClick={() => void action(async () => { if (!window.confirm("Xóa phiên này và hủy mọi tác vụ đang chạy?")) return; await api(`/sessions/${selected.id}`, "DELETE"); selectedRef.current = null; setSelected(null); dirtyRef.current = false; setDirty(false); await refresh(); })}>Xóa phiên</button></div>
      </section>}
      {selected && tab === "Lời kể" && <section className="editor-panel">{stale("translation_stale")}<h2>Bản dịch cho giọng đọc AI</h2><p className="muted">Một người dẫn chuyện, lời kể gián tiếp, số viết bằng chữ theo ngôn ngữ đích.</p>
        <textarea disabled={busy} rows={22} value={str(draft.translated)} onChange={e => change("translated", e.target.value)} />
        <div className="toolbar">{generate("Dịch lại và cập nhật SEO", "translation")}<button className="ghost-button" onClick={() => void action(async () => { await navigator.clipboard.writeText(str(draft.translated)); setNotice("Đã copy lời kể."); })}>Copy lời kể</button></div></section>}
      {selected && tab === "YouTube SEO" && <section className="editor-panel">{stale("seo_stale")}<p className="muted">Tiêu đề và mô tả được dịch sát nghĩa khi có bản gốc. Nếu không có mô tả gốc, mô tả sẽ được viết theo bản dịch lời kể. Có thể thêm emoji phù hợp để dễ đọc và hấp dẫn hơn; thẻ tag được tối ưu riêng.</p>{!str(draft.title).trim() && <p className="muted">Chưa có tiêu đề gốc: tiêu đề sẽ được tạo theo nội dung câu chuyện.</p>}{!str(draft.description).trim() && <p className="muted">Không có mô tả gốc: tự tạo mô tả theo bản dịch lời kể, kèm emoji phù hợp.</p>}<h2>Tiêu đề video</h2><pre>{str(draft.new_title) || "Tiêu đề chưa được tạo"}</pre><p className="muted">{str(draft.new_title).length}/100 ký tự</p><h2>Mô tả video</h2><pre>{str(draft.new_description) || "Mô tả chưa được tạo"}</pre><h2>Thẻ tag</h2><pre>{str(draft.seo_tags)}</pre><div className="toolbar">{(["new_title", "new_description", "seo_tags"] as const).map(field => <button disabled={busy} key={field} className="ghost-button" onClick={() => { const value = window.prompt(field === "new_title" ? "Tiêu đề mới (tối đa 100 ký tự)" : field === "new_description" ? "Mô tả mới" : "Thẻ tag", str(draft[field])); if (value !== null) void action(() => editArtifact(field, value)); }}>Sửa {field === "new_title" ? "tiêu đề" : field === "new_description" ? "mô tả" : "tag"}</button>)}</div>{generate("Dịch lại tiêu đề, mô tả và tạo tag", "seo")}</section>}
      {selected && tab === "Form 8 giây" && <section className="editor-panel">{stale("video_forms_stale")}<h2>Prompt ảnh & video</h2><p className="muted">Chỉ dẫn sản xuất bằng tiếng Anh; lời kể và phụ đề giữ nguyên ngôn ngữ đích. Thời lượng là ước tính theo văn bản hoặc độ dài audio, cần đối chiếu khi dựng.</p>
        <label>Thời lượng giọng đọc (giây, tùy chọn)<input disabled={busy} type="number" min="1" max="1920" value={typeof draft.duration_seconds === "number" ? draft.duration_seconds : ""} onChange={e => change("duration_seconds", e.target.value ? Number(e.target.value) : null)} /></label>
        <label className="file-label">Đọc thời lượng file giọng đọc<input disabled={busy} type="file" accept="audio/*" onChange={e => { const f = e.target.files?.[0]; if (!f) return; const audio = document.createElement("audio"); const url = URL.createObjectURL(f); audio.onloadedmetadata = () => { if (Number.isFinite(audio.duration) && audio.duration <= 1920) change("duration_seconds", audio.duration); else setError("Audio phải có thời lượng hợp lệ, tối đa 32 phút."); URL.revokeObjectURL(url); }; audio.onerror = () => { URL.revokeObjectURL(url); setError("Không đọc được thời lượng audio. Bạn có thể nhập số giây."); }; audio.src = url; }} /></label>
        <div className="toolbar">{generate("Tạo toàn bộ form 8 giây", "forms")}<button disabled={busy} className="ghost-button" onClick={() => void action(() => download("txt"))}>Tải tất cả form TXT</button></div>
        <Forms key={selected.id} raw={draft.video_forms} revision={selected.revision} busy={busy} onEdit={(number, field, value, revision) => void action(() => editArtifact("scene", value, {scene_number:number, prompt_field:field, revision}))} onCopy={text => void action(async () => { await navigator.clipboard.writeText(text); setNotice("Đã copy nhóm form."); })} /></section>}
      {selected && tab === "Nhân vật" && <section className="editor-panel">{stale("character_bible_stale")}<h2>Hồ sơ & ảnh tham chiếu</h2><div className="toolbar">{generate("Tạo hồ sơ nhân vật", "characters")}{generate("Tạo ảnh tham chiếu", "images")}<button disabled={busy} className="ghost-button" onClick={() => void action(async () => setImages(await api(`/sessions/${selected.id}/images`)))}>Xem ảnh đã lưu</button><button disabled={busy} className="ghost-button" onClick={() => void action(() => download("zip"))}>Tải tất cả ảnh ZIP</button></div>
        <pre>{str(draft.character_bible)}</pre><details><summary>Hồ sơ chi tiết</summary><pre>{pretty(draft.character_profile_json)}</pre></details>{stale("character_images_stale")}<div className="image-grid">{images.map(image => <a key={image.url} href={image.url} target="_blank" rel="noreferrer"><img src={image.url} alt={image.name} /><span>{image.name} ↗</span></a>)}</div></section>}
      {tab === "Tác vụ" && <section className="editor-panel"><h2>Hàng đợi trên máy chủ</h2><p className="muted">Checkpoint giữ lại khi worker khởi động lại. Tiếp tục job lỗi dùng đầu vào ban đầu; sửa nội dung rồi tạo job mới nếu muốn thay đổi.</p>{jobs.length === 0 && <p className="muted">Chưa có tác vụ.</p>}{jobs.map(job => <article className="job-card" key={job.id}><div className="toolbar"><strong>{sessions.find(s => s.id === job.session_id)?.name || "Phiên đã xóa"} · {jobNames[job.job_type] || job.job_type}</strong><span className="status-pill">{statusNames[job.status] || job.status} · lần {job.attempts}</span></div><p>{job.stage}</p><progress aria-label={`Tiến trình ${jobNames[job.job_type] || job.job_type}`} value={jobPercent(job)} max={100} /><small>{jobPercent(job)}% · {job.id.slice(0, 8)}</small>{job.error && <p className="error-message">{job.error}</p>}<div className="toolbar">{active(job) && <button disabled={busy} className="ghost-button" onClick={() => void action(async () => { await api(`/jobs/${job.id}/cancel`, "POST"); await refresh(); })}>Hủy tác vụ</button>}{job.status === "failed" && job.session_id && <button disabled={busy || !healthy} className="secondary-button" onClick={() => void action(async () => { await api(`/jobs/${job.id}/retry`, "POST"); await refresh(); })}>Tiếp tục từ checkpoint</button>}</div></article>)}</section>}
      {tab === "Cấu hình API" && <section className="editor-panel"><h2>Nhà cung cấp AI</h2><p className="muted">API key đã lưu được giữ trên máy chủ. Để trống ô key sẽ giữ key hiện tại; dùng “Xóa key” khi cần.</p>
        <label>Nền tảng<select disabled={busy} value={provider} onChange={e => { setPref("api_provider", e.target.value); setModels([]); }}>{Object.keys(providers).map(p => <option key={p}>{p}</option>)}</select></label>
        <label>API key {config.configured_keys.includes(`api_key_${provider}`) && <small className="status-good">Đã lưu</small>}<input disabled={busy} type="password" autoComplete="new-password" value={changes[`api_key_${provider}`] ?? ""} onChange={e => { const value = e.target.value; setChanges(old => { const next = { ...old }; if (value) next[`api_key_${provider}`] = value; else delete next[`api_key_${provider}`]; return next; }); }} placeholder="Nhập key mới nếu muốn thay đổi" /></label>
        <button className="ghost-button" onClick={() => setPref(`api_key_${provider}`, "")}>Xóa key đã lưu khi lưu cấu hình</button>
        <div className="form-grid"><label>Base URL<input disabled={busy} value={pref(`api_base_${provider}`, providers[provider]?.base_url)} onChange={e => setPref(`api_base_${provider}`, e.target.value)} /></label><label>Model<input disabled={busy} list="models" value={pref(`api_model_id_${provider}`, providers[provider]?.model)} onChange={e => setPref(`api_model_id_${provider}`, e.target.value)} /><datalist id="models">{models.map(m => <option key={m}>{m}</option>)}</datalist></label></div>
        <details><summary>Tùy chọn API tương thích</summary><label>Giao thức<select value={pref(`api_format_${provider}`, "chat")} onChange={e => setPref(`api_format_${provider}`, e.target.value)}><option value="chat">OpenAI Chat Completions</option><option value="anthropic">Anthropic Messages</option></select></label><label>Xác thực<select value={pref(`api_auth_mode_${provider}`, providers[provider]?.auth || "bearer")} onChange={e => setPref(`api_auth_mode_${provider}`, e.target.value)}><option value="bearer">Bearer token</option><option value="api_key">API key</option></select></label></details>
        {[['image_api_key_input', 'OpenAI Images API key'], ['supadata_api_key_input', 'Supadata API key (dự phòng phụ đề đang có)']].map(([key, label]) => <label key={key}>{label} {config.configured_keys.includes(key) && <small className="status-good">Đã lưu</small>}<input disabled={busy} type="password" autoComplete="new-password" value={changes[key] ?? ""} placeholder="Giữ key hiện tại nếu để trống" onChange={e => { const value = e.target.value; setChanges(old => { const next = { ...old }; if (value) next[key] = value; else delete next[key]; return next; }); }} /><button type="button" className="ghost-button" onClick={() => setPref(key, "")}>Xóa key khi lưu</button></label>)}
        <div className="toolbar"><button disabled={busy} className="primary-button" onClick={() => void action(async () => { const values = { ...changes, api_provider: provider, [`api_base_${provider}`]: pref(`api_base_${provider}`, providers[provider]?.base_url), [`api_model_id_${provider}`]: pref(`api_model_id_${provider}`, providers[provider]?.model) }; setConfig(await api("/settings", "PUT", { values, version: config.version })); setChanges({}); setNotice("Đã mã hóa và lưu cấu hình."); })}>Lưu cấu hình</button><button disabled={busy || Object.keys(changes).length > 0} className="ghost-button" onClick={() => void action(async () => { await api("/providers/test", "POST"); setNotice("Kết nối API thành công."); })}>Kiểm tra API đã lưu</button><button disabled={busy || Object.keys(changes).length > 0} className="ghost-button" onClick={() => void action(async () => setModels(await api<string[]>("/providers/models", "POST")))}>Quét model</button></div></section>}
      {tab === "Chuyển dữ liệu" && <><MigrationCheck /><section className="editor-panel"><h2>Nhập phiên V1</h2><p className="muted">Giữ nguyên nội dung và cấu hình mã hóa. Phiên đã có trong V2 được giữ lại. Không xóa dữ liệu V1.</p><button disabled={busy} className="primary-button" onClick={() => void action(async () => { const result = await api<{ imported: number; preserved_existing: number }>("/migration/legacy/import", "POST"); setNotice(`Đã nhập ${result.imported} phiên; giữ ${result.preserved_existing} phiên đã có.`); await refresh(); setConfig(await api("/settings")); })}>Kiểm tra và nhập dữ liệu V1</button></section></>}
      {tab === "AI33" && <section className="editor-panel"><h2>AI33 / OpenSpeaker</h2><p className="muted">Tác vụ LMT tiếp tục trên worker khi bạn dùng AI33.</p><a className="secondary-button" href="https://ai33.pro/app" target="_blank" rel="noreferrer">Mở AI33 ↗</a><iframe title="AI33" src="https://ai33.pro/app" className="ai33-frame" referrerPolicy="no-referrer" /></section>}
    </section>
  </main>;
}

function Forms({ raw, onCopy, onEdit, busy, revision }: { raw: unknown; onCopy: (text: string) => void; onEdit: (number: number, field: string, value: string, revision: number) => void; busy: boolean; revision: number }) {
  const [editRevision, setEditRevision] = useState(revision);
  const [editing, setEditing] = useState<number | null>(null);
  const [promptField, setPromptField] = useState("visual_prompt");
  const [content, setContent] = useState("");
  let scenes: Data[] = [];
  try { const parsed = JSON.parse(str(raw) || "{}").scenes; scenes = Array.isArray(parsed) ? parsed : []; } catch { return <p className="muted">Chưa đọc được form.</p>; }
  const groups = Array.from({ length: Math.ceil(scenes.length / 99) }, (_, i) => scenes.slice(i * 99, (i + 1) * 99));
  const text = (scene: Data) => `${scene.number} | 8s\nImage: ${str(scene.image_prompt)}\nVideo: ${str(scene.visual_prompt)}\nVoice: ${str(scene.voiceover)}\nSubtitles: ${typeof scene.subtitles === "string" ? scene.subtitles : pretty(scene.subtitles || "")}\nNext: ${str(scene.transition_to_next)}`;
  return <div>{!scenes.length && <p className="muted">Chưa có form. Nhấn tạo sau khi có bản dịch.</p>}{groups.map((group, i) => <details className="form-group" key={i}><summary>Form {i * 99 + 1}–{i * 99 + group.length} · {group.length} cảnh</summary><button className="ghost-button" onClick={() => onCopy(group.map(text).join("\n\n"))}>Copy toàn bộ nhóm</button>{group.map((scene, j) => <div key={j}><pre>{text(scene)}</pre><button disabled={busy} className="ghost-button" onClick={() => { setEditing(Number(scene.number)); setEditRevision(revision); setPromptField("visual_prompt"); setContent(str(scene.visual_prompt)); }}>Sửa prompt cảnh {String(scene.number)}</button>{editing === Number(scene.number) && <div><select aria-label="Loại prompt" value={promptField} onChange={e => { setPromptField(e.target.value); setContent(str(scene[e.target.value])); }}><option value="visual_prompt">Prompt video</option><option value="image_prompt">Prompt ảnh</option><option value="transition_to_next">Chuyển cảnh</option></select><textarea aria-label="Nội dung prompt" rows={8} value={content} onChange={e => setContent(e.target.value)} /><button disabled={busy} className="secondary-button" onClick={() => onEdit(Number(scene.number), promptField, content, editRevision)}>Lưu prompt</button><button className="ghost-button" onClick={() => setEditing(null)}>Đóng</button></div>}</div>)}</details>)}</div>;
}

function Thumbnail({ url, download }: { url: string; download: () => void }) {
  const id = /(?:v=|youtu\.be\/|\/shorts\/|\/live\/)([\w-]{11})/.exec(url)?.[1];
  if (!id) return null;
  return <div className="thumbnail-preview"><img src={`https://i.ytimg.com/vi/${id}/hqdefault.jpg`} alt="Thumbnail gốc YouTube" /><button className="secondary-button" onClick={download}>Tải thumbnail gốc</button></div>;
}
