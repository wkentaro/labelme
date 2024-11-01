from qtpy.QtGui import QFontDatabase, QFont

import labelme.fonts.font_rc

from labelme.logger import logger

class SlavicFont:  
    # def usage_example():
    #     label = QtWidgets.QLabel("AI Prompt")
    #     label.setText("Якосhрjаxл на де\\\\\\\\еалеt")
    #     label.setFont(SlavicFont.GetFont())
    
    __font = None

    ALL_LETTERS = ' !"#$%\'+,-.0123456789:;<=>?ABCDEFGHIJKLMNOPQRSTUVWXYZ\\^_`abcdefghijklmnopqrstuvwxyz{|}ЂЃѓ…†‡€‰Љ‹ЊЌЋЏђ‘’“”•™љ›њќћџЎўЈ¤Ґ¦§Ё©®Ї°±Ііґµё№єјЅѕїАБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдежзийклмнопрстуфхцчшщъыьэюя'
    LETTERS = 'абвгдежзийклмнопрстуфхцчшщъыьэюяfimoptvwxzіµѕ !,.;:°'
    DIACRITICAL_SIGNS = '123568'
    TITLA = '+7=>?bcdg'
    
    @classmethod    
    def GetFont(cls, size):
        if cls.__font is None:
            fontId = QFontDatabase.addApplicationFont(":/Hirmos_new.ttf")
            if fontId == 0:
                fontName = QFontDatabase.applicationFontFamilies(fontId)[0]
                cls.__font = QFont(fontName, size)
            else:
                cls.__font = QFont()
                logger.warning("Failed to load slavic font. Loading default font.")
        return cls.__font
    