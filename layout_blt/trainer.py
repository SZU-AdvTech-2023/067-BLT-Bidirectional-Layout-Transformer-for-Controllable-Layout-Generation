import os
import math
import logging
import wandb
from sample import sample as sample
from tqdm import tqdm
import numpy as np
import torch
import random

from torch.utils.data.dataloader import DataLoader


logger = logging.getLogger(__name__)


def main():
    ...


class TrainerConfig:
    # optimization parameters
    max_epochs = 10
    batch_size = 64
    learning_rate = 3e-4
    betas = (0.9, 0.98)
    grad_norm_clip = 1.0
    weight_decay = 0.1  # only applied on matmul weights
    # learning rate decay params: linear warmup followed by cosine decay to 10% of original
    lr_decay = True
    warmup_iters = 5000
    final_iters = 25000  # (at what point we reach 10% of original LR)
    # 掩码率变化
    start_mask_rate = 0.15
    end_mask_rate = 0.7
    full_mask_rate_at = 25000  # 何时掩码率达到最大
    # checkpoint settings
    ckpt_dir = None
    samples_dir = None
    sample_every = 1
    num_workers = 0  # for DataLoader

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def check_for_nan_gradients(model):
    for name, param in model.named_parameters():
        if param.grad is not None:
            if torch.isnan(param.grad).sum() > 0:
                print(f"{name} has NaN gradients")
                return True
    return False


class Trainer:

    def __init__(self, model, train_dataset, test_dataset, config, args):
        self.model = model
        self.train_dataset = train_dataset
        self.test_dataset = test_dataset
        self.config = config
        self.iters = 0
        self.optimizer = model.configure_optimizers(config)
        print("Using wandb")
        wandb.init(project='layout_BLT', name=args.exp)
        wandb.config.update(args)

        # take over whatever gpus are on the system
        self.device = 'cpu'
        if torch.cuda.is_available():
            self.device = torch.cuda.current_device()
            self.model = torch.nn.DataParallel(self.model).to(self.device)
        print(f"using device: {self.device}")

        if args.load:
            self.load_checkpoint()

    def load_checkpoint(self):
        print(f"load checkpoint {self.config.load_name}")
        ckpt_path = f"save/{self.config.load_name}.pth"
        logger.info("loading %s", ckpt_path)
        checkpoint = torch.load(ckpt_path)
        # 本来代码里的raw_model是为了处理使用DataParallel的情况,下面的代码是等价的
        if isinstance(self.model, torch.nn.DataParallel):
            self.model.module.load_state_dict(checkpoint)
        else:
            self.model.load_state_dict(checkpoint)

    def save_checkpoint(self,id=None):
        # DataParallel wrappers keep raw model object in .module attribute
        raw_model = self.model.module if hasattr(
            self.model, "module") else self.model
        ckpt_path = os.path.join(self.config.ckpt_dir, f'checkpoint{f"No.{id}" if id is not None else ""}.pth')
        logger.info("saving %s", ckpt_path)
        torch.save(raw_model.state_dict(), ckpt_path)

    def run_epoch_(self, epoch, split):
        optimizer = self.optimizer
        is_train = split == 'train'
        self.model.train(is_train)
        data = self.train_dataset if is_train else self.test_dataset
        loader = DataLoader(data, shuffle=is_train, pin_memory=True,
                            batch_size=self.config.batch_size,
                            num_workers=self.config.num_workers)
        losses = []
        pbar = tqdm(enumerate(loader), total=len(loader))
        for it, y in pbar:
            # place data on the correct device
            y = y.to(self.device)
            #调整掩码率
            if is_train:
                mask_rate = self.config.start_mask_rate + \
                    (self.config.end_mask_rate-self.config.start_mask_rate) * \
                    random.random()
                    #min(self.iters/self.config.full_mask_rate_at,1)#*random.random()**(2)
                    #random.random()**(1/2)
            else:
                 mask_rate = 0.15 + \
                    (0.7-0.15) * \
                    min(it/pbar.total,1)
        
            x, masks = BLT_masking(
                y, self.train_dataset.mask_token, self.train_dataset.eos_token, self.train_dataset.pad_token, training=is_train,mask_rate=mask_rate)

            # forward the model
            with torch.set_grad_enabled(is_train):
                if is_train:
                    self.model.train()
                else:
                    self.model.eval()
                # import ipdb; ipdb.set_trace()
                _, loss = self.model(x, targets=y, masks=masks)
                loss = loss.mean()  # collapse all losses if they are scattered on multiple gpus
                losses.append(loss.item())

            if is_train:

                # backprop and update the parameters
                self.model.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(  # 这个函数用来限制梯度的范围
                    self.model.parameters(), self.config.grad_norm_clip)

                if check_for_nan_gradients(self.model):
                    print("NaN gradients detected. Aborting training.")
                    return

                self.optimizer.step()
                self.iters += 1
                # decay the learning rate based on our progress
                if self.config.lr_decay:
                    # self.tokens += (y >= 0).sum()  # number of tokens processed this step (i.e. label is not -100)
                    if self.iters < self.config.warmup_iters:
                        # linear warmup
                        lr_mult = float(self.iters) / \
                            float(max(1, self.config.warmup_iters))
                    else:
                        # cosine learning rate decay
                        progress = min(1, float(self.iters - self.config.warmup_iters) / float(
                            max(1, self.config.final_iters - self.config.warmup_iters)))
                        lr_mult = max(
                            0.1, 0.5 * (1.0 + math.cos(math.pi * progress)))
                    lr = self.config.learning_rate * lr_mult
                    for param_group in optimizer.param_groups:
                        param_group['lr'] = lr
                else:
                    lr = self.config.learning_rate

                # report progress
                wandb.log({
                    'train loss': loss.item(),
                    'lr': lr, 'epoch': epoch,
                    'mask_rate': mask_rate
                }, step=self.iters)
                pbar.set_description(
                    f"epoch {epoch} {split} loss {loss.item():.5f}. lr {lr:e}. mask rate {mask_rate:.2f}")
            else:
                pbar.set_description(
                    f"epoch {epoch} {split} loss {loss.item():.5f}. mask rate {mask_rate:.2f}")

        if not is_train:
            test_loss = float(np.mean(losses))
            logger.info("test loss: %f", test_loss)
            wandb.log({'test loss': test_loss,'15 loss':losses[0],'70 loss':losses[-1]}, step=self.iters)
            return test_loss
        # def run_epoch结束

    def test(self, epoch=0):
        model = self.model
        data = self.test_dataset
        test_batch = data[100:120].to(self.device)

        layouts = test_batch.detach().cpu().numpy()
        input_layouts = [self.train_dataset.render(
            layout) for layout in layouts]
        # self.save_combined_image(input_layouts,"input_layouts")

        masked_batch, masks = test_masking(
            test_batch, data.mask_token, data.eos_token, data.pad_token)

        layouts = sample(model, masked_batch, masks=masks, once=True,
                         temperature=1.0, sample=False, p=None, y=test_batch).detach().cpu().numpy()
        recon_layouts = [self.train_dataset.render(
            layout) for layout in layouts]
        # self.save_combined_image(recon_layouts,"recon_layouts")

        layouts = sample(model, masked_batch, masks=masks, once=False,
                         temperature=1.0, sample=True, p=0.95, y=test_batch).detach().cpu().numpy()
        sample_random_layouts = [
            self.train_dataset.render(layout) for layout in layouts]
        # self.save_combined_image(sample_random_layouts,"sample_random_layouts")

        layouts = sample(model, masked_batch, masks=masks, once=False,
                         temperature=1.0, sample=False, p=None, y=test_batch).detach().cpu().numpy()
        sample_det_layouts = [self.train_dataset.render(
            layout) for layout in layouts]
        # self.save_combined_image(sample_det_layouts,"sample_det_layouts")

        wandb.log({
            "input_layouts": [wandb.Image(pil, caption=f'input_{epoch:02d}_{i:02d}.png')
                              for i, pil in enumerate(input_layouts)],
            "recon_layouts": [wandb.Image(pil, caption=f'recon_{epoch:02d}_{i:02d}.png')
                              for i, pil in enumerate(recon_layouts)],
            "sample_random_layouts": [wandb.Image(pil, caption=f'sample_random_{epoch:02d}_{i:02d}.png')
                                      for i, pil in enumerate(sample_random_layouts)],
            "sample_det_layouts": [wandb.Image(pil, caption=f'sample_det_{epoch:02d}_{i:02d}.png')
                                   for i, pil in enumerate(sample_det_layouts)], }, step=self.iters)

    def train(self):

        best_loss = float('inf')
        epoch = 0
        while True:
            epoch += 1

            self.run_epoch_(epoch, 'train')
            if self.test_dataset is not None:
                with torch.no_grad():
                    test_loss = self.run_epoch_(
                        epoch, 'test')
                    
            self.save_checkpoint(epoch)
            # supports early stopping based on the test loss, or just save always if no test set is provided
            good_model = self.test_dataset is None or test_loss is None or test_loss < best_loss
            print(f"{epoch=} {test_loss=} {good_model=}")
            if self.config.ckpt_dir is not None and good_model:
                best_loss = test_loss
                self.save_checkpoint()

            # sample from the model
            if self.config.samples_dir is not None and (epoch+1) % self.config.sample_every == 0:
                self.test(epoch)

            if epoch >= self.config.max_epochs:
                print("运行结束,输入正整数继续训练,任意非数字退出:\n")
                temp = input()
                try:
                    temp = int(temp)
                    if temp > 0:
                        self.config.max_epochs += temp
                        continue
                    else:
                        print("Please enter a positive number.")

                except ValueError:
                    print("Invalid input. Please enter a valid number.")
                    break


def BLT_masking(inputs, mask_token, eos_token, pad_token, *, mask_rate=0.50, training=True):
    '''
    我认为mask不需要复杂的机制
    参数:
        inputs:要处理的串,以一个或多个batch的形式输入
        mask_token:用来表示mask的token
        pad_token:用来表示pad的token
        training: 是否为训练模式
    返回:
        masked_inputs:mask后的输入
        weights:用来表示被mask位置的0,1数组
    '''
    total_dim = 7  # 一个框所占的token数量
    layout_dim = 2  # 除类型外,一类数据所占token数量

    should_mask = (inputs != pad_token) & (inputs != eos_token)  # eos不能被遮蔽
    pos_id = torch.arange(inputs.shape[1], device=inputs.device)
    #should_remask = (pos_id % total_dim >= 3) & should_mask

    if not training:
        original_seed = torch.initial_seed()
        torch.manual_seed(0)  # 设置固定的随机种子

    # 遮蔽
    lens = torch.sum(should_mask, axis=-1)
    mask_lens = torch.ceil(lens * mask_rate).to(torch.int64)

    rand = torch.rand(inputs.shape, device=inputs.device)
    rand[~should_mask] = 2.0
    inserted_rand = torch.cat((rand, torch.ones(
        (rand.shape[0], 1), device=rand.device) * -1), dim=1)  # 防止之后gather访问出界

    sorted_rand, _ = torch.sort(inserted_rand, dim=-1)
    cut_off = sorted_rand.gather(-1, (mask_lens).unsqueeze(1))
    cut_off[cut_off == 2.0] = 1.0
    should_mask &= (rand <= cut_off)

    masked_inputs = torch.where(
        should_mask, mask_token, inputs)  # should_remask不会被记录

    if not training:
        torch.manual_seed(original_seed)  # 还原随机种子
    return masked_inputs, should_mask


def test_masking(inputs, mask_token, eos_token, pad_token):
    device = inputs.device
    batch_size = len(inputs)
    max_len = max(len(s) for s in inputs)

    masked_inputs = torch.ones(
        batch_size, max_len, dtype=torch.long, device=device) * pad_token
    should_mask = torch.zeros(
        batch_size, max_len, dtype=torch.bool, device=device)

    for i, seq in enumerate(inputs):
        eos_index = (seq == eos_token).nonzero(as_tuple=True)[
            0].item() if eos_token in seq else len(seq)
        seq_len = eos_index  # exclude eos_token and padding
        masked_inputs[i, :seq_len + 1] = seq[:seq_len+1].clone().detach()

        if i % 2 == 0:
            mask_indices = torch.arange(seq_len, device=device)[torch.isin(
                torch.arange(seq_len, device=device) % 7, torch.tensor([1, 2], device=device))]
        elif i % 2 == 1:
            mask_indices = torch.arange(seq_len, device=device)[torch.isin(
                torch.arange(seq_len, device=device) % 7, torch.tensor([1, 2], device=device))]

        should_mask[i, mask_indices] = True
        masked_inputs[i, mask_indices] = mask_token

    return masked_inputs, should_mask


if __name__ == '__main__':
    main()
