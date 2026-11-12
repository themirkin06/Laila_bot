import importlib.util
import pathlib
import sys
import types
import unittest
from unittest.mock import patch


ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG_STUB = types.ModuleType("config")
CONFIG_STUB.DB_AKTIF = False
CONFIG_STUB.DB_ANAHTAR_ONEK = "bot:durum:"
CONFIG_STUB.HAFIZA_LIMITI = 40
CONFIG_STUB.UPSTASH_TOKEN = ""
CONFIG_STUB.UPSTASH_URL = ""
SPEC = importlib.util.spec_from_file_location("memory_under_test", ROOT / "memory.py")
MEMORY = importlib.util.module_from_spec(SPEC)
with patch.dict(sys.modules, {"config": CONFIG_STUB}):
    SPEC.loader.exec_module(MEMORY)


class UserMemoryTests(unittest.TestCase):
    def test_remembers_explicit_low_sensitivity_interest(self):
        state = {}
        profile = MEMORY.kullanici_bilgisi_ogren(state, "Ben kahve içmeyi çok seviyorum.")
        self.assertIn("kahve içmeyi", profile["bilgiler"])
        self.assertIn("kahve içmeyi", MEMORY.kullanici_profili_prompt(state))

    def test_does_not_infer_preferences_or_store_sensitive_statements(self):
        state = {}
        MEMORY.kullanici_bilgisi_ogren(state, "Bugün kahve içtim.")
        MEMORY.kullanici_bilgisi_ogren(state, "Adresim İstanbul'da.")
        MEMORY.kullanici_bilgisi_ogren(state, "Şifremi seviyorum.")
        self.assertEqual(MEMORY.kullanici_profili_al(state)["bilgiler"], [])

    def test_deduplicates_and_caps_remembered_interests(self):
        state = {}
        MEMORY.kullanici_bilgisi_ogren(state, "Hobim kitap okumak.")
        MEMORY.kullanici_bilgisi_ogren(state, "Hobim kitap okumak.")
        self.assertEqual(MEMORY.kullanici_profili_al(state)["bilgiler"], ["kitap okumak"])
        for index in range(14):
            MEMORY.kullanici_bilgisi_ogren(state, f"En sevdiğim şey{index} özel tercih.")
        self.assertLessEqual(len(MEMORY.kullanici_profili_al(state)["bilgiler"]), 12)


if __name__ == "__main__":
    unittest.main()
