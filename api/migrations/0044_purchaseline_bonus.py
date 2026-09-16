from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("api", "0043_product_archived")]
    operations = [
        migrations.AddField("purchaseline", "bonus_qty", models.DecimalField(decimal_places=3, default=0, max_digits=12)),
        migrations.AddField("purchaseline", "discount", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
    ]
