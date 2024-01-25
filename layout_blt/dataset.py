import numpy as np
import torch
from torch.utils.data.dataset import Dataset
from PIL import Image, ImageDraw, ImageOps, ImageFont
import seaborn as sns
import json
import os
import math


def main():
    os.chdir(os.path.dirname(os.path.realpath(__file__)))  # 强制修改当前目录
    dataset = JSONLayout("../PubLayNet/train.json")
    dataset2 = JSONLayout("../PubLayNet/val.json")

    # dataset.render(dataset[2]).show()

    for i in range(5):
        random_index = np.random.choice(np.arange(len(dataset.data)))
        random_row = dataset.data[random_index]
        dataset.render(random_row).show()


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


class JSONLayout(Dataset):
    def __init__(self, json_path, max_length=None, percentage=1, precision=8):
        # 取出文件名
        file_name = os.path.basename(json_path)
        # 去掉文件名后缀
        file_name = os.path.splitext(file_name)[0]
        # 将文件名插入模板
        save_path = f"{file_name}.npy"

        if os.path.exists(save_path) and os.path.exists("categories_name.npy"):
            self.data = np.load(save_path)
            self.categories_name = np.load("categories_name.npy")
            self.size = pow(2, precision)
            self.max_length = self.data.shape[-1]
            self.vocab_size = self.size + \
                self.categories_name.shape[-1]+3  # mask, eos, pad tokens

            self.mask_token = self.vocab_size - 3
            self.eos_token = self.vocab_size - 2
            self.pad_token = self.vocab_size - 1

            self.colors = gen_colors(self.categories_name.shape[-1])
        else:
            with open(json_path, "r") as f:
                data = json.loads(f.read())

            self.categories_name = {}
            for category in data['categories']:
                self.categories_name[category["id"]] = category["name"]
            self.categories_name = np.array(
                list(self.categories_name.values()))

            dict_images = {}
            dict_bboxs = {}
            dict_categories = {}
            dict_conditions = {}
            for image in data['images']:
                dict_images[image["id"]] = [image["width"], image["height"]]
                dict_bboxs[image["id"]] = []
                dict_categories[image["id"]] = []
                dict_conditions[image["id"]] = []

            for annotation in data['annotations']:
                dict_bboxs[annotation["image_id"]].append(annotation["bbox"])
                dict_categories[annotation["image_id"]].append(
                    annotation["category_id"])
                dict_conditions[annotation["image_id"]].append([annotation["bbox"][3]*annotation["bbox"][2], math.atan2(
                    annotation["bbox"][3],annotation["bbox"][2])*2/math.pi])

            del data

            self.size = pow(2, precision)
            self.vocab_size = self.size + \
                self.categories_name.shape[-1]+3  # mask, eos, pad tokens

            self.mask_token = self.vocab_size - 3
            self.eos_token = self.vocab_size - 2
            self.pad_token = self.vocab_size - 1

            self.max_length = max_length
            self.percentage = percentage
            if self.max_length is None:
                all_lengths = [len(categories)
                               for categories in dict_categories.values()]
                sorted_lengths = sorted(all_lengths)
                num_to_keep = int(len(sorted_lengths) * self.percentage)
                # 7 => cxywhar
                self.max_length = sorted_lengths[num_to_keep - 1] * 7 + 1

            self.data = []
            for id in dict_bboxs:  # 335703
                bboxs = np.array(dict_bboxs[id])  # xywh
                images = np.array(dict_images[id])
                conditions = np.array(dict_conditions[id])  # ar
                categories = np.array(dict_categories[id])  # c
                widths = images[0][np.newaxis, np.newaxis]
                heights = images[1][np.newaxis, np.newaxis]

                conditions[:,0]/=(images[0]*images[1])
                conditions[:,0]=np.sqrt(conditions[:,0])
                conditions=np.round(conditions * self.size).astype(int)

                bboxs = bboxs / \
                    np.concatenate((widths, heights, widths, heights), axis=-1)
                bboxs = np.round(bboxs * self.size).astype(int)

                if not (np.all((bboxs >= 0) & (bboxs <= self.size - 1))):
                    continue  # 原文中使用了裁剪方案,我选择直接跳过出界的数据
                if not (np.all((bboxs[..., :2] + bboxs[..., 2:] <= self.size - 1))):
                    continue

                indices = reading_order(bboxs)
                #indices = np.lexsort((bboxs[:, 0], bboxs[:, 1]))
                bboxs = bboxs[indices]
                conditions =conditions[indices]
                categories = categories[indices]+self.size-1


                #最终组装数据
                combined = np.column_stack((categories, bboxs ,conditions))
                combined = np.append(combined.flatten(), self.eos_token)

                if combined.shape[-1] > self.max_length:
                    continue

                data = np.pad(combined.flatten(), (0, self.max_length - len(
                    combined.flatten())), 'constant', constant_values=(self.pad_token,))
                self.data.append(data)
            self.colors = gen_colors(self.categories_name.shape[-1])
            self.data = np.array(self.data)

            np.save(save_path, self.data)  # 335685
            np.save("categories_name.npy", self.categories_name)

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        return torch.tensor(self.data[idx], dtype=torch.long)

    def render(self, layout):
        layout = np.array(layout)
        img = Image.new('RGB', (1024, 1024), color=(255, 255, 255))
        draw = ImageDraw.Draw(img, 'RGBA')
        layout = layout.reshape(-1)
        layout = layout[:np.argwhere(layout == self.eos_token)[-1][0]]
        layout = layout[: len(layout) // 7 * 7].reshape(-1, 7)
        box = layout[:, 1:5].astype(np.float32)
        box = box / self.size
        box = box * 1024
        box[:, [2, 3]] = box[:, [0, 1]] + box[:, [2, 3]]

        # 绘制方框
        for i in range(len(layout)):
            x1, y1, x2, y2 = box[i]
            cat = layout[i][0]
            col = self.colors[cat-self.size] if 0 <= cat - \
                self.size < len(self.colors) else [0, 0, 0]
            draw.rectangle([x1, y1, x2, y2],
                           outline=tuple(col) + (200,),
                           fill=tuple(col) + (64,),
                           width=2)

            # 绘制方框编号和折线连接方框中心点
        """
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
        """

        # 添加图片边框
        img = ImageOps.expand(img, border=2)

        return img


def reading_order(bboxs, indices=None):
    if indices is None:
        indices = np.arange(len(bboxs))

    n = len(indices)
    if n == 1:
        return np.array([indices[0]])

    x1, y1, w, h = bboxs[:, 0], bboxs[:, 1], bboxs[:, 2], bboxs[:, 3]
    x2, y2 = x1 + w, y1 + h
    candidate=[]#距离
    candidate_cut=[]#切分结果

    # 从左至右遍历所有元素的右边
    sort_indices = indices[np.argsort(x1[indices])]
    left_half = []
    right_half, not_left_half = list(reversed(indices[np.argsort(x1[indices])])), list(
        reversed(indices[np.argsort(x2[indices])]))
    checked=set()
    

    for col_cut in x1[sort_indices]:
        # 检查right_half和not_left_half
        while len(right_half) > 0 and x1[right_half[-1]] < col_cut:
            right_half.pop()

        while len(not_left_half) > 0 and x2[not_left_half[-1]] <= col_cut:
            left_half.append(not_left_half[-1])
            not_left_half.pop()

        # 检查是否有元素被直线切到
        if col_cut not in checked and  len(right_half) != 0 and len(left_half)!=0 and len(left_half) + len(right_half) == len(indices):
            checked.add(col_cut)
            candidate.append(col_cut-x2[left_half[-1]])
            candidate_cut.append([left_half[:],right_half[:]])

    # 从上至下遍历所有元素的底边
    sort_indices = indices[np.argsort(y1[indices])]
    top_half = []
    bottom_half, not_top_half = list(reversed(indices[np.argsort(y1[indices])])), list(
        reversed(indices[np.argsort(y2[indices])]))
    checked=set()

    for rol_cut in y1[sort_indices]:
        # 检查bottom_half和not_top_half
        while len(bottom_half) > 0 and y1[bottom_half[-1]] < rol_cut:
            bottom_half.pop()

        while len(not_top_half) > 0 and y2[not_top_half[-1]] <= rol_cut:
            top_half.append(not_top_half[-1])
            not_top_half.pop()

        # 检查是否有元素被直线切到
        if rol_cut not in checked and  len(bottom_half) != 0 and len(top_half)!=0 and len(top_half) + len(bottom_half) == len(indices):
            checked.add(rol_cut)
            candidate.append(rol_cut-y2[top_half[-1]])
            candidate_cut.append([top_half[:],bottom_half[:]])

    if len(candidate)==0:
        # 如果都不能划分，则按照np.lexsort((bboxs[:, 0], bboxs[:, 1]))排序取出第一个元素，对剩下的部分递归
        idx = np.lexsort((bboxs[indices, 0], bboxs[indices, 1]))
        return np.concatenate((indices[idx[:1]], reading_order(bboxs, indices[idx[1:]])))
    else:
        #否则，选取厚度最大的切割线作为本次的切割线
        cut = candidate_cut[np.argmax(candidate)]
        return np.concatenate((reading_order(bboxs, np.array(cut[0])), reading_order(bboxs, np.array(cut[1]))))


if __name__ == '__main__':
    main()
