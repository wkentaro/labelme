from barcode_reader.dynamsoft import DynamsoftBarcodeReader
from labelme.label_file import LabelFile
from labelme.shape import Shape
from labelme import PY2
from qtpy import QtCore
from qtpy.QtCore import Qt
from qtpy.QtCore import QThread
from qtpy.QtCore import Signal as pyqtSignal
from qtpy import QtGui
from qtpy import QtWidgets
import threading
import os
import os.path as osp

class IntelligenceWorker(QThread):
    sinOut = pyqtSignal(int,int)
    def __init__(self, parent, images, source):
        super(IntelligenceWorker, self).__init__(parent)
        self.parent = parent
        self.source = source
        self.images = images

    def run(self):
        index = 0
        total = len(self.images)
        for filename in self.images:
            if self.parent.isVisible==False:
                return
            if self.source.operationCanceled==True:
                return
            index = index + 1
            json_name = osp.splitext(filename)[0] + ".json"
            if os.path.exists(json_name):
                continue
            self.sinOut.emit(index,total)
            try:
                print("Decoding "+filename)
                s = self.source.getBarcodeShapesOfOne(filename)
                self.source.saveLabelFile(filename, s)
            except Exception as e:
                print(e)

class Intelligence():
    def __init__(self,parent):
        self.reader = DynamsoftBarcodeReader()
        self.parent = parent
        

            
    def getBarcodeShapesOfOne(self,filename):
        results = self.reader.decode_file(filename)["results"]
        s = []
        for result in results:
            shape = Shape()
            shape.label = result["barcodeFormat"]
            shape.content = result["barcodeText"]
            shape.shape_type="polygon"
            shape.flags = {}
            shape.other_data = {}
            for i in range(1,5):
                x = result["x"+str(i)]
                y = result["y"+str(i)]
                shape.addPoint(QtCore.QPointF(x, y))
            shape.close()
            s.append(shape)
            #self.addLabel(shape)
        return s
        
    def detectBarcodesOfAll(self,images):
        self.pd = self.startOperationDialog()
        self.thread = IntelligenceWorker(self.parent,images,self)
        self.thread.sinOut.connect(self.updateDialog)
        self.thread.start()
    
    def updateDialog(self, completed, total):
        progress = int(completed/total*100)
        self.pd.setLabelText(str(completed) +"/"+ str(total))
        self.pd.setValue(progress)
            
    def startOperationDialog(self):
        self.operationCanceled = False
        pd1 =  QtWidgets.QProgressDialog('Progress','Cancel',0,100,self.parent)
        pd1.setLabelText('Progress')
        pd1.setCancelButtonText('Cancel')
        pd1.setRange(0, 100)
        pd1.setValue(0)
        pd1.setMinimumDuration(0)
        pd1.show()
        pd1.canceled.connect(self.onProgressDialogCanceled)
        return pd1
        
    def onProgressDialogCanceled(self):
        self.operationCanceled = True
        if self.parent.lastOpenDir and osp.exists(self.parent.lastOpenDir):
            self.parent.importDirImages(self.parent.lastOpenDir)
        else:
            self.parent.loadFile(self.parent.filename)
        
    
    def saveLabelFile(self, filename, detectedShapes):
        lf = LabelFile()
        
        def format_shape(s):
            data = s.other_data.copy()
            data.update(
                dict(
                    label=s.label.encode("utf-8") if PY2 else s.label,
                    points=[(p.x(), p.y()) for p in s.points],
                    group_id=s.group_id,
                    content=s.content,
                    shape_type=s.shape_type,
                    flags=s.flags,
                )
            )
            return data

        shapes = [format_shape(item) for item in detectedShapes]
        
        imageData = LabelFile.load_image_file(filename)
        image = QtGui.QImage.fromData(imageData)
        if osp.dirname(filename) and not osp.exists(osp.dirname(filename)):
            os.makedirs(osp.dirname(filename))
        json_name = osp.splitext(filename)[0] + ".json"
        imagePath = osp.relpath(filename, osp.dirname(json_name))
        lf.save(
            filename=json_name,
            shapes=shapes,
            imagePath=imagePath,
            imageData=imageData,
            imageHeight=image.height(),
            imageWidth=image.width(),
            otherData={},
            flags={},
        )