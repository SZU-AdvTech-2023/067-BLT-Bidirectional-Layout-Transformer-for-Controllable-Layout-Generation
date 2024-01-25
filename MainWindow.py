import sys
import json
from PySide6.QtWidgets import QApplication, QMainWindow, QToolBar, QTabWidget, QSplitter, QWidget, QLabel, QFileDialog,QMessageBox
from PySide6.QtCore import Qt, QSaveFile, QIODevice, QDir, QFileInfo, QFile
from PySide6.QtGui import QAction
from DragListWidget import DragListWidget
from CanvaAndButton import CanvaAndButton
from connect import ModelConnecter
from ppt import PPTPage


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("基于transformer的文档布局生成器")

        # Create toolbar
        toolbar = self.addToolBar("Toolbar")
        load_action = toolbar.addAction("加载")
        load_action.triggered.connect(self.do_load)
        new_action = toolbar.addAction("新建")
        new_action.triggered.connect(self.new_tab)
        help_action=toolbar.addAction("帮助")
        help_action.triggered.connect(self.show_help)
        lock_action=toolbar.addAction("全部锁定")
        lock_action.triggered.connect(self.lock_all)
        clean_action=toolbar.addAction("纯净模式")
        clean_action.triggered.connect(self.clean_mode)

        # Create tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setUsesScrollButtons(True)
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setMovable(True)
        self.tab_widget.tabCloseRequested.connect(self.close_tab)

        self.resize(1000, 700)

        # Add initial tab
        self.new_tab()

        # Set central widget
        self.setCentralWidget(self.tab_widget)

        self.model_connecter = ModelConnecter()

        self.save_directory = "../save"
        self.save_file = "data.txt"

    def show_help(self):
        """
        显示帮助信息
        """
        msg = QMessageBox()
        msg.setWindowTitle("使用说明")
        msg.setText("请参考以下说明：")
        msg.setInformativeText("""
        简单入门：

        使用“添加”按钮添加任意数量的元素后，点击“生成”，就能生成含有指定数量元素的布局了。
        “导出”按钮可以生成的布局以ppt的形式导出，可以观察布局对应到文档中的效果，也可以复制到word中直接使用。
        “保存”按钮可以将生成的布局连同锁定信息一起保存，以供以后读取。
        “检测”按钮可以检测出与全局不相符的元素，如果已经选中这个元素，则会尝试调整。
        
        进阶操作：

        元素属性从左到右是：
        C:元素类型
        X:左上角横坐标
        Y:左上角纵坐标
        W:元素宽度
        H:元素高度
        A:面积
        R:长宽比
        需要说明的是：面积和长宽比并不是实际的面积和长宽比，而是做了一定映射，这里建议使用下面提到是拖放操作来设置面积和长宽比。

        右键点击元素属性的按钮可以将其展开或关闭，展开后，可以进行具体数值的调整。
        左键点击点击元素属性的按钮可以锁定其数值，锁定后，模型将不会修改其数值，而是将其作为约束生成其他内容。
        按住shift再点击这个元素的空白部分可以一次性锁定这个元素的所有属性。
        
        当你选择一个元素时，右侧这个元素对应的矩形边框会变成黑色，此时能在右侧画布中拖放以设置这个元素的尺寸信息。
        如果按住shift再进行拖放，则只会修改元素的位置。

        按住元素进行拖动可以调整此元素在序列中的顺序，顺序越靠后，这个元素在生成结果中的阅读顺序也会靠后。可以观察右边画框中的角标信息和代表阅读顺序的折线。

        注意事项：
        如果你希望自定义导出的内容,可以查阅./ppt/文件夹下的说明。尽管有自定义的功能，但最好还是在导出的ppt中进行修改。
        这个模型是一个基于概率的机器学习模型。按照给定的约束生成可能性最高的输出。然而，如果约束与训练数据相差过大可能无法生成合理的结果。并且，体积和长宽比的约束效力并不强，模型有可能不按照给定的约束生成结果。训练集的元素个数最大是23个，如果输入的元素个数超过23个，模型可能会出错。

        """)
        msg.setIcon(QMessageBox.Information)
        msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        msg.exec()

    def new_tab(self, check=False, name="New Tab"):
        """
        新建一个tab
        """
        # Create split widget
        split_widget = QSplitter()

        # Add DragListWidget and CanvaAndButton to split widget
        draglist = DragListWidget()
        split_widget.addWidget(draglist)
        draglist.itemChanged.connect(self.on_item_Changed)
        draglist.rowChanged.connect(self.on_row_Changed)
        canva_and_button = CanvaAndButton()
        canva_and_button.rectChanged.connect(self.on_rect_Changed)
        canva_and_button.ask_generate.connect(self.do_generate)
        canva_and_button.ask_detect.connect(self.do_detect)
        canva_and_button.ask_export.connect(self.do_export)
        canva_and_button.ask_save.connect(self.do_save)
        split_widget.addWidget(canva_and_button)

        # Set initial splitter position
        split_widget.setSizes([self.width() / 3, self.width() / 3 * 2])
        split_widget.setStretchFactor(0, 0)
        split_widget.setStretchFactor(1, 1)

        # Set color of splitter handle
        split_widget.setStyleSheet(
            "QSplitter::handle { background-color: black }")

        # Add tab to tab widget
        index = self.tab_widget.addTab(split_widget, name)
        self.tab_widget.setCurrentIndex(index)
        self.render({}, tab_index=index)

    def do_generate(self, tab_index=None):
        """
        生成布局
        """
        if tab_index is None:
            tab_index = self.tab_widget.currentIndex()
        data = self.get_data(tab_index)
        confirmed = self.get_confirmed_data(tab_index)
        generated_data = self.model_connecter.generate(data, confirmed)
        data = self.set_data(generated_data,tab_index)

    def do_detect(self, tab_index=None):
        """
        离群值检测
        """
        if tab_index is None:
            tab_index = self.tab_widget.currentIndex()

        data = self.tab_widget.widget(tab_index).widget(0).get_data_from_input_form()
        index=self.model_connecter.detect(data)
        if index != self.tab_widget.widget(tab_index).widget(0).currentRow():
            
            self.tab_widget.widget(tab_index).widget(0).setCurrentRow(index)
        else:
            confirmed_data = self.get_confirmed_data(tab_index)
            data = self.get_data(tab_index)
            confirmed_data = [{key: (True if i !=index else confirmed_data[i][key])  for key in item.keys()} for i,item in  enumerate(confirmed_data)]
            generated_data = self.model_connecter.generate(data, confirmed_data)
            data = self.set_data(generated_data,tab_index)

    def do_export(self, tab_index=None):
        """
        导出布局
        """
        if tab_index is None:
            split_widget = self.tab_widget.currentWidget()
        else:
            split_widget = self.tab_widget.widget(tab_index)
        data = split_widget.widget(0).get_data_from_input_form()

        # create a file dialog to select file name and path
        file_dialog = QFileDialog(self)
        # set mode to save file
        file_dialog.setAcceptMode(QFileDialog.AcceptSave)
        file_dialog.setFileMode(QFileDialog.AnyFile)  # set mode to any file

        # set filter to only allow txt files
        file_dialog.setNameFilter("*.pptx")

        # set default directory and file name
        file_dialog.setDirectory(QDir(self.save_directory))
        file_dialog.selectFile("output.pptx")

        if file_dialog.exec():  # show the dialog and wait for user input
            # get the selected file name
            file_name = file_dialog.selectedFiles()[0]

            page = PPTPage()
            page.rander(data, size=self.model_connecter.model_caller.size)
            page.save(filename=file_name)

    def do_save(self, tab_index=None):
        """
        保存布局
        """
        if tab_index is None:
            split_widget = self.tab_widget.currentWidget()
        else:
            split_widget = self.tab_widget.widget(tab_index)
        tab_index = self.tab_widget.indexOf(
            split_widget)  # get the index of the widget
        data = split_widget.widget(0).get_data_from_input_form()
        confirmed = split_widget.widget(0).get_confirmed_data_from_input_form()
        save_data = [data, confirmed]

        # create a file dialog to select file name and path
        file_dialog = QFileDialog(self)
        # set mode to save file
        file_dialog.setAcceptMode(QFileDialog.AcceptSave)
        file_dialog.setFileMode(QFileDialog.AnyFile)  # set mode to any file

        # set filter to only allow txt files
        file_dialog.setNameFilter("*.txt")

        # set default directory and file name
        file_dialog.setDirectory(QDir(self.save_directory))
        file_dialog.selectFile("data.txt")

        if file_dialog.exec():  # show the dialog and wait for user input
            # get the selected file name
            file_name = file_dialog.selectedFiles()[0]

            # convert save_data to json string
            json_data = json.dumps(save_data)

            # create a QSaveFile object with the file name
            save_file = QSaveFile(file_name)

            # open the file for writing
            if save_file.open(QIODevice.WriteOnly):
                # write the json data to the file
                # encode the string as bytes
                save_file.write(json_data.encode())

                # commit the write operation and rename the temporary file
                if save_file.commit():
                    print("Data saved successfully")
                else:
                    print("Failed to save data")
                    save_file.cancelWriting()  # discard the temporary file

                # create a QFileInfo object with the selected file path
                file_info = QFileInfo(file_dialog.selectedFiles()[0])
                # get the directory path as a string
                self.save_directory = file_info.dir().path()
                self.save_file = file_info.fileName()  # get the file name as a string
                # set the tab name to baseName
                self.tab_widget.setTabText(tab_index, file_info.baseName())
            else:
                print("Failed to open file for writing")

    def do_load(self):
        """
        加载布局
        """
        # create a file dialog to select file name and path
        file_dialog = QFileDialog(self)
        # set mode to open file
        file_dialog.setAcceptMode(QFileDialog.AcceptOpen)
        # set mode to existing file
        file_dialog.setFileMode(QFileDialog.ExistingFile)

        # set filter to only allow txt files
        file_dialog.setNameFilter("*.txt")

        # set default directory
        file_dialog.setDirectory(QDir(self.save_directory))

        if file_dialog.exec():  # show the dialog and wait for user input
            # get the selected file name
            file_name = file_dialog.selectedFiles()[0]
            # create a QFileInfo object with the selected file path
            file_info = QFileInfo(file_dialog.selectedFiles()[0])
            # create a QFile object with the file name
            load_file = QFile(file_name)

            # open the file for reading
            if load_file.open(QIODevice.ReadOnly):
                # read the json data from the file
                json_data = load_file.readAll().data()  # decode the bytes as string

                # convert json string to save_data list
                load_data = json.loads(json_data)

                print("Data loaded successfully")

                self.new_tab(name=file_info.baseName())
                split_widget = self.tab_widget.currentWidget()
                drag_list_widget = split_widget.widget(0)

                drag_list_widget.load_data(load_data[0], load_data[1])

                return load_data

            else:
                print("Failed to open file for reading")

    def lock_all(self):
        """
        全部锁定
        """
        # 获取当前选择的tab_index
        tab_index = self.tab_widget.currentIndex()

        # 调用self.get_confirmed_data(tab_index)获取数据
        data = self.get_confirmed_data(tab_index)

        # 判断是否所有项都为True
        if all(value for item in data for value in item.values()):
            # 如果所有项都为True，则全部改为False
            confirmed_data = [{key: False for key in item.keys()} for item in data]
        else:
            # 如果不是所有项都为True，则全部改为True
            confirmed_data = [{key: True for key in item.keys()} for item in data]

        # 调用self.set_confirmed_data(confirmed_data，tab_index)保存数据
        self.set_confirmed_data(confirmed_data, tab_index)
    
    def clean_mode(self):
        """
        纯净模式
        """
        split_widget = self.tab_widget.currentWidget()
        split_widget.widget(1).set_clean_mode(not split_widget.widget(1).if_clean_mode())
        


    def on_item_Changed(self, tab_index, list_index, label, value):
        """
        当列表中的元素被修改时，更新布局
        """
        data = self.get_data(tab_index=tab_index)
        self.render(data, tab_index=tab_index)
    
    def on_row_Changed(self,tab_index,list_index):
        """
        当列表中选中的行被修改时，更新布局
        """
        if tab_index is None:
            split_widget = self.tab_widget.currentWidget()
        else:
            split_widget = self.tab_widget.widget(tab_index)
        split_widget.widget(1).set_selected_row(list_index)
        

    def on_rect_Changed(self, tab_index):
        """
        当画布中的矩形被修改时，更新布局
        """
        split_widget = self.tab_widget.widget(tab_index)
        list_index = split_widget.widget(0).currentRow()
        if list_index == -1:
            return
        data = split_widget.widget(1).get_rect()

        # 获取当前按下的修饰键
        modifiers = QApplication.keyboardModifiers()

        # 判断是否按下了shift键
        if modifiers == Qt.ShiftModifier:
            # 如果按下了shift键，则修改位置
            data = split_widget.widget(1).get_pos()
            self.set_data(data, list_index=list_index)
        else:
            # 如果没有按下shift键，进行正常的矩形绘制
            data = split_widget.widget(1).get_rect()
            self.set_data(data, list_index=list_index)

    def render(self, data, tab_index=None, list_index=None):
        """
        渲染布局
        """
        if tab_index is None:
            split_widget = self.tab_widget.currentWidget()
        else:
            split_widget = self.tab_widget.widget(tab_index)
        split_widget .widget(1).render_layout(data)

    def close_tab(self, index):
        """
        关闭tab
        """
        self.tab_widget.removeTab(index)

    def get_data(self, tab_index=None, list_index=None):
        """
        获取数据
        """
        if tab_index is None:
            split_widget = self.tab_widget.currentWidget()
        else:
            split_widget = self.tab_widget.widget(tab_index)
        drag_list_widget = split_widget .widget(0)
        data = drag_list_widget.get_data_from_input_form(list_index)
        # print(*data,sep="\n")
        return data

    def get_confirmed_data(self, tab_index=None, list_index=None):
        """
        获取确认数据
        """
        if tab_index is None:
            split_widget = self.tab_widget.currentWidget()
        else:
            split_widget = self.tab_widget.widget(tab_index)
        drag_list_widget = split_widget .widget(0)
        confirmed_data = drag_list_widget.get_confirmed_data_from_input_form(
            list_index)
        #print(*confirmed_data, sep="\n")
        return confirmed_data

    def set_data(self, data, tab_index=None, list_index=None):
        """
        设置数据
        """
        if tab_index is None:
            split_widget = self.tab_widget.currentWidget()
        else:
            split_widget = self.tab_widget.widget(tab_index)
        drag_list_widget = split_widget .widget(0)
        drag_list_widget.set_data_to_input_form(data, list_index)

    def set_confirmed_data(self, confirmed_data, tab_index=None, list_index=None):
        """
        设置确认数据
        """
        if tab_index is None:
            split_widget = self.tab_widget.currentWidget()
        else:
            split_widget = self.tab_widget.widget(tab_index)
        drag_list_widget = split_widget .widget(0)
        drag_list_widget.set_confirmed_data_to_input_form(
            confirmed_data, list_index)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())