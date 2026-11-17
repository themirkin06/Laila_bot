import unittest

from voice import VOICE_PROFILES, resolve_voice_style


class VoiceStyleTests(unittest.TestCase):
    def test_character_and_emotion_change_delivery_parameters(self):
        neutral = resolve_voice_style("leyla", "Bugün buradayım.")
        happy = resolve_voice_style("leyla", "Harika, çok sevindim!")
        sad = resolve_voice_style("leyla", "Üzüldüm, özledim.")
        self.assertEqual(happy[2], "bright")
        self.assertEqual(sad[2], "sad")
        self.assertNotEqual(neutral[:2], happy[:2])
        self.assertNotEqual(happy[:2], sad[:2])

    def test_all_characters_have_a_turkish_voice_and_parameters_stay_bounded(self):
        self.assertTrue(all(voice.startswith("tr-TR-") for voice in VOICE_PROFILES.values()))
        for key in VOICE_PROFILES:
            rate, pitch, _ = resolve_voice_style(key, "Öfkeliyim, yeter artık!")
            self.assertGreaterEqual(int(rate.rstrip("%")), -18)
            self.assertLessEqual(int(rate.rstrip("%")), 18)
            self.assertGreaterEqual(int(pitch.rstrip("Hz")), -3)
            self.assertLessEqual(int(pitch.rstrip("Hz")), 3)


if __name__ == "__main__":
    unittest.main()

