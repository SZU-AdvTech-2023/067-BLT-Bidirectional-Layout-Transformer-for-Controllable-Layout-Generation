# 导入PySide6模块
from PySide6.QtWidgets import QApplication, QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QFrame
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QIcon, QPolygon, QImage, QPixmap
from PySide6.QtCore import Qt, QPoint, QRect, QSize, QRectF, QSizeF
from PySide6 import QtCore
import sys
from connect import adjust_rect, clamp, DataTransformer

# 定义自定义的画板类，继承自QFrame


class Canvas(QFrame):

    rectChanged = QtCore.Signal()

    def __init__(self):
        super().__init__()
        # 设置画板的背景颜色为白色
        self.setStyleSheet("background-color: white;")
        # 设置画板的边框样式为黑色实线
        self.setFrameStyle(QFrame.Box | QFrame.Plain)
        self.pixmap = QPixmap()
        # 添加一个属性来保存当前的矩形坐标
        self.rect = None
        self.canvas_size = 1024
        self.layout = {}
        self.select = -1
        self.clean_mode=False
        self.dataTransformer = DataTransformer()

    
    def render_layout(self, layout=None, select=-1):
        if layout is not None:
            self.layout = layout
        if select != -1:
            self.select = select
            
        # 调用render_layout(data)将数据渲染为qpixmap类型
        self.dataTransformer.randerSize=int(1.5*self.canvas_size)
        self.pixmap = self.dataTransformer.render_layout(self.layout,select=self.select,clean_mode=self.clean_mode)
        # 更新画板
        self.update()


    def set_selected_row(self,row):
        self.select=row
        self.render_layout()
    def if_clean_mode(self):
        return self.clean_mode

    def set_clean_mode(self,clean_mode):
        self.clean_mode=clean_mode
        self.render_layout()

    def resizeEvent(self, event):
        # 获取窗口的宽度和高度
        window_width = self.parent().width()
        window_height = self.parent().height()

        # 计算出画板的大小和位置
        self.canvas_size = min(window_width, window_height-50)
        canvas_x = (window_width - self.canvas_size) / 2
        canvas_y = 0  # (window_height - canvas_size) / 2

        # 使用setGeometry方法来设置画板的几何形状
        self.setGeometry(canvas_x, canvas_y,
                         self.canvas_size, self.canvas_size)

        self.render_layout()


    def paintEvent(self, event):
        # 将图片绘制到画板上，并根据画板的大小进行缩放
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self.width(), self.height(), self.pixmap)

        '''
        if self.rect:
            painter.setPen(QPen(Qt.red)) # 设置矩形的颜色为红色
            painter.setBrush(Qt.NoBrush) # 设置矩形不填充颜色
            painter.drawRect(self.rect) # 绘制矩形
        '''
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # 如果鼠标左键按下，获取鼠标位置，并将其作为矩形起始点
            self.rect = QRectF(event.position(), QSizeF())

            self.update()
            self.rectChanged.emit()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self.rect:
            # 如果鼠标左键移动，并且有当前矩形，更新矩形大小

            bottom_right = event.position()
            top_left = self.rect.topLeft()

            width = bottom_right.x() - top_left.x()
            height = bottom_right.y() - top_left.y()

            size = QSizeF(width, height)
            self.rect.setSize(size)

            self.update()
            self.rectChanged.emit()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect:
            # 如果鼠标左键松开，并且有当前矩形，完成绘制
            self.update()
            self.rectChanged.emit()
        else:
            super().mouseReleaseEvent(event)

    def get_rect(self):
        # 获取画板的宽度和高度
        canvas_width = self.width()
        canvas_height = self.height()

        # 创建一个QRectF对象
        r = adjust_rect(self.rect)

        # 用画板的宽度和高度来除以矩形的x、y、width和height，得到缩放后的矩形
        # 把r的x、y、width和height限制在0~1之间
        r.moveTo(clamp(r.x() / canvas_width, 0, 1),
                 clamp(r.y() / canvas_height, 0, 1))
        r.setWidth(clamp(r.width() / canvas_width, 0, 1))
        r.setHeight(clamp(r.height() / canvas_height, 0, 1))
        # 把QRectF对象转换为dict
        r = self.dataTransformer.qrectf_to_dict(r)

        return r

    def get_pos(self):
        # 获取画板的宽度和高度
        canvas_width = self.width()
        canvas_height = self.height()

        pos = self.rect.bottomRight()

        pos.setX(clamp(pos.x() / canvas_width, 0, 1))
        pos.setY(clamp(pos.y() / canvas_height, 0, 1))

        r = self.dataTransformer.pos_to_dict(pos)
        # print(r.bottomRight())

        return r  # 把QRectF对象转换为dict

    # 定义自定义的按钮组件类，继承自QWidget


class ButtonWidget(QWidget):

    ask_generate = QtCore.Signal()
    ask_export = QtCore.Signal()
    ask_save = QtCore.Signal()
    ask_detect = QtCore.Signal()

    def __init__(self):
        super().__init__()

        # 创建三个QPushButton对象，并设置它们的图标和文本
        self.generate_button = QPushButton()
        self.generate_button.setText("生成")
        self.generate_button.clicked.connect(self.ask_generate)

        self.detect_button = QPushButton()
        self.detect_button.setText("检测")
        self.detect_button.clicked.connect(self.ask_detect)

        self.export_button = QPushButton()
        self.export_button.setText("导出")
        self.export_button.clicked.connect(self.ask_export)


        self.save_button = QPushButton()
        self.save_button.setText("保存")
        self.save_button.clicked.connect(self.ask_save)

        # 创建一个水平布局，并将三个按钮添加到布局中
        layout = QHBoxLayout()
        layout.addWidget(self.generate_button)
        layout.addWidget(self.detect_button)
        layout.addWidget(self.export_button)
        layout.addWidget(self.save_button)
        

        # 将布局设置给按钮组件
        self.setLayout(layout)


# 定义主窗口类，继承自QWidget


class CanvaAndButton(QWidget):

    rectChanged = QtCore.Signal(int)
    ask_generate = QtCore.Signal(int)
    ask_export = QtCore.Signal(int)
    ask_save = QtCore.Signal(int)
    ask_detect = QtCore.Signal(int)

    def __init__(self):
        super().__init__()

        # 创建一个Canvas对象和一个ButtonWidget对象
        self.canvas = Canvas()
        self.button_widget = ButtonWidget()

        # 创建一个垂直布局，并将画板和按钮组件添加到布局中
        layout = QVBoxLayout()
        layout.addWidget(self.canvas)
        layout.addStretch()
        layout.addWidget(self.button_widget)

        self.canvas.rectChanged.connect(self.on_rect_Changed)
        self.button_widget.ask_generate.connect(self.on_ask_generate)
        self.button_widget.ask_export.connect(self.on_ask_export)
        self.button_widget.ask_save.connect(self.on_ask_save)
        self.button_widget.ask_detect.connect(self.on_ask_detect)

        #self.canvas.setMinimumSize(self.button_widget.width(),self.button_widget.width())

        # 将布局设置给主窗口
        self.setLayout(layout)

        # 设置主窗口的标题和大小
        self.setWindowTitle("画布")
        self.resize(400, 400)

    def get_tab_index(self):
        split_widget = self.parent()
        tab_widget = split_widget.parent()
        tab_index = tab_widget.indexOf(split_widget)
        return tab_index
    
    def on_ask_detect(self):
        self.ask_detect.emit(self.get_tab_index())

    def on_ask_generate(self):
        self.ask_generate.emit(self.get_tab_index())

    def on_ask_export(self):
        self.ask_export.emit(self.get_tab_index())

    def on_ask_save(self):
        self.ask_save.emit(self.get_tab_index())

    def on_rect_Changed(self):
        self.rectChanged.emit(self.get_tab_index())

    def get_rect(self):
        return self.canvas.get_rect()

    def get_pos(self):
        return self.canvas.get_pos()
    
    def if_clean_mode(self):
        return self.canvas.if_clean_mode()
    
    def set_clean_mode(self,clean_mode):
        self.canvas.set_clean_mode(clean_mode)

    def render_layout(self, layout):
        self.canvas.render_layout(layout)

    def set_selected_row(self,row):
        self.canvas.set_selected_row(row)


if __name__ == "__main__":
    # 创建一个QApplication对象
    app = QApplication(sys.argv)

    # 创建一个MainWindow对象，并显示它
    print("start")
    window = CanvaAndButton()
    window.canvas.render_layout([{'C': 'text', 'X': 0, 'Y': 0, 'W': 100, 'H': 100, 'A': 0, 'R': 0},
                                 {'C': 'title', 'X': 100, 'Y': 100, 'W': 50, 'H': 50, 'A': 0, 'R': 0}])
    print("end")
    window.show()

    # 进入应用程序的主循环
    app.exec()
