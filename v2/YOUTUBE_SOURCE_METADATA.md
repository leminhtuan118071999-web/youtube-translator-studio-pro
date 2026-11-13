# YouTube source metadata

After Start, V2 retrieves subtitles and original title, description and tags concurrently. Original text is preserved in the session; SEO translation uses the original description and tags when available. Manual title/description take precedence. Resume caches metadata for the same video and invalidates completed SEO when original inputs differ.

Public watch-page extraction is best effort. Missing fields, explicit empty fields, and successfully fetched fields have distinct UI statuses. oEmbed can recover a title only. If a description or tags cannot be obtained, generated output is explicitly labelled as generated from content rather than a translation of original metadata. No extra AI call is used to retrieve metadata. Requests have timeouts, bounded page size, a streaming deadline and a fixed YouTube host.

Tests mock YouTube responses and verify original text preservation, missing/empty statuses, network failure, concurrent retrieval, original-tag prompting and checkpoint reuse. Real availability depends on YouTube access from the worker.
