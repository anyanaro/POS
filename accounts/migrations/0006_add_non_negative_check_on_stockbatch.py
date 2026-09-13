# accounts/migrations/00xx_add_non_negative_check_on_stockbatch.py
from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
       ('accounts', '0005_alter_supplier_code'),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "ALTER TABLE accounts_stockbatch "
                "ADD CONSTRAINT stockbatch_qty_non_negative "
                "CHECK (qty_on_hand >= 0);"
            ),
            reverse_sql=(
                "ALTER TABLE accounts_stockbatch "
                "DROP CONSTRAINT IF EXISTS stockbatch_qty_non_negative;"
            ),
        )
    ]
