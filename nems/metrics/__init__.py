"""Collection of performance metrics and related utilities.

Score model outputs by MSE, likelihood, prediction correlation, etc.
Measure equivalence, sparsity, and other properties of model predictions and/or
recorded neural responses. These can also be used as cost functions for the
default SciPy backend.

# TODO: These contents don't all exist yet, sketching this out based on
#       the strfy proposal document.
Contents
--------
    `mse.py`         : Compute mean squared error between prediction and target.
    `correlation.py` : As above, but compute Pearson correlation coefficient.
    `equivalence.py` : Measure functional similarity of different models.
    `sparseness.py`  : Measure lifetime sparseness of responses and predictions.

"""

from .mse import mse, nmse
from .correlation import correlation, noise_corrected_r


# TODO: This should move to scipy backend, keep model assessment at top level.

metric_nicknames = {'corr': correlation, 'r_ceiling': noise_corrected_r}
def get_metric(name):
    if name in metric_nicknames:
        metric = metric_nicknames[name]
    else:
        metric = globals().get(name, None)
    if metric is None:
        raise TypeError(f"Metric name '{name}' could not be found.")

    return metric
