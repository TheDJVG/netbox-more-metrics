import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0010_gfk_indexes"),
        ("netbox_more_metrics", "0002_metric_metric_value"),
    ]

    operations = [
        migrations.AlterField(
            model_name="metric",
            name="content_type",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="core.objecttype",
            ),
        ),
    ]
