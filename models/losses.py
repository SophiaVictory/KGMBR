import torch as t
from config.configurator import configs

def cal_bpr_loss(anc_embeds, pos_embeds, neg_embeds):
	pos_preds = (anc_embeds * pos_embeds).sum(-1)
	neg_preds = (anc_embeds * neg_embeds).sum(-1)
	diff_preds = pos_preds - neg_preds
	return - diff_preds.sigmoid().log().sum()

def reg_pick_embeds(embeds_list):
	reg_loss = 0
	for embeds in embeds_list:
		reg_loss += embeds.square().sum()
	return reg_loss

def cal_infonce_loss(embeds1, embeds2, all_embeds2):
	normed_embeds1 = embeds1 / t.sqrt(embeds1.square().sum(-1))
	normed_embeds2 = embeds2 / t.sqrt(embeds2.square().sum(-1))
	normed_all_embeds2 = all_embeds2 / t.sqrt(all_embeds2.square().sum(-1))
	nume_term = -(normed_embeds1 * normed_embeds2).sum(-1)
	deno_term = t.log(t.sum(t.exp(normed_embeds1 @ normed_all_embeds2.T), dim=-1))
	cl_loss = (nume_term + deno_term).sum()
	return cl_loss