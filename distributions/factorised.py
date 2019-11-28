from typing import Sequence

import torch
from torch.distributions import Distribution, register_kl, kl_divergence
from torch.distributions.constraints import Constraint

from models.mixture import Mixture


def _iterate_parts(value, ndims: Sequence[int]):
    for ndim in ndims:
        yield value[..., :ndim]
        value = value[..., ndim:]


class _FactorisedSupport(Constraint):
    def __init__(self, supports: Sequence[Constraint], ndims: Sequence[int]):
        self.supports = supports
        self.ndims = ndims

    def check(self, value):
        return all(support.check(part)
                   for support, part in zip(self.supports, _iterate_parts(value, self.ndims)))


class Factorised(Distribution):
    arg_constraints = {}

    def __init__(self, factors: Sequence[Distribution], validate_args=None):
        self.factors = factors
        batch_shape = factors[0].batch_shape
        event_shape = torch.Size([sum(factor.event_shape[0] for factor in self.factors)])
        self._ndims = [factor.event_shape[0] if len(factor.event_shape) > 0 else 1
                       for factor in self.factors]
        super().__init__(batch_shape, event_shape, validate_args)

    @property
    def has_rsample(self):
        return any(factor.has_rsample for factor in self.factors)

    @property
    def support(self):
        return _FactorisedSupport([factor.support for factor in self.factors], self._ndims)

    def rsample(self, sample_shape=torch.Size()):
        return torch.cat([factor.rsample(sample_shape) for factor in self.factors], dim=-1)

    def marginal(self, factor_indices: Sequence[int]) -> 'Factorised':
        return Factorised([self.factors[i] for i in factor_indices],
                          validate_args=self._validate_args)

    def log_prob(self, value):
        return sum(factor.log_prob(part)
                   for factor, part in zip(self.factors, self.partition_dimensions(value)))

    def entropy(self):
        return sum(factor.entropy() for factor in self.factors)

    def partition_dimensions(self, data):
        return _iterate_parts(data, self._ndims)

    @property
    def mean(self):
        return torch.cat([factor.mean for factor in self.factors], dim=-1)

    @property
    def variance(self):
        return sum(factor.variance for factor in self.factors)


@register_kl(Factorised, Factorised)
def _kl_factorised_factorised(p: Factorised, q: Factorised):
    return sum(kl_divergence(p_factor, q_factor)
               for p_factor, q_factor in zip(p.factors, q.factors))


# class FactorisedMixture(Mixture[Factorised]):
#     def posterior(self, potentials: Factorised) -> 'FactorisedMixture':
#         post_factors = [factor for factor in self.components.factors]
#         post_components =
#         post_logits = self.mixing.logits


if __name__ == '__main__':
    import torch.distributions as td

    B, D1, D2 = 5, 3, 4
    N = 1000

    dist1 = td.MultivariateNormal(torch.zeros(D1), torch.eye(D1)).expand((B,))
    dist2 = td.Dirichlet(torch.ones(D2)).expand((B,))
    print(dist1.batch_shape, dist1.event_shape)
    print(dist2.batch_shape, dist2.event_shape)
    fact = Factorised([dist1, dist2])
    print(fact.batch_shape, fact.event_shape)
    samples = fact.rsample((N,))
    print(samples[0])
    print(samples.shape)
    logp = fact.log_prob(samples)
    print(logp.shape)
    entropy = fact.entropy()
    print(entropy.shape)
    print(entropy, -logp.mean())
    print()

    print(td.kl_divergence(fact, fact))
    mixture = Mixture(torch.ones(B), fact)
    samples = mixture.rsample((N,))
    logp = mixture.log_prob(samples)
    print(samples.shape)
    print(logp.shape)