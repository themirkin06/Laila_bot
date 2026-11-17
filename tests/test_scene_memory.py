import json
import unittest

from scene_memory import explicit_destination, scene_state_context, update_scene_state


class SceneMemoryTests(unittest.TestCase):
    def test_only_explicit_movement_to_a_known_place_updates_location(self):
        state = {"scene_states": {"leyla": {"location": None, "companions": []}}}
        self.assertTrue(update_scene_state(state, "leyla", "Mutfakta televizyonu kapat\u0131p mutfa\u011fa ge\u00e7tim."))
        self.assertEqual(state["scene_states"]["leyla"]["location"], "mutfa\u011fa")
        self.assertIsNone(explicit_destination("Birazdan i\u015fe ba\u015flayaca\u011f\u0131m."))
        self.assertIsNone(explicit_destination("Sana do\u011fru geliyorum."))
        state["scene_states"]["leyla"]["location"] = "ev"
        self.assertFalse(update_scene_state(state, "leyla", "Merve'ye gidiyorum.", known_people=["Merve"]))
        self.assertEqual(state["scene_states"]["leyla"]["location"], "ev")

    def test_unknown_or_ambiguous_destination_never_replaces_last_known_place(self):
        state = {"scene_states": {"leyla": {"location": "ev", "companions": []}}}
        changed = update_scene_state(state, "leyla", "Biraz kahve i\u00e7meye gidiyorum.")
        self.assertFalse(changed)
        self.assertEqual(state["scene_states"]["leyla"]["location"], "ev")
        self.assertIn("Son a\u00e7\u0131k\u00e7a belirtilen konum: ev", scene_state_context(state, "leyla"))
        self.assertIn("son bilinen durumu koru", scene_state_context({}, "leyla"))

    def test_named_destination_and_companions_survive_redis_json_round_trip(self):
        state = {}
        update_scene_state(state, "asli", "Y\u0131ld\u0131z Park\u0131'na gidiyoruz.", ["Hatice", "Zeynep"])
        restored = json.loads(json.dumps(state, ensure_ascii=False))
        self.assertEqual(restored["scene_states"]["asli"]["location"], "Y\u0131ld\u0131z Park\u0131'na")
        context = scene_state_context(restored, "asli")
        self.assertIn("Hatice, Zeynep", context)


if __name__ == "__main__":
    unittest.main()

