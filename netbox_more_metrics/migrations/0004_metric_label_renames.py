from django.db import migrations, models

import netbox_more_metrics.validators


class Migration(migrations.Migration):

    dependencies = [
        ("netbox_more_metrics", "0003_alter_metric_content_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="metric",
            name="label_renames",
            field=models.JSONField(
                blank=True,
                default=dict,
                validators=[netbox_more_metrics.validators.validate_label_renames],
            ),
        ),
    ]
