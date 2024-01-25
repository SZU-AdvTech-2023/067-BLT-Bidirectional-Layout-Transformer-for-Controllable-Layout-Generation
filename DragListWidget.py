import sys
from PySide6 import QtCore, QtWidgets, QtGui
from InputForm import InputForm
from connect import DataTransformer


class DragListWidget(QtWidgets.QListWidget):

    itemChanged = QtCore.Signal(int, int, str, object)
    rowChanged = QtCore.Signal(int, int)

    def __init__(self, parent=None):
        super(DragListWidget, self).__init__(parent)
        self.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        # Set minimum width
        self.setMinimumWidth(175)

        # Add an "add" button
        self.add_add_button()

        self.itemClicked.connect(self.on_item_clicked)
        self.currentRowChanged.connect(self.on_current_row_changed)

        self.dataTransformer = DataTransformer()
    
    def on_current_row_changed(self, row):
        self.rowChanged.emit(self.get_tab_index(),row)

    def addNewItem(self):
        # 删除末尾的按钮
        self.takeItem(self.count() - 1)

        # Add a new item to the list
        item = QtWidgets.QListWidgetItem()
        item.setSizeHint(QtCore.QSize(120, 500))  # 设置列表项大小
        self.addItem(item)

        # Create a widget to hold the handle, input form and delete button
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # Add a handle for dragging
        handle = QtWidgets.QLabel(f"{self.count()}.")
        handle.setStyleSheet("font-size: 12px; padding: 5px;")
        fm = QtGui.QFontMetrics(handle.font())
        handle_width = fm.boundingRect(handle.text()).width()+10
        handle.setFixedWidth(handle_width)
        layout.addWidget(handle)
        handle.setProperty("item", item)

        # Add an input form widget
        input_form = InputForm()
        layout.addWidget(input_form)
        input_form.set_index(self.count())
        input_form.inputChanged.connect(self.on_input_changed)
        input_form.sizeChanged.connect(self.on_size_changed)

        # Add a delete button
        delete_button = QtWidgets.QPushButton("X")
        delete_button.setStyleSheet('background-color: rgb(200, 100, 100); color: white; font-weight: bold; font-size: 12px; width: 20px; height: 20px;')
        delete_button.setObjectName("deleteButton")
        delete_button_width = fm.boundingRect(delete_button.text()).width()+10
        delete_button.setFixedWidth(delete_button_width)
        delete_button.setFixedHeight(delete_button_width)
        delete_button.clicked.connect(self.on_delete_button_clicked)
        layout.addWidget(delete_button)
        delete_button.setProperty("item", item)

        self.setItemWidget(item, widget)

        self.setCurrentItem(item)

        # Add an "add" button at the end of the list
        self.add_add_button()
        self.reheight()

        self.itemChanged.emit(self.get_tab_index(), -1, -1, -1)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.setCurrentRow(-1)
        super().mousePressEvent(event)

    def get_tab_index(self):
        split_widget = self.parent()
        if split_widget is None:
            return -1
        tab_widget = split_widget.parent()
        tab_index = tab_widget.indexOf(split_widget)
        return tab_index

    def sizeHint(self):
        # Calculate the total height of all items
        total_height = 0
        for i in range(self.count()):
            item = self.item(i)
            widget = self.itemWidget(item)
            total_height += widget.sizeHint().height()

        # Add space for the add button
        total_height += 30

        # Return the calculated size hint
        return QtCore.QSize(self.viewportSizeHint().width(), total_height)

    def on_input_changed(self, list_index, label, value):
        tab_index = self.get_tab_index()
        self.itemChanged.emit(tab_index, list_index, label, value)
        #print(tab_index,list_index ,label, value)
    
    def on_size_changed(self):
        #print("on_size_changed!")
        self.reheight()

    # Get the sender button and the associated list item
    def on_delete_button_clicked(self):
        sender_button = self.sender()
        list_item = sender_button.property("item")
        # Remove the list item and its widget
        if list_item is not None:
            index = self.row(list_item)
            self.takeItem(index)
        self.remark()
        self.itemChanged.emit(self.get_tab_index(), -1, -1, -1)

    def on_item_clicked(self, item):
        # 获取当前按下的修饰键 
        modifiers = QtWidgets.QApplication.keyboardModifiers() 
        # 判断是否按下了shift键 
        if modifiers == QtCore.Qt.ShiftModifier: 
            index=self.row(item)
            if index==self.count()-1:return
            # get the confirmed data for the given index
            data = self.get_confirmed_data_from_input_form(index)
            # check if all values are True
            if all(data.values()):
                # set all values to False
                for key in data:
                    data[key] = False
            else:
                # set all values to True
                for key in data:
                    data[key] = True
            # set the confirmed data back to the input form
            self.set_confirmed_data_to_input_form(data, index)

            

    def clear_all_items(self):
        self.clear()
        self.add_add_button()
        self.itemChanged.emit(self.get_tab_index(), -1, -1, -1)

    def add_add_button(self):
        # Create a widget to hold the add button
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # Add an "add" button
        add_button = QtWidgets.QPushButton("添加")
        add_button.setFixedHeight(30)
        add_button.setObjectName("addButton")
        add_button.clicked.connect(self.addNewItem)
        
        layout.addWidget(add_button)

        # Add the widget as the last item in the list
        item = QtWidgets.QListWidgetItem()
        item.setSizeHint(QtCore.QSize(120, add_button.height()))
        self.addItem(item)
        self.setItemWidget(item, widget)

    def startDrag(self, supportedActions):
        self.current_item = self.currentItem()
        super(DragListWidget, self).startDrag(supportedActions)

    def dropEvent(self, event):
        if self.current_item is None:
            return
        rect = self.visualItemRect(self.current_item)
        bottom_y = rect.bottom()
        y = event.position().y()

        # 以下判断都是为了防止super().dropEvent(event)出错。
        if 0 <= y - bottom_y <= rect.height()//2 or self.currentRow() == self.count() - 2 and y > bottom_y:
            return

        # Remove the "add" button from the list
        self.takeItem(self.count() - 1)

        super().dropEvent(event)
        event.accept()

        self.remark()

        # Add the "add" button back to the list
        self.add_add_button()
        self.setCurrentRow(-1)
        self.setCurrentItem(self.current_item)

        self.itemChanged.emit(self.get_tab_index(), -1, -1, -1)

    def resizeEvent(self, event):
        self.reheight()
        super().resizeEvent(event)

    def remark(self):
        for i in range(self.count()):
            # 获取每个项的widget
            #widget = self.itemWidget(self.item(i)).layout().itemAt(0).widget()
            item = self.itemWidget(self.item(i))
            # 如果widget是QPushButton，则跳过
            if item is None or isinstance(item.layout().itemAt(0).widget(), QtWidgets.QPushButton):
                continue
            # 更新把手
            handle = item.layout().itemAt(0).widget()
            handle.setText(f"{i+1}.")
            fm = QtGui.QFontMetrics(handle.font())
            handle_width = fm.boundingRect(handle.text()).width()+10
            handle.setFixedWidth(handle_width)
            # 更新序号
            item.layout().itemAt(1).widget().set_index(i+1)

    def reheight(self):
        for i in range(self.count()):
            item = self.item(i)
            widget = self.itemWidget(item)
            # 获取每个项的widget
            # 如果widget是QPushButton，则跳过
            if widget is None or isinstance(widget.layout().itemAt(0).widget(), QtWidgets.QPushButton):
                continue
            input_form = self.input_form(i)
            item.setSizeHint(QtCore.QSize(120, input_form.height()+10))

    def input_form(self, i):
        item = self.item(i)
        widget = self.itemWidget(item)
        # 获取每个项的widget
        # 如果widget是QPushButton，则跳过
        if widget is None or isinstance(widget.layout().itemAt(0).widget(), QtWidgets.QPushButton):
            return None
        input_form = widget.layout().itemAt(1).widget()
        return input_form

    def get_data_from_input_form(self, index=None):
        if index is not None:
            input_form = self.input_form(index)
            if input_form is not None:
                return input_form.get_data()
            else:
                return None
        else:
            data = []
            for i in range(self.count()-1):
                input_form = self.input_form(i)
                if input_form is not None:
                    data.append(input_form.get_data())
            return data

    def get_confirmed_data_from_input_form(self, index=None):
        if index is not None:
            input_form = self.input_form(index)
            if input_form is not None:
                return input_form.get_confirmed()
            else:
                return None
        else:
            confirmed_data = []
            for i in range(self.count()-1):
                input_form = self.input_form(i)
                if input_form is not None:
                    confirmed_data.append(input_form.get_confirmed())
            return confirmed_data

    def set_data_to_input_form(self, data, index=None):
        self.blockSignals(True)
        if index is not None:
            input_form = self.input_form(index)
            if input_form is not None:
                input_form.set_data(data)
        else:
            if len(data) != self.count() - 1:
                print("Error: Data length does not match the number of input forms.")
                return
            for i in range(len(data)):
                input_form = self.input_form(i)
                if input_form is not None:
                    input_form.set_data(data[i])
        self.blockSignals(False)
        self.on_input_changed(-1, -1, -1)


    def set_confirmed_data_to_input_form(self, confirmed_data, index=None):
        self.blockSignals(True)
        if index is not None:
            input_form = self.input_form(index)
            if input_form is not None:
                input_form.set_confirmed(confirmed_data)
        else:
            if len(confirmed_data) != self.count() - 1:
                print(
                    "Error: Confirmed data length does not match the number of input forms.")
                return
            for i in range(len(confirmed_data)):
                input_form = self.input_form(i)
                if input_form is not None:
                    input_form.set_confirmed(confirmed_data[i])
        self.blockSignals(False)
        self.on_input_changed(-1, -1, -1)


    def load_data(self, data, confirmed_data=None):
        self.blockSignals(True)
        # Clear all items
        self.clear_all_items()

        # Check if data and confirmed_data have the same length
        if confirmed_data is not None:
            if len(data) != len(confirmed_data):
                print("Error: Data and confirmed data do not have the same length.")
                return

        # Add new items
        for _ in range(len(data)):
            self.addNewItem()

        # Set data and confirmed data
        self.set_data_to_input_form(data)
        if confirmed_data is not None:
            self.set_confirmed_data_to_input_form(confirmed_data)
        self.blockSignals(False)
        self.on_input_changed(-1, -1, -1)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()

        self.list_widget = DragListWidget()

        # Add some items to the list
        for i in range(5):
            self.list_widget.addNewItem()

        # Set the list widget as the central widget of the window
        self.setCentralWidget(self.list_widget)


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
