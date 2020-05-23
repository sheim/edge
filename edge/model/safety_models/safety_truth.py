import pickle as pkl
import numpy as np
from pathlib import Path

from .. import GroundTruth
from edge.space import Segment, ProductSpace, StateActionSpace
from edge.utils import get_parameters_lookup_dictionary


class SafetyTruth(GroundTruth):
    def __init__(self, env):
        super(SafetyTruth, self).__init__()
        self.env = env

        # These attributes are initialized either by compute, load,
        # or from_vibly_file
        self.stateaction_space = None
        self.viable_set = None
        self.unviable_set = None
        self.failure_set = None
        self.state_measure = None
        self.measure_value = None

    def get_training_examples(self, n_examples=2000, from_viable=True,
                              from_failure=False, viable_proportion=0.6):
        def sample_when_true(n, condition):
            if n > 0:
                idx_satisfying_condition = np.argwhere(condition)
            else:
                idx_satisfying_condition = np.empty(
                    shape=(0, len(condition.shape)),
                    dtype=int
                )

            n = min(n, len(idx_satisfying_condition))
            sample = np.random.choice(
                idx_satisfying_condition.shape[0], n, replace=False
            )
            sample_idx_list = idx_satisfying_condition[sample]
            sample_idx_tuple = tuple(zip(*sample_idx_list))
            if len(sample_idx_tuple) == 0:
                sample_idx_tuple = ((), ())

            sample_x = np.array([
                self.stateaction_space[tuple(idx)]
                for idx in sample_idx_list
            ]).reshape((-1, self.stateaction_space.index_dim))
            sample_y = self.measure[sample_idx_tuple].squeeze()
            return sample_x, sample_y

        n_viable = 0 if not from_viable\
            else n_examples if not from_failure\
            else int(viable_proportion * n_examples)
        n_failure = n_examples - n_viable

        viable_x, viable_y = sample_when_true(
            n_viable, self.viable_set.astype(bool)
        )
        failure_x, failure_y = sample_when_true(
            n_failure, self.failure_set.astype(bool)
        )

        train_x = np.vstack((viable_x, failure_x))
        train_y = np.hstack((viable_y, failure_y))

        return train_x, train_y

    def measure(self, state, action):
        stateactions = self.stateaction_space[state, action]
        if len(stateactions.shape) > 1:
            index = [
                self.stateaction_space.get_index_of(sa, around_ok=True)
                for sa in stateactions
            ]
            # We get a tuple of indexes along each coordinate to index the
            # NumPy array
            index = tuple(zip(*index))
        else:
            index = tuple(self.stateaction_space.get_index_of(stateactions,
                                                              around_ok=True))
        return self.measure_value[index]

    def is_viable(self, state=None, action=None, stateaction=None):
        if stateaction is None:
            stateaction = self.stateaction_space[state, action]
        index = self.stateaction_space.get_index_of(
            stateaction, around_ok=True
        )
        return self.viable_set[index] == 1

    def is_unviable(self, state, action):
        sa = self.stateaction_space[state, action]
        index = self.stateaction_space.get_index_of(
            sa, around_ok=True
        )
        out = self.unviable_set[index] == 1
        return out

    def is_failure(self, state, action):
        index = self.stateaction_space.get_index_of(
            (state, action), around_ok=True
        )
        return self.failure_set[index] == 1

    def from_vibly_file(self, vibly_file_path):
        with vibly_file_path.open('rb') as f:
            data = pkl.load(f)
        # dict_keys(['grids', 'Q_map', 'Q_F', 'Q_V', 'Q_M', 'S_M', 'p', 'x0'])
        states = data['grids']['states']
        actions = data['grids']['actions']

        if len(states) != self.env.state_space.index_dim:
            raise IndexError('Size mismatch : expected state space with '
                             f'{self.env.state_space.index_dim} dimensions, '
                             f'got {len(states)}')
        if len(actions) != self.env.action_space.index_dim:
            raise IndexError('Size mismatch : expected action space with '
                             f'{self.env.action_space.index_dim} dimensions, '
                             f'got {len(actions)}')

        def get_product_space(np_components):
            segments = [Segment(comp[0], comp[-1], comp.shape[0])
                        for comp in np_components]
            product_space = ProductSpace(*segments)
            return product_space

        state_space = get_product_space(states)
        action_space = get_product_space(actions)
        self.stateaction_space = StateActionSpace(state_space, action_space)

        self.state_measure = data['S_M']
        self.measure_value = data['Q_M']
        self.viable_set = data['Q_V']
        self.failure_set = data['Q_F']
        self.unviable_set = ~self.failure_set
        self.unviable_set[self.viable_set] = False

        # TODO get rid of that
        self.viable_set = self.viable_set.astype(float)
        self.failure_set = self.failure_set.astype(float)
        self.unviable_set = self.unviable_set.astype(float)

        lookup_dictionary = get_parameters_lookup_dictionary(self.env)

        for vibly_pname, vibly_value in data['p'].items():
            pname = lookup_dictionary[vibly_pname]
            if pname is not None:
                value = self.env.dynamics.parameters[pname]
                if value != vibly_value:
                    raise ValueError(
                        f'Value mismatch: value loaded for {pname} from '
                        f'{vibly_pname} does not match. Expected {value}, '
                        f'got {vibly_value}'
                    )

    def compute(self, Q_map_path=None):
        self.stateaction_space = self.env.stateaction_space

        if Q_map_path is not None:
            Q_map = np.load(Q_map_path)
            if Q_map.shape != self.stateaction_space.shape:
                raise ValueError('Loaded map shape and stateaction space shape '
                                 'don\'t match')
        else:
            Q_map = self.env.dynamics.compute_map()
        action_axes = tuple([
            self.stateaction_space.state_space.index_dim + k
            for k in range(self.stateaction_space.action_space.index_dim)
        ])

        def next_state_fails(next_index):
            return self.env.is_failure_state(
                self.stateaction_space.state_space[next_index]
            )

        failure_set = np.array(
            list(map(
                next_state_fails,
                Q_map.reshape(-1).tolist()
            ))
        ).reshape(Q_map.shape)
        viable_set = np.logical_not(failure_set)
        viability_kernel = viable_set.any(axis=action_axes)
        previous_viability_kernel = np.zeros_like(viability_kernel, dtype=bool)

        done = False
        while not done:
            for index, _ in iter(self.stateaction_space):
                is_viable = viable_set[index]
                if is_viable:
                    next_state_index = Q_map[index]
                    next_is_viable = viability_kernel[next_state_index]
                    if not next_is_viable:
                        viable_set[index] = False
            previous_viability_kernel = viability_kernel
            viability_kernel = viable_set.any(axis=action_axes)
            done = np.all(viability_kernel == previous_viability_kernel)


        self.viable_set = viable_set
        self.failure_set = failure_set
        self.unviable_set = np.logical_and(
            np.logical_not(viable_set),
            np.logical_not(failure_set)
        )
        self.state_measure = self.viable_set.mean(axis=action_axes)

        def next_state_measure(next_index):
            return self.state_measure[next_index]
        self.measure_value = np.array(
            list(map(
                next_state_measure,
                Q_map.reshape(-1).tolist()
            ))
        ).reshape(Q_map.shape)

    def save(self, save_path):
        save_dict = {
            'viable_set': self.viable_set,
            'unviable_set': self.unviable_set,
            'failure_set': self.failure_set,
            'state_measure': self.state_measure,
            'measure_value': self.measure_value
        }
        np.savez(save_path, **save_dict)

    @staticmethod
    def load(load_path, env):
        truth = SafetyTruth(env)
        truth.stateaction_space = env.stateaction_space

        loaded = np.load(load_path)

        for attribute_name, attribute in loaded.items():
            setattr(truth, attribute_name, attribute)

        if truth.stateaction_space.shape != truth.viable_set.shape:
            raise ValueError(f'Got {truth.viable_set.shape} shape for the '
                             'viable set, expected '
                             f'{truth.stateaction_space.shape}')

        return truth
