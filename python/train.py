import random
import numpy as np
from collections import defaultdict, deque
from chess import Board, Game
from MCTS_pure import MCTSPlayer as MCTS_Pure
from MCTS import MCTSPlayer
from policy_value_net import PolicyValueNet  



class Train():
    def __init__(self, init_model=None):
       

        '''
            self.learn_rate：学习率，用于神经网络的训练
            self.lr_multiplier：学习率乘数，用于调整学习率
            self.temp：温度参数，用于控制 MCTS 中的探索和利用平衡
            self.n_playout：每次 AI 决策时进行的 MCTS 模拟次数
            self.c_puct：MCTS 中的 UCT 参数，用于平衡探索和利用
            self.buffer_size：存储训练数据的缓冲区大小
            self.batch_size：每次训练时使用的批次大小
            self.data_buffer：使用 deque 创建一个双端队列，用于存储训练数据，其最大长度为 buffer_size
            self.play_batch_size：每次自我对弈时使用的批次大小
            self.epochs：训练时的迭代轮数
            '''

        self.board_width = 20
        self.board_height = 20
        self.n_in_row = 5
        self.board = Board(width=self.board_width,
                           height=self.board_height,
                           n_in_row=self.n_in_row)
        self.game = Game(self.board)
       
        self.learn_rate = 2e-3
        self.lr_multiplier = 1.0  
        self.temp = 1.0  
        self.n_playout = 400  
        self.c_puct = 5
        self.buffer_size = 10000
        self.batch_size = 512  
        self.data_buffer = deque(maxlen=self.buffer_size)
        self.play_batch_size = 1
        self.epochs = 5 
        self.kl_targ = 0.02
        self.check_freq = 50
        self.game_batch_num = 1500
        self.best_win_ratio = 0.0
   
        self.pure_mcts_playout_num = 1000
        if init_model:
      
            self.policy_value_net = PolicyValueNet(self.board_width,   self.board_height,   model_file=init_model)
        else:
          
            self.policy_value_net = PolicyValueNet(self.board_width,   self.board_height)
        self.mcts_player = MCTSPlayer(self.policy_value_net.policy_value_fn,  c_puct=self.c_puct,  n_playout=self.n_playout,  is_selfplay=1)

    def get_equi_data(self, play_data):

        extend_data = []
        for state, mcts_prob, winner in play_data:
            for i in [1, 2, 3, 4]:

                equi_state = np.array([np.rot90(s, i) for s in state])
                equi_mcts_prob = np.rot90(np.flipud(
                    mcts_prob.reshape(self.board_height, self.board_width)), i)
                extend_data.append((equi_state,
                                    np.flipud(equi_mcts_prob).flatten(),
                                    winner))
             
                equi_state = np.array([np.fliplr(s) for s in equi_state])
                equi_mcts_prob = np.fliplr(equi_mcts_prob)
                extend_data.append((equi_state,
                                    np.flipud(equi_mcts_prob).flatten(),
                                    winner))
        return extend_data

    def collect_selfplay_data(self, n_games=1):
       
        for i in range(n_games):
            winner, play_data = self.game.start_self_play(self.mcts_player,
                                                          temp=self.temp)
            play_data = list(play_data)[:]
            self.episode_len = len(play_data)
      
            play_data = self.get_equi_data(play_data)
            self.data_buffer.extend(play_data)

    def policy_update(self):
    
        mini_batch = random.sample(self.data_buffer, self.batch_size)
        state_batch = [data[0] for data in mini_batch]
        mcts_probs_batch = [data[1] for data in mini_batch]
        winner_batch = [data[2] for data in mini_batch]
        old_probs, old_v = self.policy_value_net.policy_value(state_batch)
        for i in range(self.epochs):
            loss, entropy = self.policy_value_net.train_step(
                    state_batch,
                    mcts_probs_batch,
                    winner_batch,
                    self.learn_rate*self.lr_multiplier)
            new_probs, new_v = self.policy_value_net.policy_value(state_batch)
            kl = np.mean(np.sum(old_probs * (
                    np.log(old_probs + 1e-10) - np.log(new_probs + 1e-10)),
                    axis=1)
            )
            if kl > self.kl_targ * 4:  
                break
     
        if kl > self.kl_targ * 2 and self.lr_multiplier > 0.1:
            self.lr_multiplier /= 1.5
        elif kl < self.kl_targ / 2 and self.lr_multiplier < 10:
            self.lr_multiplier *= 1.5

        explained_var_old = (1 -
                             np.var(np.array(winner_batch) - old_v.flatten()) /
                             np.var(np.array(winner_batch)))
        explained_var_new = (1 -
                             np.var(np.array(winner_batch) - new_v.flatten()) /
                             np.var(np.array(winner_batch)))
        print(("kl:{:.5f},"
               "lr_multiplier:{:.3f},"
               "loss:{},"
               "entropy:{},"
               "explained_var_old:{:.3f},"
               "explained_var_new:{:.3f}"
               ).format(kl,
                        self.lr_multiplier,
                        loss,
                        entropy,
                        explained_var_old,
                        explained_var_new))
        return loss, entropy

    def policy_evaluate(self, n_games=10):

        current_mcts_player = MCTSPlayer(self.policy_value_net.policy_value_fn, c_puct=self.c_puct, n_playout=self.n_playout)
        pure_mcts_player = MCTS_Pure(c_puct=5,  n_playout=self.pure_mcts_playout_num)
        win_cnt = defaultdict(int)
        for i in range(n_games):
            winner = self.game.start_play(current_mcts_player,
                                          pure_mcts_player,
                                          start_player=i % 2)
            win_cnt[winner] += 1
        win_ratio = 1.0*(win_cnt[1] + 0.5*win_cnt[-1]) / n_games
        return win_ratio

    def run(self):

   
        for i in range(self.game_batch_num):
            self.collect_selfplay_data(self.play_batch_size)
            print("batch i:{}".format(i+1))
            if len(self.data_buffer) > self.batch_size:
                loss, entropy = self.policy_update()

            if (i+1) % self.check_freq == 0:
                print("current selfplay batch: {}".format(i+1))
                win_ratio = self.policy_evaluate()
                self.policy_value_net.save_model('./current_policy.model')
                if win_ratio > self.best_win_ratio:
                    print("new policy!!!!!!!!")
                    self.best_win_ratio = win_ratio
                    
                    self.policy_value_net.save_model('./best_policy.model')
                    if (self.best_win_ratio == 1.0 and
                            self.pure_mcts_playout_num < 5000):
                        self.pure_mcts_playout_num += 1000
                        self.best_win_ratio = 0.0



if __name__ == '__main__':
    training_pipeline = Train()
    training_pipeline.run()
