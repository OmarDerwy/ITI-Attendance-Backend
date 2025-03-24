from django.test import TestCase
from django.utils.timezone import now
from users.models import CustomUser
from .models import LostItem, FoundItem, MatchedItem, ItemStatusChoices


class LostAndFoundTestCase(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email='testuser@example.com',  
            password='password123'
        )

        # Create a lost item
        self.lost_item = LostItem.objects.create(
            name="Lost Wallet",
            description="A black leather wallet",
            place="Library",
            user=self.user
        )

        # Create a found item
        self.found_item = FoundItem.objects.create(
            name="Found Wallet",
            description="A black leather wallet found near the library",
            place="Library",
            user=self.user
        )

        # Create a matched item
        self.matched_item = MatchedItem.objects.create(
            lost_item=self.lost_item,
            found_item=self.found_item,
            similarity_score=0.95,
            status=MatchedItem.MatchingResult.SUCCEEDED
        )


    def test_lost_item_creation(self):
        self.assertEqual(self.lost_item.name, "Lost Wallet")
        self.assertEqual(self.lost_item.status, ItemStatusChoices.LOST)

    def test_found_item_creation(self):
        self.assertEqual(self.found_item.name, "Found Wallet")
        self.assertEqual(self.found_item.status, ItemStatusChoices.FOUND)

    def test_matched_item_creation(self):
        self.assertEqual(self.matched_item.lost_item, self.lost_item)
        self.assertEqual(self.matched_item.found_item, self.found_item)
        self.assertEqual(self.matched_item.similarity_score, 0.95)
        self.assertEqual(self.matched_item.status, MatchedItem.MatchingResult.SUCCEEDED)

    def test_update_lost_item_status(self):
        self.lost_item.status = ItemStatusChoices.MATCHED
        self.lost_item.save()
        self.lost_item.refresh_from_db()
        self.assertEqual(self.lost_item.status, ItemStatusChoices.MATCHED)

    def test_update_found_item_status(self):
        self.found_item.status = ItemStatusChoices.MATCHED
        self.found_item.save()
        self.found_item.refresh_from_db()
        self.assertEqual(self.found_item.status, ItemStatusChoices.MATCHED)

    def test_confirmed_match(self):
        self.matched_item.status = MatchedItem.MatchingResult.SUCCEEDED
        self.matched_item.confirmed_at = now()
        self.matched_item.save()

        self.lost_item.status = ItemStatusChoices.CONFIRMED
        self.lost_item.save()

        self.found_item.status = ItemStatusChoices.CONFIRMED
        self.found_item.save()

        self.matched_item.refresh_from_db()
        self.lost_item.refresh_from_db()
        self.found_item.refresh_from_db()

        self.assertEqual(self.matched_item.status, MatchedItem.MatchingResult.SUCCEEDED)
        self.assertIsNotNone(self.matched_item.confirmed_at)
        self.assertEqual(self.lost_item.status, ItemStatusChoices.CONFIRMED)
        self.assertEqual(self.found_item.status, ItemStatusChoices.CONFIRMED)

    def test_unique_match_constraint(self):
        with self.assertRaises(Exception):
            MatchedItem.objects.create(
                lost_item=self.lost_item,
                found_item=self.found_item,
                similarity_score=0.90
            )

    def test_string_representation(self):
        self.assertEqual(str(self.lost_item), "Lost Wallet (Lost)")
        self.assertEqual(str(self.found_item), "Found Wallet (Found)")
        self.assertEqual(str(self.matched_item), "Match: Lost Wallet ↔ Found Wallet")
