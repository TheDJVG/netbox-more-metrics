import re

import django.contrib.postgres.fields
import django.core.validators
import django.db.models.deletion
import taggit.managers
import utilities.json
from django.db import migrations, models

import netbox_more_metrics.models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        ("extras", "0084_staging"),
    ]

    operations = [
        migrations.CreateModel(
            name="MetricCollection",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                (
                    "custom_field_data",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        encoder=utilities.json.CustomFieldJSONEncoder,
                    ),
                ),
                ("name", models.CharField(max_length=50)),
                ("description", models.CharField(blank=True, max_length=255)),
                ("enabled", models.BooleanField(default=True)),
                ("include_in_default", models.BooleanField(default=False)),
                (
                    "tags",
                    taggit.managers.TaggableManager(
                        through="extras.TaggedItem", to="extras.Tag"
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
            bases=(models.Model, netbox_more_metrics.models.ObjectAbsoluteUrlMixin),
        ),
        migrations.CreateModel(
            name="Metric",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                (
                    "custom_field_data",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        encoder=utilities.json.CustomFieldJSONEncoder,
                    ),
                ),
                ("name", models.CharField(max_length=50)),
                ("enabled", models.BooleanField(default=True)),
                (
                    "metric_name",
                    models.CharField(
                        max_length=50,
                        unique=True,
                        validators=[
                            django.core.validators.RegexValidator(
                                re.compile("^[a-zA-Z_][a-zA-Z0-9_]+\\Z"),
                                "Enter a valid “metric_name” consisting of letters, numbers or underscores.",
                                "invalid",
                            )
                        ],
                    ),
                ),
                ("metric_description", models.CharField(max_length=255)),
                (
                    "metric_labels",
                    django.contrib.postgres.fields.ArrayField(
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
                    ),
                ),
                ("metric_type", models.CharField(max_length=50)),
                ("filter", models.JSONField(blank=True, default=dict)),
                (
                    "collections",
                    models.ManyToManyField(
                        related_name="metrics",
                        to="netbox_more_metrics.metriccollection",
                    ),
                ),
                (
                    "content_type",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="contenttypes.contenttype",
                    ),
                ),
                (
                    "tags",
                    taggit.managers.TaggableManager(
                        through="extras.TaggedItem", to="extras.Tag"
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
            bases=(models.Model, netbox_more_metrics.models.ObjectAbsoluteUrlMixin),
        ),
    ]
