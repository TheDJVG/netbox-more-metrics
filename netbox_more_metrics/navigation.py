from extras.plugins import PluginMenuButton, PluginMenuItem
from utilities.choices import ButtonColorChoices

metriccollection_buttons = [
    PluginMenuButton(
        link="plugins:netbox_more_metrics:metriccollection_add",
        title="Add",
        icon_class="mdi mdi-plus-thick",
        color=ButtonColorChoices.GREEN,
    )
]

metric_buttons = [
    PluginMenuButton(
        link="plugins:netbox_more_metrics:metric_add",
        title="Add",
        icon_class="mdi mdi-plus-thick",
        color=ButtonColorChoices.GREEN,
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
