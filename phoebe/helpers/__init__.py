import numpy as np
from copy import deepcopy as _deepcopy
from scipy.special import erfinv as _erfinv
from scipy.stats import norm as _norm

from phoebe import u

try:
    import dynesty as _dynesty
except ImportError:
    _use_dynesty = False
else:
    _use_dynesty = True

try:
    import emcee
except ImportError:
    _use_emcee = False
else:
    _use_emcee = True

_skip_filter_checks = {'check_default': False, 'check_visible': False}

def process_mcmc_chains_from_solution(b, solution, burnin=None, thin=None, lnprob_cutoff=None, adopt_parameters=None, flatten=True):
    """
    Process the full MCMC chain and expose the `lnprobabilities` and `samples`
    after applying `burnin`, `thin`, `lnprob_cutoff`.

    See also:
    * <phoebe.helpers.process_mcmc_chains>
    * <phoebe.parameters.solver.sampler.emcee>

    Arguments
    ---------------
    * `b` (<phoebe.frontend.bundle.Bundle>): the Bundle
    * `solution` (string): solution label
    * `burnin` (int, optional, default=None): If not None, will override
        the value in the solution.
    * `thin` (int, optional, default=None): If not None, will override
        the value in the solution.
    * `lnprob_cutoff` (float, optional, default=None): If not None, will override
        the value in the solution.
    * `adopt_parameters` (list, optional, default=None): If not None, will
        override the value in the solution.
    * `flatten` (bool, optional, default=True): whether to flatten to remove
        the "walkers" dimension.  If False, `lnprob_cutoff` will replace entries
        with nans rather than excluding them.

    Returns
    -----------
    * (array, array): `lnprobablities` (flattened to 1D if `flatten`) and `samples`
        (flattened to 2D if `flatten`) after processing
    """
    solution_ps = b.get_solution(solution=solution, **_skip_filter_checks)
    adopt_inds, adopt_uniqueids = b._get_adopt_inds_uniqueids(solution_ps, adopt_parameters=adopt_parameters)

    return process_mcmc_chains(solution_ps.get_value(qualifier='lnprobabilities', **_skip_filter_checks),
                               solution_ps.get_value(qualifier='samples', **_skip_filter_checks),
                               solution_ps.get_value(qualifier='burnin', burnin=burnin, **_skip_filter_checks),
                               solution_ps.get_value(qualifier='thin', thin=thin, **_skip_filter_checks),
                               solution_ps.get_value(qualifier='lnprob_cutoff', lnprob_cutoff=lnprob_cutoff, **_skip_filter_checks),
                               adopt_inds=adopt_inds, flatten=flatten)

def process_mcmc_chains(lnprobabilities, samples, burnin=0, thin=1, lnprob_cutoff=-np.inf, adopt_inds=None, flatten=True):
    """
    Process the full MCMC chain and expose the `lnprobabilities` and `samples`
    after applying `burnin`, `thin`, `lnprob_cutoff`.

    See also:
    * <phoebe.helpers.process_mcmc_chains_from_solution>

    Arguments
    -------------
    * `lnprobabilities` (array): array of all lnprobabilites as returned by MCMC.
        Should have shape: (`niters`, `nwalkers`).
    * `samples` (array): array of all samples from the chains as returned by MCMC.
        Should have shape: (`niters`, `nwalkers`, `nparams`).
    * `burnin` (int, optional, default=0): number of iterations to exclude from
        the beginning of the chains.  Must be between `0` and `niters`.
    * `thin` (int, optional, default=1): after applying `burnin`, take every
        `thin` iterations.  Must be between `1` and (`niters`-`burnin`)
    * `lnprob_cutoff` (float, optiona, default=-inf): after applying `burnin`
        and `thin`, reject any entries (in both `lnprobabilities` and `samples`)
        in which `lnprobabilities` is below `lnprob_cutoff`.
    * `adopt_inds` (list, optional, default=None): if not None, only expose
        the parameters in `samples` with `adopt_inds` indices.  Each entry
        in the list should be between `0` and `nparams`.
    * `flatten` (bool, optional, default=True): whether to flatten to remove
        the "walkers" dimension.  If False, `lnprob_cutoff` will replace entries
        with nans rather than excluding them.

    Returns
    -----------
    * (array, array): `lnprobablities` (flattened to 1D if `flatten`) and `samples`
        (flattened to 2D if `flatten`) after processing

    Raises
    ------------
    * TypeError: if `burnin` or `thin` are not integers
    * ValueError: if `lnprobabilities` or `samples` have the wrong shape
    * ValueError: if `burnin`, `thin`, or `adopt_inds` are not valid given
        the shapes of `lnprobabilities` and `samples`.
    """
    if not isinstance(burnin, int):
        raise TypeError("burnin must be of type int")
    if not isinstance(thin, int):
        raise TypeError("thin must be of type int")

    if len(lnprobabilities.shape) != 2:
        raise ValueError("lnprobablities must have shape (niters, nwalkers), not {}".format(lnprobabilities.shape))
    if len(samples.shape) != 3:
        raise ValueError("samples must have shape (niters, nwalkers, nparams), not {}".format(samples.shape))

    if lnprobabilities.shape[0] != samples.shape[0] or lnprobabilities.shape[1] != samples.shape[1]:
        raise ValueError("lnprobablities and samples must have same size for first 2 dimensions lnprobabilities.shape=(niters, nwalkers), samples.shape=(niters, nwalkers, nparams)")

    niters, nwalkers, nparams = samples.shape

    if adopt_inds is not None:
        if not isinstance(adopt_inds, list):
            raise TypeError("adopt_inds must be of type list or None")
        if not np.all([ai < nparams and ai >=0 for ai in adopt_inds]):
            raise ValueError("each item in adopt_inds must be between 0 and {}".format(nparams))

    if burnin < 0:
        raise ValueError("burnin must be >=0")
    if burnin >= niters:
        raise ValueError("burnin must be < {}".format(niters))
    if thin < 1:
        raise ValueError("thin must be >= 1")
    if thin >= niters-burnin:
        raise ValueError("thin must be < {}".format(niters-burnin))


    # lnprobabilities[iteration, walker]
    lnprobabilities = lnprobabilities[burnin:, :][::thin, :]
    # samples[iteration, walker, parameter]
    samples = samples[burnin:, :, :][::thin, : :]
    if adopt_inds is not None:
        samples = samples[:, :, adopt_inds]

    if flatten:
        lnprob_inds = np.where(lnprobabilities > lnprob_cutoff)
        samples = samples[lnprob_inds]
        lnprobabilities = lnprobabilities[lnprob_inds]
        # samples 2D (n, nparameters)
        # lnprobabilities 1D (n)
    else:
        lnprobabilities = _deepcopy(lnprobabilities)
        samples = _deepcopy(samples)

        samples[lnprobabilities < lnprob_cutoff] = np.nan
        lnprobabilities[lnprobabilities < lnprob_cutoff] = np.nan

        # lnprobabilities 2D (niters (after burnin, thin), nwalkers), replaced with nans where lnprob_cutoff applies
        # samples 3D (niters (after burning,thin), nwalkers, nparameters)

    return lnprobabilities, samples

def acf(ts, nlags=0, submean=False, normed=True):
    """
    Compute the autocorrelation function of any input array.

    See also:
    * <phoebe.helpers.process_acf>
    * <phoebe.helpers.process_acf_from_solution>

    Arguments
    ------------
    * `ts`
    * `nlags`
    * `submean`
    * `normed`

    Returns
    -----------
    * (array): autocorrelation function
    """
    nlags = len(ts) if nlags==0 else nlags
    c0 = np.sum((ts-ts.mean())**2)/len(ts) if normed else 1.0
    if submean:
        acf = np.array([np.sum((ts[k:]-ts[k:].mean())*(ts[:len(ts)-k]-ts[:len(ts)-k].mean()))/c0/len(ts) for k in range(nlags)])
    else:
        acf = np.array([np.sum((ts[k:]-ts.mean())*(ts[:len(ts)-k]-ts.mean()))/c0/len(ts) for k in range(nlags)])

    return acf

def acf_ci(lents, p=0.05):
    return np.sqrt(2)*_erfinv(1-p)/np.sqrt(lents)

def acf_ci_bartlett(lents, acf, p=0.05):
    vacf = np.ones_like(acf)/lents
    vacf[0] = 0
    vacf[1] = 1/lents
    vacf[2:] *= 1+2*np.cumsum(acf[1:-1]**2)
    return _norm.ppf(1-p/2) * np.sqrt(vacf)


def process_acf(lnprobabilities, samples, nlags=0):
    """
    Compute the autocorrelation function from input lnprobabilities and samples.

    To apply burnin, call <phoebe.helpers.process_mcmc_chains> first or use
    <phoebe.helpers.process_acf_from_solution> instead.

    See also:
    * <phoebe.helpers.process_acf_from_solution>
    * <phoebe.helpers.acf>
    * <phoebe.helpers.acf_ci_bartlett>
    * <phoebe.helpers.acf_ci>

    Arguments
    ---------------
    * `lnprobabilities` (array): array of all lnprobabilites as returned by MCMC.
        Should have shape: (`niters`, `nwalkers`).
    * `samples` (array): array of all samples from the chains as returned by MCMC.
        Should have shape: (`niters`, `nwalkers`, `nparams`).
    * `nlags` (int, optional, default=0): number of lags to use.  Passed
        directly to <phoebe.helpers.acf>.  If 0, will default to the number
        of iterations in `lnprobabilities` and `samples`.

    Returns
    ---------------
    * (list of arrays, list of arrays, float): output from <phoebe.helpers.acf>
        for `lnprobabilities` and each parameter in `samples`, output from
        <phoebe.helpers.acf_ci_bartlett> for `lnprobabilities_proc` and each
        parameter in `samples`, output from <phoebe.helpers.acf_ci>.
    """
    niters, nwalkers, nparams = samples.shape

    if nlags > niters:
        raise ValueError("nlags must be <= number of remaining iterations (after burnin)")
    if nlags == 1:
        raise ValueError("nlags must be > 1")

    acfs = [np.array([acf(lnprobabilities[:,iwalker], nlags=nlags) for iwalker in range(nwalkers)])]

    for iparam in range(nparams):
        acfs.append(np.array([acf(samples[:,iwalker,iparam], nlags=nlags) for iwalker in range(nwalkers)]))

    ci_bartletts = [np.array([acf_ci_bartlett(niters, acfs[iparam][iwalker]) for iwalker in range(nwalkers)]) for iparam in range(len(acfs))]

    # acfs list with length nparams+1 of arrays vs lag
    # ci_bartletts with length nparams+1 of arrays vs lag
    # acf_ci float
    return acfs, ci_bartletts, acf_ci(niters)

def process_acf_from_solution(b, solution, nlags=None, burnin=None, lnprob_cutoff=None, adopt_parameters=None):
    """
    Compute the autocorrelation function from an emcee solution.

    See also:
    * <phoebe.helpers.process_acf>
    * <phoebe.helpers.acf>
    * <phoebe.helpers.acf_ci_bartlett>
    * <phoebe.helpers.acf_ci>

    Arguments
    --------------
    * `b` (<phoebe.frontend.bundle.Bundle>): the Bundle
    * `solution` (string): solution label
    * `nlags` (int, optional, default=None): If not None, will override the
        value in the solution.
    * `burnin` (int, optional, default=None): If not None, will override
        the value in the solution.
    * `lnprob_cutoff` (float, optional, default=None): If not None, will override
        the value in the solution.
    * `adopt_parameters` (list, optional, default=None): If not None, will
        override the value in the solution.

    Returns
    ------------
    * (dictionary, dictionary, float) dictionary with keys being the parameter twigs
        (or 'lnprobabilities') and values being the output of <phoebe.helpers.acf>
        (array with shape (nwalkers, nlags)), dictionary with keys being the
        parameter twigs (or 'lnprobabilities') and values being the output
        of <phoebe.helpers.acf_ci_bartlett>, and float being the
        confidence intervale from <phoebe.helpers.acf_ci>.
    """
    solution_ps = b.get_solution(solution=solution, **_skip_filter_checks)
    if solution_ps.kind != 'emcee':
        raise TypeError("solution does not point to an emcee solution")

    lnprobabilities, samples = process_mcmc_chains_from_solution(b,
                                                                 solution,
                                                                 burnin=burnin,
                                                                 thin=1,
                                                                 lnprob_cutoff=lnprob_cutoff,
                                                                 adopt_parameters=adopt_parameters,
                                                                 flatten=False)


    nlags = solution_ps.get_value(qualifier='nlags', nlags=nlags, **_skip_filter_checks)

    acfs, acf_bartletts, acf_ci = process_acf(lnprobabilities, samples, nlags)

    if adopt_parameters is None:
        adopt_parameters = solution_ps.get_value(qualifier='fitted_twigs', **_skip_filter_checks)

    keys = ['lnprobabilities'] + list(adopt_parameters)
    if len(keys) != len(acfs):
        # TODO: if adopt_parameters has a wildcard, we may instead want to get the indices and manually retrieve the matching twigs/uniqueids
        raise ValueError("adopt_parameters length does not match returned length of samples")

    acf_dict = {k: acf for k,acf in zip(keys, acfs)}
    acf_bartletts = {k: acf_bartlett for k,acf_bartlett in zip(keys, acf_bartletts)}
    return acf_dict, acf_bartletts, acf_ci


def get_emcee_object_from_solution(b, solution, adopt_parameters=None):
    """
    Expose the `EnsembleSampler` object in `emcee` from the solution <phoebe.parameters.ParameterSet>.

    See also:
    * <phoebe.helpers.get_emcee_object>
    * <phoebe.parameters.solver.sampler.emcee>

    Arguments
    ------------
    * `b` (<phoebe.frontend.bundle.Bundle>): the Bundle
    * `solution` (string): solution label with `kind=='dynesty'`
    * `adopt_parameters` (list, optional, default=None): If not None, will
        override the value of `adopt_parameters` in the solution.

    Returns
    -----------
    * [emcee.EnsembleSampler](https://emcee.readthedocs.io/en/stable/user/sampler/#emcee.EnsembleSampler) object
    """
    solution_ps = b.get_solution(solution=solution, **_skip_filter_checks)
    if solution_ps.kind != 'emcee':
        raise ValueError("solution_ps must have kind 'emcee'")

    adopt_inds, adopt_uniqueids = b._get_adopt_inds_uniqueids(solution_ps, adopt_parameters=adopt_parameters)

    samples = solution_ps.get_value(qualifier='samples', **_skip_filter_checks) # shape: (niters, nwalkers, nparams)
    lnprobabilites = solution_ps.get_value(qualifier='lnprobabilities', **_skip_filter_checks) # shape: (niters, nwalkers)
    acceptance_fractions = solution_ps.get_value(qualifier='acceptance_fractions', **_skip_filter_checks) # shape: (nwalkers)

    return get_emcee_object(samples[:,:,adopt_inds], lnprobabilites, acceptance_fractions)

def get_emcee_object(samples, lnprobabilities, acceptance_fractions):
    """
    Expose the `EnsembleSampler` object in `emcee`.

    See also:
    * <phoebe.helpers.get_emcee_object_from_solution>

    Arguments
    ------------
    * `samples` (array): samples with shape (niters, nwalkers, nparams)
    * `lnprobabilities` (array): log-probablities with shape (niters, nwalkers)
    * `acceptance_fractions` (array): acceptance fractions with shape (nwalkers)

    Returns
    -----------
    * [emcee.EnsembleSampler](https://emcee.readthedocs.io/en/stable/user/sampler/#emcee.EnsembleSampler) object
    """
    if not _use_emcee:
        raise ImportError("emcee is not installed")

    backend = emcee.backends.Backend()
    backend.nwalkers = samples.shape[1]
    backend.ndim = samples.shape[2]
    backend.iteration = samples.shape[0]
    backend.accepted = acceptance_fractions
    backend.chain = samples
    backend.log_prob = lnprobabilities
    backend.initialized = True
    backend.random_state = None
    if not hasattr(backend, 'blobs'):
        # some versions of emcee seem to have a bug where it tries
        # to access backend.blobs but that does not exist.  Since
        # we don't use blobs, we'll get around that by faking it to
        # be None
        backend.blobs = None

    return backend


def get_dynesty_object_from_solution(b, solution, adopt_parameters=None):
    """
    Expose the `results` object in `dynesty` from the solution <phoebe.parameters.ParameterSet>.

    See also:
    * <phoebe.helpers.get_dynesty_object>
    * <phoebe.parameters.solver.sampler.dynesty>

    Arguments
    ------------
    * `b` (<phoebe.frontend.bundle.Bundle>): the Bundle
    * `solution` (string): solution label with `kind=='dynesty'`
    * `adopt_parameters` (list, optional, default=None): If not None, will
        override the value of `adopt_parameters` in the solution.

    Returns
    -----------
    * [dynesty.results.Results](https://dynesty.readthedocs.io/en/latest/api.html#module-dynesty.results) object
    """
    solution_ps = b.get_solution(solution=solution, **_skip_filter_checks)
    if solution_ps.kind != 'dynesty':
        raise ValueError("solution_ps must have kind 'dynesty'")

    adopt_inds, adopt_uniqueids = b._get_adopt_inds_uniqueids(solution_ps, adopt_parameters=adopt_parameters)

    return get_dynesty_object(adopt_inds=adopt_inds, **{p.qualifier: p.get_value() for p in solution_ps.to_list() if p.qualifier in ['nlive', 'niter', 'ncall', 'eff', 'samples', 'samples_id', 'samples_it', 'samples_u', 'logwt', 'logl', 'logvol', 'logz', 'logzerr', 'information', 'bound_iter', 'samples_bound', 'scale']})

def get_dynesty_object(nlive, niter, ncall, eff,
                       samples, samples_id, samples_it, samples_u,
                       logwt, logl, logvol, logz, logzerr,
                       information, bound_iter,
                       samples_bound, scale,
                       adopt_inds=None):
    """
    Expose the `results` object in `dynesty`.

    This can then be passed to any [dynesty helper function](https://dynesty.readthedocs.io/en/latest/api.html#module-dynesty.results)
    that takes `results`.

    See also:
    * <phoebe.helpers.get_dynesty_object_from_solution>

    Arguments
    ------------
    * positional arguments: all positional arguments are passed directly to dynesty.
    * `adopt_inds` (list, optional, default=None): If not None, only include
        the parameters with `adopt_inds` indices from `samples` and `samples_u`.

    """
    if not _use_dynesty:
        raise ImportError("dynesty is not installed")

    def _filter_by_adopt_inds(p, adopt_inds):
        if adopt_inds is not None and p.qualifier in ['samples', 'samples_u']:
            return p.value[:, adopt_inds]
        return p.value

    return _dynesty.results.Results(nlive=nlive, niter=niter, ncall=ncall, eff=eff,
                                    samples=samples, samples_id=samples_id,
                                    samples_it=samples_it, samples_u=samples_u,
                                    logwt=logwt, logl=logl, logvol=logvol, logz=logz, logzerr=logzerr,
                                    information=information, bound_iter=bound_iter,
                                    samples_bound=samples_bound, scale=scale)

def get_unit_in_system(original_unit, system):
    """
    Convert a unit into a given system (either 'si' or 'solar')

    Arguments
    -----------------
    * `original_unit` (astropy unit object or string): the original unit
    * `system` (string): whether to convert to 'si' or 'solar' units

    Returns
    -----------------
    * unit
    """
    if isinstance(original_unit, str):
        original_unit = u.Unit(original_unit)

    if system.lower() == 'si':
        if u._get_physical_type(original_unit) not in u._physical_types_to_si.keys():
            raise ValueError("cannot convert {} to {}".format(original_unit, system))
        return u.Unit(u._physical_types_to_si.get(u._get_physical_type(original_unit)))
    elif system.lower() == 'solar':
        if u._get_physical_type(original_unit) not in u._physical_types_to_solar.keys():
            raise ValueError("cannot convert {} to {}".format(original_unit, system))
        return u._physical_types_to_solar.get(u._get_physical_type(original_unit))
    else:
        raise NotImplementedError("system must be 'si' or 'solar'")
