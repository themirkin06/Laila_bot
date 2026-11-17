import ast
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class ConversationGuidanceTests(unittest.TestCase):
    def test_shared_guidance_covers_context_and_adaptive_question_frequency(self):
        source = (ROOT / "ai.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        function = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "llm_cevap")
        assignment = next(
            node for node in function.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "dogal_sohbet_kilavuzu" for target in node.targets)
        )
        literals = [node.value for node in ast.walk(assignment) if isinstance(node, ast.Constant) and isinstance(node.value, str)]
        guidance = " ".join(literals)
        for phrase in (
            "Ben çıkıyorum",
            "Sonra ne oldu?",
            "Soru sıklığını konuşmanın ritmine göre ayarla",
            "kullanıcı yanıt vermeden yeni bir soru ekleme",
            "ortak yönerge onları tek bir konuşma tarzına sokmasın",
        ):
            self.assertIn(phrase, guidance)

    def test_character_profiles_and_individual_voice_definitions_remain(self):
        namespace = {}
        exec(compile((ROOT / "characters.py").read_text(encoding="utf-8"), "characters.py", "exec"), namespace)
        profiles = namespace["KARAKTERLER"]
        names = {profiles[key]["isim"] for key in profiles}
        self.assertEqual(names, {"Leyla", "Merve", "Aslı", "Dilek", "Ece", "Ayşe", "Asena"})
        for key in ("leyla", "merve", "asli", "dilek", "ece", "ayse", "dondu"):
            self.assertIn(namespace["KARAKTER_PROMPTLARI"][key], profiles[key]["prompt"])

    def test_ai_horde_provider_and_selected_model_are_pinned(self):
        source = (ROOT / "ai.py").read_text(encoding="utf-8")
        self.assertIn('LLM_PROVIDER = "aihorde"', source)
        self.assertIn('AI_HORDE_MODELS = "koboldcpp/G4-MeroMero-26B-A4B-it-uncensored-heretic"', source)
        self.assertIn("No automatic provider fallback", source)

    def test_adult_chat_and_dialogue_guidance_keep_personality_and_no_fixed_length(self):
        config = (ROOT / "config.py").read_text(encoding="utf-8")
        characters = (ROOT / "characters.py").read_text(encoding="utf-8")
        ai = (ROOT / "ai.py").read_text(encoding="utf-8")
        self.assertIn("argo ve küfür karakterin kişiliğine", config.casefold())
        self.assertIn("Sabit kelime sınırın yok", characters)
        self.assertIn("Sabit kelime veya cümle sınırın yok", ai)


    def test_each_character_has_a_distinct_adult_voice_profile(self):
        namespace = {}
        exec(compile((ROOT / "characters.py").read_text(encoding="utf-8"), "characters.py", "exec"), namespace)
        profiles = namespace["NSFW_KARAKTER_SESLERI"]
        self.assertEqual(set(profiles), {"leyla", "merve", "asli", "dilek", "ece", "ayse", "dondu"})
        self.assertEqual(len(set(profiles.values())), 7)
        self.assertTrue(all("Cesaret " in profile for profile in profiles.values()))
        config = (ROOT / "config.py").read_text(encoding="utf-8")
        characters = (ROOT / "characters.py").read_text(encoding="utf-8")
        self.assertIn("yalnızca imaya veya üstü kapalı dile", config.casefold())
        self.assertIn("Normal sohbeti cinselleştirme", config)
        self.assertIn("her turda flört üretme", config.casefold())
        self.assertIn("karakterin sesine uygun doğrudan kelimeler", characters.casefold())
        ai_source = (ROOT / "ai.py").read_text(encoding="utf-8")
        self.assertIn("modelin iç muhakemesi", ai_source)
        self.assertIn("*italik*", ai_source)
        self.assertIn(r"<\|channel\|>", ai_source)
        self.assertIn("NSFW_KARAKTER_SESLERI.get(karakter_key", ai_source)
        self.assertIn("aynı cinsel ifade ve açılışları tekrarlama", ai_source.casefold())

    def test_changed_python_modules_parse(self):
        for filename in ("ai.py", "characters.py", "photos.py", "main.py", "config.py", "voice.py", "scene_memory.py"):
            ast.parse((ROOT / filename).read_text(encoding="utf-8"), filename=filename)


if __name__ == "__main__":
    unittest.main()

