import ast
import importlib.util
import pathlib
import re
import sys
import types
import unittest
from unittest.mock import patch

from PIL import Image

import characters

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG_STUB = types.ModuleType("config")
CONFIG_STUB.AI_HORDE_IMAGE_API_KEY = "test-key"
CONFIG_STUB.AI_HORDE_IMAGE_MAX_WAIT = 30
CONFIG_STUB.AI_HORDE_IMAGE_MODEL = "test-image-model"
CONFIG_STUB.CF_ACCOUNT_ID = ""
CONFIG_STUB.CF_API_TOKEN = ""
CONFIG_STUB.CF_AKTIF = False
CONFIG_STUB.CF_IMAGE_MODEL = "test-image-model"
PHOTOS_SPEC = importlib.util.spec_from_file_location("photos_under_test", ROOT / "photos.py")
photos = importlib.util.module_from_spec(PHOTOS_SPEC)
with patch.dict(sys.modules, {"config": CONFIG_STUB}):
    PHOTOS_SPEC.loader.exec_module(photos)


ALL_KEYS = ("leyla", "merve", "asli", "dilek", "ece", "ayse", "dondu")


class PhotoPromptTests(unittest.TestCase):
    def test_all_seven_characters_have_individual_identity_scene_and_default_clothing(self):
        self.assertEqual(set(ALL_KEYS), set(characters.FOTO_KISI))
        self.assertEqual(set(ALL_KEYS), set(characters.FOTO_SAHNELER))
        self.assertEqual(set(ALL_KEYS), set(characters.FOTO_VARSAYILAN_KIYAFET))
        for key in ALL_KEYS:
            with self.subTest(character=key):
                prompt = characters.foto_promptu(characters.KARAKTERLER[key])
                self.assertIn(characters.FOTO_KISI[key], prompt)
                self.assertTrue(characters.FOTO_SAHNELER[key])

    def test_leyla_and_ayse_headscarves_are_optional_when_outfit_is_requested(self):
        request = (
            "USER PHOTO REQUEST (highest priority): Wearing a bright blue dress without a headscarf.\n"
            "Requested framing: natural medium portrait framing.\n"
            "CONVERSATION CONTEXT (continuity only): Previous scene shows her in her usual clothes."
        )
        for key in ("leyla", "ayse"):
            with self.subTest(character=key):
                for closeness in (0, 3):
                    prompt = characters.foto_promptu(
                        characters.KARAKTERLER[key], yakinlik=closeness, scene_prompt=request,
                    )
                    self.assertIn("bright blue dress without a headscarf", prompt)
                    self.assertIn("do not retain, add, or substitute any default headscarf", prompt)
                    self.assertNotIn(characters.FOTO_VARSAYILAN_KIYAFET[key], prompt)

        turkish_request = (
            "USER PHOTO REQUEST (highest priority): Başörtüsüz, beyaz bir elbiseyle fotoğraf gönder.\n"
            "CONVERSATION CONTEXT (continuity only): Her zamanki kıyafeti."
        )
        self.assertTrue(characters.foto_istegindeki_kiyafeti_bul(turkish_request))

    def test_full_length_prompt_requires_uncropped_head_to_toe_and_feet(self):
        request = (
            "USER PHOTO REQUEST (highest priority): Fotoğrafını tam boy gönder, ayakların da görünsün.\n"
            "Requested framing: full-length, head to toe, full outfit and both feet visible without cropping.\n"
            "CONVERSATION CONTEXT (continuity only): Previous portrait is close-up."
        )
        prompt = characters.foto_promptu(characters.KARAKTERLER["merve"], scene_prompt=request)
        self.assertIn("soles of both feet", prompt)
        self.assertIn("do not crop any part", prompt)

    def test_current_request_is_separated_from_lower_priority_conversation_context(self):
        tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
        function = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "foto_konusma_baglamini_olustur"
        )
        namespace = {"re": re}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "main.py", "exec"), namespace)
        result = namespace[function.name]([], "Kırmızı elbise giy ve tam boy çek.")
        self.assertLess(result.index("USER PHOTO REQUEST (highest priority)"), result.index("CONVERSATION CONTEXT (continuity only)"))
        self.assertIn("Requested framing: full-length", result)

    def test_gallery_uses_saved_pool_photos_without_running_generation(self):
        tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
        function = next(
            node for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "karakter_galerisi_goster"
        )
        calls = {
            node.func.attr for node in ast.walk(function)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        self.assertNotIn("foto_uret_bytes", calls)
        self.assertNotIn("get_file", calls)
        self.assertIn("send_media_group", calls)
        self.assertIn("send_photo", calls)

    def test_explicit_foot_visibility_phrasing_triggers_photo_and_full_length(self):
        tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
        pattern_assignment = next(
            node for node in tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "FOTO_KALIBI" for target in node.targets)
        )
        namespace = {"re": re}
        exec(compile(ast.Module(body=[pattern_assignment], type_ignores=[]), "main.py", "exec"), namespace)
        full_length = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "foto_konusma_baglamini_olustur"
        )
        exec(compile(ast.Module(body=[full_length], type_ignores=[]), "main.py", "exec"), namespace)
        request = "Ayaklarım da görünsün, fotoğrafını tam boy gönder."
        self.assertTrue(namespace["FOTO_KALIBI"].search(request))
        scene = namespace[full_length.name]([], request)
        self.assertIn("Requested framing: full-length", scene)

    def test_denoising_strength_is_conservative_and_increases_only_for_edits(self):
        self.assertEqual(photos._denoising_strength(""), 0.42)
        outfit = "USER PHOTO REQUEST (highest priority): Wear a red dress."
        self.assertEqual(photos._denoising_strength(outfit), 0.47)
        full_body = "Requested framing: full-length, head to toe."
        self.assertEqual(photos._denoising_strength(full_body), 0.50)

    def test_full_length_reference_uses_portrait_canvas_and_standard_keeps_source_ratio(self):
        from io import BytesIO

        source = BytesIO()
        Image.new("RGB", (512, 512), "white").save(source, format="PNG")
        full_webp, width, height = photos._source_to_webp(source.getvalue(), full_length=True)
        self.assertEqual((width, height), (768, 1024))
        with Image.open(BytesIO(full_webp)) as framed:
            self.assertEqual(framed.getpixel((384, 900)), (127, 127, 127))
        _, width, height = photos._source_to_webp(source.getvalue(), full_length=False)
        self.assertEqual((width, height), (512, 512))


if __name__ == "__main__":
    unittest.main()
