import torch as t
from torch import nn
import torch.nn.functional as F
import math
from config.configurator import configs
from models.loss_utils import cal_bpr_loss, reg_pick_embeds
from models.base_model import BaseModel
from models.model_utils import GCNLayer

init = nn.init.xavier_uniform_
uniformInit = nn.init.uniform

class KCGN(BaseModel):
	def __init__(self, data_handler):
		super(KCGN, self).__init__(data_handler)
		self.layer_num = configs['model']['layer_num']
		self.reg_weight = configs['model']['reg_weight']
		self.fuse = configs['model']['fuse']
		self.lam = configs['model']['lam']
		self.subnode = configs['model']['subnode']
		self.time_step = configs['model']['time_step']

		self.user_embeds = nn.Parameter(init(t.empty(self.user_num, self.embedding_size)))
		self.item_embeds = nn.Parameter(init(t.empty(self.item_num, self.embedding_size)))

		slope = configs['model']['slope']
		self.act = nn.LeakyReLU(negative_slope=slope)
		if self.fuse == 'weight':
			self.w = nn.Parameter(t.Tensor(self.item_num, data_handler.rating_class, 1))
			init(self.w)
		
		self.t_e = TimeEncoding(self.embedding_size, data_handler.max_time)
		self.layers = nn.ModuleList()
		for i in range(self.layer_num - 1):
			self.layers.append(GCNLayer(self.embedding_size, self.embedding_size, weight=True, bias=False, activation=self.act))

		self.is_training = True
	
	def _propagate(self, adj, embeds):
		return t.spmm(adj, embeds)
	
	def forward(self, adj, keep_rate):
		if not self.is_training:
			return self.final_embeds[:self.user_num], self.final_embeds[self.user_num:]
		embeds = t.concat([self.user_embeds, self.item_embeds], axis=0)
		embeds_list = [embeds]
		adj = self.edge_dropper(adj, keep_rate)
		for i in range(self.layer_num):
			embeds = self._propagate(adj, embeds_list[-1])
			embeds_list.append(embeds)
		embeds = sum(embeds_list) / len(embeds_list)
		self.final_embeds = embeds
		return embeds[:self.user_num], embeds[self.user_num:]
	
	def cal_loss(self, batch_data):
		self.is_training = True
		user_embeds, item_embeds = self.forward(self.adj, self.keep_rate)
		ancs, poss, negs = batch_data
		anc_embeds = user_embeds[ancs]
		pos_embeds = item_embeds[poss]
		neg_embeds = item_embeds[negs]
		bpr_loss = cal_bpr_loss(anc_embeds, pos_embeds, neg_embeds)
		reg_loss = reg_pick_embeds([anc_embeds, pos_embeds, neg_embeds])
		loss = bpr_loss + self.reg_weight * reg_loss
		losses = {'bpr_loss': bpr_loss, 'reg_loss': reg_loss}
		return loss, losses

	def full_predict(self, batch_data):
		user_embeds, item_embeds = self.forward(self.adj, 1.0)
		self.is_training = False
		pck_users, train_mask = batch_data
		pck_users = pck_users.long()
		pck_user_embeds = user_embeds[pck_users]
		full_preds = pck_user_embeds @ item_embeds.T
		full_preds = self._mask_predict(full_preds, train_mask)
		return full_preds

class TimeEncoding(nn.Module):
	def __init__(self, n_hid, max_len=240, dropout=0.2):
		super(TimeEncoding, self).__init__()
		position = t.arange(0., max_len).unsqueeze(1)
		div_term = 1 / (10000 ** (t.arange(0., n_hid * 2, 2.)) / n_hid / 2)

		self.emb = nn.Embedding(max_len, n_hid * 2)
		self.emb.weight.data[:, 0::2] = t.sin(position * div_term) / math.sqrt(n_hid)
		self.emb.weight.data[:, 1::2] = t.cos(position * div_term) / math.sqrt(n_hid)
		self.emb.weight.requires_grad = False

		self.emb.weight.data[0] = t.zeros_like(self.emb.weight.data[-1])
		self.emb.weight.data[1] = t.zeros_like(self.emb.weight.data[-1])
		self.lin = nn.Linear(n_hid * 2, n_hid)
	
	def forward(self, time):
		return self.lin(self.emb(time))