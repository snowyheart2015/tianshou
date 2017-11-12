import os
import time
import sys

import numpy as np
import tensorflow as tf
import tensorflow.contrib.layers as layers

import multi_gpu
import time

#os.environ["CUDA_VISIBLE_DEVICES"] = "1"
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

def residual_block(input, is_training):
	normalizer_params = {'is_training': is_training,
						 'updates_collections': tf.GraphKeys.UPDATE_OPS}
	h = layers.conv2d(input, 256, kernel_size=3, stride=1, activation_fn=tf.nn.relu,
					  normalizer_fn=layers.batch_norm, normalizer_params=normalizer_params,
					  weights_regularizer=layers.l2_regularizer(1e-4))
	h = layers.conv2d(h, 256, kernel_size=3, stride=1, activation_fn=tf.identity,
					  normalizer_fn=layers.batch_norm, normalizer_params=normalizer_params,
					  weights_regularizer=layers.l2_regularizer(1e-4))
	h = h + input
	return tf.nn.relu(h)


def policy_heads(input, is_training):
	normalizer_params = {'is_training': is_training,
						 'updates_collections': tf.GraphKeys.UPDATE_OPS}
	h = layers.conv2d(input, 2, kernel_size=1, stride=1, activation_fn=tf.nn.relu,
					  normalizer_fn=layers.batch_norm, normalizer_params=normalizer_params,
					  weights_regularizer=layers.l2_regularizer(1e-4))
	h = layers.flatten(h)
	h = layers.fully_connected(h, 362, activation_fn=tf.identity, weights_regularizer=layers.l2_regularizer(1e-4))
	return h


def value_heads(input, is_training):
	normalizer_params = {'is_training': is_training,
						 'updates_collections': tf.GraphKeys.UPDATE_OPS}
	h = layers.conv2d(input, 2, kernel_size=1, stride=1, activation_fn=tf.nn.relu,
					  normalizer_fn=layers.batch_norm, normalizer_params=normalizer_params,
					  weights_regularizer=layers.l2_regularizer(1e-4))
	h = layers.flatten(h)
	h = layers.fully_connected(h, 256, activation_fn=tf.nn.relu, weights_regularizer=layers.l2_regularizer(1e-4))
	h = layers.fully_connected(h, 1, activation_fn=tf.nn.tanh, weights_regularizer=layers.l2_regularizer(1e-4))
	return h


x = tf.placeholder(tf.float32, shape=[None, 19, 19, 17])
is_training = tf.placeholder(tf.bool, shape=[])
z = tf.placeholder(tf.float32, shape=[None, 1])
pi = tf.placeholder(tf.float32, shape=[None, 362])

h = layers.conv2d(x, 256, kernel_size=3, stride=1, activation_fn=tf.nn.relu, normalizer_fn=layers.batch_norm,
				  normalizer_params={'is_training': is_training, 'updates_collections': tf.GraphKeys.UPDATE_OPS},
				  weights_regularizer=layers.l2_regularizer(1e-4))
for i in range(19):
	h = residual_block(h, is_training)
v = value_heads(h, is_training)
p = policy_heads(h, is_training)
# loss = tf.reduce_mean(tf.square(z-v)) - tf.multiply(pi, tf.log(tf.clip_by_value(tf.nn.softmax(p), 1e-8, tf.reduce_max(tf.nn.softmax(p)))))
value_loss = tf.reduce_mean(tf.square(z - v))
policy_loss = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits(labels=pi, logits=p))

reg = tf.add_n(tf.get_collection(tf.GraphKeys.REGULARIZATION_LOSSES))
total_loss = value_loss + policy_loss + reg
# train_op = tf.train.MomentumOptimizer(1e-4, momentum=0.9, use_nesterov=True).minimize(total_loss)
update_ops = tf.get_collection(tf.GraphKeys.UPDATE_OPS)
with tf.control_dependencies(update_ops):
	train_op = tf.train.RMSPropOptimizer(1e-4).minimize(total_loss)
var_list = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES)
saver = tf.train.Saver(max_to_keep=10, var_list=var_list)


def train():
	data_path = "/home/tongzheng/data/"
	data_name = os.listdir("/home/tongzheng/data/")
	epochs = 100
	batch_size = 128

	result_path = "./checkpoints/"
	with multi_gpu.create_session() as sess:
		sess.run(tf.global_variables_initializer())
		ckpt_file = tf.train.latest_checkpoint(result_path)
		if ckpt_file is not None:
			print('Restoring model from {}...'.format(ckpt_file))
			saver.restore(sess, ckpt_file)
		for epoch in range(epochs):
			for name in data_name:
				data = np.load(data_path + name)
				boards = data["boards"]
				wins = data["wins"]
				ps = data["ps"]
				print (boards.shape)
				print (wins.shape)
				print (ps.shape)
				batch_num = boards.shape[0] // batch_size
				index = np.arange(boards.shape[0])
				np.random.shuffle(index)
				value_losses = []
				policy_losses = []
				regs = []
				time_train = -time.time()
				for iter in range(batch_num):
					lv, lp, r, value, prob, _ = sess.run([value_loss, policy_loss, reg, v, tf.nn.softmax(p), train_op],
														 feed_dict={x: boards[
															 index[iter * batch_size:(iter + 1) * batch_size]],
																	z: wins[index[
																			iter * batch_size:(iter + 1) * batch_size]],
																	pi: ps[index[
																		   iter * batch_size:(iter + 1) * batch_size]],
																	is_training: True})
					value_losses.append(lv)
					policy_losses.append(lp)
					regs.append(r)
					if iter % 1 == 0:
						print(
						"Epoch: {}, Part {}, Iteration: {}, Time: {}, Value Loss: {}, Policy Loss: {}, Reg: {}".format(
							epoch, name, iter, time.time() + time_train, np.mean(np.array(value_losses)),
							np.mean(np.array(policy_losses)), np.mean(np.array(regs))))
						time_train = -time.time()
						value_losses = []
						policy_losses = []
						regs = []
					if iter % 20 == 0:
						save_path = "Epoch{}.Part{}.Iteration{}.ckpt".format(epoch, name, iter)
						saver.save(sess, result_path + save_path)
				del data, boards, wins, ps

def forward(call_number):
    #checkpoint_path = "/home/yama/rl/tianshou/AlphaGo/checkpoints"
    checkpoint_path = "/home/yama/rl/tianshou/AlphaGo/checkpoints/jialian"
    board_file = np.genfromtxt("/home/yama/rl/tianshou/leela-zero/src/mcts_nn_files/board_" + call_number, dtype='str');
    human_board = np.zeros((17, 19, 19))
    #TODO : is it ok to ignore the last channel?
    for i in range(17):
        human_board[i] = np.array(list(board_file[i])).reshape(19, 19)
    feed_board = human_board.transpose(1, 2, 0).reshape(1, 19, 19, 17)
    #print(feed_board.shape)

    #npz_board = np.load("/home/yama/rl/tianshou/AlphaGo/data/7f83928932f64a79bc1efdea268698ae.npz")
    #print(npz_board["boards"].shape)
    #feed_board = npz_board["boards"][10].reshape(-1, 19, 19, 17)
    ##print(feed_board)
    #show_board = feed_board[0].transpose(2, 0, 1)
    #print("board shape : ", show_board.shape)
    #print(show_board)

    itflag = True
    with multi_gpu.create_session() as sess:
            sess.run(tf.global_variables_initializer())
            ckpt_file = tf.train.latest_checkpoint(checkpoint_path)
            if ckpt_file is not None:
            	#print('Restoring model from {}...'.format(ckpt_file))
            	saver.restore(sess, ckpt_file)
            else:
            	raise ValueError("No model loaded")
            res = sess.run([tf.nn.softmax(p),v], feed_dict={x:feed_board, is_training:itflag})
            #res = sess.run([tf.nn.softmax(p),v], feed_dict={x:fix_board["boards"][300].reshape(-1, 19, 19, 17), is_training:False})
            #res = sess.run([tf.nn.softmax(p),v], feed_dict={x:fix_board["boards"][50].reshape(-1, 19, 19, 17), is_training:True})
            #print(np.argmax(res[0]))
            np.savetxt(sys.stdout, res[0][0], fmt="%.6f", newline=" ")
            np.savetxt(sys.stdout, res[1][0], fmt="%.6f", newline=" ")
            pv_file = "/home/yama/rl/tianshou/leela-zero/src/mcts_nn_files/policy_value"
            np.savetxt(pv_file, np.concatenate((res[0][0], res[1][0])), fmt="%.6f", newline=" ")
            #np.savetxt(pv_file, res[1][0], fmt="%.6f", newline=" ")
    return res

if __name__=='__main__':
        np.set_printoptions(threshold='nan')
        #time.sleep(2)
        forward(sys.argv[1])