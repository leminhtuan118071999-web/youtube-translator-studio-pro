import unittest
from unittest.mock import patch

from voice_alignment import (
    align_target_words, audio_aligned_plan, whisper_word_timestamps,
    speech_statistics, duration_weighted_plan, TransientAudioAPIError,
)


class VoiceAlignmentTests(unittest.TestCase):
    def test_match_audio_words_and_assign_to_real_8s_boundaries(self):
        script = "One two three four five six seven eight"
        words = script.split()
        timepoints = [0.3, 1.1, 3.2, 7.8, 8.2, 9.4, 13.0, 15.8]
        stamps = [{"word": word, "start": start, "end": start + 0.2}
                  for word, start in zip(words, timepoints)]
        positions, score = align_target_words(script, stamps, 16.0)
        self.assertEqual(positions, timepoints)
        self.assertEqual(score, 1.0)
        plan = audio_aligned_plan(script, "Tiếng Anh", 16.0, positions)
        self.assertEqual(plan["alignment_mode"], "whisper_word_timestamps")
        self.assertEqual([s["voiceover"] for s in plan["scenes"]],
                         ["One two three four", "five six seven eight"])
        self.assertEqual([s["duration_seconds"] for s in plan["scenes"]], [8, 8])

    def test_auto_scene_count_voice_rate_and_last_scene_padding(self):
        text = " ".join(["word"] * 100)
        stats = speech_statistics(text, 25.5)
        self.assertEqual(stats["form_count"], 4)
        self.assertEqual(stats["video_duration_seconds"], 32)
        self.assertEqual(stats["padding_seconds"], 6.5)
        self.assertAlmostEqual(stats["average_wpm"], 235.3, places=1)
        plan = duration_weighted_plan(text, "Tiếng Anh", 25.5)
        self.assertEqual(len(plan["scenes"]), 4)
        self.assertEqual(plan["speech_stats"]["form_count"], 4)
        self.assertEqual(plan["alignment_mode"], "duration_weighted_estimate")
        self.assertEqual(" ".join(x["voiceover"] for x in plan["scenes"]), text)

    def test_audio_length_and_translated_word_count_both_inform_estimate(self):
        # The audio length fixes the number of 8s clips, while translation
        # density determines expected speech pace and content per clip.
        audio_seconds = 870.24
        normal = speech_statistics(" ".join(["word"] * 1900), audio_seconds)
        self.assertEqual(normal["form_count"], 109)
        self.assertEqual(normal["video_duration_seconds"], 872)
        self.assertEqual(normal["translated_word_count"], 1900)
        self.assertAlmostEqual(normal["words_per_8s"], 17.4, places=1)
        self.assertEqual(normal["pacing_notice"], "")

        too_long = speech_statistics(" ".join(["word"] * 4000), audio_seconds)
        self.assertEqual(too_long["form_count"], 109)
        self.assertIn("dài", too_long["pacing_notice"])

        too_short = speech_statistics(" ".join(["word"] * 100), audio_seconds)
        self.assertEqual(too_short["form_count"], 109)
        self.assertIn("ngắn", too_short["pacing_notice"])

    def test_silent_audio_windows_still_generate_forms(self):
        text = "hello world"
        plan = duration_weighted_plan(text, "Tiếng Anh", 17.0)
        self.assertEqual(len(plan["scenes"]), 3)
        self.assertEqual(" ".join(s["voiceover"] for s in plan["scenes"] if s["voiceover"]), text)

    def test_reject_different_audio_from_translation(self):
        with self.assertRaisesRegex(ValueError, "khác nhiều"):
            align_target_words(
                "red fox runs in a quiet dark forest",
                [{"word": x, "start": n, "end": n + 0.5}
                 for n, x in enumerate("sun moon stars snow cloud rain thunder".split())],
                9.0,
            )

    def test_word_transcription_calls_real_endpoint(self):
        class MockResponse:
            ok = True
            def json(self):
                return {"words": [
                    {"word": "Hello", "start": 0.1, "end": 0.4},
                    {"word": "world", "start": 0.6, "end": 0.9},
                ]}
        with patch("voice_alignment.requests.post", return_value=MockResponse()) as send:
            stamps = whisper_word_timestamps(b"audio-data", "narration.mp3", "secret")
        self.assertEqual(len(stamps), 2)
        self.assertEqual(stamps[0]["word"], "Hello")
        self.assertEqual(send.call_args.args[0], "https://api.openai.com/v1/audio/transcriptions")
        self.assertIn("Bearer secret", send.call_args.kwargs["headers"].values())

    def test_whisper_502_retries_once_and_classifies_temporary_failure(self):
        class BadResponse:
            ok = False
            status_code = 502
        with patch("voice_alignment.requests.post", return_value=BadResponse()) as post, patch(
            "voice_alignment.time.sleep"
        ) as sleep:
            with self.assertRaisesRegex(TransientAudioAPIError, "502"):
                whisper_word_timestamps(b"audio", "voice.mp3", "secret")
        self.assertEqual(post.call_count, 2)
        sleep.assert_called_once()

    def test_whisper_502_then_success_recovers_timestamps(self):
        class Response:
            def __init__(self, code, body=None):
                self.status_code = code
                self.ok = code == 200
                self.body = body
            def json(self):
                return self.body
        good = Response(200, {"words": [
            {"word": "test", "start": 0.0, "end": 0.3},
        ]})
        with patch(
            "voice_alignment.requests.post",
            side_effect=[Response(502), good],
        ) as post, patch("voice_alignment.time.sleep"):
            stamped = whisper_word_timestamps(b"voice", "file.mp3", "secret")
        self.assertEqual(post.call_count, 2)
        self.assertEqual(stamped[0]["word"], "test")

    def test_401_is_not_silently_treated_as_transient(self):
        class Unauthorized:
            ok = False
            status_code = 401
        with patch("voice_alignment.requests.post", return_value=Unauthorized()) as post:
            with self.assertRaisesRegex(ValueError, "401"):
                whisper_word_timestamps(b"voice", "file.mp3", "bad")
        post.assert_called_once()

    def test_reject_oversized_or_missing_audio(self):
        with self.assertRaises(ValueError):
            whisper_word_timestamps(b"x" * (25 * 1024 * 1024 + 1), "large.mp3", "key")
        with self.assertRaises(ValueError):
            whisper_word_timestamps(b"small", "small.mp3", "")


if __name__ == "__main__":
    unittest.main()
