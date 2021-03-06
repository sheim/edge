import unittest
import numpy as np
import gym

from edge.model.safety_models import SafetyTruth
from edge.envs import Hovership
from edge.space import StateActionSpace
from edge.gym_wrappers import GymEnvironmentWrapper


class CartPole(GymEnvironmentWrapper):
    def __init__(self, discretization_shape):
        gym_env = gym.make('CartPole-v1')
        super(CartPole, self).__init__(gym_env, discretization_shape)


class SafetyTruthTest(unittest.TestCase):
    def test_from_vibly(self):
        env = Hovership()
        truth = SafetyTruth(env)

        vibly_file_path = '../data/ground_truth/from_vibly/hover_map.pickle'
        truth.from_vibly_file(vibly_file_path)

        self.assertTrue(isinstance(truth.stateaction_space, StateActionSpace))
        self.assertEqual(truth.viable_set.shape, truth.measure_value.shape)
        self.assertEqual(truth.viable_set.shape, truth.unviable_set.shape)
        self.assertEqual(truth.viable_set.shape, truth.failure_set.shape)

    def test_get_training_examples(self):
        env = Hovership()
        truth = SafetyTruth(env)

        vibly_file_path = '../data/ground_truth/from_vibly/hover_map.pickle'
        truth.from_vibly_file(vibly_file_path)

        train_x, train_y = truth.get_training_examples(n_examples=2000)
        self.assertEqual(train_x.shape[0], train_y.shape[0])
        self.assertEqual(train_x.shape[0], 2000)
        self.assertEqual(train_x.shape[1],
                         truth.stateaction_space.index_dim)
        train_x, train_y = truth.get_training_examples(
            n_examples=2000, from_failure=True, viable_proportion=0.6
        )
        self.assertEqual(train_x.shape[0], train_y.shape[0])
        self.assertEqual(train_x.shape[0], 2000)
        self.assertEqual(train_x.shape[1],
                         truth.stateaction_space.index_dim)
        self.assertTrue((train_y[:1200] > 0).all())
        self.assertTrue((train_y[1200:] == 0).all())

    def test_gym_truth_computation(self):
        env = CartPole((50, 50, 50, 50, 50))
        print('Computing map...')
        Q_map = env.compute_dynamics_map()
        print('Done.\nSaving map...')
        save_path = './cartpole_map.npz'
        np.savez(save_path, Q_map)