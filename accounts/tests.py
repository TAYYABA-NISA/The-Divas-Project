from django.test import TestCase
from django.urls import reverse

from .models import User


class RoleLoginTests(TestCase):
    def setUp(self):
        self.password = "test-password-123"
        self.candidate = User.objects.create_user(
            username="cand", password=self.password, role=User.Role.CANDIDATE
        )
        self.examiner = User.objects.create_user(
            username="exam", password=self.password, role=User.Role.EXAMINER
        )
        self.admin = User.objects.create_user(
            username="boss", password=self.password, role=User.Role.ADMINISTRATOR,
            is_staff=True, is_superuser=True,
        )

    def login(self, username, role):
        return self.client.post(
            reverse("login"), {"username": username, "password": self.password, "role": role}
        )

    def test_login_page_offers_all_three_roles(self):
        response = self.client.get(reverse("login"))
        for value in ("CANDIDATE", "EXAMINER", "ADMIN"):
            self.assertContains(response, f'value="{value}"')

    def test_each_role_signs_in_and_lands_on_its_area(self):
        cases = (
            ("cand", "CANDIDATE", reverse("examinations:candidate-dashboard")),
            ("exam", "EXAMINER", reverse("examinations:exam-list")),
            ("boss", "ADMIN", reverse("admin:index")),
        )
        for username, role, landing in cases:
            with self.subTest(role=role):
                self.client.logout()
                response = self.login(username, role)
                self.assertRedirects(response, reverse("accounts:dashboard"), fetch_redirect_response=False)
                self.assertRedirects(self.client.get(reverse("accounts:dashboard")), landing,
                                     fetch_redirect_response=False)

    def test_wrong_role_is_rejected_without_revealing_valid_credentials(self):
        response = self.login("cand", "EXAMINER")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "correct username and password for the selected role")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_wrong_password_is_rejected(self):
        response = self.client.post(
            reverse("login"), {"username": "cand", "password": "nope", "role": "CANDIDATE"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
