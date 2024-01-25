import torch
import torch.nn as nn
import torch.nn.functional as F
import math


class BLTConfig:
    """ base BLT config, params common to all GPT versions"""
    embd_pdrop = 0.1
    resid_pdrop = 0.1
    attn_pdrop = 0.1

    def __init__(self, vocab_size, **kwargs):
        self.vocab_size = vocab_size
        for k, v in kwargs.items():
            setattr(self, k, v)


class BLT(nn.Module):
    def __init__(self, mconf):
        super(BLT, self).__init__()
        self.mconf = mconf
        self.embedder = LayoutEmbed(
            embed_size=mconf.embed_size,
            hidden_dropout_prob=mconf.hidden_dropout_prob,
            vocab_size=mconf.vocab_size,
            pad_token=mconf.pad_token
        )
        """mask_lens = torch.ceil(lens * mask_rate).type(torch.int64)"""
        self.bert_layers = nn.Sequential(*[BertLayer(intermediate_size=mconf.intermediate_size,
                                                     embed_size=mconf.embed_size,
                                                     hidden_dropout_prob=mconf.hidden_dropout_prob,
                                                     n_head=mconf.n_head,
                                                     attention_probs_dropout_prob=mconf.attention_probs_dropout_prob) for i in range(mconf.n_layer)])
        self.bert_mlm = BertMlmLayer(
            embed_size=mconf.embed_size,
            vocab_size=mconf.vocab_size
        )

    def configure_optimizers(self, train_config):
        """
        一个用来选择需要weight_decay的变量的函数
        """
        # 定义优化器的超参数
        weight_decay = train_config.weight_decay
        lr = train_config.learning_rate
        betas = train_config.betas

        # 创建AdamW优化器
        optimizer = torch.optim.AdamW(self.parameters(), lr=lr, betas=betas, weight_decay=weight_decay)
        """
        
        decay_params = []
        no_decay_params = []
        for pn, p in self.named_parameters():
            if pn.endswith("weight") and isinstance(self._modules[pn.split(".")[0]], (torch.nn.Linear,)):
                decay_params.append(p)
            else:
                no_decay_params.append(p)
        optim_groups = [{"params": decay_params, "weight_decay": train_config.weight_decay},
                        {"params": no_decay_params, "weight_decay": 0.0}]
        optimizer = torch.optim.AdamW(
            optim_groups, lr=train_config.learning_rate, betas=train_config.betas)
        """
        
        return optimizer

    def forward(self, input_ids, targets=None, masks=None):
        input_ids = input_ids.long()
        pad_mask = (input_ids == self.mconf.pad_token)   

        input_embeddings = self.embedder(input_ids)
        layer_input = input_embeddings

        for bert_layer in self.bert_layers:
            layer_input = bert_layer(layer_input, pad_mask)

        layer_output = layer_input

        logits = self.bert_mlm(
            layer_output)

        if targets is None:
            loss = 0
        else:
            if masks is not None:
                masks = masks.view(-1)
                loss = torch.nn.functional.cross_entropy(
                    logits.view(-1, logits.size(-1))[masks], targets.view(-1)[masks])
            else:
                loss = torch.nn.functional.cross_entropy(
                    logits.view(-1, logits.size(-1)), targets.view(-1))

        return logits, loss

class PositionalEncoding(torch.nn.Module):
    def __init__(self, d_model,max_len=5000):
        super(PositionalEncoding, self).__init__()


        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        self.register_buffer('pe', pe)

    def forward(self, x):
        return self.pe[x, :]

class LayoutEmbed(nn.Module):
    def __init__(self, embed_size, hidden_dropout_prob, vocab_size, pad_token, hidden_size=None):
        '''
        布局嵌入。
        词嵌入和位置嵌入

        属性:
        embed_size:嵌入维数。
        hidden_dropout_prob:丢弃率。
        vocab_size:词汇量。
        embed_size:嵌入维数投影长度
        '''
        layout_dim = 2
        total_dim = 7


        super(LayoutEmbed, self).__init__()
        self.embed_size = embed_size
        self.hidden_dropout_prob = hidden_dropout_prob
        self.vocab_size = vocab_size
        self.total_dim = total_dim
        self.hidden_size = hidden_size
        self.pad_token = pad_token
        # Token embeddings.
        self.word_embedder = nn.Embedding(vocab_size, embed_size)

        # Position embeddings.
        self.position_embedder = PositionalEncoding(embed_size)

        #这个已经用不到了，但是因为保存的模型有这一项所以没办法删除
        self.asset_embedder = PositionalEncoding(embed_size)

        self.attribute_embedder = nn.Embedding(#特征嵌入
            total_dim, embed_size)

        self.layer_norm = nn.LayerNorm(embed_size)

        if self.hidden_size:
            self.dense = nn.Linear(embed_size, hidden_size)

    def forward(self, input_ids):
        seq_length = input_ids.shape[1]
        position_ids = torch.arange(seq_length,device=input_ids.device).unsqueeze(0)

        word_embeddings = self.word_embedder(input_ids)
        position_embeddings = self.position_embedder(position_ids)

        input_embeddings = word_embeddings + position_embeddings


        input_embeddings = self.layer_norm(input_embeddings)
        if self.hidden_size:
            input_embeddings = self.dense(input_embeddings)
        input_embeddings = F.dropout(
            input_embeddings, p=self.hidden_dropout_prob, training=self.training)

        return input_embeddings


class BertMlmLayer(nn.Module):
    """Bert layer for masked token prediction."""

    def __init__(self, embed_size, vocab_size):
        super(BertMlmLayer, self).__init__()
        self.embed_size = embed_size
        self.mlm_dense = nn.Linear(embed_size, self.embed_size)
        self.mlm_ln = nn.LayerNorm(self.embed_size)
        self.decoder_layer = nn.Linear(embed_size,vocab_size)

    def forward(self, last_layer):
        mlm_hidden = self.mlm_dense(last_layer)
        mlm_hidden = F.gelu(mlm_hidden)
        mlm_hidden = self.mlm_ln(mlm_hidden)
        
        logits = self.decoder_layer(mlm_hidden)

        return logits


class BertLayer(nn.Module):
    """A single Bert layer."""

    def __init__(self, embed_size, intermediate_size, hidden_dropout_prob,
                 n_head, attention_probs_dropout_prob):
        super(BertLayer, self).__init__()

        self.bert_attention = BertAttention(
            embed_size=embed_size,
            hidden_dropout_prob=hidden_dropout_prob,
            n_head=n_head,
            attention_probs_dropout_prob=attention_probs_dropout_prob)

        self.bert_mlp = BertMlp(
            embed_size=embed_size,
            hidden_dropout_prob=hidden_dropout_prob,
            intermediate_size=intermediate_size)

    def forward(self, layer_input, pad_mask):
        attention_output = self.bert_attention(layer_input, pad_mask)
        layer_output = self.bert_mlp(attention_output)
        return layer_output


class BertMlp(nn.Module):
    """BERT MLP layer that is part of each BERT layer."""

    def __init__(self, embed_size, hidden_dropout_prob, intermediate_size):
        super(BertMlp, self).__init__()
        self.intermediate_output = nn.Linear(embed_size, intermediate_size)
        self.layer_output = nn.Linear(intermediate_size, embed_size)
        self.hidden_dropout_prob = hidden_dropout_prob
        self.layer_norm = nn.LayerNorm(embed_size)

    def forward(self, attention_output):
        # Bert intermediate layer.
        intermediate_output = self.intermediate_output(attention_output)
        intermediate_output = torch.nn.functional.gelu(intermediate_output)

        # Bert output layer.
        layer_output = self.layer_output(intermediate_output)
        layer_output = F.dropout(
            layer_output, p=self.hidden_dropout_prob, training=self.training)
        layer_output = self.layer_norm(layer_output + attention_output)

        return layer_output


class BertAttention(nn.Module):
    def __init__(self, embed_size, hidden_dropout_prob, n_head, attention_probs_dropout_prob):
        super(BertAttention, self).__init__()
        self.hidden_dropout_prob = hidden_dropout_prob
        self.self_attention = nn.MultiheadAttention(
            embed_size, n_head, dropout=attention_probs_dropout_prob, batch_first=True)
        self.attention_probs_dropout_prob=attention_probs_dropout_prob
        self.dropout = nn.Dropout(hidden_dropout_prob)
        self.layer_norm = nn.LayerNorm(embed_size)

    def forward(self, layer_input, pad_mask):

        attention_output, _ = self.self_attention(
            layer_input, layer_input, layer_input)#, key_padding_mask=pad_mask)

        attention_output = F.dropout(
            attention_output, p=self.hidden_dropout_prob, training=self.training)

        attention_output = self.layer_norm(attention_output + layer_input)

        return attention_output
