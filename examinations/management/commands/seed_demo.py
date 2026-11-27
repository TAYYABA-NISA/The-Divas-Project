"""Create idempotent fictional data for the Technoverse demonstration."""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import User
from examinations.models import Question, QuestionChoice


DEMO_PASSWORD = "DemoPass!2026"

DEMO_USERS = (
    {
        "username": "admin_demo",
        "first_name": "Amina",
        "last_name": "Admin",
        "email": "admin.demo@example.test",
        "role": User.Role.ADMINISTRATOR,
        "is_staff": True,
        "is_superuser": True,
    },
    {
        "username": "examiner_ayesha",
        "first_name": "Ayesha",
        "last_name": "Khan",
        "email": "ayesha.khan@example.test",
        "role": User.Role.EXAMINER,
        "is_staff": False,
        "is_superuser": False,
    },
    {
        "username": "examiner_bilal",
        "first_name": "Bilal",
        "last_name": "Ahmed",
        "email": "bilal.ahmed@example.test",
        "role": User.Role.EXAMINER,
        "is_staff": False,
        "is_superuser": False,
    },
    {
        "username": "candidate_fatima",
        "first_name": "Fatima",
        "last_name": "Noor",
        "email": "fatima.noor@example.test",
        "role": User.Role.CANDIDATE,
        "is_staff": False,
        "is_superuser": False,
    },
    {
        "username": "candidate_hassan",
        "first_name": "Hassan",
        "last_name": "Ali",
        "email": "hassan.ali@example.test",
        "role": User.Role.CANDIDATE,
        "is_staff": False,
        "is_superuser": False,
    },
    {
        "username": "candidate_mariam",
        "first_name": "Mariam",
        "last_name": "Iqbal",
        "email": "mariam.iqbal@example.test",
        "role": User.Role.CANDIDATE,
        "is_staff": False,
        "is_superuser": False,
    },
    {
        "username": "candidate_omer",
        "first_name": "Omer",
        "last_name": "Raza",
        "email": "omer.raza@example.test",
        "role": User.Role.CANDIDATE,
        "is_staff": False,
        "is_superuser": False,
    },
    {
        "username": "candidate_sara",
        "first_name": "Sara",
        "last_name": "Javed",
        "email": "sara.javed@example.test",
        "role": User.Role.CANDIDATE,
        "is_staff": False,
        "is_superuser": False,
    },
)

DEMO_QUESTIONS = (
    {
        "author": "examiner_ayesha",
        "category": "Programming Fundamentals",
        "difficulty": Question.Difficulty.EASY,
        "question_type": Question.Type.SINGLE_CHOICE,
        "prompt": "Which Python value represents true?",
        "marks": Decimal("1.00"),
        "choices": (("True", True), ("False", False), ("None", False)),
    },
    {
        "author": "examiner_ayesha",
        "category": "Programming Fundamentals",
        "difficulty": Question.Difficulty.MEDIUM,
        "question_type": Question.Type.MULTIPLE_SELECT,
        "prompt": "Which Python collection types are mutable?",
        "marks": Decimal("2.00"),
        "choices": (("list", True), ("tuple", False), ("dict", True), ("str", False)),
    },
    {
        "author": "examiner_ayesha",
        "category": "Programming Fundamentals",
        "difficulty": Question.Difficulty.HARD,
        "question_type": Question.Type.WRITTEN,
        "prompt": "Explain why an algorithm with O(n log n) complexity can scale better than O(n²).",
        "marks": Decimal("5.00"),
        "choices": (),
    },
    {
        "author": "examiner_bilal",
        "category": "Data Structures",
        "difficulty": Question.Difficulty.EASY,
        "question_type": Question.Type.SINGLE_CHOICE,
        "prompt": "Which data structure follows last-in, first-out order?",
        "marks": Decimal("1.00"),
        "choices": (("Queue", False), ("Stack", True), ("Tree", False)),
    },
    {
        "author": "examiner_bilal",
        "category": "Data Structures",
        "difficulty": Question.Difficulty.MEDIUM,
        "question_type": Question.Type.MULTIPLE_SELECT,
        "prompt": "Which operations are typically O(1) on a hash table on average?",
        "marks": Decimal("2.00"),
        "choices": (("Lookup by key", True), ("Insert by key", True), ("Sort all entries", False)),
    },
    {
        "author": "examiner_bilal",
        "category": "Data Structures",
        "difficulty": Question.Difficulty.HARD,
        "question_type": Question.Type.WRITTEN,
        "prompt": "Compare a balanced binary search tree with a hash table for ordered range queries.",
        "marks": Decimal("5.00"),
        "choices": (),
    },
)


class Command(BaseCommand):
    help = "Create or refresh fictional Technoverse demo users and question-bank data."

    @transaction.atomic
    def handle(self, *args, **options):
        users = {}
        for data in DEMO_USERS:
            username = data["username"]
            user, _ = User.objects.get_or_create(username=username)
            for field, value in data.items():
                setattr(user, field, value)
            user.set_password(DEMO_PASSWORD)
            user.save()
            users[username] = user

        for data in DEMO_QUESTIONS:
            question, _ = Question.objects.update_or_create(
                author=users[data["author"]],
                prompt=data["prompt"],
                defaults={
                    "category": data["category"],
                    "difficulty": data["difficulty"],
                    "question_type": data["question_type"],
                    "default_marks": data["marks"],
                },
            )
            expected_positions = set()
            for position, (text, is_correct) in enumerate(data["choices"], start=1):
                QuestionChoice.objects.update_or_create(
                    question=question,
                    position=position,
                    defaults={"text": text, "is_correct": is_correct},
                )
                expected_positions.add(position)
            question.choices.exclude(position__in=expected_positions).delete()

        self.stdout.write(
            self.style.SUCCESS(
                "Demo data is ready: 1 administrator, 2 examiners, 5 candidates and 6 questions."
            )
        )
