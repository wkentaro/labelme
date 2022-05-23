from typing import Any, List
from labelme import __main__ as annotator
from labelme.utils import api
from labelme.utils import aws
import sys
import os
import json
from dotenv import dotenv_values
import pandas as pd
from PyQt5 import QtCore, QtWidgets
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QMessageBox
)

class QueueTableModel(QtCore.QAbstractTableModel):
    def __init__(self, data):
        super(QueueTableModel, self).__init__()
        self._data = data

    def data(self, index, role):
        if role == Qt.DisplayRole:
            value = self._data.iloc[index.row(), index.column()]
            return str(value)

    def rowCount(self, index):
        return self._data.shape[0]

    def columnCount(self, index):
        return self._data.shape[1]

    def headerData(self, section, orientation, role):
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return str(self._data.columns[section])
            if orientation == Qt.Vertical:
                return str(self._data.index[section])

class MainWindow(QMainWindow):

    def __init__(self, *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)
        self.setWindowTitle("DeepWalk Manual Software")
        self.setFixedSize(800, 300)

        self.manual_api = api.api_utils()
        self.aws_api = aws.aws_utils()

        self.setWindowTitle("Integrated Annotator")
        self.hlayout = QHBoxLayout()
        self.left_layout = QVBoxLayout()
        self.right_layout = QVBoxLayout()

        self.username_line = QLineEdit()
        self.username_line.setPlaceholderText("username")
        self.left_layout.addWidget(self.username_line)

        self.password_line = QLineEdit()
        self.password_line.setEchoMode(QLineEdit.Password)
        self.password_line.setPlaceholderText("password")
        self.left_layout.addWidget(self.password_line)

        self.aws_key_id_line = QLineEdit()
        self.aws_key_id_line.setPlaceholderText("aws_key_id")
        self.left_layout.addWidget(self.aws_key_id_line)

        self.aws_secret_key_line = QLineEdit()
        self.aws_secret_key_line.setEchoMode(QLineEdit.Password)
        self.aws_secret_key_line.setPlaceholderText("aws_secret_key")
        self.left_layout.addWidget(self.aws_secret_key_line)

        self.login_button = QPushButton()
        self.login_button.setText('Login')
        self.login_button.clicked.connect(self.login)
        self.left_layout.addWidget(self.login_button)

        self.right_layout.addWidget(QLabel("Queues"))

        self.queue_table = QtWidgets.QTableView()
        self.queue_table.setFixedSize(520, 200)
        self.right_layout.addWidget(self.queue_table)

        self.annotate_button = QPushButton()
        self.annotate_button.setText('Annotate')
        self.annotate_button.clicked.connect(self.annotate)
        self.right_layout.addWidget(self.annotate_button)

        self.hlayout.addLayout(self.left_layout)
        self.hlayout.addLayout(self.right_layout)

        self.central_widget = QWidget()
        self.central_widget.setLayout(self.hlayout)
        self.setCentralWidget(self.central_widget)

        self.configure_from_dotenv()
        self.show()

    def configure_from_dotenv(self):
        config = dotenv_values(".env")
        config_vals = ["username", "password", "AWS_KEY_ID", "AWS_SECRET_KEY"]
        if "username" in config:
            self.username_line.setText(config["username"])
        if "password" in config:
            self.password_line.setText(config["password"])
        if "AWS_KEY_ID" in config:
            self.aws_key_id_line.setText(config["AWS_KEY_ID"])
        if "AWS_SECRET_KEY" in config:
            self.aws_secret_key_line.setText(config["AWS_SECRET_KEY"])

        if all(val in config for val in config_vals):
            self.login()

    def login(self):
        username = self.username_line.text()
        password = self.password_line.text()
        aws_key_id = self.aws_key_id_line.text()
        aws_secret_key = self.aws_secret_key_line.text()
        self.aws_api.configure_login(aws_key_id, aws_secret_key)

        code = self.manual_api.login(username, password)
        if (code == 200):
            self.display_queues()
        else:
            QMessageBox.about(self, "", "Log in failed")

    def display_queues(self):
        users_dict =  self.get_users_dict()
        if users_dict is None:
            return

        username_lookup = {}
        for user_id in users_dict:
            username_lookup[user_id] = self.manual_api.getUsername(user_id)
        
        columns = ["username", "to_label", "labelled", "to_qc", "to_fix"]
        internal_data = []
        for user_id in users_dict:
            internal_data.append([
                username_lookup[user_id],
                users_dict[user_id]["preprocessed"],
                users_dict[user_id]["labelled"],
                users_dict[user_id]["qc"],
                users_dict[user_id]["failed"]
            ])
            
        data = pd.DataFrame(internal_data, columns = columns)
        self.queue_table_model = QueueTableModel(data)
        self.queue_table.setModel(self.queue_table_model)

    def get_users_dict(self):
        self.models = self.manual_api.get_models()

        if self.models is None:
            return None

        users_dict = {}
        display_stages = {"preprocessed": 0, "labelled": 0, "qc": 0, "failed": 0}
        for model in self.models:
            model["folder"] = model["folder"].strip('/')
            stage = model["stage"]
            user_id = model["userId"]

            if stage in display_stages:
                if not (user_id in users_dict):
                    users_dict[user_id] = display_stages.copy()
                users_dict[user_id][stage] += 1
        
        return users_dict
                    
    def annotate(self):
        rows = [index.row() for index in self.queue_table.selectedIndexes()]
        cols = [index.column() for index in self.queue_table.selectedIndexes()]
        if len(rows) == 0 or len(cols) == 0:
            return

        if len(rows) > 1 or len(cols) > 1:
            QMessageBox.about(self, "", "Please select one index")
            return

        username_index = self.queue_table_model.index(rows[0], 0)
        username = self.queue_table_model.data(index=username_index, role=0)

        if cols[0] == 1:
            annotator.main(
                "label",
                username,
                self.manual_api,
                self.aws_api,
                config_fp = os.path.abspath("annotator_labelmerc")
            )

        if cols[0] == 3:
            annotator.main(
                "qc",
                username,
                self.manual_api,
                self.aws_api,
                config_fp = os.path.abspath("qc_labelmerc")
            )

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    sys.exit(app.exec_())
