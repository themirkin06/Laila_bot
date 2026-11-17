import json
import pathlib
import unittest

import characters
from social_world import (
    WORLD_REDIS_KEY,
    append_scene_memories,
    create_character,
    discover_from_text,
    empty_world,
    find_character_key,
    normalize_world,
    social_scene_context,
    update_scene_cast,
)


ALL_MAIN = characters.KARAKTERLER


class SocialWorldTests(unittest.TestCase):
    def test_startup_world_is_empty_and_uses_a_separate_redis_key(self):
        world = empty_world()
        self.assertEqual(world["characters"], {})
        self.assertEqual(world["relationships"], [])
        self.assertEqual(WORLD_REDIS_KEY, "bot:sosyal_dunya:v1")

    def test_story_introduction_creates_one_stable_character_with_identity_and_relationship(self):
        world = empty_world()
        found = discover_from_text(
            world, "Ayşe'nin komşusu Hatice bugün ziyarete geldi.", "ayse", "Ayşe", ALL_MAIN,
        )
        self.assertEqual(len(found), 1)
        key = found[0]
        profile = world["characters"][key]
        again, created = create_character(world, "hatice", "komşu", "ayse", "Ayşe")
        self.assertFalse(created)
        self.assertEqual(again["key"], key)
        self.assertEqual(profile["appearance_prompt"], again["appearance_prompt"])
        self.assertEqual(profile["yas"], again["yas"])
        self.assertEqual(world["relationships"][0]["source"], "ayse")

    def test_named_npc_photo_request_discovers_person_even_with_turkish_suffix(self):
        world = empty_world()
        found = discover_from_text(
            world, "Hatice'nin fotoğrafını gönder.", "ayse", "Ayşe", ALL_MAIN,
        )
        self.assertEqual(len(found), 1)
        self.assertEqual(world["characters"][found[0]]["isim"], "Hatice")

    def test_multiple_people_can_join_and_depart_without_losing_memories(self):
        world = empty_world()
        state = {"sahne_katilimcilari": [], "son_yan_karakterler": []}
        joined, _ = update_scene_cast(
            state, "Ayşe'nin komşusu Hatice ziyarete geldi.", world, ALL_MAIN, "ayse",
        )
        self.assertEqual(len(joined), 1)
        first = joined[0]
        second_profile, _ = create_character(world, "Zeynep", "üniversite arkadaşı", "merve", "Merve")
        state["son_yan_karakterler"].append(second_profile["key"])
        joined, _ = update_scene_cast(
            state, "Zeynep de gelsin, bizimle otursun.", world, ALL_MAIN, "ayse",
        )
        self.assertEqual(len(state["sahne_katilimcilari"]), 2)
        self.assertEqual(joined, [second_profile["key"]])
        append_scene_memories(state, list(state["sahne_katilimcilari"]), "Hoş geldiniz.", "Ayşe: Merhaba!")
        _, departed = update_scene_cast(state, "Hatice eve dönsün.", world, ALL_MAIN, "ayse")
        self.assertEqual(departed, [first])
        self.assertNotIn(first, state["sahne_katilimcilari"])
        self.assertTrue(state["yan_karakter_hafizasi"][first])
        self.assertIn(first, world["characters"])

    def test_scene_context_keeps_side_speakers_separate_and_uses_private_memories(self):
        world = empty_world()
        profile, _ = create_character(world, "Hatice", "komşu", "ayse", "Ayşe")
        state = {
            "sahne_katilimcilari": [profile["key"]],
            "yan_karakter_hafizasi": {profile["key"]: [{"role": "user", "content": "Çay içelim."}]},
            "sosyal_olaylar": [],
        }
        context = social_scene_context(state, world, "ayse", "Ayşe")
        self.assertIn("Hatice — sahnede ve konuşabilir", context)
        self.assertIn("İsim: söz", context)
        self.assertIn("Çay içelim", context)

    def test_dynamic_identity_and_relationships_survive_json_redis_round_trip(self):
        world = empty_world()
        profile, _ = create_character(world, "Selin", "iş arkadaşı", "asli", "Aslı")
        saved = json.dumps(world, ensure_ascii=False)
        restored = normalize_world(json.loads(saved))
        self.assertEqual(restored["characters"][profile["key"]]["prompt"], profile["prompt"])
        self.assertEqual(restored["relationships"], world["relationships"])

    def test_ambiguous_duplicate_first_names_do_not_create_another_person(self):
        world = empty_world()
        create_character(world, "Hatice Yılmaz", "komşu", "ayse", "Ayşe")
        create_character(world, "Hatice Demir", "arkadaş", "merve", "Merve")
        self.assertIsNone(find_character_key("Hatice", world))
        profile, created = create_character(world, "Hatice", "tanıdık", "ayse", "Ayşe")
        self.assertFalse(created)
        self.assertEqual(profile, {})


if __name__ == "__main__":
    unittest.main()

