""" Implements Deep Q-Learning Learner. """
import tensorflow as tf
from derl.alg.dqn import DQN
from derl.learners.learner import Learner
from derl.models import NatureDQNModel
from derl.policies import EpsilonGreedyPolicy
from derl.runners.experience_replay import make_dqn_runner
from derl.train import StepVariable, linear_anneal


class DQNLearner(Learner):
  """ Deep Q-Learning Learner. """
  @staticmethod
  def get_defaults(env_type="atari"):
    return {
        "atari": {
            "num-train-steps": int(200e6),
            "exploration-epsilon-start": 1.,
            "exploration-epsilon-end": 0.01,
            "exploration-end-step": int(1e6),
            "storage-size": int(1e6),
            "storage-init-size": int(50e3),
            "not-prioritized": dict(action="store_false", dest="prioritized"),
            "per-alpha": 0.6,
            "per-beta": dict(type=float, default=(0.4, 1.), nargs=2),
            "steps-per-sample": 4,
            "batch-size": 32,
            "nstep": 3,
            "lr": 2.5e-4,
            "optimizer-decay": 0.95,
            "optimizer-momentum": 0.,
            "optimizer-epsilon": 0.01,
            "gamma": .99,
            "target-update-period": int(40e3),
            "no-double": dict(action="store_false", dest="double"),
        },
    }.get(env_type)

  @staticmethod
  def make_model(env, init=None, **kwargs):
    """ Creates Nature-DQN model for a given env. """
    if init is None:
      init = dict(kernel_initializer=tf.initializers.he_uniform(),
                  bias_initializer=tf.initializers.he_uniform())
    return NatureDQNModel(input_shape=env.observation_space.shape,
                          output_units=env.action_space.n, **init, **kwargs)

  @staticmethod
  def make_runner(env, args, model=None):
    model = model or DQNLearner.make_model(env)
    step_var = StepVariable("global_step", tf.train.create_global_step())
    epsilon = linear_anneal(
        "exploration_epsilon", args.exploration_epsilon_start,
        args.exploration_end_step, step_var, args.exploration_epsilon_end)
    policy = EpsilonGreedyPolicy(model, epsilon)
    kwargs = vars(args)
    runner_kwargs = {k: kwargs[k] for k in ("storage_size", "storage_init_size",
                                            "batch_size", "steps_per_sample",
                                            "nstep", "prioritized")
                     if k in kwargs}
    runner = make_dqn_runner(env, policy, args.num_train_steps,
                             step_var=step_var, **runner_kwargs)
    return runner

  @staticmethod
  def make_alg(runner, args):
    model = runner.policy.model
    env = runner.env
    # TODO: support any model by clonning the model from runner.
    target_model = DQNLearner.make_model(env)
    target_model.set_weights(model.get_weights())

    kwargs = vars(args)
    optimizer_kwargs = {
        "decay": kwargs.get("decay", 0.95),
        "momentum": kwargs.get("momentum", 0.),
        "epsilon": kwargs.get("optimizer_epsilon", 0.01),
    }
    optimizer = tf.train.RMSPropOptimizer(args.lr, **optimizer_kwargs)
    dqn_kwargs = {k: kwargs[k] for k in
                  ("gamma", "target_update_period", "double") if k in kwargs}
    alg = DQN(model, target_model, optimizer, **dqn_kwargs)
    return alg
