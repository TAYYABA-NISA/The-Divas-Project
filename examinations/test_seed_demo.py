from django.core.management import call_command
from django.test import TestCase

from accounts.models import User
from examinations.management.commands.seed_demo import DEMO_PASSWORD
from examinations.models import Question


class SeedDemoCommandTests(TestCase):
    def test_command_creates_repeatable_demo_users_and_valid_question_bank(self):
        call_command("seed_demo")
        call_command("seed_demo")

        self.assertEqual(User.objects.filter(role=User.Role.ADMINISTRATOR).count(), 1)
        self.assertEqual(User.objects.filter(role=User.Role.EXAMINER).count(), 2)
        self.assertEqual(User.objects.filter(role=User.Role.CANDIDATE).count(), 5)

        administrator = User.objects.get(username="admin_demo")
        self.assertTrue(administrator.is_staff)
        self.assertTrue(administrator.is_superuser)
        self.assertTrue(administrator.check_password(DEMO_PASSWORD))

        self.assertEqual(Question.objects.count(), 6)
        for difficulty in Question.Difficulty.values:
            self.assertTrue(Question.objects.filter(difficulty=difficulty).exists())

        for question in Question.objects.exclude(question_type=Question.Type.WRITTEN):
            self.assertGreaterEqual(question.choices.count(), 2)
            self.assertTrue(question.choices.filter(is_correct=True).exists())
            if question.question_type == Question.Type.SINGLE_CHOICE:
                self.assertEqual(question.choices.filter(is_correct=True).count(), 1)

        self.assertFalse(
            Question.objects.filter(question_type=Question.Type.WRITTEN, choices__isnull=False).exists()
        )
