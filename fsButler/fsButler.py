import os
import numpy as np

import lsst.afw.image as afwImage
import lsst.afw.table as afwTable

from . import utils

"""
Butler class that works around the LSST butler by looking at the file system.
"""

def _concatenateCats(cats):
    """
    Concatenate a list of catalogs into a single catalog
    """

    cat = cats[0]

    for i in range(1, len(cats)):
        cat.extend(cats[i], deep=False)

    return cat

class fsButler(object):

    _filters = ['HSC-G', 'HSC-R', 'HSC-I', 'HSC-Z', 'HSC-Y']

    def __init__(self, dataRoot):
        
        self.dataRoot = dataRoot

        import lsst.daf.persistence as dafPersist
        self.butler = dafPersist.Butler(dataRoot)

    @staticmethod
    def singleExpIds(dataRoot, filter=None, visit=None, ccd=None):
        """
        Returns a list of data Ids for single exposures in a given dataRoot directory
    
        Arguments
        dataRoot: The directory where the rerun data is stored
    
        Keywords
        filter: If None return the ids with all the filters, if present return only the ids
                with a given filter
        visit: If None return the ids with all the visits, if present return only the ids
                with a given visit 
        ccd: If None return the ids with all the ccds, if present return only the ids
                with a given ccd
        """
    
        if filter and visit and ccd:
            return [{'filter' : filter, 'visit' : visit, 'ccd' : ccd}]

        import re
    
        subDirs = os.listdir(dataRoot)
        dataDirs = []
        for d in subDirs:
            if d.isdigit():
                dataDirs.append(d)
    
        dataIds = []
        for d in dataDirs:
            cDir = os.path.join(dataRoot, d)
            if filter:
                filterPath = os.path.join(cDir, filter)
                if os.path.isdir(filterPath):
                    dirFilters = [filter]
                else:
                    continue
            else:
                dirFilters = os.listdir(cDir)
            for df in dirFilters:
                outputPath = os.path.join(os.path.join(cDir, df), 'output')
                outputs = os.listdir(outputPath)
                for o in outputs:
                    if re.match(r"^SRC-", o):
                        match = re.match(r"^SRC-([0-9]{7})-([0-9]{3}).fits", o)    

                        if match == None:
                            print "WARNING: Failed to read visit and ccd numbers from\
                                  {0}".format(os.path.join(outputPath, o))
                            continue

                        visitNumber = int(match.group(1))
                        ccdNumber = int(match.group(2))
                        if visit == None and ccd == None:
                            dataIds.append({'filter' : df, 'visit' : visitNumber, 'ccd' : ccdNumber})
                        elif visit != None and ccd == None:
                            if visitNumber == visit:
                                dataIds.append({'filter' : df, 'visit' : visitNumber, 'ccd' : ccdNumber})
                        elif visit == None and ccd != None:
                            if ccdNumber == ccd:
                                dataIds.append({'filter' : df, 'visit' : visitNumber, 'ccd' : ccdNumber})
                        elif visit != None and ccd != None:
                            if visitNumber == visit and ccdNumber == ccd:
                                dataIds.append({'filter' : df, 'visit' : visitNumber, 'ccd' : ccdNumber})

        return dataIds
    
    @staticmethod
    def deepCoaddIds(dataRoot, filter=None, tract=None, patch=None):
        """
        Returns a list of data Ids for deep coadds in a given dataRoot directory
    
        Arguments
        dataRoot: The directory where the rerun data is stored
    
        Keywords
        filter: If None return the ids with all the filters, if present return only the ids
                with a given filter
        tract: If None return the ids with all the tracts, if present return only the ids
                with a given tract
        patch: If None return the ids with all the patches, if present return only the ids
                with a given patch
        """
    
        if filter and tract and patch:
            return [{'filter' : filter, 'tract' : tract, 'patch' : patch}]

        deepCoaddPath = os.path.join(dataRoot,'deepCoadd-results')
    
        if filter:
            filters = [filter]
        else:
            filters = os.listdir(deepCoaddPath)
    
        dataIds = []
        for f in filters:
            filterPath = os.path.join(deepCoaddPath, f)
    
            if tract:
                tracts = [tract]
            else: 
                tracts = os.listdir(filterPath)
    
            for t in tracts:
                tractPath = os.path.join(filterPath, t)
    
                if patch:
                    patches = [patch]
                else:
                    patches = os.listdir(tractPath)
    
                for p in patches:
                    dataIds.append({'filter' : f, 'tract' : int(t), 'patch' : p})
    
        return dataIds
    
    @staticmethod
    def getIds(dataRoot, dataType, **dataId):
        """
        Returns a list of data Ids for data of type `dataType` in a given dataRoot directory
    
        Arguments
        dataRoot: The directory where the rerun data is stored
        dataType: The type of data element we want to fetch
    
        Keywords
        dataId: Dictionary of keywords that specify a dataId, if None all the data elements of type
                `dataType` will be returned. If the id is complete it will only return a single data
                element.
        """

        if dataType == 'src' or dataType == 'calexp_md':
            dataIds = fsButler.singleExpIds(dataRoot, **dataId)
        elif dataType == 'deepCoadd' or dataType == 'deepCoadd_src' or dataType == 'deepCoadd_calexp_md':
            dataIds = fsButler.deepCoaddIds(dataRoot, **dataId)
        else:
            raise ValueError("Data type {0} is not implemented".format(dataType))

        return dataIds

    def fetchIds(self, dataType, **dataId):
        """
        Returns a list of data Ids for data of type `dataType` in a given dataRoot directory
    
        Arguments
        dataType: The type of data element we want to fetch
    
        Keywords
        dataId: Dictionary of keywords that specify a dataId, if None all the data elements of type
                `dataType` will be returned. If the id is complete it will only return a single data
                element.
        """

        return self.getIds(self.dataRoot, dataType, **dataId)

    @staticmethod
    def _getCalexpType(dataType):
        if dataType == 'src':
            return 'calexp_md'
        elif dataType == 'deepCoadd_src':
            return 'deepCoadd_calexp_md'
        elif dataType == 'calexp_md' or dataType == 'deepCoadd_calexp_md':
            return dataType
        elif dataType == 'calexp' or dataType == 'deepCoadd':
            return dataType
        else:
            raise ValueError("Unkown dataType")

    def _getZeroMagFlux(self, dataType, **id):
        """
        Get the zero magnitude flux for the given data type and data id
        It also returns the psf associated with the data id in case it's needed
        later (e.g. when withSeeing=True)
        """
        calexpType = self._getCalexpType(dataType)
        if self.butler.datasetExists(calexpType, **id):
            calexp_md = self.butler.get(calexpType, **id)
            psf = calexp_md.getPsf()
            calib = afwImage.Calib(calexp_md)
            fluxMag0, fluxMag0Err = calib.getFluxMag0()
        else:
            calexpType = dataType[:-4]
            calexp = self.butler.get(calexpType, **id)
            psf = calexp.getPsf()
            calib = calexp.getCalib()
            fluxMag0, fluxMag0Err = calib.getFluxMag0()
        return fluxMag0, fluxMag0Err, psf

    def fetchDataset(self, dataType='src', flags=None, immediate=True, withZeroMagFlux=True,
                     filterSuffix=None, scm=None, withSeeing=True, seeingAtPos=False, **dataId):
        """
        Returns the union of all the data elements of type `dataType` that match the id `dataId`
    
        Keywords
        dataType: The type of data element we want to fetch
        flags: Flags for the data id
        immediate: If True the butler makes sure it returns the actual data and not a proxy of it
        withZeroMagFlux: If true, an extra pair of columns will be added to the catalog for the zero
                         magnitude flux and its error estimate.
        filterSuffix: If present, a suffix corresponding to the filter will be appended to suffixable
                      fields. For example if dataId has `filter='HSC-I'`, you can set
                      `filterSiffix=i` to append a `.i` to all the column names.
        scm: If None, generate a new schema mapper
        dataId: Dictionary of keywords that specify a dataId, if None all the data elements of type
                `dataType` will be returned. If the id is complete it will only return a single data
                element.
        withSeeing: If true add a column for the FWHM of the PSF at each source's location.
        seeingAtPos: If true compute the seeing at each object's position, if False simply use
                     the seeing at the average position of the patch (in the case of coadds) or
                     ccd (in the case of single exposures).
        """
    
        dataIds = self.getIds(self.dataRoot, dataType, **dataId)
    
        dataset = []
        for id in dataIds:
            if self.butler.datasetExists(dataType, **id):
                dataElement = self.butler.get(dataType, flags=flags, immediate=immediate, **id)
                if withZeroMagFlux or withSeeing:
                    fluxMag0, fluxMag0Err, psf = self._getZeroMagFlux(dataType, **id)
                    # Compute seeing at average position
                    seeingAvgPos = psf.computeShape().getDeterminantRadius()
                if isinstance(dataElement, afwTable.SourceCatalog):
                    if scm == None:
                        scm = utils.createSchemaMapper(dataElement, filterSuffix=filterSuffix,
                                                       withZeroMagFlux=withZeroMagFlux,
                                                       withSeeing=withSeeing)
                    outputSchema = scm.getOutputSchema()
                    outputCat = afwTable.SimpleCatalog(outputSchema)
                    good = utils.goodSources(dataElement)
                    outputCat.reserve(np.sum(good))
                    for i, record in enumerate(dataElement):
                        if good[i]:
                            outputRecord = outputCat.addNew()
                            outputRecord.assign(record, scm)
                            if withZeroMagFlux:
                                if filterSuffix:
                                    suffix = utils._getFilterSuffix(filterSuffix)
                                    outputRecord.set('flux.zeromag'+suffix, fluxMag0)
                                    outputRecord.set('flux.zeromag.err'+suffix, fluxMag0Err)
                                else:
                                    outputRecord.set('flux.zeromag', fluxMag0)
                                    outputRecord.set('flux.zeromag.err', fluxMag0Err)
                            if withSeeing:
                                if seeingAtPos:
                                    pos = record.getCentroid()
                                    try:
                                        seeing = psf.computeShape(pos).getDeterminantRadius()
                                    except:
                                        seeing = psf.computeShape().getDeterminantRadius()
                                else:
                                    seeing = seeingAvgPos
                                if filterSuffix:
                                    pos = record.getCentroid()
                                    suffix = utils._getFilterSuffix(filterSuffix)
                                    outputRecord.set('seeing'+suffix, seeing)
                                else:
                                    outputRecord.set('seeing', seeing)
                    dataset.append(outputCat)
                else:
                    dataset.append(dataElement)
            else:
                print "WARNING: The data id {0} does not exist for data type {1}".format(id,dataType)
    
        if len(dataset) == 0:
            return None

        if len(dataset) == 1:
            return dataset[0]
    
        return _concatenateCats(dataset)
