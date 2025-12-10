from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("netbox_more_metrics", "0004_metric_label_renames"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="metric",
            options={"ordering": ("name", "pk")},
        ),
        migrations.AlterModelOptions(
            name="metriccollection",
            options={"ordering": ("name", "pk")},
        ),
    ]
