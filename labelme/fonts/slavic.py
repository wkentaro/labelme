from qtpy.QtGui import QFontDatabase, QFont
import labelme.fonts.font_rc
from labelme.logger import logger

class SlavicFont:
    LETTERS = 'абвгдежзийклмнопрстуфхцчшщъыьэюяufimoptvwxzіµѕ ,.;:°'
    DIACRITICAL_SIGNS = '1268'
    TITLA = '57+=>?bcdg'
    
    __font_family = None
    
    @classmethod
    def load_font(cls):
        if cls.__font_family is None:
            font_id = QFontDatabase.addApplicationFont(":/Hirmos_with_t_titlo.ttf")
            if font_id >= 0:
                cls.__font_family = QFontDatabase.applicationFontFamilies(font_id)[0]
            else:
                logger.warning("Failed to load slavic font. Using default font.")
                cls.__font_family = ""
        return cls.__font_family
    
    @classmethod
    def GetFont(cls, size=12):
        font_family = cls.load_font()
        font = QFont(font_family if font_family else "")
        font.setPixelSize(size)
        font.setStyleStrategy(QFont.PreferAntialias | QFont.PreferQuality)
        return font
    