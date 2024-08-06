import re

import django.contrib.postgres.fields
import django.core.validators
from django.db import migrations, models

import netbox_more_metrics.validators


class Migration(migrations.Migration):

    dependencies = [
        ("netbox_more_metrics", "0004_metric_label_renames"),
    ]

    operations = [
        migrations.AlterField(
            model_name="metric",
            name="metric_labels",
            field=django.contrib.postgres.fields.ArrayField(
                base_field=models.CharField(
                    max_length=50,
                    validators=[
                        django.core.validators.RegexValidator(
                            re.compile("^[a-zA-Z_][a-zA-Z0-9_]+\\Z"),
                            "Enter a valid “label_name” consisting of letters, numbers or underscores.",
                            "invalid",
                        )
                    ],
                ),
                size=None,
                validators=[netbox_more_metrics.validators.validate_labels],
            ),
        ),
    ]
