from PyQt5.QtWidgets import QListWidget, QListWidgetItem
from PyQt5.QtCore import Qt

class FileListWidget(QListWidget):
    def set_base_path(self, base_path):
        self.base_path = base_path

    def addItem(self, item):
        # 提取文件名（不带路径）
        full_path = item.text()
        filename = full_path[len(self.base_path):]
        # 创建项并存储完整路径到 UserRole
        item.setData(Qt.UserRole, full_path)  # 存储完整路径
        item.setData(Qt.UserRole + 1, filename)  # 存储文件名
        super().addItem(item)
        self._update_display_text()  # 更新显示文本

    def _update_display_text(self):
        for row in range(self.count()):
            item = self.item(row)
            filename = item.data(Qt.UserRole+1)
            item.setText(f"{row + 1}: {filename}")  # 显示带行号的文件名