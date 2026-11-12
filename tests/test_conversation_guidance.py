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

    def test_changed_python_modules_parse(self):
        for filename in ("ai.py", "characters.py"):
            ast.parse((ROOT / filename).read_text(encoding="utf-8"), filename=filename)


if __name__ == "__main__":
    unittest.main()
