# coding: UTF-8
import os
import time
import torch
import numpy as np
from train_eval import train, init_network
from importlib import import_module
import argparse

parser = argparse.ArgumentParser(description='Chinese Text Classification')
# parser.add_argument('--model', type=str, required=True, help='choose a model: TextCNN, TextRNN, FastText, TextRCNN, TextRNN_Att, DPCNN, Transformer')
# parser.add_argument('--embedding', default='pre_trained', type=str, help='random or pre_trained')
# parser.add_argument('--word', default=False, type=bool, help='True for word, False for char')
parser.add_argument('--g', type=int, default=1, help='gpu id')

args = parser.parse_args()

embedding = 'random'  # 'w2v_300.npy'  'random'
model_name = 'TextCNN' # TextCNN, TextRNN, FastText, TextRCNN, TextRNN_Att, DPCNN, Transformer
use_word = True  # 中文用char更好，不会有OOV+学习char分布比word分布更容易(因为量多

if __name__ == '__main__':

    os.environ["CUDA_VISIBLE_DEVICES"] = '%s'%(str(args.g))
    dataset = 'dataset'  # 数据集THUCNews
    # 搜狗新闻:embedding_SougouNews.npz, 腾讯:embedding_Tencent.npz, 随机初始化:random
    # embedding = 'embedding_SougouNews.npz'
    # if args.embedding == 'random':
    #     embedding = 'random'
    # model_name = args.model
    if model_name == 'FastText':
        from utils_fasttext import build_dataset, build_iterator, get_time_dif
        embedding = 'random'
    else:
        from utils import build_dataset, build_iterator, get_time_dif

    x = import_module(name='models.' + model_name)  # 绝对导入
    config = x.Config(dataset, embedding)  # Config类

    np.random.seed(1)
    torch.manual_seed(1)
    torch.cuda.manual_seed_all(1)
    torch.backends.cudnn.deterministic = True  # 保证每次结果一样

    start_time = time.time()
    vocab, train_data, dev_data, test_data = build_dataset(config, use_word)
    train_iter = build_iterator(train_data, config)
    dev_iter = build_iterator(dev_data, config)
    test_iter = build_iterator(test_data, config)  # an object
    time_dif = get_time_dif(start_time)
    print("加载数据耗时:", time_dif)

    # train
    config.n_vocab = len(vocab)
    model = x.Model(config).to(config.device)
    print(model)

    if model_name != 'Transformer':
        init_network(model)
    train(config, model, train_iter, dev_iter, test_iter)
'''
trainset
mean:907
max:57921
min:2
'''
