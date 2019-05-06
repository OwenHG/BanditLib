import copy
import datetime
import json
import os.path
from random import sample, seed, shuffle

import matplotlib.pyplot as plt
import numpy as np

from conf import save_address, sim_files_folder
# from Rewards.FairReward import FairReward
from Recommendation import Recommendation
from Rewards.LinearReward import LinearReward
from Rewards.SocialLinearReward import SocialLinearReward


class RewardManager():
	def __init__(self, arg_dict, reward_type = 'Linear'):
		for key in arg_dict:
			setattr(self, key, arg_dict[key])
		#self.W, self.W0 = self.constructAdjMatrix(self.sparseLevel)

		# Pass arguments to the reward functions using a dictionary
		reward_arg_dict = {}
		try:
			self.reward = globals()[reward_type + 'Reward'](reward_arg_dict)
		except KeyError:
			self.reward = LinearReward(reward_arg_dict)

		# if(reward_type == 'social_linear'):
		# 	self.reward = SocialLinearReward(self.k, self.W)
		# elif(reward_type == 'fair'):
		# 	self.reward = FairReward(self.k)
		# else:
		# 	self.reward = LinearReward(self.k)
	
	def batchRecord(self, iter_):
		if iter_ % 25 == 0:
			print "Iteration %d"%iter_, "Pool", len(self.articlePool)," Elapsed time", datetime.datetime.now() - self.startTime

	def regulateArticlePool(self, time, user_id):
		# Randomly generate articles
		self.articlePool = sample(self.articles, self.poolArticleSize)

	def getL2Diff(self, x, y):
		return np.linalg.norm(x-y) # L2 norm

	def runAlgorithms(self, algorithms, diffLists):
		self.startTime = datetime.datetime.now()
		timeRun = self.startTime.strftime('_%m_%d_%H_%M') 
		filenameWriteRegret = os.path.join(save_address, 'AccRegret' + timeRun + '.csv')
		filenameWritePara = os.path.join(save_address, 'ParameterEstimation' + timeRun + '.csv')

		# compute co-theta for every user
		tim_ = []
		BatchCumlateRegret = {}
		AlgRegret = {}
		CoThetaVDiffList = {}
		RDiffList ={}
		RVDiffList = {}

		CoThetaVDiff = {}
		RDiff ={}
		RVDiff = {}

		Var = {}
		
		# Initialization
		userSize = len(self.users)
		for alg_id in algorithms:
			AlgRegret[alg_id] = []
			BatchCumlateRegret[alg_id] = []
			Var[alg_id] = []

		
		with open(filenameWriteRegret, 'w') as f:
			f.write('Time(Iteration)')
			f.write(',' + ','.join( [str(alg_id) for alg_id in algorithms.iterkeys()]))
			f.write('\n')
		
		with open(filenameWritePara, 'w') as f:
			f.write('Time(Iteration)')
			diffLists.initial_write(f)
			f.write('\n')
		
		# Training
		np.random.seed(58)
		seed(58)
		shuffle(self.articles)
		for iter_ in range(self.training_iterations):
			article = self.articles[iter_]										
			for u in self.users:
				noise = self.noise()
				reward = self.reward.getReward(u, article)
				reward += noise
				for alg_id, alg in algorithms.items():
					alg.updateParameters(article, reward, u.id)	

			for alg_block in algorithms.values():
				if alg_block['name'] == 'syncCoLinUCB':
					alg_block['algorithm'].LateUpdate()	

		#Testing
		article_pool_history = {}
		for iter_ in range(self.testing_iterations):
			total = 0
			counter = 0
			for u in self.users:
				self.regulateArticlePool(iter_, u.id) # select random articles
				if self.save_pool:
					if iter_ not in article_pool_history:
						article_pool_history[iter_] = {}
					article_pool_history[iter_][u.id] = [a.id for a in self.articlePool]

				noise = self.noise()
				#get optimal reward for user x at time t
				#pool_copy = copy.deepcopy(self.articlePool)
				OptimalReward, OptimalArticle = self.reward.getOptimalReward(u, self.articlePool)
				# print "Optimal Reward", OptimalReward
				#OptimalReward = self.reward.getOptimalRecommendationReward(u, self.articlePool, self.k)
				OptimalReward += noise

				for alg_id, alg_block in algorithms.items():
					alg_name = alg_block['name']
					alg = alg_block['algorithm']
					if alg_name == 'FairUCB':
						recommendation = alg.createIncentivizedRecommendation(self.articlePool, u.id, self.k)
						total += recommendation.k
						counter += 1
						# Have the user choose what is the best article for them
						article, incentive = u.chooseArticle(recommendation)
						# Tell the system the users choice
						best_rec = Recommendation(1, [article])
						reward, pickedArticle = self.reward.getRecommendationReward(u, best_rec, noise)
						u.updateParameters(pickedArticle.contextFeatureVector, reward)
					else:
						recommendation = alg.createRecommendation(self.articlePool, u.id, self.k)

						# Assuming that the user will always be selecting one item for each iteration
						#pickedArticle = recommendation.articles[0]
						reward, pickedArticle = self.reward.getRecommendationReward(u, recommendation, noise)
						# print "ActualReward", reward
					if (self.testing_method=="online"):
						alg.updateParameters(pickedArticle, reward, u.id)
						#alg.updateRecommendationParameters(recommendation, rewardList, u.id)
						if alg_name =='CLUB':
							n_components= alg.updateGraphClusters(u.id,'False')

					# print "Regret", float(OptimalReward - reward)
					regret = OptimalReward - reward
					AlgRegret[alg_id].append(regret)

					if u.id == 0:
						if alg_name in ['LBFGS_random','LBFGS_random_around','LinUCB', 'LBFGS_gradient_inc']:
							means, vars = alg.getProb(self.articlePool, u.id)
							Var[alg_id].append(vars[0])

					# #update parameter estimation record
					diffLists.update_parameters(alg_id, self, u, alg, pickedArticle, reward, noise)
			for alg_block in algorithms.values():
				if alg_block['name'] == 'syncCoLinUCB':
					alg_block['algorithm'].LateUpdate()
			diffLists.append_to_lists(userSize)
				
			if iter_%self.batchSize == 0:
				self.batchRecord(iter_)
				tim_.append(iter_)
				for alg_id in algorithms.iterkeys():
					BatchCumlateRegret[alg_id].append(sum(AlgRegret[alg_id]))

				with open(filenameWriteRegret, 'a+') as f:
					f.write(str(iter_))
					f.write(',' + ','.join([str(BatchCumlateRegret[alg_id][-1]) for alg_id in algorithms.iterkeys()]))
					f.write('\n')
				with open(filenameWritePara, 'a+') as f:
					f.write(str(iter_))
					diffLists.iteration_write(f)
					f.write('\n')

		if self.save_pool:
			with open(self.pool_filename, 'w') as outfile:
				json.dump(article_pool_history, outfile)


		if (self.plot==True): # only plot
			# plot the results	
			f, axa = plt.subplots(1, sharex=True)
			for alg_id in algorithms.iterkeys():	
				axa.plot(tim_, BatchCumlateRegret[alg_id],label = alg_id)
				print '%s: %.2f' % (alg_id, BatchCumlateRegret[alg_id][-1])
			axa.legend(loc='upper left',prop={'size':9})
			axa.set_xlabel("Iteration")
			axa.set_ylabel("Regret")
			axa.set_title("Accumulated Regret")
			plt.show()

			# plot the estimation error of co-theta
			f, axa = plt.subplots(1, sharex=True)
			time = range(self.testing_iterations)
			diffLists.plot_diff_lists(axa, time)
		
			axa.legend(loc='upper right',prop={'size':6})
			axa.set_xlabel("Iteration")
			axa.set_ylabel("L2 Diff")
			axa.set_yscale('log')
			axa.set_title("Parameter estimation error")
			plt.show()

		finalRegret = {}
		for alg_id in algorithms.iterkeys():
			finalRegret[alg_id] = BatchCumlateRegret[alg_id][:-1]
		return finalRegret
