from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("api", "0045_sale_courtesy")]
    operations = [
        migrations.AddField("orderline", "variation_id", models.CharField(blank=True, default="", max_length=40)),
    ]
