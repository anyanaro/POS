from django.db import migrations, models


def assign_legacy_bc_numbers(apps, schema_editor):
    Product = apps.get_model("accounts", "Product")
    Supplier = apps.get_model("accounts", "Supplier")
    Insurance = apps.get_model("accounts", "Insurance")

    for product in Product.objects.filter(bc_number__isnull=True):
        product.bc_number = f"LEGACY-PRODUCT-{product.pk}"
        product.save(update_fields=["bc_number"])
    for supplier in Supplier.objects.filter(bc_number__isnull=True):
        supplier.bc_number = f"LEGACY-SUPPLIER-{supplier.pk}"
        supplier.save(update_fields=["bc_number"])
    for insurance in Insurance.objects.filter(bc_number__isnull=True):
        insurance.bc_number = f"LEGACY-INSURANCE-{insurance.pk}"
        insurance.save(update_fields=["bc_number"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0038_auditevent"),
    ]

    operations = [
        migrations.AddField(
            model_name="insurance",
            name="bc_number",
            field=models.CharField(max_length=100, null=True),
        ),
        migrations.AddField(
            model_name="product",
            name="bc_number",
            field=models.CharField(max_length=100, null=True),
        ),
        migrations.AddField(
            model_name="supplier",
            name="bc_number",
            field=models.CharField(max_length=100, null=True),
        ),
        migrations.RunPython(assign_legacy_bc_numbers, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="insurance",
            name="bc_number",
            field=models.CharField(max_length=100, unique=True),
        ),
        migrations.AlterField(
            model_name="product",
            name="bc_number",
            field=models.CharField(max_length=100, unique=True),
        ),
        migrations.AlterField(
            model_name="supplier",
            name="bc_number",
            field=models.CharField(max_length=100, unique=True),
        ),
    ]
