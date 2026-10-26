import unittest
from unittest.mock import patch

from voice_alignment import (
    align_target_words, audio_aligned_plan, whisper_word_timestamps,
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

    def test_reject_oversized_or_missing_audio(self):
        with self.assertRaises(ValueError):
            whisper_word_timestamps(b"x" * (25 * 1024 * 1024 + 1), "large.mp3", "key")
        with self.assertRaises(ValueError):
            whisper_word_timestamps(b"small", "small.mp3", "")


if __name__ == "__main__":
    unittest.main()
