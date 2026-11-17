import ast
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class EmptyReplyGuardTests(unittest.TestCase):
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
