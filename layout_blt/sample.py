
import torch
from torch.nn import functional as F

def choose_from_probs(probs, sample=False, p=None):
    """
    从probs中进行采样，使用核采样方法，并返回选择的项及其置信度
    """
    if sample:
        if p and p >= 0 and p < 1:
            # 对概率分布进行排序
            sorted_probs, sorted_indices = torch.sort(probs, dim=-1, descending=True)
            # 计算累加概率
            cum_sum_probs = torch.cumsum(sorted_probs, dim=-1)
            # 创建一个掩码，以确定哪些项需要保留
            nucleus = cum_sum_probs < p
            # 将数据整体右移，删除最后一项，并在左侧插入一个true
            nucleus = torch.cat([nucleus.new_ones(nucleus.shape[:-1] + (1,)), nucleus[..., :-1]], dim=-1)
            sorted_probs[~nucleus] = 0

            normalized_probs = sorted_probs# / torch.sum(sorted_probs, dim=-1, keepdim=True)

            # 从概率分布中进行采样并返回选择的项及其置信度
            flat_probs = normalized_probs.reshape(-1, normalized_probs.shape[-1])
            flat_indices = torch.multinomial(flat_probs, 1)
            indices = flat_indices.reshape(-1, normalized_probs.shape[-2])
    
            choose = sorted_indices.gather(-1, indices.unsqueeze(-1)).squeeze(-1)
            confidence = normalized_probs.gather(-1,
                                           indices.unsqueeze(-1)).squeeze(-1)
        else:
            flat_probs = probs.reshape(-1, probs.shape[-1])
            flat_indices = torch.multinomial(flat_probs, 1)
            indices = flat_indices.reshape(-1, probs.shape[-2])

            choose = indices
            confidence = probs.gather(-1, indices.unsqueeze(-1)).squeeze(-1)
    else:
        confidence, choose = probs.max(dim=-1)

    return confidence, choose


def sample(model, x, masks, once=False,max_steps=0,temperature=1.0, sample=False, p=None, y=None):
    """从模型的结果中采样的函数"""
    model.eval()
    weights = masks.clone()
    total_dim = 7
    layout_dim = 2
    position_ids = torch.arange(x.shape[-1])[None, :].to(x.device)
    asset_ids= position_ids//total_dim

    max_value = torch.inf * \
    torch.ones(
        x.shape[:-1]).unsqueeze(-1).to(x.device)
    
    min_value = -torch.inf * \
    torch.ones(
        x.shape[:-1]).unsqueeze(-1).to(x.device)

    with torch.no_grad():
        if once:  # 一次采样
            logits, _ = model(x)

            probs = F.softmax(logits / temperature, dim=-1)

            confidence, choose = choose_from_probs(probs, sample,p)

            x = torch.where(weights, choose, x)
        else:  # 从两侧多次采样
            step=0
            while weights.any():
                step+=1
                n = weights.sum(dim=-1)
                if max_steps==0:
                    step_length=torch.where(n>0,1,0)
                else:
                    step_length=torch.ceil(n/(max_steps-step+1)).type(torch.int64)
                sorted_weights,_ = torch.sort(torch.where(weights,asset_ids,torch.inf)) # 对weights进行排序,并用inf替换0元素
                sorted_weights = torch.cat(#这一步是为了防止step_length出界
                    (min_value,sorted_weights), dim=-1)
                kth_smallest = torch.gather(sorted_weights, 1, step_length.unsqueeze(-1)) # 根据step_length中的值获取sorted_weights中对应位置的元素
                sorted_weights,_ = torch.sort(torch.where(weights,asset_ids,-torch.inf), descending=True) # 对weights进行降序排序，并用-inf替换0元素
                sorted_weights = torch.cat(#这一步是为了防止step_length出界
                    (max_value,sorted_weights), dim=-1)
                kth_largest = torch.gather(sorted_weights, 1, step_length.unsqueeze(-1)) # 根据step_length中的值获取sorted_weights中对应位置的元素

                mask_to_fill=((asset_ids>=kth_largest)|(asset_ids<=kth_smallest))&weights

                logits, _ = model(x, y)

                probs = F.softmax(logits / temperature, dim=-1)

                confidence, choose = choose_from_probs(
                    probs, sample, p)
                confidence[~mask_to_fill] = 0

                sorted_confidence, _ = confidence.sort(
                    dim=-1, descending=True)

                sorted_confidence = torch.cat(#这一步是为了防止step_length出界
                    (max_value,sorted_confidence), dim=-1)
                

                selected_confidence = sorted_confidence.gather(
                    -1, step_length.unsqueeze(-1))

                selected_indices = (confidence >= selected_confidence)

                x = torch.where(selected_indices, choose, x)
                weights &= (~selected_indices)
    model.train()
    return x

def bad_sample(model, x, masks, once=False,max_steps=0,temperature=1.0, sample=False, p=None, y=None):
    """从模型的结果中采样的函数,没有顺序限制"""
    model.eval()
    weights = masks.clone()

    with torch.no_grad():
        if once:  # 一次采样
            logits, _ = model(x)

            probs = F.softmax(logits / temperature, dim=-1)

            confidence, choose = choose_from_probs(probs, sample, p)

            x = torch.where(weights, choose, x)
        else:  # 按照论文要求多次采样
            step=0
            while weights.any():
                step+=1
                remaining_mask = weights
                if remaining_mask.sum() == 0:
                    break

                n = torch.clamp(remaining_mask.sum(dim=-1), min=0,max=1)

                logits, _ = model(x, y)

                probs = F.softmax(logits / temperature, dim=-1)

                confidence, choose = choose_from_probs(
                    probs, sample, p)

                confidence[~remaining_mask] = 0

                sorted_confidence, _ = confidence.sort(
                    dim=-1, descending=True)

                min_value = torch.inf * \
                    torch.ones(
                        sorted_confidence.shape[:-1]).unsqueeze(-1).to(x.device)
                sorted_confidence = torch.cat(#这一步是为了防止n出界
                    (min_value,sorted_confidence), dim=-1)
                

                selected_confidence = sorted_confidence.gather(
                    -1, n.unsqueeze(-1))

                selected_indices = (confidence >= selected_confidence)

                x = torch.where(selected_indices, choose, x)
                weights &= (~selected_indices)
    model.train()
    return x

def outlier_detect(model,x,masks):
    # 模型评估模式
    model.eval()
    # 总维度
    total_dim = 7
    # 布局维度
    layout_dim = 2
    # 最小索引
    min_indexs=-1 * \
        torch.ones(x.shape[:-1], dtype=torch.int64).to(x.device)
    # 最小概率
    min_probs = torch.inf * \
        torch.ones(x.shape[:-1]).to(x.device)

    with torch.no_grad():
        # 遍历所有布局
        for j in range(x.shape[-1]//total_dim):
            # 克隆x
            x_copy=x.clone()
            # 将第j个布局替换为mask_token
            x_copy[:,j*total_dim:(j+1)*total_dim]= model.mconf.mask_token
            # 获取模型的输出
            logits, _ = model(x_copy)
            # 计算概率
            probs = F.softmax(logits, dim=-1)
            # 计算第j个布局的概率
            j_prob=torch.gather(probs[:,j*total_dim:(j+1)*total_dim],-1,x[:,j*total_dim:(j+1)*total_dim].unsqueeze(-1)).squeeze(-1).log().sum(dim=-1)
            # 更新最小概率和最小索引
            min_indexs=torch.where((j_prob< min_probs) & (masks[:,j*total_dim:(j+1)*total_dim]).all(), j,min_indexs)
            min_probs=torch.where((j_prob<min_probs) & (masks[:,j*total_dim:(j+1)*total_dim]).all(),j_prob,min_probs)
    
    # 模型训练模式
    model.train()
    return min_indexs