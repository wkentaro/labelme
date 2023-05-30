from yapsy.IPlugin import IPlugin


class PluginOne(IPlugin):

    def __init__(self):
        super().__init__()
        self.context = None
        self.shortcut = None
        self.icon = None
        self.name = "This is plugin 1"
        self.hint = "This is an awesome plugin"
        self.reply = None

    def setContext(self, context):
        self.context = context

    def task(self):
        print(self.name)

