"""Treasury allocation — pins the constants this validator actually ships.

Every other treasury test patches SUBNET_TREASURY_PERCENTAGE/UID, so none of
them notice a change to the deployed values. Both are consensus-critical: they
change the emitted weight vector, so a validator running different numbers
disagrees with the network.
"""

import numpy as np

from bitcast.validator.rewards_scaling import allocate_subnet_treasury
from bitcast.validator.utils import config


BURN_UID = 0


def test_shipped_constants():
    assert config.SUBNET_TREASURY_UID == 155
    assert config.SUBNET_TREASURY_PERCENTAGE == 1.0


def test_full_residual_diverted_off_burn_uid():
    uids = [BURN_UID, 7, config.SUBNET_TREASURY_UID]
    rewards = np.array([0.97, 0.03, 0.0])

    final = allocate_subnet_treasury(rewards, uids)

    assert final[0] == 0.0
    assert final[1] == 0.03
    assert final[2] == 0.97
    assert final.sum() == 1.0


def test_allocation_capped_by_what_burn_uid_holds():
    """Miners earning most of the emission leaves little to divert."""
    uids = [BURN_UID, 7, config.SUBNET_TREASURY_UID]
    rewards = np.array([0.1, 0.9, 0.0])

    final = allocate_subnet_treasury(rewards, uids)

    assert final[0] == 0.0
    assert final[2] == 0.1
    assert final.sum() == 1.0


def test_missing_treasury_uid_leaves_rewards_untouched():
    """A deregistered treasury UID must not strand or duplicate emission."""
    uids = [BURN_UID, 7]
    rewards = np.array([0.97, 0.03])

    final = allocate_subnet_treasury(rewards, uids)

    assert np.allclose(final, rewards)
