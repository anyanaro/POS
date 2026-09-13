from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models.org import Branch
from accounts.models.product import Product
from ai.models import ModelRun
from ai.services.forecasting import forecast_sku_branch, persist_forecasts


class Command(BaseCommand):
    help = "Generate and persist daily sales forecasts for active branch/product combinations."

    def add_arguments(self, parser):
        parser.add_argument("--horizon", type=int, default=30)
        parser.add_argument("--branch", type=int, help="Only forecast this branch ID")
        parser.add_argument("--product", type=int, help="Only forecast this product ID")
        parser.add_argument("--no-prophet", action="store_true", help="Use the deterministic seasonal-naive model")

    def handle(self, *args, **options):
        horizon = max(1, min(options["horizon"], 90))
        branches = Branch.objects.filter(active=True)
        products = Product.objects.filter(active=True)
        if options.get("branch"):
            branches = branches.filter(pk=options["branch"])
        if options.get("product"):
            products = products.filter(pk=options["product"])

        run = ModelRun.objects.create(
            model_name="daily-sales-forecast",
            params={
                "horizon_days": horizon,
                "prefer_prophet": not options["no_prophet"],
                "branch_id": options.get("branch"),
                "product_id": options.get("product"),
            },
            status="running",
        )
        processed = 0
        generated = 0
        skipped = 0
        failures = []

        for branch in branches:
            for product in products:
                processed += 1
                try:
                    predictions, model_version = forecast_sku_branch(
                        branch.id,
                        product.id,
                        horizon_days=horizon,
                        prefer_prophet=not options["no_prophet"],
                    )
                    if not predictions:
                        skipped += 1
                        continue
                    with transaction.atomic():
                        generated += persist_forecasts(
                            branch.id,
                            product.id,
                            predictions,
                            model_version,
                        )
                except Exception as exc:
                    failures.append({
                        "branch_id": branch.id,
                        "product_id": product.id,
                        "error": str(exc),
                    })
                    self.stderr.write(
                        self.style.WARNING(
                            f"Forecast failed for branch {branch.id}, product {product.id}: {exc}"
                        )
                    )

        status = "failed" if failures and not generated else "completed"
        run.status = status
        run.ended_at = timezone.now()
        run.metrics = {
            "processed": processed,
            "generated": generated,
            "skipped_insufficient_history": skipped,
            "failures": failures,
        }
        run.save(update_fields=["status", "ended_at", "metrics"])

        self.stdout.write(self.style.SUCCESS(
            f"Daily forecasts complete: processed={processed}, generated={generated}, "
            f"skipped={skipped}, failures={len(failures)}"
        ))
        if failures:
            self.stdout.write("Inspect the latest ai.ModelRun record for failure details.")
