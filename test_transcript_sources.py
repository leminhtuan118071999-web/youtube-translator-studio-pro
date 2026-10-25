import unittest
from unittest.mock import Mock, patch

from transcript_sources import (
    parse_supadata_result, parse_uploaded_subtitles,
    fetch_with_fallback, supadata_transcript,
)


class TranscriptFallbackTests(unittest.TestCase):
    def test_native_response(self):
        with patch("transcript_sources.native_transcript", return_value=("Original transcript", "English")):
            with patch("transcript_sources.supadata_transcript") as backup:
                text, lang, origin = fetch_with_fallback("Kj1ZWTTWQ0A", "secret")
                self.assertEqual(text, "Original transcript")
                self.assertEqual(origin, "YouTube trực tiếp")
                backup.assert_not_called()

    def test_ip_block_uses_optional_fallback(self):
        with patch("transcript_sources.native_transcript", side_effect=RuntimeError("YouTube blocking IP")):
            with patch("transcript_sources.supadata_transcript", return_value=("Recovered text", "en")):
                content, lang, origin = fetch_with_fallback("Kj1ZWTTWQ0A", "supadata-key")
                self.assertEqual(content, "Recovered text")
                self.assertEqual(origin, "Supadata")

    def test_no_key_shows_short_vietnamese_guidance(self):
        with patch("transcript_sources.native_transcript", side_effect=RuntimeError("IP blocked: long error")):
            with self.assertRaises(RuntimeError) as error:
                fetch_with_fallback("Kj1ZWTTWQ0A")
            self.assertIn("Supadata", str(error.exception))
            self.assertIn(".srt/.vtt/.txt", str(error.exception))
            self.assertNotIn("IP blocked: long error", str(error.exception))

    def test_subtitle_json_string(self):
        self.assertEqual(parse_supadata_result({"content":"dzień dobry","lang":"pl"}),("dzień dobry","pl"))

    def test_subtitle_json_chunks(self):
        text, lang = parse_supadata_result({
            "content":[{"text":"Hello"},{"text":"world"}],"lang":"en"
        })
        self.assertEqual(text, "Hello world")

    def test_srt_file_extraction(self):
        data=b"1\n00:00:00,200 --> 00:00:01,000\n<i>Hello</i>\n\n2\n00:00:02,200 --> 00:00:04,000\nWorld"
        self.assertEqual(parse_uploaded_subtitles("test.srt", data), "Hello World")

    def test_vtt_file_extraction(self):
        data=b"WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nBonjour\n\n00:00:03.000 --> 00:00:05.000\nBonjour\nBienvenue"
        self.assertEqual(parse_uploaded_subtitles("test.vtt", data), "Bonjour Bienvenue")

    def test_txt_file(self):
        self.assertEqual(parse_uploaded_subtitles("hello.txt",b"abc xyz"),"abc xyz")

    @patch("transcript_sources._get")
    def test_immediate_supadata_result(self, get):
        get.return_value = (200,{"content":"ready","lang":"en"})
        result = supadata_transcript("12345678901","mykey")
        self.assertEqual(result,("ready","en"))
        self.assertEqual(get.call_args.kwargs["params"]["mode"], "auto")

    @patch("transcript_sources._get")
    def test_async_supadata_result(self,get):
        get.side_effect = [
            (202,{"jobId":"abcdef123"}),
            (200,{"status":"processing"}),
            (200,{"status":"completed","content":"done","lang":"pl"}),
        ]
        result=supadata_transcript("12345678901","mykey",sleep=lambda _: None)
        self.assertEqual(result,("done","pl"))
        self.assertEqual(get.call_count,3)

    def test_reject_giant_files(self):
        with self.assertRaises(ValueError):
            parse_uploaded_subtitles("clip.txt", b"a"*(4*1024*1024+1))

if __name__ == "__main__":
    unittest.main()
