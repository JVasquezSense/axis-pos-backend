from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("api", "0039_sale_detail")]
    operations = [
        migrations.AddField("shiftclose", "number", models.PositiveIntegerField(default=0)),
        migrations.AddField("shiftclose", "started_at", models.DateTimeField(blank=True, null=True)),
    ]
