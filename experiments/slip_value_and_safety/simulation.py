from pathlib import Path
import numpy as np

from edge import ModelLearningSimulation
from edge.envs import Slip
from edge.agent import ValueAndSafetyLearner
from edge.reward import AffineReward, ConstantReward
from edge.graphics.plotter import QValueAndSafetyPlotter
from edge.model.safety_models import SafetyTruth


class LowGoalSlip(Slip):
    # * This goal incentivizes the agent to run fast
    def __init__(self, dynamics_parameters=None):
        super(LowGoalSlip, self).__init__(
            dynamics_parameters=dynamics_parameters,
            random_start=True
        )

        reward = AffineReward(self.stateaction_space, [(1, 0), (0, 0)])
        self.reward = reward


class PenalizedSlip(LowGoalSlip):
    def __init__(self, penalty_level=100, dynamics_parameters=None):
        super(PenalizedSlip, self).__init__(dynamics_parameters)

        def penalty_condition(state, action, new_state, reward):
            return self.is_failure_state(new_state)

        penalty = ConstantReward(self.reward.stateaction_space, -penalty_level,
                                 reward_condition=penalty_condition)

        self.reward += penalty


def affine_interpolation(t, start, end):
    return start + (end - start) * t


def identity_or_duplicated_value(possible_tuple):
    if isinstance(possible_tuple, tuple):
        return possible_tuple
    else:
        return possible_tuple, possible_tuple


class ValueAndSafetyLearningSimulation(ModelLearningSimulation):
    def __init__(self, name, max_samples, greed, step_size, discount_rate,
                 gamma_optimistic, gamma_cautious, lambda_cautious,
                 q_x_seed, q_y_seed, s_x_seed, s_y_seed,
                 shape, every, glie_start):
        dynamics_parameters = {
            'shape': shape
        }
        self.env = LowGoalSlip(dynamics_parameters=dynamics_parameters)

        self.q_hyperparameters = {
            'outputscale_prior': (0.4, 2),
            'lengthscale_prior': (0.05, 0.1),
            'noise_prior': (0.001, 0.002)
        }
        self.s_hyperparameters = {
            'outputscale_prior': (0.4, 2),
            'lengthscale_prior': (0.2, 0.1),
            'noise_prior': (0.001, 0.002)
        }
        self.q_x_seed = q_x_seed
        self.q_y_seed = q_y_seed
        self.s_x_seed = s_x_seed
        self.s_y_seed = s_y_seed

        self.gamma_optimistic_start, self.gamma_optimistic_end = identity_or_duplicated_value(gamma_optimistic)
        self.gamma_cautious_start, self.gamma_cautious_end = identity_or_duplicated_value(gamma_cautious)
        self.lambda_cautious_start, self.lambda_cautious_end = identity_or_duplicated_value(lambda_cautious)
        self.gamma_optimistic = self.gamma_optimistic_start
        self.gamma_cautious = self.gamma_cautious_start
        self.lambda_cautious = self.lambda_cautious_start

        self.agent = ValueAndSafetyLearner(
            self.env,
            greed=greed,
            step_size=step_size,
            discount_rate=discount_rate,
            q_x_seed=self.q_x_seed,
            q_y_seed=self.q_y_seed,
            gamma_optimistic=self.gamma_optimistic,
            gamma_cautious=self.gamma_cautious,
            lambda_cautious=self.lambda_cautious,
            s_x_seed=s_x_seed,
            s_y_seed=s_y_seed,
            q_gp_params=self.q_hyperparameters,
            s_gp_params=self.s_hyperparameters,
        )

        self.ground_truth = SafetyTruth(self.env)
        self.ground_truth.from_vibly_file(
            Path(__file__).parent.parent.parent / 'data' / 'ground_truth' /
            'from_vibly' / 'slip_map.pickle'
        )

        plotters = {
            'Q-Values_Safety': QValueAndSafetyPlotter(self.agent, self.ground_truth)
        }

        # plotters = {}

        output_directory = Path(__file__).parent.resolve()
        super(ValueAndSafetyLearningSimulation, self).__init__(output_directory, name,
                                                               plotters)

        self.max_samples = max_samples
        self.every = every
        if isinstance(glie_start, float):
            self.glie_start = int(glie_start * self.max_samples)
        else:
            self.glie_start = glie_start

    def get_models_to_save(self):
        # The keys must be the same as the actual names of the attributes, this is used in load_models.
        # This is hacky and should be replaced
        return {
            'Q_model': self.agent.Q_model,
            'safety_model': self.agent.safety_model
        }

    def load_models(self, skip_local=False):
        from edge.model.safety_models import MaternSafety
        from edge.model.value_models import GPQLearning
        models_names = list(self.get_models_to_save().keys())
        loaders= {
            'Q_model': lambda mpath: GPQLearning(mpath, self.env.stateaction_space, self.q_x_seed, self.q_y_seed),
            'safety_model': lambda mpath: MaternSafety(mpath, self.env.stateaction_space, self.gamma_optimistic,
                                                       self.s_x_seed, self.s_y_seed),
        }
        for mname in models_names:
            if not skip_local:
                load_path = self.local_models_path / mname
            else:
                load_path = self.models_path / mname
            setattr(
                self.agent,
                mname,
                loaders[mname](load_path)
            )

    def run(self):
        n_samples = 0
        self.save_figs(prefix='0')

        # train hyperparameters
        print('Optimizing hyperparameters...')
        s_train_x, s_train_y = self.ground_truth.get_training_examples()
        self.agent.fit_models(
            s_epochs=5, s_train_x=s_train_x, s_train_y=s_train_y, s_optimizer_kwargs={'lr': 0.1}
        )
        self.agent.fit_models(
            s_epochs=5, s_train_x=s_train_x, s_train_y=s_train_y, s_optimizer_kwargs={'lr': 0.01}
        )
        self.agent.fit_models(
            s_epochs=5, s_train_x=s_train_x, s_train_y=s_train_y, s_optimizer_kwargs={'lr': 0.001}
        )
        print('Lengthscale:',self.agent.safety_model.gp.covar_module.base_kernel.lengthscale)
        print('Outputscale:',self.agent.safety_model.gp.covar_module.outputscale)
        print('Done.')
        print('Training...')
        while n_samples < self.max_samples:
            reset_state = self.agent.get_random_safe_state()
            self.agent.reset(reset_state)
            failed = self.agent.failed
            n_steps = 0
            while not failed and n_steps < 50:
                n_samples += 1
                n_steps += 1
                old_state = self.agent.state
                new_state, reward, failed = self.agent.step()
                action = self.agent.last_action

                # * start reducing eps to converge to a greedy policy.
                if self.glie_start is not None and n_samples > self.glie_start:
                    self.agent.greed *= (n_samples - self.glie_start) / (
                                        (n_samples - self.glie_start + 1))
                self.agent.gamma_optimistic = affine_interpolation(
                    n_samples / self.max_samples,
                    self.gamma_optimistic_start,
                    self.gamma_optimistic_end
                )
                self.agent.gamma_cautious = affine_interpolation(
                    n_samples / self.max_samples,
                    self.gamma_cautious_start,
                    self.gamma_cautious_end
                )
                self.agent.lambda_cautious = affine_interpolation(
                    n_samples / self.max_samples,
                    self.lambda_cautious_start,
                    self.lambda_cautious_end
                )

                self.on_run_iteration(n_samples, old_state, action, new_state,
                                      reward, failed)

                if n_samples >= self.max_samples:
                    break
            self.agent.reset()
        print('Done.')

        self.save_figs(prefix=f'{self.name}_final')
        self.compile_gif()

    def on_run_iteration(self, n_samples, *args, **kwargs):
        super(ValueAndSafetyLearningSimulation, self).on_run_iteration(*args, **kwargs)

        print(f'Iteration {n_samples}/{self.max_samples}: {self.agent.greed}')
        if n_samples % self.every == 0:
            self.save_figs(prefix=f'{n_samples}')


if __name__ == '__main__':
    sim = ValueAndSafetyLearningSimulation(
        name='with_hyper_opt',
        max_samples=100,
        greed=0.1,
        step_size=0.6,
        discount_rate=0.8,
        gamma_optimistic=(0.7, 0.9),
        gamma_cautious=(0.75, 0.9),
        lambda_cautious=(0, 0.05),
        q_x_seed=np.array([0.4, 0.6]),
        q_y_seed=np.array([1]),
        s_x_seed=np.array([[0.4, 0.6], [0.8, 0.4]]),
        s_y_seed=np.array([1, 0.8]),
        shape=(201,201),
        every=10,
        glie_start=0.9
    )
    sim.set_seed(0)

    sim.run()
    sim.save_models()
