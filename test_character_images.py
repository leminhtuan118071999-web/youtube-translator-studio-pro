"""Character references: safe names, actual PNG responses, ZIP and isolation."""
import base64
import io
import unittest
import zipfile
from unittest.mock import patch

from character_images import (
    IMAGE_STORE, CharacterImageStore, character_specs,
    create_character_png, filename_part, session_images_zip,
    detailed_character_profiles, character_reference_description,
)


PNG = b"\x89PNG\r\n\x1a\n" + b"fake-png-data"


class CharacterImagesTests(unittest.TestCase):
    def test_extracts_named_characters_without_duplicates(self):
        profile = {
            "character_bible": "Ala: hair black, a red coat for every scene.",
            "characters": [
                {"name": "Ala", "description": "Black hair, red coat"},
                {"name": "Ola", "description": "Blue jacket, blonde hair"},
                {"name": "Ala", "description": "Duplicate"},
            ],
        }
        self.assertEqual(
            character_specs(profile),
            [("Ala", "Black hair, red coat"), ("Ola", "Blue jacket, blonde hair")]
        )

    def test_fallback_colon_line_and_maximum_characters(self):
        profile = {"character_bible": "\n".join(
            f"Name{i}: A person with distinct clothes and face {i}"
            for i in range(20)
        )}
        self.assertEqual(len(character_specs(profile)), 8)

    def test_complete_named_profiles_are_kept_individually(self):
        profile = {"characters": [
            {"name": "Tấm", "description": "Young protagonist in plain clothes",
             "role": "Nhân vật chính", "age": "thiếu nữ (đề xuất)",
             "face": "mặt trái xoan", "hair": "tóc đen dài",
             "outfit": "áo nâu, váy thẫm", "palette": "nâu, đen",
             "signature": "khăn lụa", "source_notes": "Màu áo là đề xuất",
             "reference_prompt": "Full-body character sheet, face visible"},
            {"name": "Cám", "description": "A recurring antagonist",
             "face": "mặt tròn", "outfit": "áo xanh"},
        ]}
        sheets = detailed_character_profiles(profile)
        self.assertEqual([sheet["name"] for sheet in sheets], ["Tấm", "Cám"])
        self.assertEqual(sheets[0]["age"], "thiếu nữ (đề xuất)")
        self.assertEqual(sheets[1]["face"], "mặt tròn")
        self.assertEqual(sheets[1]["hair"], "")
        ready = character_reference_description(sheets[0])
        self.assertIn("mặt trái xoan", ready)
        self.assertIn("áo nâu", ready)
        self.assertIn("Full-body character sheet", ready)

    def test_legacy_bible_can_be_shown_without_false_details(self):
        sheets = detailed_character_profiles({
            "character_bible": "Linh: Red scarf and medium-length black hair."
        })
        self.assertEqual(len(sheets), 1)
        self.assertEqual(sheets[0]["description"], "Red scarf and medium-length black hair.")
        self.assertEqual(sheets[0]["age"], "")

    def test_names_are_sanitized_and_each_session_has_distinct_zip(self):
        self.assertEqual(filename_part("Ala/evil?.png"), "Ala_evil_.png")
        name, result = session_images_zip(
            {"Ala/hero": PNG, "Ola": PNG}, "Phiên 12"
        )
        self.assertIn("Phiên_12", name)
        with zipfile.ZipFile(io.BytesIO(result)) as archive:
            names = archive.namelist()
            self.assertEqual(names, ["Ala_hero.png", "Ola.png"])
            self.assertTrue(all(archive.read(n) == PNG for n in names))
        second = CharacterImageStore()
        second.save("account:1", "session1", "Ala", PNG)
        self.assertFalse(second.images("account:1", "session2"))
        self.assertFalse(second.images("account:2", "session1"))
        second.clear("account:1", "session1")
        self.assertFalse(second.images("account:1", "session1"))

    def test_real_image_endpoint_response_decoded_and_key_never_leaked(self):
        class Response:
            ok = True
            status_code = 200

            def json(self):
                return {"data": [{"b64_json": base64.b64encode(PNG).decode()}]}
        with patch("character_images.requests.post", return_value=Response()) as send:
            image = create_character_png(
                "KEY_SECRET", "Ala", "Black hair, red coat",
                style="2D", bible="Ala keeps the same red coat"
            )
        self.assertEqual(image, PNG)
        self.assertEqual(
            send.call_args.args[0],
            "https://api.openai.com/v1/images/generations",
        )
        self.assertEqual(send.call_args.kwargs["json"]["n"], 1)
        self.assertIn("Bearer KEY_SECRET", send.call_args.kwargs["headers"].values())

    def test_401_diagnostic_explains_separate_openai_key(self):
        class Unauthorized:
            ok = False
            status_code = 401
        with patch("character_images.requests.post", return_value=Unauthorized()):
            with self.assertRaisesRegex(RuntimeError, "OpenAI.*API key") as err:
                create_character_png(
                    "very-private-key", "Ala", "Red clothes",
                    style="2D", bible="Ala wears red",
                )
        self.assertIn("Groq", str(err.exception))
        self.assertIn("Chạy lại riêng", str(err.exception))
        self.assertNotIn("very-private-key", str(err.exception))

    def test_403_and_429_are_reported_distinctly(self):
        class Rejected:
            ok = False
            def __init__(self, code):
                self.status_code = code
        for code, expected in ((403, "quyền"), (429, "quota")):
            with patch("character_images.requests.post", return_value=Rejected(code)):
                with self.assertRaises(RuntimeError) as err:
                    create_character_png(
                        "secret", "Ala", "Red clothes",
                        style="2D", bible="",
                    )
            self.assertIn(expected, str(err.exception))

    def test_error_avoids_exposing_image_credentials(self):
        class Response:
            ok = False
            status_code = 401
        with patch("character_images.requests.post", return_value=Response()):
            with self.assertRaisesRegex(RuntimeError, "401") as error:
                create_character_png("very-private-key", "Ala", "Red coat",
                                     style="2D", bible="")
        self.assertNotIn("very-private-key", str(error.exception))


if __name__ == "__main__":
    unittest.main()
