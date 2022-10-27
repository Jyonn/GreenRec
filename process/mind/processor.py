import os
import random

import numpy as np
import pandas as pd
from UniTok import Vocab, UniTok, Column
from UniTok.tok import IdTok, SplitTok, BertTok, EntTok, BaseTok


class ClickTok(BaseTok):
    def __init__(self, name: str):
        super().__init__(name)
        self.vocab.append(0)
        self.vocab.append(1)
        self.vocab.deny_edit()

    def t(self, obj):
        return int(obj)


class Processor:
    def __init__(self, data_dir, store_dir):
        self.data_dir = data_dir
        self.store_dir = store_dir

        os.makedirs(self.store_dir, exist_ok=True)

        self.train_store_dir = os.path.join(self.store_dir, 'train')
        self.dev_store_dir = os.path.join(self.store_dir, 'dev')

        self.nid = Vocab(name='nid')
        self.uid = Vocab(name='uid')

    def read_news_data(self, mode):
        return pd.read_csv(
            filepath_or_buffer=os.path.join(self.data_dir, mode, 'news.tsv'),
            sep='\t',
            names=['nid', 'cat', 'subcat', 'title', 'abs', 'url', 'tit_ent', 'abs_ent'],
            usecols=['nid', 'cat', 'subcat', 'title', 'abs'],
        )

    def read_user_data(self, mode):
        return pd.read_csv(
            filepath_or_buffer=os.path.join(self.data_dir, mode, 'behaviors.tsv'),
            sep='\t',
            names=['session', 'uid', 'time', 'history', 'predict'],
            usecols=['uid', 'history']
        )

    def _read_inter_data(self, mode):
        return pd.read_csv(
            filepath_or_buffer=os.path.join(self.data_dir, mode, 'behaviors.tsv'),
            sep='\t',
            names=['imp', 'uid', 'time', 'history', 'predict'],
            usecols=['imp', 'uid', 'predict']
        )

    def read_inter_data(self, mode):
        df = self._read_inter_data(mode)
        data = dict(imp=[], uid=[], nid=[], click=[])
        for line in df.itertuples():
            predicts = line.predict.split(' ')
            data['imp'].extend([line.imp] * len(predicts))
            data['uid'].extend([line.uid] * len(predicts))
            for predict in predicts:
                nid, click = predict.split('-')
                data['nid'].append(nid)
                data['click'].append(int(click))
        return pd.DataFrame(data)

    def get_news_tok(self, max_title_len=0, max_abs_len=0):
        txt_tok = BertTok(name='english', vocab_dir='bert-base-uncased')

        return UniTok().add_col(Column(
            name='nid',
            tokenizer=IdTok(name='nid', vocab=self.nid).as_sing(),
        )).add_col(Column(
            name='cat',
            tokenizer=EntTok(name='cat').as_sing()
        )).add_col(Column(
            name='subcat',
            tokenizer=EntTok(name='subcat').as_sing(),
        )).add_col(Column(
            name='title',
            tokenizer=txt_tok.as_list(max_length=max_title_len),
        )).add_col(Column(
            name='abs',
            tokenizer=txt_tok.as_list(max_length=max_abs_len),
        ))

    def get_user_tok(self, max_history: int = 0):
        user_ut = UniTok()
        user_ut.add_col(Column(
            name='uid',
            tokenizer=IdTok(name='uid', vocab=self.uid).as_sing(),
        )).add_col(Column(
            name='history',
            tokenizer=SplitTok(
                name='history',
                sep=' ',
                vocab=self.nid
            ).as_list(max_length=max_history, slice_post=True),
        ))
        return user_ut

    def get_inter_tok(self):
        return UniTok().add_col(Column(
            name='imp',
            tokenizer=IdTok(name='imp').as_sing(),
        )).add_col(Column(
            name='uid',
            tokenizer=EntTok(name='uid', vocab=self.uid).as_sing(),
        )).add_col(Column(
            name='nid',
            tokenizer=EntTok(name='nid', vocab=self.nid).as_sing(),
        )).add_col(Column(
            name='click',
            tokenizer=ClickTok(name='click').as_sing(),
        ))

    def combine_news_data(self):
        news_train_df = self.read_news_data('train')
        news_dev_df = self.read_news_data('dev')
        news_df = pd.concat([news_train_df, news_dev_df])
        news_df = news_df.drop_duplicates(['nid'])
        return news_df

    def combine_user_df(self):
        user_train_df = self.read_user_data('train')
        user_dev_df = self.read_user_data('dev')

        user_df = pd.concat([user_train_df, user_dev_df])
        user_df = user_df.drop_duplicates(['uid'])
        return user_df

    def combine_inter_df(self):
        inter_train_df = self.read_inter_data('train')
        inter_dev_df = self.read_inter_data('dev')
        inter_dev_df.imp += max(inter_train_df.imp)

        inter_df = pd.concat([inter_train_df, inter_dev_df])
        return inter_df

    @staticmethod
    def splitter(l: list, portions: list):
        random.shuffle(l)

        portions = np.array(portions)
        portions = portions * 1.0 / portions.sum() * len(l)
        portions = list(map(int, portions))
        portions[-1] = len(l) - sum(portions[:-1])

        pos = 0
        parts = []
        for i in portions:
            parts.append(l[pos: pos+i])
            pos += i
        return parts

    def reassign_inter_df(self):
        inter_df = self.combine_inter_df()
        imp_list = inter_df.imp.drop_duplicates().to_list()

        train_imps, dev_imps, test_imps = self.splitter(imp_list, [8, 1, 1])
        inter_train_df, inter_dev_df, inter_test_df = [], [], []

        inter_groups = inter_df.groupby('imp')
        for imp, imp_df in inter_groups:
            if imp in train_imps:
                inter_train_df.append(imp_df)
            elif imp in dev_imps:
                inter_dev_df.append(imp_df)
            else:
                inter_test_df.append(imp_df)
        return pd.concat(inter_train_df), pd.concat(inter_dev_df), pd.concat(inter_test_df)

    def analyse_news(self):
        tok = self.get_news_tok(
            max_title_len=0,
            max_abs_len=0
        )
        df = self.combine_news_data()
        tok.read_file(df).analyse()

    def analyse_user(self):
        tok = self.get_user_tok(max_history=0)
        df = self.combine_user_df()
        tok.read_file(df).analyse()

    def analyse_inter(self):
        tok = self.get_inter_tok()
        df = self.combine_inter_df()
        tok.read_file(df).analyse()

    def tokenize(self):
        news_tok = self.get_news_tok(
            max_title_len=20,
            max_abs_len=50
        )
        news_df = self.combine_news_data()
        news_tok.read_file(news_df).tokenize().store_data(os.path.join(self.store_dir, 'news'))

        user_tok = self.get_user_tok(max_history=30)
        user_df = self.combine_user_df()
        user_tok.read_file(user_df).tokenize().store_data(os.path.join(self.store_dir, 'user'))

        for inter_df, mode in zip(self.reassign_inter_df(), ['train', 'dev', 'test']):
            inter_tok = self.get_inter_tok()
            if mode in ['train', 'dev']:
                inter_df = inter_df[inter_df.click == 1]
            inter_tok.read_file(inter_df).tokenize().store_data(os.path.join(self.store_dir, mode))


if __name__ == '__main__':
    p = Processor(
        data_dir='/data1/qijiong/Data/MIND/',
        store_dir='../../data/MIND-small'
    )
    # p.analyse_news()
    # p.analyse_user()
    # p.analyse_inter()
    p.tokenize()
