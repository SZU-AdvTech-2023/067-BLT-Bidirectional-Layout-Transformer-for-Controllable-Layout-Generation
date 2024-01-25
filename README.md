# 项目名称

这是一个自动文档布局生成模型,也支持掩码形条件的输入

## 安装步骤

以下步骤将指导您如何安装和设置项目。

### 步骤 1: 下载数据集

将 PubLayNet 数据集下载到项目的 `PubLayNet` 文件夹中。

### 步骤 2: 配置环境

根据 `environment.yml` 文件配置您的环境。这可以通过以下命令完成：

```bash
conda env create -f environment.yml
```
### 步骤 3: 训练模型

运行 layout_blt 文件夹中的 main.py 文件来训练模型
```bash
python layout_blt/main.py
```
### 步骤 4: 存储模型

将生成的模型存档命名为 layout.pth 并放入 layout_blt/save 文件夹。
### 步骤 5: 运行应用

最后，运行 MainWindow.py 来启动应用。

```bash
python MainWindow.py
```