from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0007_user_profile"),
    ]

    operations = [
        migrations.AddField(
            model_name="table",
            name="x",
            field=models.FloatField(default=50),
        ),
        migrations.AddField(
            model_name="table",
            name="y",
            field=models.FloatField(default=50),
        ),
        migrations.AddField(
            model_name="table",
            name="shape",
            field=models.CharField(
                choices=[("round", "Redonda"), ("square", "Cuadrada"), ("rect", "Rectangular")],
                default="square",
                max_length=10,
            ),
        ),
    ]
