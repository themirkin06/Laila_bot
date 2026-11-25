import json
import unittest

from scene_memory import explicit_destination, scene_state_context, update_scene_state


class SceneMemoryTests(unittest.TestCase):
    def test_only_explicit_movement_to_a_known_place_updates_location(self):
        state = {"scene_states": {"leyla": {"location": None, "companions": []}}}
        self.assertTrue(update_scene_state(state, "leyla", "Mutfakta televizyonu kapatıp mutfağa geçtim."))
        self.assertEqual(state["scene_states"]["leyla"]["location"], "mutfağa")
        self.assertIsNone(explicit_destination("Birazdan işe başlayacağım."))
        self.assertIsNone(explicit_destination("Sana doğru geliyorum."))
        state["scene_states"]["leyla"]["location"] = "ev"
        self.assertFalse(update_scene_state(state, "leyla", "Merve'ye gidiyorum.", known_people=["Merve"]))
        self.assertEqual(state["scene_states"]["leyla"]["location"], "ev")

    def test_unknown_or_ambiguous_destination_never_replaces_last_known_place(self):
        state = {"scene_states": {"leyla": {"location": "ev", "companions": []}}}
        changed = update_scene_state(state, "leyla", "Biraz kahve içmeye gidiyorum.")
        self.assertFalse(changed)
        self.assertEqual(state["scene_states"]["leyla"]["location"], "ev")
        self.assertIn("Karakterin son açıkça belirtilen konumu: ev", scene_state_context(state, "leyla"))
        self.assertIn("son bilinen durumu koru", scene_state_context({}, "leyla"))

    def test_named_destination_and_companions_survive_json_round_trip(self):
        state = {}
        self.assertTrue(update_scene_state(state, "asli", "Yıldız Parkı'na gidiyoruz.", ["Hatice", "Zeynep"]))
        restored = json.loads(json.dumps(state, ensure_ascii=False))
        self.assertEqual(restored["scene_states"]["asli"]["location"], "Yıldız Parkı'na")
        context = scene_state_context(restored, "asli")
        self.assertIn("Hatice, Zeynep", context)

    def test_coming_means_on_the_way_not_arrived(self):
        state = {}
        self.assertTrue(update_scene_state(state, "leyla", "Yanına geliyorum.", speaker="user"))
        context = scene_state_context(state, "leyla")
        self.assertIn("henüz varmış", context)
        self.assertEqual(state["scene_states"]["leyla"]["user_presence"], "yolda")

    def test_arrival_phrases_mark_togetherness(self):
        for phrase in ("Geldim.", "Kapıdayım.", "İçeri girdim."):
            with self.subTest(phrase=phrase):
                state = {}
                update_scene_state(state, "leyla", phrase, speaker="user")
                self.assertEqual(state["scene_states"]["leyla"]["user_presence"], "birlikte")

    def test_character_travel_to_user_is_tracked_separately(self):
        state = {}
        update_scene_state(state, "leyla", "Senin yanına geliyorum.", speaker="character")
        self.assertEqual(state["scene_states"]["leyla"]["character_presence"], "kullaniciya_yolda")
        self.assertNotIn("user_presence", state["scene_states"]["leyla"])
        self.assertIn("Karakter kullanıcıya doğru yolda", scene_state_context(state, "leyla"))


if __name__ == "__main__":
    unittest.main()
