from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.http import HttpResponse
from django.test import SimpleTestCase, override_settings
from django.urls import path

from .error_handlers import bad_request, page_not_found, permission_denied, server_error


def ok_view(request):
    return HttpResponse("ok")


def forbidden_view(request):
    raise PermissionDenied("This examination belongs to another examiner.")


def bad_request_view(request):
    raise SuspiciousOperation("Internal parser detail must not be shown.")


def exploding_view(request):
    raise RuntimeError("private database detail must not be shown")


urlpatterns = [
    path("ok/", ok_view),
    path("forbidden/", forbidden_view),
    path("bad-request/", bad_request_view),
    path("explode/", exploding_view),
    path("api/explode/", exploding_view),
]
handler400 = bad_request
handler403 = permission_denied
handler404 = page_not_found
handler500 = server_error


@override_settings(ROOT_URLCONF=__name__, DEBUG=False)
class ErrorHandlerTests(SimpleTestCase):
    def setUp(self):
        self.client.raise_request_exception = False

    def test_server_error_is_safe_and_has_support_reference(self):
        response = self.client.get("/explode/")

        self.assertEqual(response.status_code, 500)
        self.assertContains(response, "Something went wrong", status_code=500)
        self.assertContains(response, "Reference:", status_code=500)
        self.assertNotContains(response, "private database detail", status_code=500)
        self.assertRegex(response["X-Request-ID"], r"^[0-9a-f]{32}$")

    def test_failed_post_does_not_offer_an_automatic_retry(self):
        response = self.client.post("/explode/")

        self.assertEqual(response.status_code, 500)
        self.assertNotContains(response, "Try again", status_code=500)

    def test_api_error_is_json_instead_of_an_html_crash_page(self):
        response = self.client.get("/api/explode/")

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["code"], "server_error")
        self.assertIn("reference", response.json())
        self.assertNotContains(response, "private database detail", status_code=500)

    def test_ajax_and_json_accept_requests_receive_json(self):
        ajax_response = self.client.get(
            "/missing/", HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )
        accept_response = self.client.get(
            "/missing/", HTTP_ACCEPT="application/json"
        )

        self.assertEqual(ajax_response.status_code, 404)
        self.assertEqual(ajax_response.json()["code"], "not_found")
        self.assertEqual(accept_response.status_code, 404)
        self.assertEqual(accept_response.json()["code"], "not_found")

    def test_permission_page_explains_the_deliberate_denial(self):
        response = self.client.get("/forbidden/")

        self.assertEqual(response.status_code, 403)
        self.assertContains(
            response,
            "This examination belongs to another examiner.",
            status_code=403,
        )

    def test_bad_request_does_not_expose_parser_details(self):
        response = self.client.get("/bad-request/")

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Check the submitted information", status_code=400)
        self.assertNotContains(response, "Internal parser detail", status_code=400)

    def test_not_found_page_gives_a_clear_recovery_action(self):
        response = self.client.get("/missing/")

        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "We could not find that page", status_code=404)
        self.assertContains(response, "Return to dashboard", status_code=404)

    def test_every_response_gets_a_different_request_id(self):
        first = self.client.get("/ok/")
        second = self.client.get("/ok/")

        self.assertNotEqual(first["X-Request-ID"], second["X-Request-ID"])
