from django.db import migrations


def backfill(apps, schema_editor):
    """El rol único que tenía cada quien pasa a ser el primero de su lista."""
    for model in ("UserProfile", "Employee"):
        Model = apps.get_model("api", model)
        for obj in Model.objects.all():
            if not obj.roles:
                obj.roles = [obj.role]
                obj.save(update_fields=["roles"])


class Migration(migrations.Migration):
    dependencies = [("api", "0036_multi_roles")]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
