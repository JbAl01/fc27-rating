"""Roles not fetched yet are estimated from known cards with the same position and OVR (20.10: Stanway, Joan
García and most evo cards had 0 role points only because FUT.GG had not fetched their page)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fcrating.model import ROLE_ESTIMATE, impute_roles, load_config, role_bonus  # noqa: E402
from fcrating.schema import Player  # noqa: E402

CFG = load_config(ROOT / "config")


def card(name, ovr, pos="CM", roles=None, known=True, alts=()):
    return Player(name=name, position=pos, alt_positions=list(alts), ovr=ovr, attributes={}, id=name,
                  roles=roles or {}, roles_complete=known)


class RoleImputeTests(unittest.TestCase):
    def test_unknown_roles_get_the_level_of_known_cards(self):
        known = [card(f"K{i}", 87, roles={"CM": {"Box-to-Box": 2}}) for i in range(25)]
        known += [card(f"L{i}", 72, roles={"CM": {"Playmaker": 1}}) for i in range(25)]
        gold, low = card("Ny", 86, known=False), card("Lav", 71, known=False)
        n = impute_roles(known + [gold, low])
        self.assertEqual(n, 2)
        self.assertEqual(gold.roles, {"CM": {ROLE_ESTIMATE: 2}})
        self.assertEqual(low.roles, {"CM": {ROLE_ESTIMATE: 1}})
        self.assertEqual(known[0].roles, {"CM": {"Box-to-Box": 2}})          # known roles are never touched

    def test_estimated_roles_count_like_known_ones(self):
        a = card("A", 86, roles={"CM": {"Box-to-Box": 2}})
        b = card("B", 86, roles={"CM": {ROLE_ESTIMATE: 2}}, known=False)
        w = CFG["weights"]
        self.assertEqual(role_bonus(a, "CM", w)[0], role_bonus(b, "CM", w)[0])
        self.assertEqual(role_bonus(b, "CM", w)[0], 2.0)

    def test_no_known_cards_no_guess(self):
        p = card("Alene", 80, known=False)
        impute_roles([p])
        self.assertEqual(p.roles, {})


if __name__ == "__main__":
    unittest.main()
