from netbox.plugins import PluginMenuButton, PluginMenuItem

metriccollection_buttons = [
    PluginMenuButton(
        link="plugins:netbox_more_metrics:metriccollection_add",
        title="Add",
        icon_class="mdi mdi-plus-thick",
        permissions=("netbox_more_metrics.add_metriccollection",),
    )
]

metric_buttons = [
    PluginMenuButton(
        link="plugins:netbox_more_metrics:metric_add",
        title="Add",
        icon_class="mdi mdi-plus-thick",
        permissions=("netbox_more_metrics.add_metric",),
    )
]

menu_items = (
    PluginMenuItem(
        link="plugins:netbox_more_metrics:metriccollection_list",
        link_text="Metric Collections",
        buttons=metriccollection_buttons,
    ),
    PluginMenuItem(
        link="plugins:netbox_more_metrics:metric_list",
        link_text="Metrics",
        buttons=metric_buttons,
    ),
)
