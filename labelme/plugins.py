import functools

from . import utils
from yapsy_gui import DialogPlugins


class AttachPluginsSystem(object):

    def __init__(self, parent):
        self.tr = parent.tr
        self.parent = parent
        self.shortcuts = dict()
        self.shortcuts["plugins"] = None
        self.manager = DialogPlugins(self.parent)
        self.action = functools.partial(utils.newAction, parent)
        self.manager.pluginsUpdate.connect(self.loadMenus)
        self.loadMenus()

    def loadMenus(self):
        self.parent.menus.plugins.clear()

        for plugin in self.manager.plugins:
            plugin.plugin_object.setContext(self.parent)

        actions = [self.menuEntry(plugin) for plugin in self.manager.plugins]

        menu_manager = self.action(
            self.tr("Manage Plugins"),
            self.showPluginManager,
            self.shortcuts["plugins"],
            "plugin",
            self.tr("Shows Plugins Manager"),
            enabled=True,
        )

        actions.append(None)
        actions.append(menu_manager)
        utils.addActions(self.parent.menus.plugins, actions)

        self.manager.displayPlugins()

    def menuEntry(self, plugin):
        return self.action(
            self.tr(plugin.plugin_object.name),
            plugin.plugin_object.task,
            plugin.plugin_object.shortcut,
            plugin.plugin_object.icon,
            self.tr(plugin.plugin_object.hint),
            enabled=True,
        )

    def showPluginManager(self):
        self.manager.show()
