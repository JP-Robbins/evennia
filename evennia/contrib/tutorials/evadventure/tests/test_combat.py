"""
Test EvAdventure combat.

"""

from collections import deque
from unittest.mock import Mock, call, patch

from evennia.utils import create
from evennia.utils.test_resources import BaseEvenniaTest

from .. import combat_turnbased as combat
from ..characters import EvAdventureCharacter
from ..enums import Ability, WieldLocation
from ..npcs import EvAdventureMob
from ..objects import EvAdventureConsumable, EvAdventureRunestone, EvAdventureWeapon
from ..rooms import EvAdventureRoom
from .mixins import EvAdventureMixin


class EvAdventureCombatHandlerTest(BaseEvenniaTest):
    """
    Test methods on the turn-based combat handler

    """

    maxDiff = None

    # make sure to mock away all time-keeping elements
    @patch(
        "evennia.contrib.tutorials.evadventure.combat_turnbased.EvAdventureCombatHandler.interval",
        new=-1,
    )
    @patch(
        "evennia.contrib.tutorials.evadventure.combat_turnbased.delay",
        new=Mock(return_value=None),
    )
    def setUp(self):
        super().setUp()

        self.location = create.create_object(EvAdventureRoom, key="testroom")
        self.combatant = create.create_object(
            EvAdventureCharacter, key="testchar", location=self.location
        )

        self.location.allow_combat = True
        self.location.allow_death = True

        self.target = create.create_object(
            EvAdventureMob,
            key="testmonster",
            location=self.location,
            attributes=(("is_idle", True),),
        )

        # mock the msg so we can check what they were sent later
        self.combatant.msg = Mock()
        self.target.msg = Mock()

        self.combathandler = combat.get_or_create_combathandler(self.combatant)
        # add target to combat
        self.combathandler.add_combatants(self.target)

    def _get_action(self, action_dict={"key": "nothing"}):
        action_class = self.combathandler.action_classes[action_dict["key"]]
        return action_class(self.combathandler, self.combatant, action_dict)

    def _run_actions(
        self, action_dict, action_dict2={"key": "nothing"}, combatant_msg=None, target_msg=None
    ):
        """
        Helper method to run an action and check so combatant saw the expected message.
        """
        self.combathandler.queue_action(self.combatant, action_dict)
        self.combathandler.queue_action(self.target, action_dict2)
        self.combathandler.execute_full_turn()
        if combatant_msg is not None:
            # this works because we mock combatant.msg in SetUp
            self.combatant.msg.assert_called_with(combatant_msg)
        if target_msg is not None:
            # this works because we mock target.msg in SetUp
            self.combatant.msg.assert_called_with(target_msg)

    def test_combatanthandler_setup(self):
        """Testing all is set up correctly in the combathandler"""

        chandler = self.combathandler
        self.assertEqual(dict(chandler.combatants), {self.combatant: deque(), self.target: deque()})
        self.assertEqual(
            dict(chandler.action_classes),
            {
                "nothing": combat.CombatActionDoNothing,
                "attack": combat.CombatActionAttack,
                "stunt": combat.CombatActionStunt,
                "use": combat.CombatActionUseItem,
                "wield": combat.CombatActionWield,
                "flee": combat.CombatActionFlee,
                "hinder": combat.CombatActionHinder,
            },
        )
        self.assertEqual(chandler.flee_timeout, 1)
        self.assertEqual(dict(chandler.advantage_matrix), {})
        self.assertEqual(dict(chandler.disadvantage_matrix), {})
        self.assertEqual(dict(chandler.fleeing_combatants), {})
        self.assertEqual(dict(chandler.defeated_combatants), {})

    def test_combathandler_msg(self):
        """Test sending messages to all in handler"""

        self.location.msg_contents = Mock()

        self.combathandler.msg("test_message")

        self.location.msg_contents.assert_called_with(
            "test_message",
            exclude=[],
            from_obj=None,
            mapping={"testchar": self.combatant, "testmonster": self.target},
        )

    def test_remove_combatant(self):
        """Remove a combatant."""

        self.combathandler.remove_combatant(self.target)

        self.assertEqual(dict(self.combathandler.combatants), {self.combatant: deque()})

    def test_stop_combat(self):
        """Stopping combat, making sure combathandler is deleted."""

        self.combathandler.stop_combat()
        self.assertIsNone(self.combathandler.pk)

    def test_get_sides(self):
        """Getting the sides of combat"""

        combatant2 = create.create_object(
            EvAdventureCharacter, key="testchar2", location=self.location
        )
        target2 = create.create_object(
            EvAdventureMob,
            key="testmonster2",
            location=self.location,
            attributes=(("is_idle", True),),
        )
        self.combathandler.add_combatants(combatant2, target2)

        # allies to combatant
        allies, enemies = self.combathandler.get_sides(self.combatant)
        self.assertEqual((allies, enemies), ([combatant2], [self.target, target2]))

        # allies to monster
        allies, enemies = self.combathandler.get_sides(self.target)
        self.assertEqual((allies, enemies), ([target2], [self.combatant, combatant2]))

    def test_queue_and_execute_action(self):
        """Queue actions and execute"""

        donothing = {"key": "nothing"}

        self.combathandler.queue_action(self.combatant, donothing)
        self.assertEqual(
            dict(self.combathandler.combatants),
            {self.combatant: deque([donothing]), self.target: deque()},
        )

        mock_action = Mock()
        self.combathandler.action_classes["nothing"] = Mock(return_value=mock_action)

        self.combathandler.execute_next_action(self.combatant)

        self.combathandler.action_classes["nothing"].assert_called_with(
            self.combathandler, self.combatant, donothing
        )
        mock_action.execute.assert_called_once()

    def test_execute_full_turn(self):
        """Run a full (passive) turn"""

        donothing = {"key": "nothing"}

        self.combathandler.queue_action(self.combatant, donothing)
        self.combathandler.queue_action(self.target, donothing)

        self.combathandler.execute_next_action = Mock()

        self.combathandler.execute_full_turn()

        self.combathandler.execute_next_action.assert_has_calls(
            [call(self.combatant), call(self.target)], any_order=True
        )

    def test_combat_action(self):
        """General tests of action functionality"""

        combatant = self.combatant
        target = self.target

        action = self._get_action({"key": "nothing"})

        self.assertTrue(action.can_use())

        action.give_advantage(combatant, target)
        action.give_disadvantage(combatant, target)

        self.assertTrue(action.has_advantage(combatant, target))
        self.assertTrue(action.has_disadvantage(combatant, target))

        action.lose_advantage(combatant, target)
        action.lose_disadvantage(combatant, target)

        self.assertFalse(action.has_advantage(combatant, target))
        self.assertFalse(action.has_disadvantage(combatant, target))

        action.flee(combatant)
        self.assertIn(combatant, self.combathandler.fleeing_combatants)

        action.unflee(combatant)
        self.assertNotIn(combatant, self.combathandler.fleeing_combatants)

        action.msg(f"$You() attack $You({target.key}).")
        combatant.msg.assert_called_with(text=("You attack testmonster.", {}), from_obj=combatant)

    def test_action__do_nothing(self):
        """Do nothing"""

        actiondict = {"key": "nothing"}
        self._run_actions(actiondict, actiondict)
        self.assertEqual(self.combathandler.turn, 1)

        self.combatant.msg.assert_not_called()

    @patch("evennia.contrib.tutorials.evadventure.combat_turnbased.rules.randint")
    def test_attack__miss(self, mock_randint):

        actiondict = {"key": "attack", "target": self.target}

        mock_randint.return_value = 8  # target has default armor 11, so 8+1 str will miss
        self._run_actions(actiondict)
        self.assertEqual(self.target.hp, 4)

    @patch("evennia.contrib.tutorials.evadventure.combat_turnbased.rules.randint")
    def test_attack__success__still_alive(self, mock_randint):
        actiondict = {"key": "attack", "target": self.target}

        mock_randint.return_value = 11  # 11 + 1 str will hit beat armor 11
        # make sure target survives
        self.target.hp = 20
        self._run_actions(actiondict)
        self.assertEqual(self.target.hp, 9)

    @patch("evennia.contrib.tutorials.evadventure.combat_turnbased.rules.randint")
    def test_attack__success__kill(self, mock_randint):
        actiondict = {"key": "attack", "target": self.target}

        mock_randint.return_value = 11  # 11 + 1 str will hit beat armor 11
        self._run_actions(actiondict)
        self.assertEqual(self.target.hp, -7)
        # after this the combat is over
        self.assertIsNone(self.combathandler.pk)

    @patch("evennia.contrib.tutorials.evadventure.combat_turnbased.rules.randint")
    def test_stunt_fail(self, mock_randint):
        action_dict = {
            "key": "stunt",
            "recipient": self.combatant,
            "target": self.target,
            "advantage": True,
            "stunt_type": Ability.STR,
            "defense_type": Ability.DEX,
        }
        mock_randint.return_value = 8  # fails 8+1 dex vs DEX 11 defence
        self._run_actions(action_dict)
        self.assertEqual(self.combathandler.advantage_matrix[self.combatant], {})
        self.assertEqual(self.combathandler.disadvantage_matrix[self.combatant], {})

    @patch("evennia.contrib.tutorials.evadventure.combat_turnbased.rules.randint")
    def test_stunt_advantage__success(self, mock_randint):
        action_dict = {
            "key": "stunt",
            "recipient": self.combatant,
            "target": self.target,
            "advantage": True,
            "stunt_type": Ability.STR,
            "defense_type": Ability.DEX,
        }
        mock_randint.return_value = 11  #  11+1 dex vs DEX 11 defence is success
        self._run_actions(action_dict)
        self.assertEqual(
            bool(self.combathandler.advantage_matrix[self.combatant][self.target]), True
        )

    @patch("evennia.contrib.tutorials.evadventure.combat_turnbased.rules.randint")
    def test_stunt_disadvantage__success(self, mock_randint):
        action_dict = {
            "key": "stunt",
            "recipient": self.target,
            "target": self.combatant,
            "advantage": False,
            "stunt_type": Ability.STR,
            "defense_type": Ability.DEX,
        }
        mock_randint.return_value = 11  #  11+1 dex vs DEX 11 defence is success
        self._run_actions(action_dict)
        self.assertEqual(
            bool(self.combathandler.disadvantage_matrix[self.target][self.combatant]), True
        )

    def test_use_item(self):
        """
        Use up a potion during combat.

        """
        item = create.create_object(
            EvAdventureConsumable, key="Healing potion", attributes=[("uses", 2)]
        )

        item.use = Mock()

        action_dict = {
            "key": "use",
            "item": item,
            "target": self.target,
        }

        self.assertEqual(item.uses, 2)
        self._run_actions(action_dict)
        self.assertEqual(item.uses, 1)
        self._run_actions(action_dict)
        self.assertEqual(item.pk, None)  # deleted, it was used up

    def test_swap_wielded_weapon_or_spell(self):
        """
        First draw a weapon (from empty fists), then swap that out to another weapon, then
        swap to a spell rune.

        """
        sword = create.create_object(EvAdventureWeapon, key="sword")
        zweihander = create.create_object(
            EvAdventureWeapon,
            key="zweihander",
            attributes=(("inventory_use_slot", WieldLocation.TWO_HANDS),),
        )
        runestone = create.create_object(EvAdventureRunestone, key="ice rune")

        # check hands are empty
        self.assertEqual(self.combatant.weapon.key, "Empty Fists")
        self.assertEqual(self.combatant.equipment.slots[WieldLocation.WEAPON_HAND], None)
        self.assertEqual(self.combatant.equipment.slots[WieldLocation.TWO_HANDS], None)

        # swap to sword

        actiondict = {"key": "wield", "item": sword}

        self._run_actions(actiondict)
        self.assertEqual(self.combatant.weapon, sword)
        self.assertEqual(self.combatant.equipment.slots[WieldLocation.WEAPON_HAND], sword)
        self.assertEqual(self.combatant.equipment.slots[WieldLocation.TWO_HANDS], None)

        # swap to zweihander (two-handed sword)
        actiondict["item"] = zweihander

        from evennia import set_trace

        set_trace()
        self._run_actions(actiondict)
        self.assertEqual(self.combatant.weapon, zweihander)
        self.assertEqual(self.combatant.equipment.slots[WieldLocation.WEAPON_HAND], None)
        self.assertEqual(self.combatant.equipment.slots[WieldLocation.TWO_HANDS], zweihander)

        # swap to runestone (also using two hands)
        actiondict["item"] = runestone

        self._run_actions(actiondict)
        self.assertEqual(self.combatant.weapon, runestone)
        self.assertEqual(self.combatant.equipment.slots[WieldLocation.WEAPON_HAND], None)
        self.assertEqual(self.combatant.equipment.slots[WieldLocation.TWO_HANDS], runestone)

        # swap back to normal one-handed sword
        actiondict["item"] = sword

        self._run_actions(actiondict)
        self.assertEqual(self.combatant.weapon, sword)
        self.assertEqual(self.combatant.equipment.slots[WieldLocation.WEAPON_HAND], sword)
        self.assertEqual(self.combatant.equipment.slots[WieldLocation.TWO_HANDS], None)


#     def test_flee__success(self):
#         """
#         Test fleeing twice, leading to leaving combat.
#
#         """
#         # first flee records the fleeing state
#         self._run_action(combat_turnbased.CombatActionFlee, None)
#         self.assertTrue(self.combatant in self.combathandler.fleeing_combatants)
#
#         # second flee should remove combatant
#         self._run_action(combat_turnbased.CombatActionFlee, None)
#         self.assertIsNone(self.combathandler.pk)
#
#     @patch("evennia.contrib.tutorials.evadventure.combat_turnbased.rules.randint")
#     def test_flee__blocked(self, mock_randint):
#         """ """
#         mock_randint.return_value = 11  # means block will succeed
#
#         self._run_action(combat_turnbased.CombatActionFlee, None)
#         self.assertTrue(self.combatant in self.combathandler.fleeing_combatants)
#
#         # other combatant blocks in the same turn
#         self.combathandler.register_action(
#             self.combatant, combat_turnbased.CombatActionFlee.key, None
#         )
#         self.combathandler.register_action(
#             self.target, combat_turnbased.CombatActionBlock.key, self.combatant
#         )
#         self.combathandler._end_turn()
#         # the fleeing combatant should remain now
#         self.assertTrue(self.combatant not in self.combathandler.fleeing_combatants)
#         self.assertTrue(self.combatant in self.combathandler.combatants)


# class EvAdventureTurnbasedCombatHandlerTest(EvAdventureMixin, BaseEvenniaTest):
#     """
#     Test methods on the turn-based combat handler.
#
#     """
#
#     maxDiff = None
#
#     # make sure to mock away all time-keeping elements
#     @patch(
#         "evennia.contrib.tutorials.evadventure.combat_turnbased"
#         ".EvAdventureCombatHandler.interval",
#         new=-1,
#     )
#     @patch(
#         "evennia.contrib.tutorials.evadventure.combat_turnbased.delay",
#         new=MagicMock(return_value=None),
#     )
#     def setUp(self):
#         super().setUp()
#         self.location.allow_combat = True
#         self.location.allow_death = True
#         self.combatant = self.character
#         self.target = create.create_object(
#             EvAdventureMob,
#             key="testmonster",
#             location=self.location,
#             attributes=(("is_idle", True),),
#         )
#
#         # this already starts turn 1
#         self.combathandler = combat_turnbased.join_combat(self.combatant, self.target)
#
#     def tearDown(self):
#         self.combathandler.delete()
#         self.target.delete()
#
#     def test_remove_combatant(self):
#         self.assertTrue(bool(self.combatant.db.combathandler))
#         self.combathandler.remove_combatant(self.combatant)
#         self.assertFalse(self.combatant in self.combathandler.combatants)
#         self.assertFalse(bool(self.combatant.db.combathandler))
#
#     def test_start_turn(self):
#         self.combathandler._start_turn()
#         self.assertEqual(self.combathandler.turn, 2)
#         self.combathandler._start_turn()
#         self.assertEqual(self.combathandler.turn, 3)
#
#     def test_end_of_turn__empty(self):
#         self.combathandler._end_turn()
#
#     def test_add_combatant(self):
#         self.combathandler._init_menu = MagicMock()
#         combatant3 = create.create_object(EvAdventureCharacter, key="testcharacter3")
#         self.combathandler.add_combatant(combatant3)
#
#         self.assertTrue(combatant3 in self.combathandler.combatants)
#         self.combathandler._init_menu.assert_called_once()
#
#     def test_start_combat(self):
#         self.combathandler._start_turn = MagicMock()
#         self.combathandler.start = MagicMock()
#         self.combathandler.start_combat()
#         self.combathandler._start_turn.assert_called_once()
#         self.combathandler.start.assert_called_once()
#
#     def test_combat_summary(self):
#         result = self.combathandler.get_combat_summary(self.combatant)
#         self.assertTrue("You (4 / 4 health)" in result)
#         self.assertTrue("testmonster" in result)
#
#     def test_msg(self):
#         self.location.msg_contents = MagicMock()
#         self.combathandler.msg("You hurt the target", combatant=self.combatant)
#         self.location.msg_contents.assert_called_with(
#             "You hurt the target",
#             from_obj=self.combatant,
#             exclude=[],
#             mapping={"testchar": self.combatant, "testmonster": self.target},
#         )
#
#     def test_gain_advantage(self):
#         self.combathandler.gain_advantage(self.combatant, self.target)
#         self.assertTrue(bool(self.combathandler.advantage_matrix[self.combatant][self.target]))
#
#     def test_gain_disadvantage(self):
#         self.combathandler.gain_disadvantage(self.combatant, self.target)
#         self.assertTrue(bool(self.combathandler.disadvantage_matrix[self.combatant][self.target]))
#
#     def test_flee(self):
#         self.combathandler.flee(self.combatant)
#         self.assertTrue(self.combatant in self.combathandler.fleeing_combatants)
#
#     def test_unflee(self):
#         self.combathandler.unflee(self.combatant)
#         self.assertFalse(self.combatant in self.combathandler.fleeing_combatants)
#
#     def test_register_and_run_action(self):
#         action_class = combat_turnbased.CombatActionAttack
#         action = self.combathandler.combatant_actions[self.combatant][action_class.key]
#
#         self.combathandler.register_action(self.combatant, action.key)
#
#         self.assertEqual(self.combathandler.action_queue[self.combatant], (action, (), {}))
#
#         action.use = MagicMock()
#
#         self.combathandler._end_turn()
#         action.use.assert_called_once()
#
#     def test_get_available_actions(self):
#         result = self.combathandler.get_available_actions(self.combatant)
#         self.assertTrue(len(result), 7)
#
#
# class EvAdventureTurnbasedCombatActionTest(EvAdventureMixin, BaseEvenniaTest):
#     """
#     Test actions in turn_based combat.
#     """
#
#     @patch(
#         "evennia.contrib.tutorials.evadventure.combat_turnbased"
#         ".EvAdventureCombatHandler.interval",
#         new=-1,
#     )
#     @patch(
#         "evennia.contrib.tutorials.evadventure.combat_turnbased.delay",
#         new=MagicMock(return_value=None),
#     )
#     def setUp(self):
#         super().setUp()
#         self.location.allow_combat = True
#         self.location.allow_death = True
#         self.combatant = self.character
#         self.combatant2 = create.create_object(EvAdventureCharacter, key="testcharacter2")
#         self.target = create.create_object(
#             EvAdventureMob, key="testmonster", attributes=(("is_idle", True),)
#         )
#         self.target.hp = 4
#
#         # this already starts turn 1
#         self.combathandler = combat_turnbased.join_combat(self.combatant, self.target)
#
#     def _run_action(self, action, *args, **kwargs):
#         self.combathandler.register_action(self.combatant, action.key, *args, **kwargs)
#         self.combathandler._end_turn()
#
#     def test_do_nothing(self):
#         self.combathandler.msg = MagicMock()
#         self._run_action(combat_turnbased.CombatActionDoNothing, None)
#         self.combathandler.msg.assert_called()
#
#     @patch("evennia.contrib.tutorials.evadventure.combat_turnbased.rules.randint")
#     def test_attack__miss(self, mock_randint):
#         mock_randint.return_value = 8  # target has default armor 11, so 8+1 str will miss
#         self._run_action(combat_turnbased.CombatActionAttack, self.target)
#         self.assertEqual(self.target.hp, 4)
#
#     @patch("evennia.contrib.tutorials.evadventure.combat_turnbased.rules.randint")
#     def test_attack__success__still_alive(self, mock_randint):
#         mock_randint.return_value = 11  # 11 + 1 str will hit beat armor 11
#         # make sure target survives
#         self.target.hp = 20
#         self._run_action(combat_turnbased.CombatActionAttack, self.target)
#         self.assertEqual(self.target.hp, 9)
#
#     @patch("evennia.contrib.tutorials.evadventure.combat_turnbased.rules.randint")
#     def test_attack__success__kill(self, mock_randint):
#         mock_randint.return_value = 11  # 11 + 1 str will hit beat armor 11
#         self._run_action(combat_turnbased.CombatActionAttack, self.target)
#         self.assertEqual(self.target.hp, -7)
#         # after this the combat is over
#         self.assertIsNone(self.combathandler.pk)
#
#     @patch("evennia.contrib.tutorials.evadventure.combat_turnbased.rules.randint")
#     def test_stunt_fail(self, mock_randint):
#         mock_randint.return_value = 8  # fails 8+1 dex vs DEX 11 defence
#         self._run_action(combat_turnbased.CombatActionStunt, self.target)
#         self.assertEqual(self.combathandler.advantage_matrix[self.combatant], {})
#         self.assertEqual(self.combathandler.disadvantage_matrix[self.combatant], {})
#
#     @patch("evennia.contrib.tutorials.evadventure.combat_turnbased.rules.randint")
#     def test_stunt_advantage__success(self, mock_randint):
#         mock_randint.return_value = 11  #  11+1 dex vs DEX 11 defence is success
#         self._run_action(combat_turnbased.CombatActionStunt, self.target)
#         self.assertEqual(
#             bool(self.combathandler.advantage_matrix[self.combatant][self.target]), True
#         )
#
#     @patch("evennia.contrib.tutorials.evadventure.combat_turnbased.rules.randint")
#     def test_stunt_disadvantage__success(self, mock_randint):
#         mock_randint.return_value = 11  #  11+1 dex vs DEX 11 defence is success
#         action = combat_turnbased.CombatActionStunt
#         action.give_advantage = False
#         self._run_action(
#             action,
#             self.target,
#         )
#         self.assertEqual(
#             bool(self.combathandler.disadvantage_matrix[self.target][self.combatant]), True
#         )
#
#     def test_use_item(self):
#         """
#         Use up a potion during combat.
#
#         """
#         item = create.create_object(
#             EvAdventureConsumable, key="Healing potion", attributes=[("uses", 2)]
#         )
#         self.assertEqual(item.uses, 2)
#         self._run_action(combat_turnbased.CombatActionUseItem, item, self.combatant)
#         self.assertEqual(item.uses, 1)
#         self._run_action(combat_turnbased.CombatActionUseItem, item, self.combatant)
#         self.assertEqual(item.pk, None)  # deleted, it was used up
#
#     def test_swap_wielded_weapon_or_spell(self):
#         """
#         First draw a weapon (from empty fists), then swap that out to another weapon, then
#         swap to a spell rune.
#
#         """
#         sword = create.create_object(EvAdventureWeapon, key="sword")
#         zweihander = create.create_object(
#             EvAdventureWeapon,
#             key="zweihander",
#             attributes=(("inventory_use_slot", WieldLocation.TWO_HANDS),),
#         )
#         runestone = create.create_object(EvAdventureRunestone, key="ice rune")
#
#         # check hands are empty
#         self.assertEqual(self.combatant.weapon.key, "Empty Fists")
#         self.assertEqual(self.combatant.equipment.slots[WieldLocation.WEAPON_HAND], None)
#         self.assertEqual(self.combatant.equipment.slots[WieldLocation.TWO_HANDS], None)
#
#         # swap to sword
#         self._run_action(combat_turnbased.CombatActionSwapWieldedWeaponOrSpell, None, sword)
#         self.assertEqual(self.combatant.weapon, sword)
#         self.assertEqual(self.combatant.equipment.slots[WieldLocation.WEAPON_HAND], sword)
#         self.assertEqual(self.combatant.equipment.slots[WieldLocation.TWO_HANDS], None)
#
#         # swap to zweihander (two-handed sword)
#         self._run_action(combat_turnbased.CombatActionSwapWieldedWeaponOrSpell, None, zweihander)
#         self.assertEqual(self.combatant.weapon, zweihander)
#         self.assertEqual(self.combatant.equipment.slots[WieldLocation.WEAPON_HAND], None)
#         self.assertEqual(self.combatant.equipment.slots[WieldLocation.TWO_HANDS], zweihander)
#
#         # swap to runestone (also using two hands)
#         self._run_action(combat_turnbased.CombatActionSwapWieldedWeaponOrSpell, None, runestone)
#         self.assertEqual(self.combatant.weapon, runestone)
#         self.assertEqual(self.combatant.equipment.slots[WieldLocation.WEAPON_HAND], None)
#         self.assertEqual(self.combatant.equipment.slots[WieldLocation.TWO_HANDS], runestone)
#
#         # swap back to normal one-handed sword
#         self._run_action(combat_turnbased.CombatActionSwapWieldedWeaponOrSpell, None, sword)
#         self.assertEqual(self.combatant.weapon, sword)
#         self.assertEqual(self.combatant.equipment.slots[WieldLocation.WEAPON_HAND], sword)
#         self.assertEqual(self.combatant.equipment.slots[WieldLocation.TWO_HANDS], None)
#
#     def test_flee__success(self):
#         """
#         Test fleeing twice, leading to leaving combat.
#
#         """
#         # first flee records the fleeing state
#         self._run_action(combat_turnbased.CombatActionFlee, None)
#         self.assertTrue(self.combatant in self.combathandler.fleeing_combatants)
#
#         # second flee should remove combatant
#         self._run_action(combat_turnbased.CombatActionFlee, None)
#         self.assertIsNone(self.combathandler.pk)
#
#     @patch("evennia.contrib.tutorials.evadventure.combat_turnbased.rules.randint")
#     def test_flee__blocked(self, mock_randint):
#         """ """
#         mock_randint.return_value = 11  # means block will succeed
#
#         self._run_action(combat_turnbased.CombatActionFlee, None)
#         self.assertTrue(self.combatant in self.combathandler.fleeing_combatants)
#
#         # other combatant blocks in the same turn
#         self.combathandler.register_action(
#             self.combatant, combat_turnbased.CombatActionFlee.key, None
#         )
#         self.combathandler.register_action(
#             self.target, combat_turnbased.CombatActionBlock.key, self.combatant
#         )
#         self.combathandler._end_turn()
#         # the fleeing combatant should remain now
#         self.assertTrue(self.combatant not in self.combathandler.fleeing_combatants)
#         self.assertTrue(self.combatant in self.combathandler.combatants)
