from PyQt5.QtWidgets import *
from qtpy import QtWidgets
from PyQt5.QtCore import QSize, QEvent, Qt
from PyQt5.QtGui import QFont
from labelme.widgets.helper import Helper
from labelme.fonts.letters_description import LETTER_DESCRIPTIONS
from labelme.fonts.slavic import SlavicFont
from math import isqrt, ceil

class PushButton(QPushButton):
    SIZE = 45
    def __init__(self, text, parent=None):
        super(PushButton, self).__init__(text, parent)
        self.setText(text)
        self.setFixedSize(QSize(PushButton.SIZE, PushButton.SIZE))
        self.setFont(SlavicFont.GetFont(28))  # Увеличенный шрифт
        
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_enlarged_letter)
    
    def show_enlarged_letter(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Информация о букве")
        dialog.setFixedSize(400, 350)  # Компактный размер
        
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Буква с большим шрифтом
        letter_label = QLabel(self.text())
        letter_label.setFont(SlavicFont.GetFont(200))
        letter_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(letter_label)
        
        # Поиск описания
        description_text = "Описание отсутствует"
        current_text = self.text()
        for category in LETTER_DESCRIPTIONS.values():
            if current_text in category:
                description_text = category[current_text]
                break
        
        # Отображение описания
        description = QLabel(description_text)
        description.setWordWrap(True)
        description.setAlignment(Qt.AlignCenter)
        description.setStyleSheet("font-size: 16px;")
        layout.addWidget(description)
        
        # Кнопка закрытия
        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(dialog.close)
        layout.addWidget(close_btn)
        
        dialog.setLayout(layout)
        dialog.exec_()

class Keyboard(QtWidgets.QDialog):
    SLOT_SIZE = 60
    MAX_COLUMNS = 12
    SCREEN_MARGIN_WIDTH = 40
    SCREEN_MARGIN_HEIGHT = 100

    def __init__(self, helper, type=None):
        super(Keyboard, self).__init__()
        self.helper = helper
        
        # Основной layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Добавляем подсказку
        hint_label = QLabel("ПКМ по кнопке - информация о букве")
        hint_label.setAlignment(Qt.AlignCenter)
        hint_label.setStyleSheet("""
            QLabel {
                font-size: 14px;
                padding: 8px;
                background: #f0f0f0;
                border-bottom: 1px solid #d0d0d0;
            }
        """)
        main_layout.addWidget(hint_label)
        
        # Область с кнопками
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        
        if type == 'letter':
            self.symbol_list = list(LETTER_DESCRIPTIONS['letters'].keys()) + list(LETTER_DESCRIPTIONS["titla"].keys())
        elif type == 'diacritical':
            self.symbol_list = list(LETTER_DESCRIPTIONS['diacritical_signs'].keys())
        else:
            self.symbol_list = list(LETTER_DESCRIPTIONS['letters'].keys()) + list(LETTER_DESCRIPTIONS['diacritical_signs'].keys()) + list(LETTER_DESCRIPTIONS["titla"].keys())

        screen_rect = QApplication.desktop().availableGeometry()
        max_window_width = screen_rect.width() - self.SCREEN_MARGIN_WIDTH
        max_window_height = screen_rect.height() - self.SCREEN_MARGIN_HEIGHT

        self.columns = min(isqrt(len(self.symbol_list)) + 1, self.MAX_COLUMNS)
        self.rows = ceil(len(self.symbol_list) / self.columns)

        grid_widget = QWidget()
        self.grid_layout = QGridLayout(grid_widget)
        self.grid_layout.setSpacing(15)
        self.grid_layout.setContentsMargins(15, 15, 15, 15)

        for i, letter in enumerate(self.symbol_list):
            row = i // self.columns
            col = i % self.columns

            letter_layout = QtWidgets.QVBoxLayout()
            letter_layout.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
            letter_layout.setContentsMargins(0, 0, 0, 0)
            letter_layout.setSpacing(0)

            invite_label = QLabel()
            invite_label.setText(f"{self.get_letter(letter)}")
            invite_label.setFont(QFont('Arial', 10))
            letter_layout.addWidget(invite_label, 0, Qt.AlignTop | Qt.AlignHCenter)

            button = PushButton("")
            button.setText(f'{letter}')
            button.clicked.connect(self.click)
            letter_layout.addWidget(button)

            frame = QFrame()
            frame.setObjectName("base_frame")
            frame.setFrameStyle(QFrame.Box | QFrame.Plain)
            frame.setLineWidth(1)
            frame.setFixedSize(Keyboard.SLOT_SIZE, Keyboard.SLOT_SIZE + 5)
            frame.setStyleSheet("#base_frame {border: 1px solid rgb(184, 174, 174); border-radius: 10px;}") 
            frame.setLayout(letter_layout)

            self.grid_layout.addWidget(frame, row, col)

        scroll_area.setWidget(grid_widget)
        main_layout.addWidget(scroll_area)

        button_width = Keyboard.SLOT_SIZE + 30
        button_height = Keyboard.SLOT_SIZE + 30
        
        content_width = min(
            self.columns * button_width + 30,
            max_window_width
        )
        
        content_height = min(
            self.rows * button_height + 30,
            max_window_height
        )

        self.resize(content_width, content_height)
        self.setMinimumSize(
            min(400, content_width),
            min(300, content_height)
        )

        self.text_from_keyboard = None

    def get_letter(self, letter):
        return 'Пробел' if letter == ' ' else letter
        
    def click(self):
        button = QApplication.instance().sender()
        self.text_from_keyboard = button.text()
        self.close()

    def event(self, event):
        if event.type() == QEvent.EnterWhatsThisMode:
            QWhatsThis.leaveWhatsThisMode()
            Helper(self.helper.get_keyboard_helper()).popUp()
        return QDialog.event(self, event)

    def popUp(self):
        self.exec_() 
        return self.text_from_keyboard
    