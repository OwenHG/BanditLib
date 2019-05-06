from __future__ import division
import numpy as np


class NoisePartialSum:
    def __init__(self, start, size, noise):
        self.start = start
        self.size = size
        self.noise = noise

    def __str__(self):
        return 'NoisePartialSum(start=%i, size=%i)' % (self.start, self.size)


class NoisePartialSumStore:
    def __init__(self, noise_generator, release_method='tree', is_theta_level=False):
        if release_method != 'tree' and noise_generator.noise_type != 'laplacian':
            raise NotImplementedError
        if release_method not in ['tree', 'every', 'once', 'sqrt', 'hybrid']:
            raise NotImplementedError
        self.noise_generator = noise_generator
        self.release_method = release_method
        self.is_theta_level = is_theta_level
        self.store = {}
        self.START_TIME = 1

    def is_power_of_two(self, val):
        return ((val & (val - 1)) == 0) and val > 0

    def consolidate_for_once(self, time):
        """Delete all partial sums except at start.

        This is used for the 'once' release method. The first noise added
        will be of a magnitude great enough to protect privacy throughout
        the algorithm.

        Args:
            time (int): time of newly added partial sum
        """
        if time != self.START_TIME:
            del self.store[time]

    def consolidate_for_every(self, time):
        """Collapse all partial sums into one partial sum.

        This is used for the 'every' release method. Each new partial sum
        will have a small amount of noise that will accumulate in a bigger
        and bigger partial sum.

        Args:
            time (int): time of newly added partial sum
        """
        current_total_noise = self.store[self.START_TIME].noise
        newly_added_noise = self.store[time].noise
        new_total_noise = current_total_noise + newly_added_noise
        new_psum_size = time
        self.store[self.START_TIME] = NoisePartialSum(
            1, new_psum_size, new_total_noise)
        if time != self.START_TIME:
            del self.store[time]

    def consolidate_for_sqrt(self, time):
        """Collapse all block partial sums into one partial sum.

        This is used for the 'sqrt' release method. Theoretically, we compute partial sums
        of either a block's size or of a single item. If there are enough single items to
        create a block, consolidate them into one block. To achieve O(1) storage, we
        consolidate all block-level partial sums as well.

        Args:
            time (int): time of newly added partial sum
        """
        eps = self.noise_generator.eps
        block_size = int(np.sqrt(self.noise_generator.T))
        block_start = time - block_size + 1
        if block_start in self.store:
            for _t in range(block_start, time + 1):
                del self.store[_t]
            block_noise = self.noise_generator.laplacian(2*eps)
            if block_start == self.START_TIME:
                self.store[self.START_TIME] = NoisePartialSum(
                    self.START_TIME, block_size, block_noise)
            else:
                self.store[self.START_TIME] = NoisePartialSum(
                    self.START_TIME, self.store[self.START_TIME].size + block_size, self.store[self.START_TIME].noise + block_noise)

    def consolidate_for_tree(self, time):
        """Collapse all partial sums into "power of two"-sized blocks.

        This is used for the 'tree' release method. Instead of fixed-sized blocks like
        in the 'sqrt' release method, this consolidation technique will collapse sums
        into "power of two"-sized blocks. This method recursively combines equal-sized
        partial sums until there are no more.

        Args:
            time (int): time of newly added partial sum
        """
        prev_p_sum_time = self.store[time].start - self.store[time].size
        if prev_p_sum_time in self.store:
            if self.store[time].size == self.store[prev_p_sum_time].size:
                new_size = self.store[time].size * 2
                eps = self.noise_generator.eps
                delta = self.noise_generator.delta
                T = self.noise_generator.T
                new_noise = self.noise_generator.generate_noise_tree(eps, delta, T)
                self.store[prev_p_sum_time] = NoisePartialSum(
                    prev_p_sum_time, new_size, new_noise)
                del self.store[time]
                self.consolidate_for_tree(prev_p_sum_time)

    def consolidate_for_hybrid(self, time):
        """Collapse all partial sums into one "power of two"-sized block with a tree.

        This is used for the 'hybrid' release method.

        Args:
            time (int): time of newly added partial sum
        """
        if self.is_power_of_two(time) and time > self.START_TIME:
            new_size = time
            new_noise = self.store[self.START_TIME].noise + self.store[time].noise # should be 1 /eps
            self.store = {
                self.START_TIME: NoisePartialSum(self.START_TIME, new_size, new_noise)
            }
        else:
            prev_p_sum_time = self.store[time].start - self.store[time].size
            if prev_p_sum_time in self.store:
                if self.store[time].size == self.store[prev_p_sum_time].size:
                    new_size = self.store[time].size * 2
                    eps = self.noise_generator.eps
                    delta = self.noise_generator.delta
                    T = 2**int(np.log2(time))
                    new_noise = self.noise_generator.generate_noise_tree(eps, delta, T)
                    self.store[prev_p_sum_time] = NoisePartialSum(
                        prev_p_sum_time, new_size, new_noise)
                    del self.store[time]
                    self.consolidate_for_hybrid(prev_p_sum_time)


    def consolidate_store(self, time):
        if self.release_method == 'once':
            self.consolidate_for_once(time)
        elif self.release_method == 'every':
            self.consolidate_for_every(time)
        elif self.release_method == 'sqrt':
            self.consolidate_for_sqrt(time)
        elif self.release_method == 'tree':
            self.consolidate_for_tree(time)
        elif self.release_method == 'hybrid':
            self.consolidate_for_hybrid(time)

    def add_noise(self, time):
        T = self.noise_generator.T
        eps = self.noise_generator.eps
        delta = self.noise_generator.delta
        noise = self.noise_generator.zeros()
        if self.release_method == 'once':
            if len(self.store) == 0:
                noise = self.noise_generator.laplacian(eps / T)
        elif self.release_method == 'every':
            noise = self.noise_generator.laplacian(eps)
        elif self.release_method == 'sqrt':
            noise = self.noise_generator.laplacian(eps)
        elif self.release_method == 'tree':
            noise = self.noise_generator.generate_noise_tree(eps, delta, T)
        elif self.release_method == 'hybrid':
            if self.is_power_of_two(time):
                noise = self.noise_generator.laplacian(eps / 2)
            else:
                time_horizon = 2**int(np.log2(time))
                noise = self.noise_generator.laplacian((eps / 2) / np.log2(time_horizon))
        self.store[time] = NoisePartialSum(start=time, size=1, noise=noise)
        self.consolidate_store(time)

    def add_noise_custom(self, N, time):
        self.store[time] = NoisePartialSum(start=time, size=1, noise=N)
        self.consolidate_store(time)

    def release_noise(self):
        """Returns the sum of noise in all partial sums in store."""
        N = self.noise_generator.zeros()
        for p_sum in self.store.values():
            N += p_sum.noise
        return N


class _NoisePartialSumStore(object):
    def __init__(self, noise_generator=None):
        self.store = {}
        self.START = 1
        self.noise_generator = noise_generator

    def add(self, time, noise):
        self.store[time] = NoisePartialSum(start=time, size=1, noise=noise)
        self.consolidate()

    def consolidate(self):
        pass

    def release(self):
        if len(self.store) == 0:
            return np.zeros(shape=(1, 1))
        
        noise_shape = self.store.values()[0].noise.shape
        total_noise = np.zeros(shape=noise_shape)
        for psum in self.store.values():
            total_noise += psum.noise
        return total_noise

class OncePartialSumStore(_NoisePartialSumStore):
    def __init__(self, noise_generator=None):
        super(OncePartialSumStore, self).__init__(noise_generator)
    
    def consolidate(self):
        """Delete all partial sums except at start.

        This is used for the 'once' release method. The first noise added
        will be of a magnitude great enough to protect privacy throughout
        the rest of the algorithm.
        """
        if self.START in self.store:
            self.store = {
                self.START: self.store[self.START]
            }
        else:
            self.store = {}

class EveryPartialSumStore(_NoisePartialSumStore):
    def __init__(self, noise_generator=None):
        super(EveryPartialSumStore, self).__init__(noise_generator)
    
    def consolidate(self):
        """Collapse all partial sums into one partial sum.

        This is used for the 'every' release method. Each new partial sum
        will have a small amount of noise that will accumulate in a bigger
        and bigger partial sum.
        """
        if len(self.store) == 0:
            return
        
        noise_shape = self.store.values()[0].noise.shape
        total_noise = np.zeros(shape=noise_shape)
        for psum in self.store.values():
            total_noise += psum.noise
        self.store = {
            self.START: NoisePartialSum(start=self.START, size=1, noise=total_noise)
        }

class TwoLevelPartialSumStore(_NoisePartialSumStore):
    def __init__(self, noise_generator, block_size):
        super(TwoLevelPartialSumStore, self).__init__(noise_generator)
        self.block_size = block_size
        self.block_level_store = None
        self.single_level_store = None
        self.new_psum = None
    
    def add(self, time, noise):
        self.new_psum = NoisePartialSum(start=time, size=1, noise=noise)
        self.consolidate()

    def consolidate(self):
        """Collapse all block partial sums into one partial sum.

        This is used for the 'two-level' release method. Theoretically, we compute partial sums
        of either a block's size or of a single item. If there are enough single items to
        create a block, consolidate them into one block. To achieve O(1) storage, we
        consolidate all block-level partial sums as well.
        """
        # Consolidate new psum into size-1 psum store
        if self.single_level_store:
            start = self.single_level_store.start
            size = self.single_level_store.size + 1
            noise = self.single_level_store.noise + self.new_psum.noise
        else:
            start = self.new_psum.start
            size = self.new_psum.size
            noise = self.new_psum.noise
        self.single_level_store = NoisePartialSum(start=start, size=size, noise=noise)
        self.new_psum = None

        # Consolidate size-1 psum store into block-level psum store
        if self.single_level_store.size >= self.block_size:
            new_noise_sens = self.single_level_store.start + self.single_level_store.size - 1
            new_noise = self.noise_generator.laplacian(2 * self.noise_generator.eps, sens=new_noise_sens)
            if self.block_level_store:
                start = self.block_level_store.start
                size = self.block_level_store.size + self.single_level_store.size
                noise = self.block_level_store.noise + new_noise
            else:
                start = self.START
                size = self.single_level_store.size
                noise = new_noise
            self.block_level_store = NoisePartialSum(start=start, size=size, noise=noise)
            self.single_level_store = None

    def release(self):
        if self.block_level_store and self.single_level_store:
            return self.block_level_store.noise + self.single_level_store.noise
        elif self.block_level_store:
            return self.block_level_store.noise
        elif self.single_level_store:
            return self.single_level_store.noise
        else:
            return np.zeros(shape=(1, 1))

class TreePartialSumStore(_NoisePartialSumStore):
    def __init__(self, noise_generator=None):
        super(TreePartialSumStore, self).__init__(noise_generator)
    
    def consolidate(self):        
        """Collapse all partial sums into "power of two"-sized blocks.

        This is used for the 'tree' release method. Instead of fixed-sized blocks like
        in the 'sqrt' release method, this consolidation technique will collapse sums
        into "power of two"-sized blocks. This method recursively combines equal-sized
        partial sums until there are no more.
        """
        max_psum_start = max([psum.start for psum in self.store.values()])
        self._consolidate_helper(max_psum_start)

    def _consolidate_helper(self, time):
        prev_p_sum_time = self.store[time].start - self.store[time].size
        if prev_p_sum_time in self.store:
            if self.store[time].size == self.store[prev_p_sum_time].size:
                new_size = self.store[time].size * 2
                eps = self.noise_generator.eps  # this doesn't make sense
                delta = self.noise_generator.delta  # that these hyperparams
                T = self.noise_generator.T  # are in noise generator
                right_time_bound = self.store[prev_p_sum_time].start + new_size - 1
                new_noise = self.noise_generator.laplacian(eps / np.log2(T), sens=right_time_bound)  # yet are decoupled
                self.store[prev_p_sum_time] = NoisePartialSum(
                    prev_p_sum_time, new_size, new_noise)
                del self.store[time]
                self._consolidate_helper(prev_p_sum_time)

class HybridPartialSumStore(_NoisePartialSumStore):
    def __init__(self, noise_generator=None):
        super(HybridPartialSumStore, self).__init__(noise_generator)
        self.tree_store = {}
        self.log_store = None
        self.new_noise = None

    def is_power_of_two(self, val):
        return ((val & (val - 1)) == 0) and val > 0
    
    def add(self, time, noise):
        self.new_noise = NoisePartialSum(start=time, size=1, noise=noise)
        self.consolidate()

    def consolidate(self):
        """Collapse all partial sums into one "power of two"-sized block with a tree.

        This is used for the 'hybrid' release method.
        """
        time = self.new_noise.start
        noise = self.new_noise.noise
        if time == self.START:
            self.log_store = NoisePartialSum(start=time, size=1, noise=noise)        
        elif self.is_power_of_two(time):
            new_noise = self.log_store.noise + noise
            self.log_store = NoisePartialSum(start=self.START, size=time, noise=new_noise)
            self.tree_store = {}
        else:
            self.tree_store[time] = NoisePartialSum(start=time, size=1, noise=noise)
            self._consolidate_helper(time)
        self.new_noise = None

    def _consolidate_helper(self, time):
        prev_p_sum_time = self.tree_store[time].start - self.tree_store[time].size
        if prev_p_sum_time in self.tree_store:
            if self.tree_store[time].size == self.tree_store[prev_p_sum_time].size:
                new_size = self.tree_store[time].size * 2
                eps = self.noise_generator.eps
                T = 2**int(np.log2(time))
                right_time_bound = self.tree_store[prev_p_sum_time].start + new_size - 1
                new_noise = self.noise_generator.laplacian(eps / np.log2(T), sens=right_time_bound)
                self.tree_store[prev_p_sum_time] = NoisePartialSum(
                    prev_p_sum_time, new_size, new_noise)
                del self.tree_store[time]
                self._consolidate_helper(prev_p_sum_time)

    def release(self):
        if not self.log_store:
            return np.zeros(shape=(1, 1))
        
        total_noise = np.copy(self.log_store.noise)
        for psum in self.tree_store.values():
            total_noise += psum.noise
        return total_noise