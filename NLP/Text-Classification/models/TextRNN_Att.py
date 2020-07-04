# coding: UTF-8
import torch
import torch.nn as nn
from models.gru import GRU, GRU_ngram_attn
import torch.nn.functional as F
import numpy as np


class Config(object):

    """配置参数"""
    def __init__(self, dataset, embedding):
        self.model_name = 'TextRNN_Att'
        self.train_path = dataset + '/data/train.txt'                                # 训练集
        self.dev_path = dataset + '/data/dev.txt'                                    # 验证集
        self.test_path = dataset + '/data/test.txt'                                  # 测试集
        self.class_list = [x.strip() for x in open(
            dataset + '/data/class.txt', encoding='utf-8').readlines()]              # 类别名单
        self.vocab_path = dataset + '/data/vocab.pkl'                                # 词表
        self.save_path = dataset + '/saved_dict/' + self.model_name + '.ckpt'        # 模型训练结果
        self.log_path = dataset + '/log/' + self.model_name
        self.embedding_pretrained = torch.tensor(
            np.load(dataset + '/data/' + embedding)["embeddings"].astype('float32'))\
            if embedding != 'random' else None                                       # 预训练词向量
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')   # 设备

        self.dropout = 0.5                                              # 随机失活
        self.require_improvement = 1000                                 # 若超过1000batch效果还没提升，则提前结束训练
        self.num_classes = len(self.class_list)                         # 类别数
        self.n_vocab = 0                                                # 词表大小，在运行时赋值
        self.num_epochs = 5                                             # epoch数
        self.batch_size = 128                                           # mini-batch大小
        self.pad_size = 32                                              # 每句话处理成的长度(短填长切)
        self.learning_rate = 1e-3                                       # 学习率
        self.embed = self.embedding_pretrained.size(1)\
            if self.embedding_pretrained is not None else 300           # 字向量维度, 若使用了预训练词向量，则维度统一
        self.hidden_size = 128                                          # lstm隐藏层
        self.num_layers = 2                                             # lstm层数
        self.hidden_size2 = 64
        self.n_gram = 3
        self.n_head = 2
        self.attn_type = 2
        self.bidirectional = False


'''Attention-Based Bidirectional Long Short-Term Memory Networks for Relation Classification'''


class Model(nn.Module):
    def __init__(self, config):
        super(Model, self).__init__()
        self.cfg = config
        if config.embedding_pretrained is not None:
            self.embedding = nn.Embedding.from_pretrained(config.embedding_pretrained, freeze=False)
        else:
            self.embedding = nn.Embedding(config.n_vocab, config.embed, padding_idx=config.n_vocab - 1)
        self.cfg = config
        self.gru = GRU(config.embed, config.hidden_size, config.num_layers, n_gram=1, bidirectional=config.bidirectional) #sum:90.3, last:90.47 其实直接emb就87.2
        self.gru_n = GRU_ngram_attn(config.embed, config.hidden_size, config.num_layers,
                                     n_gram=config.n_gram, n_head=config.n_head, attn_type=config.attn_type,
                                    bidirectional=config.bidirectional)
        # self.gru = nn.GRU(config.embed, config.hidden_size, batch_first=True) #sum:90.0, last:90.7

        self.tanh = nn.Tanh()
        self.fc0 = nn.Linear(config.embed, config.hidden_size2)
        self.fc1 = nn.Linear(config.hidden_size, config.hidden_size2)
        self.fc2 = nn.Linear(config.hidden_size2, config.num_classes)

    def forward(self, x):
        x, _ = x
        x = self.embedding(x)  # [batch_size, seq_len, embeding]=[128, 32, 300]
        # H, _ = self.gru(x)  # [batch_size, seq_len, hidden_size * num_direction]=[128, 32, 256]
        out = self.gru_n(x)

        out = out.sum(1)  # [bs, h_s2]
        out = F.relu(out)
        out = self.fc0(out) if out.shape[-1] == self.cfg.embed else self.fc1(out) #[bs, h_s2]
        out = self.fc2(out)  # [bs, 10]
        return out