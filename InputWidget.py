from PySide6 import QtWidgets, QtGui, QtCore
from collections.abc import Iterable
import sys


class InputWidget(QtWidgets.QWidget):
    dataChanged = QtCore.Signal(str, object)
    sizeChanged = QtCore.Signal()

    def __init__(self, button_label: str, data):
        super().__init__()
        self.data = data
        self.layout = QtWidgets.QHBoxLayout()
        self.button = QtWidgets.QPushButton(button_label)
        self.button.clicked.connect(self.on_button_clicked)
        self.layout.addWidget(self.button)

        # 计算按钮标签的宽度
        fm = QtGui.QFontMetrics(self.button.font())
        self.button_width = fm.boundingRect(button_label).width() + 10

        # 设置按钮的最小大小
        self.button.setFixedWidth(self.button_width)

        if isinstance(data, Iterable):
            self.combo_box = QtWidgets.QComboBox()
            self.combo_box.addItems(data)

            # 计算 combo_box 内容物的宽度
            max_width = 0
            for item in data:
                item_width = fm.boundingRect(item).width()+25
                max_width = max(max_width, item_width)
            # 设置 combo_box 的最小大小
            self.combo_box.setFixedWidth(max_width)
            self.box_width = max_width

            self.layout.addWidget(self.combo_box)

            # 连接 combo_box 的 currentTextChanged 信号到自定义的槽函数，并在槽函数中发出自定义信号
            self.combo_box.currentTextChanged.connect(self.on_combo_changed)
            self.box = self.combo_box

            self.sizehint = QtCore.QSize(
                self.button_width+self.box_width+10, 25) # combo_box默认显示

        elif isinstance(data, int):
            self.spin_box = QtWidgets.QSpinBox()
            self.spin_box.setRange(0, data - 1)

            # 计算 spin_box 内容物的宽度
            max_val_str = str(data - 1)
            max_width = fm.boundingRect(max_val_str).width()+25

            # 设置 spin_box 的最小大小
            self.spin_box.setFixedWidth(max_width)
            self.box_width = max_width

            self.layout.addWidget(self.spin_box)

            # 连接 spin_box 的 valueChanged 信号到自定义的槽函数，并在槽函数中发出自定义信号
            self.spin_box.valueChanged.connect(self.on_spin_changed)
            self.box = self.spin_box

            self.box.hide()
            self.sizehint = QtCore.QSize(self.button_width, 25)  # spin_box默认隐藏

        self.setLayout(self.layout)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.RightButton:
            if self.box.isVisible():
                self.box.hide()
                self.sizehint = QtCore.QSize(self.button_width, 25)
            else:
                self.box.show()
                self.sizehint = QtCore.QSize(
                    self.button_width+self.box_width+10, 25)
            self.sizeChanged.emit()

    def on_combo_changed(self, text):
        # 发出自定义信号，并传递当前文本作为参数
        self.dataChanged.emit(self.button.text(), text)

    def on_spin_changed(self, value):
        # 发出自定义信号，并传递当前值作为参数
        self.dataChanged.emit(self.button.text(), value)

    def sizeHint(self):
        return self.sizehint

    def on_button_clicked(self):
        if "background-color: gray" in self.styleSheet():
            self.setStyleSheet("")
        else:
            self.setStyleSheet("background-color: gray")

    def get_data(self):
        if hasattr(self, 'combo_box'):
            return self.combo_box.currentText()
        elif hasattr(self, 'spin_box'):
            return self.spin_box.value()

    def is_confirmed(self):
        return "background-color: gray" in self.styleSheet()

    def set_data(self, value):
        if hasattr(self, 'combo_box'):
            index = self.combo_box.findText(value)
            if index != -1:
                self.combo_box.setCurrentIndex(index)
        elif hasattr(self, 'spin_box'):
            self.spin_box.setValue(value)

    def set_confirmed(self, confirmed):
        if confirmed:
            self.setStyleSheet("background-color: gray")
        else:
            self.setStyleSheet("")


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = InputWidget("C", ["A", "B", "C"])
    window.show()
    sys.exit(app.exec())
