from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("netbox_more_metrics", "0006_alter_metric_metric_labels"),
    ]

    operations = [
        migrations.AddField(
            model_name="metric",
            name="exclude",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
