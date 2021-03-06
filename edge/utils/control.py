import numpy as np
import scipy

# LQR controller solver adapted from
# http://www.mwm.im/lqr-controllers-with-python/


def dlqr(A, B, Q, R):
    """Solve the discrete time lqr controller.
    x[k+1] = A x[k] + B u[k]
    cost = sum x[k].T*Q*x[k] + u[k].T*R*u[k]
    """
    # ref Bertsekas, p.151
    R = np.atleast_2d(R)
    # first, try to solve the ricatti equation
    X = np.array(scipy.linalg.solve_discrete_are(A, B, Q, R))
    # compute the LQR gain
    K = np.array(scipy.linalg.inv(B.T @ X @ B + R) @ (B.T @ X @ A))
    eigVals, eigVecs = scipy.linalg.eig(A - B @ K)
    return K, X, eigVals


def lqr(A, B, Q, R):
    """Solve the continuous time lqr controller.
    dx/dt = A x + B u
    cost = integral x.T*Q*x + u.T*R*u
    """
    # ref Bertsekas, p.151
    R = np.atleast_2d(R)
    # first, try to solve the ricatti equation
    X = np.array(scipy.linalg.solve_continuous_are(A, B, Q, R))
    # compute the LQR gain
    K = np.array(scipy.linalg.inv(R) @ (B.T @ X))
    eigVals, eigVecs = scipy.linalg.eig(A - B @ K)

    return K, X, eigVals