from django.db import migrations, models


class Migration(migrations.Migration):
    # El índice va aparte: crearlo en la misma transacción que el backfill
    # falla en Postgres ("pending trigger events").
    dependencies = [("api", "0041_shift_number_backfill")]
    operations = [
        migrations.AlterField("shiftclose", "number", models.PositiveIntegerField(default=0, db_index=True)),
    ]
