from numpy import squeeze, around
import matplotlib as mpl

from . import Subplotter


class QValueSubplotter(Subplotter):
    def __init__(self, agent, colors):
        super(QValueSubplotter, self).__init__(colors)
        self.agent = agent
        self.states = squeeze(self.model.env.state_space[:])
        self.actions = squeeze(self.model.env.action_space[:])
        stateaction_grid = self.model.env.stateaction_space[:, :]
        self.states_grid = stateaction_grid[:, :, 0]
        self.actions_grid = stateaction_grid[:, :, 1]

    @property
    def model(self):
        return self.agent.Q_model

    def __get_min_max(self, Q_values):
        nonzero_Q = Q_values[Q_values.nonzero()]
        if len(nonzero_Q) == 0:
            return -1, 1
        else:
            qmin = nonzero_Q.min()
            qmax = nonzero_Q.max()
            return qmin, qmax

    def draw_on_axs(self, ax_Q, Q_values):
        vmin, vmax = self.__get_min_max(Q_values)
        self.colors.q_values_norm = mpl.colors.SymLogNorm(
            linthresh=1, linscale=1, vmin=vmin, vmax=vmax
        )
        image = ax_Q.pcolormesh(
            self.actions_grid,
            self.states_grid,
            Q_values,
            cmap=self.colors.cmap_q_values,
            norm=self.colors.q_values_norm,
            # vmin=0,#vmin,
            # vmax=1,#vmax,
            alpha=0.7
        )
        for i in range(Q_values.shape[0]):
            for j in range(Q_values.shape[1]):
                ax_Q.text(j, i, around(Q_values[i, j], 1),
                          ha='center', va='center')
        ax_Q.set_xticks(self.actions)
        ax_Q.set_yticks(self.states)

        ax_Q.set_xlabel('action space $A$')
        ax_Q.set_ylabel('state space $S$')
        frame_width_x = self.actions[-1] * .1
        ax_Q.set_xlim((self.actions[0] - frame_width_x,
                       self.actions[-1] + frame_width_x))

        frame_width_y = self.states[-1] * .05
        ax_Q.set_ylim((self.states[0] - frame_width_y,
                       self.states[-1] + frame_width_y))

        return image
