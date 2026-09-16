from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("api", "0042_shift_number_index")]
    operations = [
        migrations.AddField("product", "archived", models.BooleanField(default=False, db_index=True)),
    ]
