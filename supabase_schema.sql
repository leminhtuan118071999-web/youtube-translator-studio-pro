-- Run once inside your private Supabase project's SQL Editor.
-- Every authenticated account can read/update only its own row.
-- Never use the Supabase service_role key in Streamlit.
CREATE TABLE IF NOT EXISTS public.youtube_studio_state (
    user_id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    encrypted_config text NOT NULL DEFAULT '',
    updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.youtube_studio_state ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.youtube_studio_state FROM anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.youtube_studio_state TO authenticated;

DROP POLICY IF EXISTS "read own studio state" ON public.youtube_studio_state;
CREATE POLICY "read own studio state"
    ON public.youtube_studio_state FOR SELECT TO authenticated
    USING ((select auth.uid()) = user_id);

DROP POLICY IF EXISTS "insert own studio state" ON public.youtube_studio_state;
CREATE POLICY "insert own studio state"
    ON public.youtube_studio_state FOR INSERT TO authenticated
    WITH CHECK ((select auth.uid()) = user_id);

DROP POLICY IF EXISTS "update own studio state" ON public.youtube_studio_state;
CREATE POLICY "update own studio state"
    ON public.youtube_studio_state FOR UPDATE TO authenticated
    USING ((select auth.uid()) = user_id)
    WITH CHECK ((select auth.uid()) = user_id);

DROP POLICY IF EXISTS "delete own studio state" ON public.youtube_studio_state;
CREATE POLICY "delete own studio state"
    ON public.youtube_studio_state FOR DELETE TO authenticated
    USING ((select auth.uid()) = user_id);
