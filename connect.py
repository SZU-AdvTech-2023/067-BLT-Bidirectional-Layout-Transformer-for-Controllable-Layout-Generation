from PySide6.QtWidgets import QLabel, QApplication
from PySide6.QtGui import QPixmap
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QIcon, QPolygon, QImage
from PySide6.QtCore import Qt, QPoint, QRect, QSize, QRectF, QSizeF
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageQt
import numpy as np
import torch
import seaborn as sns
import math
from functools import lru_cache


from layout_blt.call import ModelCaller

class ModelConnecter:
    def __init__(self,size=2**8, randerSize=1024, categories=["text", "title", "list", "table", "figure"]):
        self.data_transformer=DataTransformer(size=size,randerSize=randerSize,categories=categories)
        self.model_caller=ModelCaller(load_name="layout",size=size, categories=categories,max_steps=100000)
    
    def generate(self,input_data,confirmed):
        x=torch.tensor(self.data_transformer.reformat_layout(input_data,confirmed))
        y=self.model_caller.call(x).tolist()
        output_data,_=self.data_transformer.restore_layout(y)
        return output_data

    def detect(self,input_data):
        x=torch.tensor(self.data_transformer.reformat_layout(input_data))
        index=self.model_caller.detect(x)[0]
        return index


def adjust_rect(rect):
    # 创建一个QRectF对象
    r = QRectF(rect.x(), rect.y(), rect.width(), rect.height())
    if r.width() < 0:  # 如果宽度为负数
        w = -r.width()
        r.setX(r.x() - w)  # 将x坐标减去宽度
        r.setWidth(w)  # 将宽度取反
    if r.height() < 0:  # 如果高度为负数
        h = -r.height()
        r.setY(r.y() - h)  # 将y坐标减去高度
        r.setHeight(h)  # 将高度取反
    # print(rect,"|",r)
    return r  # 返回调整后的QRectF对象


def gen_colors(num_colors):
    """
    Generate uniformly distributed `num_colors` colors
    :param num_colors:
    :return:
    """
    palette = sns.color_palette(None, num_colors)
    rgb_triples = [[int(x[0]*255), int(x[1]*255), int(x[2]*255)]
                   for x in palette]
    return rgb_triples

# 定义一个数据转换处理的类


class DataTransformer:
    # 定义初始化方法，设置属性的默认值
    def __init__(self, size=2**8,randerSize=2048, categories=["text", "title", "list", "table", "figure"]):
        self.size = size
        self.categories = categories
        self.randerSize=randerSize
        self.mask_token = size + len(categories) + 0
        self.eos_token = size + len(categories) + 1
        self.pad_token = size + len(categories) + 2
        self.colors = gen_colors(len(categories))
        
        self.count=0

    def render_layout(self, layout,select=-1,clean_mode=False):
        new_layout = self.reformat_layout(layout)
        img = self.render(tuple(tuple(x) for x in new_layout),randerSize=self.randerSize,select=select,clean_mode=clean_mode)
        return self.pil_to_qpixmap(img)

    # 将QPointF对象转换为字典对象

    def pos_to_dict(self, pos):
        item = {}
        # 获取QPointF对象的横坐标并乘以size属性
        item['X'] = int(pos.x() * self.size)
        # 获取QPointF对象的纵坐标并乘以size属性
        item['Y'] = int(pos.y() * self.size)
        return item

    # 将QRectF对象转换为字典对象

    def qrectf_to_dict(self, qrectf):
        item = {}
        item['X'] = int(qrectf.x() * self.size)
        item['Y'] = int(qrectf.y() * self.size)
        item['W'] = int(qrectf.width() * self.size)
        item['H'] = int(qrectf.height() * self.size)
        item['A'] = int((qrectf.width() * qrectf.height()) ** 0.5 * self.size)
        #item['A'] = int((qrectf.width() * qrectf.height()) * self.size)
        item['R'] = int(math.atan2(qrectf.height(), qrectf.width())
                        * 2 / math.pi * self.size)
        return item

    # 将布局列表重新格式化为整数列表
    def reformat_layout(self, layout,confirmed=None):

        new_layout = []

        # 创建一个字典，将类别名称映射到整数编号上
        cata = {c: self.size + i for i, c in enumerate(self.categories)}

        # 判断confirmed是否为None
        if confirmed is None:
            # 如果是的话，就创建一个全为True的列表
            confirmed = [{'C': True, 'X': True, 'Y': True, 'W': True,
                          'H': True, 'A': True, 'R': True} for _ in layout]

        for item, conf in zip(layout, confirmed):  # 使用zip函数同时遍历layout和confirmed列表
            c = cata[item['C']]
            x = item['X']
            y = item['Y']
            w = item['W']
            h = item['H']
            a = item['A']
            r = item['R']

            # 使用列表推导式生成一个新的项目信息列表
            new_item = [c if conf['C'] else self.mask_token,
                        x if conf['X'] else self.mask_token,
                        y if conf['Y'] else self.mask_token,
                        w if conf['W'] else self.mask_token,
                        h if conf['H'] else self.mask_token,
                        a if conf['A'] else self.mask_token,
                        r if conf['R'] else self.mask_token]

            # 将新的项目信息添加到新布局中
            new_layout.extend(new_item)

        # 在列表末尾添加结束符号
        new_layout.append(self.eos_token)

        return [new_layout]
    
    # 将整数列表还原为布局列表和确认列表
    def restore_layout(self, new_layout):
        new_layout=new_layout[0]
        layout = []
        confirmed = []
        # 创建一个字典，将整数编号映射到类别名称上
        cata = {self.size + i: c for i, c in enumerate(self.categories)}
        # 找到结束符号在列表中的位置
        eos_index = new_layout.index(self.eos_token)
        # 去掉结束符号以及之后的所有元素
        new_layout = new_layout[:eos_index]
        # 将列表分割成长度为7的子列表
        items = [new_layout[i:i+7] for i in range(0, len(new_layout), 7)]
        for item in items:
            # 使用推导式生成一个项目信息字典
            layout_item = {'C': self.categories[0] if item[0] == self.mask_token else cata[item[0]],
                        'X': 0 if item[1] == self.mask_token else item[1],
                        'Y': 0 if item[2] == self.mask_token else item[2],
                        'W': 0 if item[3] == self.mask_token else item[3],
                        'H': 0 if item[4] == self.mask_token else item[4],
                        'A': 0 if item[5] == self.mask_token else item[5],
                        'R': 0 if item[6] == self.mask_token else item[6]}
            # 使用推导式生成一个确认信息字典
            conf_item = {'C': item[0] != self.mask_token,
                        'Y': item[2] != self.mask_token,
                        'W': item[3] != self.mask_token,
                        'H': item[4] != self.mask_token,
                        'A': item[5] != self.mask_token,
                        'R': item[6] != self.mask_token}
            # 将项目信息字典和确认信息字典分别添加到布局列表和确认列表中
            layout.append(layout_item)
            confirmed.append(conf_item)
        # 返回布局列表和确认列表
        return layout, confirmed

    @lru_cache(maxsize=30)
    def render(self, layout,/,randerSize=2048,select=-1,clean_mode=False):
        #print(select,self.count)
        #self.count+=1
    
        layout = np.array(layout)
        img = Image.new('RGB', (randerSize, randerSize),
                        color=(255, 255, 255))
        draw = ImageDraw.Draw(img, 'RGBA')
        layout = layout.reshape(-1)
        layout = layout[:np.argwhere(layout == self.eos_token)[0][0]]
        layout = layout[: len(layout) // 7 * 7].reshape(-1, 7)
        box = layout[:, 1:5].astype(np.float32)
        box = box / self.size
        box = box * randerSize
        box[:, [2, 3]] = box[:, [0, 1]] + box[:, [2, 3]]

        # 绘制方框
        for i in range(len(layout)):
            x1, y1, x2, y2 = box[i]
            cat = layout[i][0]
            col = self.colors[cat-self.size] if 0 <= cat - \
                self.size < len(self.colors) else [0, 0, 0]
            if i!=select:
                draw.rectangle([x1, y1, x2, y2],
                                outline=tuple(col) + (200,),
                                fill=tuple(col) + (64,),
                                width=2)
            else:
                draw.rectangle([x1, y1, x2, y2],
                                outline=(0,0,0,255),
                                fill=tuple(col) + (64,),
                                width=4)
        if not clean_mode:
            # 绘制方框编号和折线连接方框中心点
            for i in range(len(layout)):
                x1, y1, x2, y2 = box[i]
                font = ImageFont.truetype("arial.ttf", int(20 * 2))
                draw.text((x1, y1), str(i + 1), font=font,
                        fill=(0, 0, 0, 255), align="left")

                if i > 0:
                    x1_last, y1_last, x2_last, y2_last = box[i-1]
                    x_center, y_center = (x1+x2)/2, (y1+y2)/2
                    x_center_last, y_center_last = (
                        x1_last+x2_last)/2, (y1_last+y2_last)/2
                    draw.line([(x_center_last, y_center_last), (x_center, y_center)],
                            fill=(0, 0, 0, 255), width=5)

        # 添加图片边框
        img = ImageOps.expand(img, border=2)
        return img

    def pil_to_qpixmap(self, pil_image):
        return ImageQt.toqpixmap(pil_image)

    # 定义一个获取标签对应颜色的方法
    def get_color(self, label):
        # 判断label是否在categories中
        if label in self.categories:
            # 如果是的话，就根据label在categories中的索引返回相应的颜色
            index = self.categories.index(label)
            return self.colors[index]
        else:
            # 如果不是的话，就返回黑色
            return [0, 0, 0]


def clamp(value, min_value, max_value):
    return max(min(value, max_value), min_value)
