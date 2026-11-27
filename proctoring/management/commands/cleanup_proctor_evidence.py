from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from proctoring.services import delete_expired_evidence


class Command(BaseCommand):
    help = "Delete private proctoring evidence older than the configured retention period."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days", type=int, default=getattr(settings, "PROCTOR_EVIDENCE_RETENTION_DAYS", 30)
        )

    def handle(self, *args, **options):
        try:
            deleted = delete_expired_evidence(retention_days=options["days"])
        except Exception as error:
            raise CommandError(str(error)) from error
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} expired proctor evidence clip(s)."))
