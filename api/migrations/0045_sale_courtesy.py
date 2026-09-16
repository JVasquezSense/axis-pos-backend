from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("api", "0044_purchaseline_bonus")]
    operations = [
        migrations.AddField("sale", "courtesy", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
        migrations.AlterField("sale", "method", models.CharField(
            choices=[("card", "Tarjeta"), ("cash", "Efectivo"), ("transfer", "Transferencia"), ("nequi", "Nequi"),
                     ("daviplata", "Daviplata"), ("pse", "PSE"), ("courtesy", "Cortesía")],
            default="cash", max_length=20)),
    ]
