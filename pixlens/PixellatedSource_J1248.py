import numpy,pyfits,pylab
import indexTricks as iT
from pylens import MassModels,pylens,adaptTools as aT,pixellatedTools as pT
from imageSim import SBModels,convolve
from scipy.sparse import diags
import pymc,cPickle
from scipy import optimize
import myEmcee_blobs as myEmcee #updateEmcee as myEmcee
import numpy as np, pylab as pl, pyfits as py
from pylens import lensModel
from scipy.interpolate import RectBivariateSpline
import adaptToolsBug as BB
from linslens.pixplot import *

#img1 = py.open('/data/ljo31/Lens/J1248/galsub_0.fits')[0].data.copy()[35:-40,30:-25]
#sig1 = py.open('/data/ljo31/Lens/J1248/F555W_noisemap.fits')[0].data.copy()[10:-10,20:-25][35:-40,30:-25]
#psf1 = py.open('/data/ljo31/Lens/J1248/F555W_psf1.fits')[0].data.copy()
#psf1 = psf1/np.sum(psf1)
img1 = py.open('/data/ljo31/Lens/J1248/galsub_1.fits')[0].data.copy()[35:-40,30:-25]
sig1 = py.open('/data/ljo31/Lens/J1248/F814W_noisemap.fits')[0].data.copy()[10:-10,20:-25][35:-40,30:-25]
psf1 = py.open('/data/ljo31/Lens/J1248/F814W_psf1.fits')[0].data.copy()
psf1 = psf1/np.sum(psf1)

Dx,Dy=10.,0
Dx,Dy = Dx+30.,Dy+35.

result = np.load('/data/ljo31/Lens/J1248/pixsrc_2_ctd_new')
lp,trace,dic,_= result
a1,a2 = numpy.unravel_index(lp[:,0].argmax(),lp[:,0].shape)

X = pymc.Uniform('Lens 1 x',58.7,68.7,value=dic['Lens 1 x'][a1,0,a2])
Y = pymc.Uniform('Lens 1 y',53.1,63.1,value=dic['Lens 1 y'][a1,0,a2])
B = pymc.Uniform('Lens 1 b',0.5,100.,value=dic['Lens 1 b'][a1,0,a2])
Q = pymc.Uniform('Lens 1 q',0.1,1.0,value=dic['Lens 1 q'][a1,0,a2])
ETA = pymc.Uniform('Lens 1 eta',0.5,2.5,value=dic['Lens 1 eta'][a1,0,a2])
PA = pymc.Uniform('Lens 1 pa',0,180.,value=dic['Lens 1 pa'][a1,0,a2])

SH = pymc.Uniform('extShear',0.05,0.07,value=dic['extShear'][a1,0,a2])
SHPA = pymc.Uniform('extShear PA',-70.,-30,value=dic['extShear PA'][a1,0,a2])
# try to avoid degeneracy??
lens1 = MassModels.PowerLaw('Lens 1',{'x':X,'y':Y,'b':B,'eta':ETA,'q':Q,'pa':PA})
shear = MassModels.ExtShear('shear',{'x':X,'y':Y,'b':SH,'pa':SHPA})
lenses = [lens1,shear]
pars = [X,Y,B,Q,ETA,PA,SH,SHPA]
cov = [0.1,0.1,0.1,0.1,0.1,1.,0.05,10.]

# and a mask
mask = py.open('/data/ljo31/Lens/J1248/mask100.fits')[0].data.copy()[35:-40,30:-25]
mask = mask==1
Npnts = 2  # Defines `fineness' of source reconstruction (bigger is coarser)

# Setup data for adaptive source modelling
img,sig,psf = img1, sig1,psf1
y,x = iT.coords(img.shape)
x=x+Dx
y=y+Dy
#x,y=x+dx,y+dy
cpsf = convolve.convolve(img,psf)[1]
ifltm = img[mask]
sfltm = sig[mask]
vfltm = sfltm**2
cmatm = diags(1./sfltm,0)
xm = x[mask]
ym = y[mask]
coords = [xm,ym]

PSF = pT.getPSFMatrix(psf,img.shape)
PSFm = pT.maskPSFMatrix(PSF,mask)

iflt = img.flatten()
sflt = sig.flatten()
vflt = sflt**2

xflt = x.flatten()
yflt = y.flatten()
 
src = aT.AdaptiveSource(ifltm/sfltm,ifltm.size/Npnts)

xl,yl = pylens.getDeflections(lenses,coords)
src.update(xl,yl)
# casting source pixels back and regularising
osrc = showRes(xl,yl,src,PSFm,img,sig,mask,ifltm,vfltm,cmatm,1.,0,100)
pylab.show()

reg=4.
previousResult = None

import time
def doFit(p=None,doReg=True,updateReg=True,checkImgs=True,levMar=False):
    global reg
    # Check if using levMar-style parameters
    if p is not None:
        for i in range(len(p)):
            pars[i].value = p[i]
            # If the parameter is out-of-bounds return a bad fit
            try:
                a = pars[i].logp
            except:
                return iflt/sflt

    for l in lenses:
        l.setPars()
    xl,yl = pylens.getDeflections(lenses,coords)

    src.update(xl,yl,doReg=doReg)
    lmat = PSFm*src.lmat
    if doReg==True:
        rmat = src.rmat
    else:
        rmat = None
    nupdate = 0
    if doReg==True and updateReg==True:
        nupdate = 10
    res,fit,model,_,regg = aT.getModelG(ifltm,vfltm,lmat,cmatm,rmat,reg,nupdate)
    reg = regg[0]
    if checkImgs is False:
        if levMar:
            res = res**0.5+ifltm*0.
        return -0.5*res
    # This checks is images are formed outside of the masked region
    xl,yl = pylens.getDeflections(lenses,[xflt,yflt])
    oimg,pix = src.eval(xl,yl,fit,domask=False)
    oimg = PSF*oimg
    res = (iflt-oimg)/sflt
    if levMar:
        return res
    return -0.5*(res**2).sum()


@pymc.observed
def likelihood(value=0.,tmp=pars):
    return doFit(None,True,False,True,False)

cov = numpy.array(cov)
if previousResult is not None:
    result = numpy.load(previousResult)
    lp = result[0]
    trace = numpy.array(result[1])
    a1,a2 = numpy.unravel_index(lp.argmax(),lp.shape)
    for i in range(len(pars)):
        pars[i].value = trace[a1,a2,i]
    ns,nw,np = trace.shape
    cov = numpy.cov(trace[ns/2:].reshape((ns*nw/2,np)).T)

print 'about to do doFit - i.e. get the regularisation for the current model'

doFit(None,True,False,False)
doFit(None,True,False,False)
print 'done doFit'

xl,yl = pylens.getDeflections(lenses,coords)
src.update(xl,yl)

osrc = showRes(xl,yl,src,PSFm,img,sig,mask,ifltm,vfltm,cmatm,reg,10,400)
pylab.show()
reg=4.
S = myEmcee.PTEmcee(pars+[likelihood],cov=cov,nthreads=24,nwalkers=100,ntemps=3)
S.sample(500)

print 'done emcee'
outFile = '/data/ljo31/Lens/J1248/pixsrc_2_ctd_new_Iband_2'

f = open(outFile,'wb')
cPickle.dump(S.result(),f,2)
f.close()

print 'cPickled!'

result = S.result()
lp,trace,dic,_ = result
a1,a2 = numpy.unravel_index(lp[:,0].argmax(),lp[:,0].shape)
for i in range(len(pars)):
    pars[i].value = trace[a1,0,a2,i]
    print "%18s  %8.3f"%(pars[i].__name__,pars[i].value)

print reg
doFit(None,True,False,False)
doFit(None,True,False,False)
print reg
xl,yl = pylens.getDeflections(lenses,coords)
src.update(xl,yl)
osrc = showRes(xl,yl,src,PSFm,img,sig,mask,ifltm,vfltm,cmatm,reg,0,400)
pylab.savefig('J1248_ONE.png')
reg=4.
print reg
jj=0
for jj in range(12):
    S.p0 = trace[-1]
    print 'sampling'
    S.sample(1000)

    f = open(outFile,'wb')
    cPickle.dump(S.result(),f,2)
    f.close()

    result = S.result()
    lp = result[0]

    trace = numpy.array(result[1])
    a1,a2 = numpy.unravel_index(lp[:,0].argmax(),lp[:,0].shape)
    for i in range(len(pars)):
        pars[i].value = trace[a1,0,a2,i]
    print jj
    jj+=1
    doFit(None,True,False,False)
    doFit(None,True,False,False)
    print reg
    xl,yl = pylens.getDeflections(lenses,coords)
    src.update(xl,yl)
    osrc = showRes(xl,yl,src,PSFm,img,sig,mask,ifltm,vfltm,cmatm,reg,0,400)
    pylab.savefig('J1248_ONE_iterated.png')
    reg = 4.
    print reg

print 'das Ende'

print reg
doFit(None,True,False,False)
doFit(None,True,False,False)
print reg
xl,yl = pylens.getDeflections(lenses,coords)
src.update(xl,yl)
osrc = showRes(xl,yl,src,PSFm,img,sig,mask,ifltm,vfltm,cmatm,reg,0,400)
pylab.savefig('J1248_ONE.png')
pylab.show()

