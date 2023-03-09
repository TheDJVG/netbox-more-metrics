from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_more_metrics", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="metric",
            name="metric_value",
            field=models.CharField(default="count", max_length=50),
        ),
    ]
