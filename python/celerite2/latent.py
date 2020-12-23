# -*- coding: utf-8 -*-

__all__ = [
    "prepare_rectangular_data",
    "LatentTerm",
    "KroneckerLatentTerm",
]
import numpy as np

from . import terms


def prepare_rectangular_data(N, M, t, **kwargs):
    results = dict(
        t=np.tile(np.asarray(t)[:, None], (1, M)).flatten(),
        X=np.tile(np.arange(M), N),
    )

    for k, v in kwargs.items():
        results[k] = np.ascontiguousarray(
            np.broadcast_to(v, (N, M)), dtype=np.float64
        ).flatten()

    return results


class LatentTerm(terms.Term):
    __requires_general_addition__ = True

    def __init__(
        self, term, *, dimension, left_latent=None, right_latent=None
    ):
        self._dimension = int(dimension)
        self.term = term
        self.left_latent = left_latent
        self.right_latent = right_latent

    @property
    def dimension(self):
        return self._dimension

    def get_psd(self, omega):
        raise NotImplementedError(
            "The PSD is not implemented for latent models"
        )

    def _get_latent(self, left_or_right, t, X):
        if left_or_right is None:
            return np.ones((1, 1, 1))
        if callable(left_or_right):
            left_or_right = left_or_right(t, X)
        else:
            left_or_right = np.atleast_1d(left_or_right)
        if left_or_right.ndim == 1:
            return left_or_right[None, None, :]
        if left_or_right.ndim == 2:
            return left_or_right[None, :, :]
        if left_or_right.ndim != 3:
            raise ValueError("Invalid shape for latent")
        return left_or_right

    def get_left_latent(self, t, X):
        return self._get_latent(self.left_latent, t, X)

    def get_right_latent(self, t, X):
        if self.right_latent is None and self.left_latent is not None:
            return self._get_latent(self.left_latent, t, X)
        return self._get_latent(self.right_latent, t, X)

    def get_celerite_matrices(
        self,
        t,
        diag,
        *,
        c=None,
        a=None,
        U=None,
        V=None,
        X=None,
    ):
        t = np.atleast_1d(t)
        diag = np.atleast_1d(diag)

        left = self.get_left_latent(t, X)
        right = self.get_right_latent(t, X)
        if left.shape != right.shape:
            raise ValueError(
                "The dimensions of the left and right latent models are "
                "incompatible"
            )

        c0, a0, U0, V0 = self.term.get_celerite_matrices(t, diag, X=X)
        U0 = U0[:, :, None]
        V0 = V0[:, :, None]

        N = t.shape[0]
        K = left.shape[2]
        J = c0.shape[0] * K
        c, a, U, V = self._resize_matrices(N, J, c, a, U, V)

        c[:] = np.repeat(c0, K)
        U[:] = np.ascontiguousarray(U0 * left).reshape((N, -1))
        V[:] = np.ascontiguousarray(V0 * right).reshape((N, -1))
        a[:] = diag + np.sum(U * V, axis=-1)

        return c, a, U, V


class KroneckerLatentTerm(LatentTerm):
    def __init__(self, term, *, K=None, L=None):
        self.K = None
        self.L = None
        if K is not None:
            if L is not None:
                raise ValueError("Only one of 'K' and 'L' can be defined")
            self.K = np.ascontiguousarray(np.atleast_2d(K), dtype=np.float64)
            super().__init__(
                term,
                dimension=self.K.shape[0],
                left_latent=self._left_latent,
                right_latent=self._right_latent,
            )

        elif L is not None:
            self.L = np.ascontiguousarray(L, dtype=np.float64)
            if self.L.ndim == 1:
                self.L = np.reshape(self.L, (-1, 1))
            super().__init__(
                term,
                dimension=self.L.shape[0],
                left_latent=self._lowrank_latent,
            )

        else:
            raise ValueError("One of 'K' and 'L' must be defined")

    def _left_latent(self, t, inds):
        return self.K[inds][:, None, :]

    def _right_latent(self, t, inds):
        N = len(t)
        latent = np.zeros((N, 1, self.K.shape[0]))
        latent[(np.arange(N), 0, inds)] = 1.0
        return latent

    def _lowrank_latent(self, t, inds):
        return self.L[inds][:, None, :]
