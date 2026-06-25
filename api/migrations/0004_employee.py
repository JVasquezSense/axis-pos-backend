from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0003_image_textfield"),
    ]

    operations = [
        migrations.CreateModel(
            name="Employee",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("role", models.CharField(
                    choices=[
                        ("mesero", "Mesero"),
                        ("cocinero", "Cocinero"),
                        ("cajero", "Cajero"),
                        ("admin", "Administrador"),
                        ("almacen", "Almacén"),
                    ],
                    default="mesero",
                    max_length=16,
                )),
                ("active", models.BooleanField(default=True)),
                ("phone", models.CharField(blank=True, max_length=30)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("tenant", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="employees",
                    to="api.tenant",
                )),
            ],
            options={"abstract": False},
        ),
    ]
