from django.core.management.base import BaseCommand

from vouchers.services.distribution import process_due_distribution_plans


class Command(BaseCommand):
    help = "Process voucher distribution plans whose release_date has arrived"

    def handle(self, *args, **options):
        processed = process_due_distribution_plans()
        self.stdout.write(self.style.SUCCESS(f"Processed plans: {processed}"))
