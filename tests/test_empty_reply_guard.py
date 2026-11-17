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
