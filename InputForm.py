from PySide6 import QtWidgets,QtCore
from flowlayout import FlowLayout
from InputWidget import InputWidget
import sys


class InputForm(QtWidgets.QWidget):
    
    inputChanged = QtCore.Signal(int,str, object)
    sizeChanged = QtCore.Signal()

    def __init__(self, datasize=2**8):
        super().__init__()
        self.index=0
        self.flowlayout = FlowLayout()
        self.widgets = {}
        labels = ["C", "X", "Y", "W", "H", "A", "R"]
        data = [["text", "title", "list", "table", "figure"]] + [datasize] * 6
        for label, data in zip(labels, data):
            widget = InputWidget(label, data)
            self.widgets[label] = widget
            self.flowlayout.addWidget(widget)
            widget.dataChanged.connect(self.on_data_changed)
            widget.sizeChanged.connect(self.on_size_changed)
        self.setLayout(self.flowlayout)

    def on_data_changed(self, label, value):
        self.inputChanged.emit(self.index,label, value)
    def on_size_changed(self):
        self.flowlayout.setGeometry(self.flowlayout.geometry())
        self.sizeChanged.emit()

    def get_index(self):
        return self.index
    
    def set_index(self,index):
        self.index=index

    def get_data(self):
        data = {}
        for label, widget in self.widgets.items():
            data[label] = widget.get_data()
        return data

    def get_confirmed(self):
        confirmed = {}
        for label, widget in self.widgets.items():
            confirmed[label] = widget.is_confirmed()
        return confirmed

    def set_data(self, data):
        for label, value in data.items():
            if label in self.widgets:
                self.widgets[label].set_data(value)

    def set_confirmed(self, confirmed):
        for label, value in confirmed.items():
            if label in self.widgets:
                self.widgets[label].set_confirmed(value)

    def height(self) -> int:
        return self.flowlayout.heightForWidth(self.width())


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = InputForm()
    window.show()
    sys.exit(app.exec())
