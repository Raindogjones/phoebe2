"""
Fitting using lmfit
========================

Last updated: ***time***

This example shows how to use fitting routines - on fake data, so we know the answer

Initialisation
--------------

"""
# First we'll import phoebe and create a logger

import phoebe
import numpy as np
import matplotlib.pyplot as plt
logger = phoebe.get_basic_logger()

# Create the fake data
# ---------------------

b = phoebe.Bundle()
b.lc_fromarrays(phase=np.linspace(0,1,100),dataref='fakedata')

'''
Now that we've created some fake data, let's change some parameters and see if we can recover them by fitting them later!
'''

b['incl']=87.9
b['teff@primary'] = 6543
b['pot@primary'] = 5.123

b.run_compute('preview')
b.plot_syn('fakedata')
plt.show()

np.savetxt('fakedata.lc', np.array([b['value@time@lcsyn'], b['value@flux@lcsyn']]).T )

'''
Loading the fake data as "observations"
-----------------------------------------

Now we'll create a new bundle and load these synethetic data as if they were observations
'''

b = phoebe.Bundle()
b.lc_fromfile('fakedata.lc', columns=['time','flux'], dataref='fakedata')

'''
By default all datasets that you have loaded will be used for fitting. 
If you wanted, you could disable any by label using b.disable_lc('fakedata') or b.disable_rv('fakervdata') if you have an rv dataset loaded.

Setup Fitting
----------------

Now we need to choose our parameters to fit and setup their priors.
PHOEBE 2 currently supports uniform and normal distributions.
'''
# inclination (87.9)

b.set_prior('incl', distribution='uniform', lower=80, upper=90)
b.set_adjust('incl')

# teff@primary (6543)

b.set_prior('teff@primary', distribution='uniform', lower=5000, upper=7000)
b.set_adjust('teff@primary')

# pot@primary (5.123)

b.set_prior('pot@primary', distribution='uniform', lower=4.0, upper=8.0)
b.set_adjust('pot@primary')

# For third light, we'll just allow the synthetics to scale and offset.
# These don't need priors, but do need to be set to be adjusted

'''
When modeling, PHOEBE uses the parameter pblum, or the passband luminosity, to scale the model to the observations. Additionally, 
you can set the parameter l3 to be adjusted to account for the presence of third light contaminating your system. 
'''

b.set_adjust('pblum@primary@lcdep')
b.set_adjust('pblum@secondary@lcdep')

'''
 Run Fitting
 ----------------
'''

b.run_fitting('lmfit', computelabel='preview', accept_feedback=True)

# Note that after only one iteration the values are not perfectly recovered.

print("incl (87.9): {}".format(b['value@incl']))
print("teff@primary (6543) {}".format(b['value@teff@primary']))
print("pot@primary (5.123) {}".format(b['value@pot@primary']))

'''
Plotting
------------

Let's compare the original synthetic data to the fitted model
'''

plt.subplot(211)
b.plot_obs('fakedata')
b.plot_syn('fakedata')
plt.subplot(212)
plt.plot(b['value@time@lcsyn'],b['value@flux@lcobs']-b['value@flux@lcsyn'])
plt.show()
