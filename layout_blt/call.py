import os
import argparse
import torch
import numpy as np
import random
from .model import BLT, BLTConfig
from .sample import sample,outlier_detect,bad_sample



def get_args():
    os.chdir(os.path.dirname(os.path.realpath(__file__)))  # 强制修改当前目录
    parser = argparse.ArgumentParser('Layout BLT')
    parser.add_argument("--load_name", default="终结者", help="读取现有模型进行测试")
    parser.add_argument("--load", type=bool, default=False, help="是否读取现有模型")

    parser.add_argument("--exp", default="layout", help="experiment name")
    parser.add_argument("--log_dir", default="./logs",
                        help="/path/to/logs/dir")

    parser.add_argument('--n_layer', default=4, type=int)#4
    parser.add_argument('--n_head', default=8, type=int)#8
    parser.add_argument('--hidden_dropout_prob', default=0.1, type=float)
    parser.add_argument('--attention_probs_dropout_prob',
                        default=0.1, type=float)
    parser.add_argument('--embed_size', default=512, type=int)
    parser.add_argument('--intermediate_size', default=2048, type=int)#2048

    return parser.parse_args()

class ModelCaller:
    def __init__(self,load_name="layout", size=2**8, categories=["text", "title", "list", "table", "figure"],max_steps=100):
        self.size = size

        self.categories = categories
        self.mask_token = size + len(categories) + 0
        self.eos_token = size + len(categories) + 1
        self.pad_token = size + len(categories) + 2
        self.vocab_size=size + len(categories) + 3
        args = get_args()
        args.load = True
        self.max_steps=max_steps

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"using device: {device}")

        mconf = BLTConfig(vocab_size=self.vocab_size, pad_token=self.pad_token,
                          n_layer=args.n_layer,
                          n_head=args.n_head,
                          embed_size=args.embed_size,
                          intermediate_size=args.intermediate_size,
                          hidden_dropout_prob=args.hidden_dropout_prob,
                          attention_probs_dropout_prob=args.attention_probs_dropout_prob,
                          )
        mconf = BLTConfig(vocab_size=self.vocab_size, 
                    mask_token=self.mask_token,
                    eos_token=self.eos_token,
                    pad_token=self.pad_token,
                    n_layer=args.n_layer,
                    n_head=args.n_head,
                    embed_size=args.embed_size,
                    intermediate_size=args.intermediate_size,
                    hidden_dropout_prob=args.hidden_dropout_prob,
                    attention_probs_dropout_prob=args.attention_probs_dropout_prob,
                    )

        self.model = BLT(mconf)

        self.load_checkpoint(load_name)

    def load_checkpoint(self, name="layout"):
        print(f"load checkpoint {name}.pth")
        ckpt_path = f"save/{name}.pth"
        checkpoint = torch.load(ckpt_path)

        if isinstance(self.model, torch.nn.DataParallel):
            self.model.module.load_state_dict(checkpoint)
        else:
            self.model.load_state_dict(checkpoint)
    
    def call(self,x):
        total_dim = 7
        layout_dim = 2
        masks=(x==self.mask_token)
        y=sample(model=self.model,x=x,masks=masks,temperature=1.0, sample=True, p=0.95,max_steps=self.max_steps)
        return y
    
    def detect(self, x):
        # 计算masks
        eos_positions = torch.argmax((x == self.eos_token).long(), dim=1)
        masks = torch.where(torch.arange(x.shape[1],device=x.device).unsqueeze(0) < eos_positions.unsqueeze(1), torch.tensor(True), torch.tensor(False))
    
        # 调用outlier_detect
        indexs = outlier_detect(self.model, x, masks)
        return indexs
    
    
if __name__ == "__main__":
   model_caller = ModelCaller()
   x=torch.tensor([
       [model_caller.mask_token,
        model_caller.mask_token,
        model_caller.mask_token,
        model_caller.mask_token,
        model_caller.mask_token,
        model_caller.mask_token,
        model_caller.mask_token,
        model_caller.eos_token]
       ])
   y=model_caller.detect(x)
   print(x)
   print(y)

