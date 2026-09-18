from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("api", "0046_orderline_variation")]
    operations = [
        migrations.AddField("inventorymovement", "table_number", models.PositiveIntegerField(blank=True, null=True)),
        migrations.AddField("inventorymovement", "waiter", models.CharField(blank=True, default="", max_length=80)),
    ]
