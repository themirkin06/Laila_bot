import ast
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class EmptyReplyGuardTests(unittest.TestCase):
    def test_horde_wait_extends_only_for_active_queued_or_processing_job(self):
        source = (ROOT / "ai.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        function = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "ai_horde_uret_sync"
        )
        function_source = ast.get_source_segment(source, function)
        self.assertIn('son_durum.get("waiting", 0)', function_source)
        self.assertIn('son_durum.get("processing", 0)', function_source)
        self.assertIn("aktif_is > 0 and not uzatma_yapildi", function_source)
        self.assertIn("AI_HORDE_TIMEOUT_GRACE", function_source)

    def test_turkish_square_bracketed_thought_is_removed_but_reply_survives(self):
        ai_source = (ROOT / "ai.py").read_text(encoding="utf-8")
        tree = ast.parse(ai_source)
        function = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "dusunce_bloklarini_sil"
        )
        module = ast.Module(body=[function], type_ignores=[])
        namespace = {"re": __import__("re")}
        exec(compile(module, str(ROOT / "ai.py"), "exec"), namespace)
        cleaner = namespace["dusunce_bloklarini_sil"]
        internal = "[Düşünce süreci: Kullanıcının mesajları oldukça doğrudan, arzulu ve yönlendirici. Bir cinsel etkileşim içindeyiz. "
        cleaned = cleaner(internal + "Tavrımı biraz değiştirmeliyim.]Merhaba, ne demek istediğini anladım.")
        self.assertEqual(cleaned, "Merhaba, ne demek istediğini anladım.")

    def test_unclosed_turkish_thought_block_is_discarded(self):
        ai_source = (ROOT / "ai.py").read_text(encoding="utf-8")
        tree = ast.parse(ai_source)
        function = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "dusunce_bloklarini_sil"
        )
        namespace = {"re": __import__("re")}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(ROOT / "ai.py"), "exec"), namespace)
        cleaner = namespace["dusunce_bloklarini_sil"]
        self.assertEqual(cleaner("[Düşünce süreci: modelin iç notu ve analiz"), "")

    def test_unbracketed_thought_header_is_removed_and_labeled_answer_survives(self):
        ai_source = (ROOT / "ai.py").read_text(encoding="utf-8")
        tree = ast.parse(ai_source)
        function = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "dusunce_bloklarini_sil"
        )
        namespace = {"re": __import__("re")}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(ROOT / "ai.py"), "exec"), namespace)
        cleaner = namespace["dusunce_bloklarini_sil"]
        result = cleaner("Düşünce süreci: İç not burada.\n\nCevap: Ben de seni özledim.")
        self.assertEqual(result, "Ben de seni özledim.")

    def test_unlabeled_thought_is_discarded_instead_of_leaked(self):
        ai_source = (ROOT / "ai.py").read_text(encoding="utf-8")
        tree = ast.parse(ai_source)
        function = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "dusunce_bloklarini_sil"
        )
        namespace = {"re": __import__("re")}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(ROOT / "ai.py"), "exec"), namespace)
        cleaner = namespace["dusunce_bloklarini_sil"]
        self.assertEqual(cleaner("Analysis: The user asked me to continue the scene."), "")

    def test_thought_leak_is_retried_and_never_fails_the_user_turn(self):
        source = (ROOT / "ai.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        function = next(
            node for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "llm_cevap"
        )
        function_source = ast.get_source_segment(source, function)
        self.assertIn("aynı modelle bir kez daha deneniyor", function_source)
        self.assertIn("deneme == 0", function_source)
        self.assertIn("ikinci denemede de güvenli yanıt", function_source)
        self.assertIn("Bir an için ne diyeceğimi toparlayamadım.", function_source)

    def test_ai_reply_has_nonempty_fallback_after_emoji_cleanup(self):
        tree = ast.parse((ROOT / "ai.py").read_text(encoding="utf-8"))
        function = next(
            node for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "llm_cevap"
        )
        source = ast.get_source_segment((ROOT / "ai.py").read_text(encoding="utf-8"), function)
        self.assertIn("emoji_dogal_uygula(cevap, karakter_key).strip()", source)
        self.assertIn("if not cevap:", source)
        self.assertIn("Bir an için ne diyeceğimi toparlayamadım.", source)

    def test_telegram_sender_never_passes_empty_text(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        function = next(
            node for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "mesajlari_gonder"
        )
        function_source = ast.get_source_segment(source, function)
        self.assertIn('cevap = (cevap or "").strip()', function_source)
        self.assertIn("if not cevap:", function_source)
        self.assertIn('text=guvenli', function_source)
        self.assertIn("text=duz", function_source)


if __name__ == "__main__":
    unittest.main()
