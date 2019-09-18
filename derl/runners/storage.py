""" Defines classes that store interactions. """
import numpy as np
from derl.runners.sum_tree import SumTree


class InteractionArrays:
  """ Stores arrays of interactions. """
  def __init__(self, size):
    self.size = size
    self.observations = np.empty(self.size, dtype=np.object)
    self.actions = np.empty(self.size, dtype=np.object)
    self.rewards = np.empty(self.size, dtype=np.float32)
    self.resets = np.empty(self.size, dtype=np.bool)

  def get(self, indices, nstep):
    """ Returns `nstep` interactions starting from indices `indices`. """
    # pylint: disable=misplaced-comparison-constant
    nstep_indices = (
        (indices[:, None] + np.arange(nstep)[None]) % self.size)
    next_indices = (indices + nstep) % self.size
    return {
        "observations": np.array(list(self.observations[indices])),
        "actions": np.array(list(self.actions[indices])),
        "rewards": self.rewards[nstep_indices],
        "resets": self.resets[nstep_indices],
        "next_observations": np.array(list(self.observations[next_indices])),
    }

  def set(self, indices, observations, actions, rewards, resets):
    """ Sets values under specified indices. """
    self.observations[indices] = list(observations)
    self.actions[indices] = list(actions)
    self.rewards[indices] = rewards
    self.resets[indices] = resets


class InteractionStorage:
  """ Simple circular buffer that stores interactions. """
  def __init__(self, capacity, nstep=3):
    self.capacity = capacity
    self.nstep = nstep
    self.arrays = InteractionArrays(self.capacity)
    self.index = 0
    self.is_full = self.index >= self.capacity

  @property
  def size(self):
    """ Returns the number elements stored. """
    return self.capacity if self.is_full else self.index

  def get(self, indices):
    """ Returns `nstep` interactions starting from indices `indices`. """
    # pylint: disable=misplaced-comparison-constant
    if not np.all((0 <= indices) & (indices < self.size)):
      raise ValueError(f"indices out of range(0, {self.size}): {indices}")
    return self.arrays.get(indices, self.nstep)

  def add(self, observation, action, reward, done):
    """ Adds new interaction to the storage. """
    index = self.index
    self.arrays.set([index], [observation], [action], [reward], [done])
    self.is_full = self.is_full or index + 1 == self.capacity
    self.index = (index + 1) % self.capacity
    return index

  def add_batch(self, observations, actions, rewards, resets):
    """ Adds a batch of interactions to the storage. """
    batch_size = observations.shape[0]
    if (batch_size != rewards.shape[0] or batch_size != actions.shape[0]
        or batch_size != resets.shape[0]):
      raise ValueError(
          "observations, actions, rewards, and resets all must have the same "
          "first dimension, got first dim sizes: "
          f"{actions.shape[0]}, {rewards.shape[0]}, {resets.shape[0]}")

    indices = (self.index + np.arange(batch_size)) % self.capacity
    self.arrays.set(indices, observations, actions, rewards, resets)
    self.is_full = self.is_full or self.index + batch_size >= self.capacity
    self.index = (self.index + batch_size) % self.capacity
    return indices

  def sample(self, size):
    """ Returns random sample of interactions of specified size. """
    indices = np.random.randint(self.index - self.nstep if not self.is_full
                                else self.capacity - self.nstep, size=size)
    nosample_index = (self.index + self.capacity - self.nstep) % self.capacity
    inc_mask = indices >= nosample_index
    indices[inc_mask] = (indices[inc_mask] + self.nstep) % self.capacity
    return self.get(indices)


class PrioritizedStorage(InteractionStorage):
  """ Wraps given storage to make it prioritized. """
  def __init__(self, capacity, nstep=3, start_max_priority=1):
    super().__init__(capacity, nstep)
    self.sum_tree = SumTree(capacity)
    self.max_priority = start_max_priority

  def add(self, observation, action, reward, done):
    """ Adds data to storage. """
    index = super().add(observation, action, reward, done)
    self.sum_tree.replace(index, self.max_priority)
    return index

  def add_batch(self, observations, actions, rewards, resets):
    """ Adds batch of data to storage. """
    indices = super().add_batch(observations, actions, rewards, resets)
    self.sum_tree.replace(indices, np.full(indices.size, self.max_priority))
    return indices

  def sample(self, size):
    """ Samples data from storage. """
    sums = np.linspace(0, self.sum_tree.sum, size + 1)
    samples = np.random.uniform(sums[:-1], sums[1:])
    indices = self.sum_tree.retrieve(samples)
    sample = super().get(indices)
    sample["indices"] = indices
    sample["log_probs"] = (np.log(self.sum_tree.get_value(indices))
                           - np.log(self.sum_tree.sum))
    return sample

  def update_priorities(self, indices, priorities):
    """ Updates priorities. """
    self.sum_tree.replace(indices, priorities)
