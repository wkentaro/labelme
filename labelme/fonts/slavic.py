from qtpy.QtGui import QFontDatabase, QFont

import labelme.fonts.fonts_rc

from labelme.logger import logger

class SlavicFont:  
    # def __new__(cls):
    #     if not hasattr(cls, "instance"):
    #         cls.instance = super(SlavicFont, cls).__new__(cls)
    #     return cls.instance
    
    # @staticmethod
    # def __get_font() -> QFont:     
    #     fontId = QFontDatabase.addApplicationFont(":/fonts/Hirmos.ttf")
    #     if fontId == 0:
    #         fontName = QFontDatabase.applicationFontFamilies(fontId)[0]
    #         font = QFont(fontName)
    #     else:
    #         font = QFont()
    #         logger.warning("Failed to load slavic font. Loading default font.")
    #     return font
    
    # __font = __get_font()
    
    # def GetFont(self):
    #     return self.GetFont()
    def usage_example():
        label = QtWidgets.QLabel("AI Prompt")
        label.setText("Якосhрjаxл на де\\\\\\\\еалеt")
        label.setFont(SlavicFont.GetFont())

    
    __font = None
    
    @classmethod    
    def GetFont(cls):
        if cls.__font is None:
            fontId = QFontDatabase.addApplicationFont(":/fonts/Hirmos.ttf")
            if fontId == 0:
                fontName = QFontDatabase.applicationFontFamilies(fontId)[0]
                cls.__font = QFont(fontName)
            else:
                cls.__font = QFont()
                logger.warning("Failed to load slavic font. Loading default font.")
        return cls.__font