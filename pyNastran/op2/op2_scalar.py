#pylint: disable=C0301,W0613,W0612,R0913
"""
Defines the OP2 class.
"""
from __future__ import (nested_scopes, generators, division, absolute_import,
                        print_function, unicode_literals)
from six import string_types, iteritems, PY2, b
from six.moves import range
import os
from struct import unpack, Struct
import sys

from numpy import array
import numpy as np
from scipy.sparse import coo_matrix

from pyNastran import is_release
from pyNastran.f06.errors import FatalError
from pyNastran.op2.errors import SortCodeError, DeviceCodeError, FortranMarkerError
from pyNastran.f06.tables.grid_point_weight import GridPointWeight

#============================

from pyNastran.op2.tables.lama_eigenvalues.lama import LAMA
from pyNastran.op2.tables.oee_energy.onr import ONR
from pyNastran.op2.tables.opg_appliedLoads.ogpf import OGPF

from pyNastran.op2.tables.oef_forces.oef import OEF
from pyNastran.op2.tables.oes_stressStrain.oes import OES
from pyNastran.op2.tables.ogs import OGS

from pyNastran.op2.tables.opg_appliedLoads.opg import OPG
from pyNastran.op2.tables.oqg_constraintForces.oqg import OQG
from pyNastran.op2.tables.oug.oug import OUG
from pyNastran.op2.tables.ogpwg import OGPWG
from pyNastran.op2.fortran_format import FortranFormat

from pyNastran.utils import is_binary_file
from pyNastran.utils.log import get_logger

class TrashWriter(object):
    """
    A dummy file that just trashes all data
    """
    def __init__(self, *args, **kwargs):
        """does nothing"""
        pass
    def open(self, *args, **kwargs):
        """does nothing"""
        pass
    def write(self, *args, **kwargs):
        """does nothing"""
        pass
    def close(self, *args, **kwargs):
        """does nothing"""
        pass
    def flush(self, *args, **kwargs):
        """does nothing"""
        pass


GEOM_TABLES = [
    # GEOM2 - Table of Bulk Data entry images related to element connectivity andscalar points
    # GEOM4 - Table of Bulk Data entry images related to constraints, degree-of-freedom membership and rigid element connectivity.
    b'GEOM1', b'GEOM2', b'GEOM3', b'GEOM4',  # regular
    b'GEOM1S', b'GEOM2S', b'GEOM3S', b'GEOM4S', # superelements
    b'GEOM1N', b'GEOM1VU', b'GEOM2VU',
    b'GEOM1OLD', b'GEOM2OLD', b'GEOM4OLD',

    b'EPT', b'EPTS', b'EPTOLD',
    b'EDTS',
    b'MPT', b'MPTS',

    b'PVT0', b'CASECC',
    b'EDOM', b'OGPFB1',
    # GPDT  - Grid point definition table
    # BGPDT - Basic grid point definition table.
    b'GPDT', b'BGPDT', b'BGPDTS', b'BGPDTOLD',
    b'DYNAMIC', b'DYNAMICS',

    # EQEXIN - quivalence table between external and internal grid/scalaridentification numbers.
    b'EQEXIN', b'EQEXINS',
    b'ERRORN',
    b'DESTAB', b'R1TABRG', b'HISADD',

    # eigenvalues
    b'BLAMA', b'LAMA', b'CLAMA',  #CLAMA is new
    # strain energy
    b'ONRGY1',
    # grid point weight
    b'OGPWG', b'OGPWGM',

    # other
    b'CONTACT', b'VIEWTB',
    b'KDICT', b'PERF',

    # aero?
    b'MONITOR',
]

RESULT_TABLES = [
    # new
    b'RAPCONS', b'RAQCONS', b'RADCONS', b'RASCONS', b'RAFCONS', b'RAECONS',
    b'RANCONS', b'RAGCONS', b'RADEFFM', b'RAPEATC', b'RAQEATC', b'RADEATC',
    b'RASEATC', b'RAFEATC', b'RAEEATC', b'RANEATC', b'RAGEATC',

    # stress
    b'OES1X1', b'OES1', b'OES1X', b'OES1C', b'OESCP',
    b'OESNLXR', b'OESNLXD', b'OESNLBR', b'OESTRCP',
    b'OESNL1X', b'OESRT',
    #----------------------
    # strain
    b'OSTR1X', b'OSTR1C',

    #----------------------
    # forces
    # OEF1  - Element forces (linear elements only)
    # HOEF1 - Element heat flux
    # OEF1X - Element forces with intermediate (CBAR and CBEAM) station forces
    #         and forces on nonlinear elements
    # DOEF1 - Scaled Response Spectra
    b'OEFIT', b'OEF1X', b'OEF1', b'DOEF1',


    # Table of Max values?
    # Table of RMS values?
    b'OEF1MX', b'OUGV1MX',

    #----------------------
    # spc forces - gset - sort 1
    b'OQG1', b'OQGV1',
    # mpc forces - gset - sort 1
    b'OQMG1',
    # ??? forces
    b'OQP1',

    #----------------------
    # displacement/velocity/acceleration/eigenvector/temperature
    # OUPV1 - Scaled Response Spectra
    b'OUG1', b'OUGV1', b'BOUGV1', b'OUPV1', b'OUGV1PAT',

    # OUGV1PAT - Displacements in the basic coordinate system
    # OUGV1  - Displacements in the global coordinate system
    # BOUGV1 - Displacements in the basic coordinate system
    # BOPHIG - Eigenvectors in the basic coordinate system
    # ROUGV1 - Relative OUGV1
    # TOUGV1 - Temperature OUGV1
    b'ROUGV1', b'TOUGV1', b'RSOUGV1', b'RESOES1', b'RESEF1',

    #----------------------
    # applied loads
    # OPG1 - Applied static loads
    b'OPNL1', # nonlinear applied loads - sort 1
    b'OPG1', b'OPGV1', # applied loads - gset? - sort 1
    b'OPG2', # applied loads - sort 2 - v0.8

    # grid point stresses
    b'OGS1', # grid point stresses/strains - sort 1

    #----------------------
    # other
    b'OPNL1', b'OFMPF2M',
    b'OSMPF2M', b'OPMPF2M', b'OLMPF2M', b'OGPMPF2M',

    b'OAGPSD2', b'OAGCRM2', b'OAGRMS2', b'OAGATO2', b'OAGNO2',
    b'OESPSD2', b'OESCRM2', b'OESRMS2', b'OESATO2', b'OESNO2',
    b'OEFPSD2', b'OEFCRM2', b'OEFRMS2', b'OEFATO2', b'OEFNO2',
    b'OPGPSD2', b'OPGCRM2', b'OPGRMS2', b'OPGATO2', b'OPGNO2',
    b'OQGPSD2', b'OQGCRM2', b'OQGRMS2', b'OQGATO2', b'OQGNO2',
    b'OQMPSD2', b'OQMCRM2', b'OQMRMS2', b'OQMATO2', b'OQMNO2',
    b'OUGPSD2', b'OUGCRM2', b'OUGRMS2', b'OUGATO2', b'OUGNO2',
    b'OVGPSD2', b'OVGCRM2', b'OVGRMS2', b'OVGATO2', b'OVGNO2',
    b'OSTRPSD2', b'OSTRCRM2', b'OSTRRMS2', b'OSTRATO2', b'OSTRNO2',
    b'OCRUG',
    b'OCRPG',

    b'STDISP', b'AEDISP', #b'TOLB2',

    # autoskip
    b'MATPOOL',
    b'CSTM',
    b'AXIC',
    b'BOPHIG',
    b'HOEF1',
    b'ONRGY2',

    #------------------------------------------
    # new skipped - v0.8

    # buggy
    b'IBULK',
    #b'FRL',  # frequency response list
    b'TOL',
    b'DSCM2', # normalized design sensitivity coeff. matrix

    # dont seem to crash
    b'DESCYC',
    b'DBCOPT', # design optimization history for post-processing
    b'PVT',    # table containing PARAM data
    b'XSOP2DIR',
    b'ONRGY',
    #b'CLAMA',
    b'DSCMCOL', # design sensitivity parameters
    b'CONTACTS',
    b'EDT', # aero and element deformations
    b'EXTDB',


    b'OQG2', # single point forces - sort 2 - v0.8
    b'OBC1', b'OBC2', # contact pressures and tractions at grid points
    b'OBG1', # glue normal and tangential tractions at grid points in basic coordinate system
    b'OES2', # element stresses - sort 2 - v0.8
    b'OEF2', # element forces - sort 2 - v0.8
    b'OPG2', # applied loads - sort 2 - v0.8
    b'OUGV2', # absolute displacements/velocity/acceleration - sort 2

    # contact
    b'OSPDSI1', # intial separation distance
    b'OSPDS1',  # final separation distance
    b'OQGCF1', b'OQGCF2', # contact force at grid point
    b'OQGGF1', b'OQGGF2', # glue forces in grid point basic coordinate system

    b'OUGRMS1',
    b'OESRMS1',
    b'OUGNO1',
    b'OESNO1',

    b'OSPDSI2',
    b'OSPDS2',
    b'OSTR2',
    b'OESNLXR2',

    b'CMODEXT',
    b'ROUGV2',  # relative displacement
    b'CDDATA',  # cambpell diagram table
    b'OEKE1',
    b'OES1MX', # extreme stresses?
    b'OESNLBR2',
    b'BGPDTVU', # basic grid point defintion table for a superelement and related to geometry with view-grids added

    b'OUG2T',
    b'AEMONPT',
]
# RESULT_TABLES = []

MATRIX_TABLES = [
    b'EFMFSMS', b'EFMASSS', b'RBMASSS', b'EFMFACS', b'MPFACS', b'MEFMASS', b'MEFWTS',

    b'TOLD', b'SDT', #b'STDISP',
    b'TOLB2', b'ADSPT', #b'MONITOR',
    b'PMRT', b'PFRT', b'PGRT', # b'AEMONPT',
    b'AFRT', b'AGRT',


    b'A', b'SOLVE,', b'UMERGE,', b'AA', b'AAP', b'ADELUF', b'ADELUS', b'ADELX',
    b'ADJG', b'ADJGT', b'ADRDUG', b'AEDBUXV', b'AEDW', b'AEFRC', b'AEIDW',
    b'AEIPRE', b'AEPRE', b'AG', b'AGD', b'AGG', b'AGX', b'AH', b'AJJT', b'AM2',
    b'AM3', b'ANORM', b'APART', b'APIMAT', b'APIMATT', b'APL', b'APPLOD',
    b'APU', b'ARVEC', b'AUG1', b'B', b'SOLVE,', b'B2DD', b'B2GG', b'B2PP',
    b'BAA', b'BACK', b'BANDPV', b'BASVEC', b'BASVEC0', b'BCONXI', b'BCONXT',
    b'BDD', b'BDIAG', b'BFEFE', b'BFHH', b'BHH', b'BHH1', b'BKK', b'BP', b'BPP',
    b'BRDD', b'BXX', b'BUX', b'C', b'CDELB', b'CDELK', b'CDELM', b'CFSAB',
    b'CLAMMAT', b'CLFMAT', b'CMAT', b'CMBXPHG', b'CMSQE', b'CMSTQE', b'CNVTST',
    b'CON', b'CONS1T', b'CONSBL', b'CONTVDIF', b'COORD', b'COORDO', b'CPH1',
    b'CPH2', b'CPHP', b'CPHX', b'CPHL', b'CVAL', b'CVALO', b'CVAL', b'CVALR',
    b'CVALRG', b'CVECT', b'D', b'D1JE', b'D1JK', b'D2JE', b'D2JK', b'DAR',
    b'DBUG', b'DCLDXT', b'DELB1', b'DELBSH', b'DELCE', b'DELDV', b'DELF1',
    b'DELFL', b'DELGM', b'DELGS', b'DELS', b'DELS1', b'DELTGM', b'DELVS',
    b'DELWS', b'DELX', b'DELX1', b'DESVCP', b'DESVEC', b'DESVECP', b'DJX',
    b'DM', b'DPHG', b'DPLDXI', b'DPLDXT', b'DRDUG', b'DRDUGM', b'DSCM',
    b'DSCM2', b'DSCMG', b'DSCMR', b'DSDIV', b'DSEGM', b'DSESM', b'DSTABR',
    b'DSTABU', b'DUGNI', b'DUX', b'DXDXI', b'DXDXIT', b'E', b'EFMASMTT',
    b'EFMMCOL', b'EFMMAT', b'EGK', b'EGM', b'EGTX', b'EGX', b'EMAT', b'EMM',
    b'ENEMAT', b'ENFLODB', b'ENFLODK', b'ENFLODM', b'ENFMOTN', b'ERHM',
    b'EUHM', b'EXCITEFX', b'EXCITF', b'EXCITP', b'F', b'F2J', b'FFAJ', b'FGNL',
    b'FMPF', b'FN', b'FOLMAT', b'FORE', b'FREQMASS', b'FRMDS', b'GC', b'GDGK',
    b'GDKI', b'GDKSKS', b'GEG', b'GLBRSP', b'GLBRSPDS', b'GM', b'GMD', b'GMNE',
    b'GMS', b'GOA', b'GOD', b'GPFMAT', b'GPGK', b'GPKH', b'GPIK', b'GPKE',
    b'GPMPF', b'GRDRM', b'GS', b'HMKT', b'IFD', b'IFG', b'IFP', b'IFS', b'IFST',
    b'IMAT', b'IMATG', b'K2DD', b'K2GG', b'K2PP', b'K4AA', b'K4KK', b'K4XX',
    b'KAA', b'KAAL', b'KDD', b'KDICTDS', b'KDICTX', b'KFHH', b'KFS', b'KGG',
    b'KGG1', b'KGGNL', b'KGGNL1', b'KGGT', b'KHH', b'KHH1', b'KKK', b'KLL',
    b'KLR', b'KMM', b'KNN', b'KOO', b'KPP', b'KRDD', b'KRFGG', b'KRR', b'KRZX',
    b'KSAZX', b'KSGG', b'KSS', b'KTTP', b'KTTS', b'KUX', b'KXWAA', b'KXX',
    b'LAJJT', b'LAM1DD', b'LAMAM', b'LAMMAT', b'LCPHL', b'LCPHP', b'LCPHX',
    b'LMPF', b'LSCM', b'LSEQ', b'LTF', b'M2DD', b'M2GG', b'M2PP', b'MA', b'MAA',
    b'MABXWGG', b'MAT', b'MAT1', b'MAT1N', b'MAT2', b'MAT2N', b'MATS', b'MATM',
    b'MBSP', b'MCHI', b'MCHI2', b'MDD', b'MDUGNI', b'MEA', b'MEF', b'MEM', b'MES',
    b'MEW', b'MFEFE', b'MFHH', b'MGG', b'MGGCOMB', b'MHH', b'MHH1', b'MI', b'MKK',
    b'MKNRGY', b'MLAM', b'MLAM2', b'MLL', b'MLR', b'MMP', b'MNRGYMTF', b'MOA',
    b'MOO', b'MPJN2O', b'MPP', b'MQG', b'MR', b'MRR', b'MSNRGY', b'MUG', b'MUGNI',
    b'MULNT', b'MUPN', b'MUX', b'MXWAA', b'MXX', b'MZZ', b'OTMT', b'P2G', b'PA',
    b'PBYG', b'PC1', b'PD', b'PDF', b'PDT', b'PDT1', b'PFP', b'PG', b'PG1',
    b'PGG', b'PGRV', b'PGT', b'PGUP', b'PGVST', b'PHA', b'PHA1', b'PHAREF1',
    b'PHASH2', b'PHDFH', b'PHDH', b'PHF', b'PHF1', b'PHG', b'PHG1', b'PHGREF',
    b'PHGREF1', b'PHT', b'PHX', b'PHXL', b'PHZ', b'PJ', b'PKF', b'PKYG', b'PL',
    b'PLI', b'PMPF', b'PMYG', b'PNL', b'PNLT', b'PO', b'POI', b'PPF', b'PPL',
    b'PPLT', b'PPT', b'PRBDOFS', b'PROPI', b'PROPO', b'PS', b'PSF', b'PSI',
    b'PST', b'PUG', b'PUGD', b'PUGS', b'PX', b'PXA', b'PXF', b'PXT', b'PXTDV',
    b'PXT1', b'PZ', b'QG', b'QHH', b'QHHL', b'QHJ', b'QHJK', b'QHJL', b'QKH',
    b'QKHL', b'QLL', b'QMG', b'QMPF', b'QPF', b'QR', b'QXX', b'R', b'R1VAL',
    b'R1VALO', b'R1VALR', b'R1VALRG', b'R2VAL', b'R2VALO', b'R2VALR',
    b'R2VALRG', b'R3VAL', b'R3VALO', b'R3VALR', b'R3VALRG', b'RBF', b'RECM',
    b'RDG', b'RESMATFT', b'RESMAX', b'RESMAX0', b'RGG', b'RHMCF', b'RMAT',
    b'RMATG', b'RMG', b'RMG1', b'RMPTQM', b'RMSVAL', b'RMSVALR', b'RMSVLR',
    b'RPH', b'RPV', b'RPX', b'RQA', b'RSPTQS', b'RSTAB', b'RUG', b'RUL', b'RUO',
    b'SCLFMAT', b'SEQMAP', b'SHPVEC', b'SKJ', b'SLIST', b'SMPF', b'SNORMM',
    b'SORTBOOL', b'SRKS', b'SRKT', b'SVEC', b'SYSE', b'TR', b'TRX', b'UA',
    b'UACCE', b'UAJJT', b'UAM1DD', b'UD', b'UD1', b'UDISP', b'UE', b'UG', b'UGD',
    b'UGDS', b'UGDS1', b'UGG', b'UGNI', b'UGNT', b'UGT', b'MATMOD', b'UGX',
    b'UGX1', b'UH', b'UHF', b'UHFF', b'UHFS', b'UI', b'UL', b'ULNT', b'UNITDISP',
    b'UO', b'UOO', b'UPF', b'UPNL0', b'UPNT', b'UTF', b'UVELO', b'UX', b'UXDIFV',
    b'UXF', b'UXR', b'UXT', b'UXT1', b'UXU', b'UXV', b'UXVBRL', b'UXVF', b'UXVP',
    b'UXVST', b'UXVW', b'VA', b'VG', b'VGD', b'WGTM', b'WJ', b'WRJVBRL',
    b'WSKJF', b'SOLVE,', b'XAA', b'XD', b'XDD', b'XDICT', b'XDICTB', b'XDICTDS',
    b'XDICTX', b'XG', b'XGG', b'XH', b'XINIT', b'XJJ', b'XO', b'XORTH', b'XP',
    b'XPP', b'SOLVIT', b'XSF', b'XSS', b'XZ', b'YACCE', b'YPF', b'YPO', b'YPT',
    b'YS', b'YS0', b'YSD', b'YVELO', b'Z1ZX', b'ZZX',
]
class OP2_Scalar(LAMA, ONR, OGPF,
                 OEF, OES, OGS, OPG, OQG, OUG, OGPWG, FortranFormat):
    """
    Defines an interface for the Nastran OP2 file.
    """
    def set_as_nx(self):
        self.is_nx = True
        self.is_msc = False

    def set_as_msc(self):
        self.is_nx = False
        self.is_msc = True

    def __init__(self, debug=False, log=None, debug_file=None):
        """
        Initializes the OP2_Scalar object

        Parameters
        ----------
        debug : bool; default=False
            enables the debug log and sets the debug in the logger
        log : Log()
            a logging object to write debug messages to
         (.. seealso:: import logging)
        debug_file : str; default=None (No debug)
            sets the filename that will be written to
        """
        assert isinstance(debug, bool), 'debug=%r' % debug

        self.log = get_logger(log, 'debug' if debug else 'info')
        self._count = 0
        self.op2_filename = None
        self.bdf_filename = None
        self.f06_filename = None
        self._encoding = 'utf8'

        LAMA.__init__(self)
        ONR.__init__(self)
        OGPF.__init__(self)

        OEF.__init__(self)
        OES.__init__(self)
        OGS.__init__(self)

        OPG.__init__(self)
        OQG.__init__(self)
        OUG.__init__(self)
        OGPWG.__init__(self)
        FortranFormat.__init__(self)

        self.is_vectorized = False
        self._close_op2 = True

        self.result_names = set([])

        self.grid_point_weight = GridPointWeight()
        self.words = []
        self.debug = debug
        self._last_comment = None
        #self.debug = True
        #self.debug = False
        #debug_file = None
        if debug_file is None:
            self.debug_file = None
        else:
            assert isinstance(debug_file, string_types), debug_file
            self.debug_file = debug_file

    def set_as_vectorized(self, vectorized=False, ask=False):
        """don't call this...testing"""
        if vectorized is True:
            msg = 'OP2_Scalar class doesnt support vectorization.  Use OP2 '
            msg += 'from pyNastran.op2.op2 instead.'
            raise RuntimeError(msg)
        if ask is True:
            msg = 'OP2_Scalar class doesnt support ask.'
            raise RuntimeError(msg)

    def set_subcases(self, subcases=None):
        """
        Allows you to read only the subcases in the list of iSubcases

        Parameters
        ----------
        self : OP2
            the OP2 object pointer
        subcases : List[int, ...] / int; default=None->all subcases
            list of [subcase1_ID,subcase2_ID]
        """
        #: stores the set of all subcases that are in the OP2
        #self.subcases = set([])
        if subcases is None or subcases == []:
            #: stores if the user entered [] for iSubcases
            self.isAllSubcases = True
            self.valid_subcases = []
        else:
            #: should all the subcases be read (default=True)
            self.isAllSubcases = False

            if isinstance(subcases, int):
                subcases = [subcases]

            #: the set of valid subcases -> set([1,2,3])
            self.valid_subcases = set(subcases)
        self.log.debug("set_subcases - subcases = %s" % self.valid_subcases)

    def set_transient_times(self, times):  # TODO this name sucks...
        """
        Takes a dictionary of list of times in a transient case and
        gets the output closest to those times.

        .. code-block:: python
          times = {subcaseID_1: [time1, time2],
                   subcaseID_2: [time3, time4]}
        """
        expected_times = {}
        for (isubcase, eTimes) in iteritems(times):
            etimes = list(times)
            etimes.sort()
            expected_times[isubcase] = array(etimes)
        self.expected_times = expected_times

    def _get_table_mapper(self):
        table_mapper = {
            b'RAPCONS': [self._table_passer, self._table_passer],
            b'RAQCONS': [self._table_passer, self._table_passer],
            b'RADCONS': [self._table_passer, self._table_passer],
            b'RASCONS': [self._table_passer, self._table_passer],
            b'RAFCONS': [self._table_passer, self._table_passer],
            b'RAECONS': [self._table_passer, self._table_passer],
            b'RANCONS': [self._table_passer, self._table_passer],
            b'RAGCONS': [self._table_passer, self._table_passer],
            b'RADEFFM': [self._table_passer, self._table_passer],
            b'RAPEATC': [self._table_passer, self._table_passer],
            b'RAQEATC': [self._table_passer, self._table_passer],
            b'RADEATC': [self._table_passer, self._table_passer],
            b'RASEATC': [self._table_passer, self._table_passer],
            b'RAFEATC': [self._table_passer, self._table_passer],
            b'RAEEATC': [self._table_passer, self._table_passer],
            b'RANEATC': [self._table_passer, self._table_passer],
            b'RAGEATC': [self._table_passer, self._table_passer],

            #b'HISADD': [self._hisadd_3, self._hisadd_4],  # optimization history (SOL200)
            b'HISADD': [self._table_passer, self._table_passer],
            b'R1TABRG': [self._table_passer, self._table_passer_r1tabrg],
            b'TOL': [self._table_passer, self._table_passer],

            b'MATPOOL': [self._table_passer, self._table_passer],
            b'CSTM':    [self._table_passer, self._table_passer],
            b'AXIC':    [self._table_passer, self._table_passer],
            b'BOPHIG':  [self._table_passer, self._table_passer],  # eigenvectors in basic coordinate system
            b'ONRGY2':  [self._table_passer, self._table_passer],

            b'RSOUGV1': [self._table_passer, self._table_passer],
            b'RESOES1': [self._table_passer, self._table_passer],
            b'RESEF1' : [self._table_passer, self._table_passer],
            b'DESCYC' : [self._table_passer, self._table_passer],
            b'AEMONPT' : [self._read_aemonpt_3, self._read_aemonpt_4],
            #=======================
            # OEF
            # element forces
            b'OEFIT' : [self._read_oef1_3, self._read_oef1_4],  # failure indices
            b'OEF1X' : [self._read_oef1_3, self._read_oef1_4],  # element forces at intermediate stations
            b'OEF1'  : [self._read_oef1_3, self._read_oef1_4],  # element forces or heat flux
            b'HOEF1':  [self._read_oef1_3, self._read_oef1_4], # element heat flux
            b'DOEF1' : [self._read_oef1_3, self._read_oef1_4],  # scaled response spectra - spc forces?
            #=======================
            # OQG
            # spc forces
            # OQG1/OQGV1 - spc forces in the nodal frame
            # OQP1 - scaled response spectra - spc forces
            b'OQG1' : [self._read_oqg1_3, self._read_oqg_4],
            b'OQG2' : [self._read_oqg2_3, self._read_oqg_4],

            b'OQGV1' : [self._read_oqg1_3, self._read_oqg_4],
            b'OQGV2' : [self._read_oqg2_3, self._read_oqg_4],

            'OQP1' : [self._read_oqg1_3, self._read_oqg_4],
            'OQP2' : [self._read_oqg2_3, self._read_oqg_4],

            # OQGM1     - mpc forces in the nodal frame
            b'OQMG1' : [self._read_oqg1_3, self._read_oqg_4],

            #=======================
            # OPG
            # applied loads
            b'OPG1'  : [self._read_opg1_3, self._read_opg1_4],  # applied loads in the nodal frame
            b'OPGV1' : [self._read_opg1_3, self._read_opg1_4],
            b'OPNL1' : [self._read_opg1_3, self._read_opg1_4],  # nonlinear loads

            # OGPFB1
            # grid point forces
            b'OGPFB1' : [self._read_ogpf1_3, self._read_ogpf1_4],  # grid point forces

            # ONR/OEE
            # strain energy density
            b'ONRGY1' : [self._read_onr1_3, self._read_onr1_4],  # strain energy density
            #=======================
            # OES
            # stress
            b'OES1X1'  : [self._read_oes1_3, self._read_oes1_4],  # stress - nonlinear elements
            b'OES1'    : [self._read_oes1_3, self._read_oes1_4],  # stress - linear only
            b'OES1X'   : [self._read_oes1_3, self._read_oes1_4],  # element stresses at intermediate stations & nonlinear stresses
            b'OES1C'   : [self._read_oes1_3, self._read_oes1_4],  # stress - composite
            b'OESCP'   : [self._read_oes1_3, self._read_oes1_4],
            b'OESRT'   : [self._read_oes1_3, self._read_oes1_4],

            # special nonlinear tables
            b'OESNLXR' : [self._read_oes1_3, self._read_oes1_4],  # nonlinear stresses
            b'OESNLXD' : [self._read_oes1_3, self._read_oes1_4],  # nonlinear transient stresses
            b'OESNLBR' : [self._read_oes1_3, self._read_oes1_4],
            b'OESNL1X' : [self._read_oes1_3, self._read_oes1_4],

            # strain
            b'OSTR1X'  : [self._read_oes1_3, self._read_ostr1_4],  # strain - isotropic
            b'OSTR1C'  : [self._read_oes1_3, self._read_ostr1_4],  # strain - composite
            b'OESTRCP' : [self._read_oes1_3, self._read_ostr1_4],

            #=======================
            # OUG
            # displacement/velocity/acceleration/eigenvector/temperature
            b'OUG1'    : [self._read_oug1_3, self._read_oug_4],  # displacements in nodal frame
            b'OUGV1'   : [self._read_oug1_3, self._read_oug_4],  # displacements in nodal frame
            b'BOUGV1'  : [self._read_oug1_3, self._read_oug_4],  # OUG1 on the boundary???
            b'OUGV1PAT': [self._read_oug1_3, self._read_oug_4],  # OUG1 + coord ID
            b'OUPV1'   : [self._read_oug1_3, self._read_oug_4],  # scaled response spectra - displacement
            b'TOUGV1'  : [self._read_oug1_3, self._read_oug_4],  # grid point temperature
            b'ROUGV1'  : [self._read_oug1_3, self._read_oug_4], # relative OUG

            b'OUGV2'   : [self._read_oug2_3, self._read_oug_4],  # displacements in nodal frame

            #=======================
            # OGPWG
            # grid point weight
            b'OGPWG'  : [self._read_ogpwg_3, self._read_ogpwg_4],  # grid point weight
            b'OGPWGM' : [self._read_ogpwg_3, self._read_ogpwg_4],  # modal? grid point weight

            #=======================
            # OGS
            # grid point stresses
            b'OGS1' : [self._read_ogs1_3, self._read_ogs1_4],  # grid point stresses
            #=======================
            # eigenvalues
            b'BLAMA' : [self._read_buckling_eigenvalue_3, self._read_buckling_eigenvalue_4], # buckling eigenvalues
            b'CLAMA' : [self._read_complex_eigenvalue_3, self._read_complex_eigenvalue_4],   # complex eigenvalues
            b'LAMA'  : [self._read_real_eigenvalue_3, self._read_real_eigenvalue_4],         # eigenvalues

            # ===geom passers===
            # geometry
            b'GEOM1' : [self._table_passer, self._table_passer],
            b'GEOM2' : [self._table_passer, self._table_passer],
            b'GEOM3' : [self._table_passer, self._table_passer],
            b'GEOM4' : [self._table_passer, self._table_passer],

            # superelements
            b'GEOM1S' : [self._table_passer, self._table_passer],  # GEOMx + superelement
            b'GEOM2S' : [self._table_passer, self._table_passer],
            b'GEOM3S' : [self._table_passer, self._table_passer],
            b'GEOM4S' : [self._table_passer, self._table_passer],

            b'GEOM1N' : [self._table_passer, self._table_passer],
            b'GEOM2N' : [self._table_passer, self._table_passer],
            b'GEOM3N' : [self._table_passer, self._table_passer],
            b'GEOM4N' : [self._table_passer, self._table_passer],

            b'GEOM1OLD' : [self._table_passer, self._table_passer],
            b'GEOM2OLD' : [self._table_passer, self._table_passer],
            b'GEOM3OLD' : [self._table_passer, self._table_passer],
            b'GEOM4OLD' : [self._table_passer, self._table_passer],

            b'EPT' : [self._table_passer, self._table_passer],  # elements
            b'EPTS' : [self._table_passer, self._table_passer],  # elements - superelements
            b'EPTOLD' : [self._table_passer, self._table_passer],

            b'MPT' : [self._table_passer, self._table_passer],  # materials
            b'MPTS' : [self._table_passer, self._table_passer],  # materials - superelements

            b'DYNAMIC' : [self._table_passer, self._table_passer],
            b'DYNAMICS' : [self._table_passer, self._table_passer],
            b'DIT' : [self._table_passer, self._table_passer],

            # geometry
            #b'GEOM1': [self._read_geom1_4, self._read_geom1_4],
            #b'GEOM2': [self._read_geom2_4, self._read_geom2_4],
            #b'GEOM3': [self._read_geom3_4, self._read_geom3_4],
            #b'GEOM4': [self._read_geom4_4, self._read_geom4_4],

            # superelements
            #b'GEOM1S': [self._read_geom1_4, self._read_geom1_4],
            #b'GEOM2S': [self._read_geom2_4, self._read_geom2_4],
            #b'GEOM3S': [self._read_geom3_4, self._read_geom3_4],
            #b'GEOM4S': [self._read_geom4_4, self._read_geom4_4],

            #b'GEOM1N': [self._read_geom1_4, self._read_geom1_4],
            #b'GEOM2N': [self._read_geom2_4, self._read_geom2_4],
            #b'GEOM3N': [self._read_geom3_4, self._read_geom3_4],
            #b'GEOM4N': [self._read_geom4_4, self._read_geom4_4],

            #b'GEOM1OLD': [self._read_geom1_4, self._read_geom1_4],
            #b'GEOM2OLD': [self._read_geom2_4, self._read_geom2_4],
            #b'GEOM3OLD': [self._read_geom3_4, self._read_geom3_4],
            #b'GEOM4OLD': [self._read_geom4_4, self._read_geom4_4],

            #b'EPT' : [self._read_ept_4, self._read_ept_4],
            #b'EPTS': [self._read_ept_4, self._read_ept_4],
            #b'EPTOLD' : [self._read_ept_4, self._read_ept_4],

            #b'MPT' : [self._read_mpt_4, self._read_mpt_4],
            #b'MPTS': [self._read_mpt_4, self._read_mpt_4],

            #b'DYNAMIC': [self._read_dynamics_4, self._read_dynamics_4],
            #b'DYNAMICS': [self._read_dynamics_4, self._read_dynamics_4],
            #b'DIT': [self._read_dit_4, self._read_dit_4],   # table objects (e.g. TABLED1)

            # ===passers===
            b'EQEXIN': [self._table_passer, self._table_passer],
            b'EQEXINS': [self._table_passer, self._table_passer],

            b'GPDT' : [self._table_passer, self._table_passer],     # grid points?
            b'BGPDT' : [self._table_passer, self._table_passer],    # basic grid point defintion table
            b'BGPDTS' : [self._table_passer, self._table_passer],
            b'BGPDTOLD' : [self._table_passer, self._table_passer],

            b'PVT0' : [self._table_passer, self._table_passer],  # user parameter value table
            b'DESTAB' : [self._table_passer, self._table_passer],
            b'TOLD' : [self._table_passer, self._table_passer],
            b'CASECC' : [self._table_passer, self._table_passer],  # case control deck

            b'STDISP' : [self._table_passer, self._table_passer], # matrix?
            b'AEDISP' : [self._table_passer, self._table_passer], # matrix?
            #b'TOLB2' : [self._table_passer, self._table_passer], # matrix?

            b'EDTS' : [self._table_passer, self._table_passer],
            b'FOL' : [self._table_passer, self._table_passer],
            b'MONITOR' : [self._table_passer, self._table_passer],  # monitor points
            b'PERF' : [self._table_passer, self._table_passer],
            b'VIEWTB' : [self._table_passer, self._table_passer],   # view elements

            #b'FRL0': [self._table_passer, self._table_passer],  # frequency response list

            #==================================
            # works
            #b'OUGATO2' : [self._table_passer, self._table_passer],
            #b'OUGCRM2' : [self._table_passer, self._table_passer],
            #b'OUGNO2' : [self._table_passer, self._table_passer],
            ##b'OUGPSD2' : [self._table_passer, self._table_passer],
            #b'OUGRMS2' : [self._table_passer, self._table_passer],  # rms
            # new
            b'OUGATO2' : [self._read_oug2_3, self._read_oug_4],
            b'OUGCRM2' : [self._read_oug2_3, self._read_oug_4],
            b'OUGNO2' : [self._read_oug2_3, self._read_oug_4],
            b'OUGPSD2' : [self._read_oug2_3, self._read_oug_4], # done
            b'OUGRMS2' : [self._read_oug2_3, self._read_oug_4],

            b'OQGATO2' : [self._table_passer, self._table_passer],
            b'OQGCRM2' : [self._table_passer, self._table_passer],

            b'OQGNO2' : [self._table_passer, self._table_passer],
            b'OQGPSD2' : [self._read_oqg2_3, self._read_oqg_4],
            b'OQGRMS2' : [self._table_passer, self._table_passer],

            b'OFMPF2M' : [self._table_passer, self._table_passer],
            b'OLMPF2M' : [self._table_passer, self._table_passer],
            b'OPMPF2M' : [self._table_passer, self._table_passer],
            b'OSMPF2M' : [self._table_passer, self._table_passer],
            b'OGPMPF2M' : [self._table_passer, self._table_passer],

            b'OEFATO2' : [self._table_passer, self._table_passer],
            b'OEFCRM2' : [self._table_passer, self._table_passer],
            b'OEFNO2' : [self._table_passer, self._table_passer],
            b'OEFPSD2' : [self._table_passer, self._table_passer],
            b'OEFRMS2' : [self._table_passer, self._table_passer],

            b'OESATO2' : [self._table_passer, self._table_passer],
            b'OESCRM2' : [self._table_passer, self._table_passer],
            b'OESNO2' : [self._table_passer, self._table_passer],
            b'OESPSD2' : [self._table_passer, self._table_passer],
            b'OESRMS2' : [self._table_passer, self._table_passer],

            b'OVGATO2' : [self._table_passer, self._table_passer],
            b'OVGCRM2' : [self._table_passer, self._table_passer],
            b'OVGNO2' : [self._table_passer, self._table_passer],
            b'OVGPSD2' : [self._table_passer, self._table_passer],
            b'OVGRMS2' : [self._table_passer, self._table_passer],

            #==================================
            #b'GPL': [self._table_passer, self._table_passer],
            b'OMM2' : [self._table_passer, self._table_passer],
            b'ERRORN' : [self._table_passer, self._table_passer],  # p-element error summary table
            #==================================

            b'OCRPG' : [self._table_passer, self._table_passer],
            b'OCRUG' : [self._table_passer, self._table_passer],

            b'EDOM' : [self._table_passer, self._table_passer],
            b'OUG2T' : [self._table_passer, self._table_passer],

            b'OAGPSD2' : [self._table_passer, self._table_passer],
            b'OAGATO2' : [self._table_passer, self._table_passer],
            b'OAGRMS2' : [self._table_passer, self._table_passer],
            b'OAGNO2' : [self._table_passer, self._table_passer],
            b'OAGCRM2' : [self._table_passer, self._table_passer],

            b'OPGPSD2' : [self._table_passer, self._table_passer],
            b'OPGATO2' : [self._table_passer, self._table_passer],
            b'OPGRMS2' : [self._table_passer, self._table_passer],
            b'OPGNO2' : [self._table_passer, self._table_passer],
            b'OPGCRM2' : [self._table_passer, self._table_passer],

            b'OSTRPSD2' : [self._table_passer, self._table_passer],
            b'OSTRATO2' : [self._table_passer, self._table_passer],
            b'OSTRRMS2' : [self._table_passer, self._table_passer],
            b'OSTRNO2' : [self._table_passer, self._table_passer],
            b'OSTRCRM2' : [self._table_passer, self._table_passer],

            b'OQMPSD2' : [self._table_passer, self._table_passer],
            b'OQMATO2' : [self._table_passer, self._table_passer],
            b'OQMRMS2' : [self._table_passer, self._table_passer],
            b'OQMNO2' : [self._table_passer, self._table_passer],
            b'OQMCRM2' : [self._table_passer, self._table_passer],
        }
        return table_mapper

    #def _hisadd_3(self, data):
        #"""
        #table of design iteration history for current design cycle
        #HIS table
        #"""
        #self.show_data(data, types='ifs')
        #asf

    #def _hisadd_4(self, data):
        #self.show_data(data, types='ifs')
        #asf

    def _read_aemonpt_3(self, data, ndata):
        sys.exit(self.code_information())

    def _read_aemonpt_4(self, data, ndata):
        # self.table_name = self.read_table_name(rewind=False)
        # self.log.debug('table_name = %r' % self.table_name)
        # if self.is_debug_file:
            # self.binary_debug.write('_read_geom_table - %s\n' % self.table_name)

        if self.read_mode == 1:
            return ndata
        print('name, label =(%r,%r)' % unpack(b'8s56s', data[:64]))
        print('name2=%r' % unpack(b'12s', data[84:96]))
        self.show_data(data[64:84], types='if', endian=None)
        self.show_data(data[96:], types='if', endian=None)
        #self.show_data(data[ni:], types='ifs', endian=None)
        print('--------------------------------')

        return ndata
        for i in [-4, -5, -6, -7, -8]:
            self.read_markers([i, 1, 0])
            # if self.is_debug_file:
                # self.binary_debug.write('---markers = [-1]---\n')
            data = self._read_record()

            sname = data[:64]
            print('name, label = (%r,%r)' % unpack(b'8s56s', data[:64]))
            print('name2=%r' % unpack(b'12s', data[84:96]))
            self.show_data(data[64:84], types='if', endian=None)
            self.show_data(data[96:], types='if', endian=None)
            #self.show_data(data[ni:], types='ifs', endian=None)
            print('--------------------------------')


        self.read_markers([-9, 1, 0])
        # data = self._read_record()
        # self.show_data(data, types='ifs', endian=None)
        print('--------------------------------')




        # markers = self.get_nmarkers(1, rewind=True)
        # if self.is_debug_file:
            # self.binary_debug.write('---marker0 = %s---\n' % markers)
        # self.read_markers([-2, 1, 0])
        #data = self._read_record()

        self.show_ndata(100, types='ifs')
        return ndata
        #bbbb

    def _not_available(self, data, ndata):
        """testing function"""
        if ndata > 0:
            raise RuntimeError('this should never be called...table_name=%r len(data)=%s' % (self.table_name, ndata))

    def _table_passer(self, data, ndata):
        """auto-table skipper"""
        return ndata

    def _table_passer_r1tabrg(self, data, ndata):
        """auto-table skipper"""
        if self._table4_count == 0:
            self._count += 1
        self._table4_count += 1
        return ndata

    def _validate_op2_filename(self, op2_filename):
        """
        Pops a GUI if the op2_filename hasn't been set.

        Parameters
        ----------
        self : OP2
            the OP2 object pointer
        op2_filename : str
            the filename to check (None -> gui)

        Returns
        -------
        op2_filename : str
            a valid file string
        """
        if op2_filename is None:
            from pyNastran.utils.gui_io import load_file_dialog
            wildcard_wx = "Nastran OP2 (*.op2)|*.op2|" \
                "All files (*.*)|*.*"
            wildcard_qt = "Nastran OP2 (*.op2);;All files (*)"
            title = 'Please select a OP2 to load'
            op2_filename, wildcard_level = load_file_dialog(title, wildcard_wx, wildcard_qt, dirname='')
            assert op2_filename is not None, op2_filename
        return op2_filename

    def _create_binary_debug(self):
        """
        Instatiates the ``self.binary_debug`` variable/file
        """
        if hasattr(self, 'binary_debug') and self.binary_debug is not None:
            self.binary_debug.close()
            del self.binary_debug

        wb = 'w'
        if PY2:
            wb = 'wb'

        if self.debug_file is not None:
            #: an ASCII version of the op2 (creates lots of output)
            self.log.debug('debug_file = %s' % self.debug_file)
            self.binary_debug = open(self.debug_file, wb)
            self.binary_debug.write(self.op2_filename + '\n')
            self.is_debug_file = True
        else:
            #self.binary_debug = open(os.devnull, wb)  #TemporaryFile()
            #self.binary_debug = TrashWriter('debug.out', wb)
            self.is_debug_file = False

    def read_op2(self, op2_filename=None, combine=False):
        """
        Starts the OP2 file reading

        Parameters
        ----------
        self : OP2
            the OP2 object pointer
        op2_filename : str
            the op2 file

        +--------------+-----------------------+
        | op2_filename | Description           |
        +--------------+-----------------------+
        |     None     | a dialog is popped up |
        +--------------+-----------------------+
        |    string    | the path is used      |
        +--------------+-----------------------+
        """
        self._count = 0
        if self.read_mode == 1:
            #sr = list(self._results.saved)
            #sr.sort()
            #self.log.debug('_results.saved = %s' % str(sr))
            #self.log.info('_results.saved = %s' % str(sr))
            pass

        if self.read_mode != 2:
            op2_filename = self._validate_op2_filename(op2_filename)
            self.log.info('op2_filename = %r' % op2_filename)
            if not is_binary_file(op2_filename):
                if os.path.getsize(op2_filename) == 0:
                    raise IOError('op2_filename=%r is empty.' % op2_filename)
                raise IOError('op2_filename=%r is not a binary OP2.' % op2_filename)

        bdf_extension = '.bdf'
        f06_extension = '.f06'
        (fname, extension) = os.path.splitext(op2_filename)

        self.op2_filename = op2_filename
        self.bdf_filename = fname + bdf_extension
        self.f06_filename = fname + f06_extension

        self._create_binary_debug()

        #: file index
        self.n = 0
        self.table_name = None

        if not hasattr(self, 'f') or self.f is None:
            #: the OP2 file object
            self.f = open(self.op2_filename, 'rb')
            self._endian = None
            flag_data = self.f.read(4)
            self.f.seek(0)

            if unpack(b'>i', flag_data)[0] == 4:
                self._endian = '>'
            elif unpack(b'<i', flag_data)[0] == 4:
                self._endian = '<'
            else:
                raise FatalError('cannot determine endian')
            if PY2:
                self._endian = b(self._endian)
        else:
            self.goto(self.n)


        if self.read_mode == 1:
            self._set_structs()

        #try:
        markers = self.get_nmarkers(1, rewind=True)
        #except:
            #self.goto(0)
            #try:
                #self.f.read(4)
            #except:
                #raise FatalError("The OP2 is empty.")
            #raise
        if self.is_debug_file:
            if self.read_mode == 1:
                self.binary_debug.write('read_mode = %s (vectorized; 1st pass)\n' % self.read_mode)
            elif self.read_mode == 2:
                self.binary_debug.write('read_mode = %s (vectorized; 2nd pass)\n' % self.read_mode)

        if markers == [3,]:  # PARAM, POST, -1
            if self.is_debug_file:
                self.binary_debug.write('marker = 3 -> PARAM,POST,-1?\n')
            self.post = -1
            self.read_markers([3])
            data = self.read_block()

            self.read_markers([7])
            data = self.read_block()
            assert data == b'NASTRAN FORT TAPE ID CODE - ', '%r' % data
            if self.is_debug_file:
                self.binary_debug.write('%r\n' % data)

            data = self._read_record()
            if self.is_debug_file:
                self.binary_debug.write('%r\n' % data)
            version = data.strip()
            if version.startswith(b'NX'):
                self.set_as_nx()
                self.set_table_type()
            elif version.startswith(b'MODEP'):
                # TODO: why is this separate?
                # F:\work\pyNastran\pyNastran\master2\pyNastran\bdf\test\nx_spike\out_ac11103.op2
                self.set_as_nx()
                self.set_table_type()
            elif version.startswith(b'AEROFREQ'):
                # TODO: why is this separate?
                # C:\Users\Steve\Dropbox\pyNastran_examples\move_tpl\loadf.op2
                self.set_as_msc()
                self.set_table_type()
            elif version.startswith(b'AEROTRAN'):
                # TODO: why is this separate?
                # C:\Users\Steve\Dropbox\pyNastran_examples\move_tpl\loadf.op2
                self.set_as_msc()
                self.set_table_type()
            elif version == b'XXXXXXXX':
                self.set_as_msc()
                self.set_table_type()
            else:
                raise RuntimeError('unknown version=%r' % version)

            if self.is_debug_file:
                self.binary_debug.write(data.decode(self._encoding) + '\n')
            self.read_markers([-1, 0])
        elif markers == [2,]:  # PARAM, POST, -2
            if self.is_debug_file:
                self.binary_debug.write('marker = 2 -> PARAM,POST,-2?\n')
            self.post = -2
        else:
            raise NotImplementedError(markers)

        #=================
        table_name = self.read_table_name(rewind=True, stop_on_failure=False)
        if table_name is None:
            raise FatalError('There was a Nastran FATAL Error.  Check the F06.\nNo tables exist...')

        self._make_tables()
        table_names = self._read_tables(table_name)
        if self.is_debug_file:
            self.binary_debug.write('-' * 80 + '\n')
            self.binary_debug.write('f.tell()=%s\ndone...\n' % self.f.tell())
            self.binary_debug.close()
        if self._close_op2:
            self.f.close()
            del self.binary_debug
            del self.f
        #self.remove_unpickable_data()
        return table_names

    #def create_unpickable_data(self):
        #raise NotImplementedError()
        ##==== not needed ====
        ##self.f
        ##self.binary_debug

        ## needed
        #self._geom1_map
        #self._geom2_map
        #self._geom3_map
        #self._geom4_map
        #self._dit_map
        #self._dynamics_map
        #self._ept_map
        #self._mpt_map
        #self._table_mapper

    #def remove_unpickable_data(self):
        #del self.f
        #del self.binary_debug
        #del self._geom1_map
        #del self._geom2_map
        #del self._geom3_map
        #del self._geom4_map
        #del self._dit_map
        #del self._dynamics_map
        #del self._ept_map
        #del self._mpt_map
        #del self._table_mapper

    def _make_tables(self):
        return
        global RESULT_TABLES
        table_mapper = self._get_table_mapper()
        RESULT_TABLES = table_mapper.keys()

    def _read_tables(self, table_name):
        """
        Reads all the geometry/result tables.
        The OP2 header is not read by this function.

        :param table_name: the first table's name
        """
        table_names = []
        while table_name is not None:
            table_names.append(table_name)

            if self.is_debug_file:
                self.binary_debug.write('-' * 80 + '\n')
                self.binary_debug.write('table_name = %r\n' % (table_name))

            if is_release:
                self.log.debug('  table_name=%r' % table_name)

            self.table_name = table_name
            if 0:
                self._skip_table(table_name)
            else:
                if table_name in GEOM_TABLES:
                    self._read_geom_table()  # DIT (agard)
                elif table_name == b'GPL':
                    self._read_gpl()
                elif table_name == b'MEFF':
                    self._read_meff()
                elif table_name == b'INTMOD':
                    self._read_intmod()
                #elif table_name == b'HISADD':
                    #self._read_hisadd()
                elif table_name == b'FRL':  # frequency response list
                    self._skip_table(self.table_name)
                elif table_name == b'EXTDB':
                    self._read_extdb()
                elif table_name == b'BHH':
                    self._read_bhh()
                elif table_name == b'KHH':
                    self._read_bhh()
                elif table_name == b'OMM2':
                    self._read_omm2()
                elif table_name == b'DIT':  # tables
                    self._read_dit()
                elif table_name == b'KELM':
                    self._read_kelm()
                elif table_name == b'PCOMPTS': # blade
                    self._read_pcompts()
                elif table_name == b'FOL':
                    self._read_fol()
                elif table_name in [b'SDF', b'PMRF']:  #, 'PERF'
                    self._read_sdf()
                elif table_name in MATRIX_TABLES:
                    self._read_matrix()
                elif table_name in RESULT_TABLES:
                    self._read_results_table()
                elif self.skip_undefined_matrices:
                    self._read_matrix()
                elif table_name.strip() in self.additional_matrices:
                    self._read_matrix()
                else:
                    msg = 'geom/results split: %r\n\n' % table_name
                    msg += 'If you have matrices that you want to read, see:\n'
                    msg += '  model.set_additional_matrices(matrices)'
                    raise NotImplementedError(msg)

            table_name = self.read_table_name(rewind=True, stop_on_failure=False)
        return table_names

    def _read_matrix(self):
        print('----------------------------------------------------------------')
        table_name = self.read_table_name(rewind=False, stop_on_failure=True)
        #print('table_name = %r' % table_name)
        self.read_markers([-1])
        data = self._read_record()
        matrix_num, form, mrows, ncols, tout, nvalues, g = unpack(self._endian + '7i', data)
        m = Matrix(table_name)
        self.matrices[table_name.decode('utf-8')] = m

        # matrix_num is a counter (101, 102, 103, ...)
        # 101 will be the first matrix 'A' (matrix_num=101),
        # then we'll read a new matrix 'B' (matrix_num=102),
        # etc.
        #
        # the matrix is Mrows x Ncols
        #
        # it has nvalues in it
        #
        # tout is the precision of the matrix
        # 0 - set precision by cell
        # 1 - real, single precision (float32)
        # 2 - real, double precision (float64)
        # 3 - complex, single precision (complex64)
        # 4 - complex, double precision (complex128)

        # form (bad name)
        # 1 - column matrix
        # 2 - factor matrix
        # 3 - factor matrix
        if tout == 1:
            dtype = 'float32'
        elif tout == 2:
            dtype = 'float64'
        elif tout == 3:
            dtype = 'complex64'
        elif tout == 4:
            dtype = 'complex128'
        else:
            #raise RuntimeError('tout = %s' % tout)
            dtype = '????'
            print('unexpected tout: matrix_num=%s form=%s mrows=%s ncols=%s tout=%s nvalues=%s g=%s'  % (
                matrix_num, form, mrows, ncols, tout, nvalues, g))

        if form == 1:
            if ncols != 1:
                print('unexpected size; form=%s mrows=%s ncols=%s' % (form, mrows, ncols))

        if 0:
            assert matrix_num in [101, 102, 103, 104, 104, 105], matrix_num
            if matrix_num in [101, 102]:
                assert form == 2, form
                assert mrows == 4, mrows
                assert ncols == 2, ncols
                assert tout == 1, tout
                assert nvalues == 3, nvalues
                assert g == 6250, g
            elif matrix_num in [103, 104]:
                assert form == 2, form
                assert mrows == 2, mrows
                assert ncols == 1, ncols
                assert tout == 2, tout
                assert nvalues == 4, nvalues
                assert g == 10000, g
            elif matrix_num == 105:
                assert form == 1, form  # TDOO: why is this 1?
                assert mrows == 36, mrows
                assert ncols == 2, ncols # TODO: why is this not 1
                assert tout == 1, tout
                assert nvalues == 36, nvalues  ## TODO: is this correct?
                assert g == 10000, g  ## TODO: what does this mean?
            else:
                vals = unpack(self._endian + '7i', data)
                msg = 'name=%r matrix_num=%s form=%s mrows=%s ncols=%s tout=%s nvalues=%s g=%s' % (
                    table_name, matrix_num, form, mrows, ncols, tout, nvalues, g)
                raise NotImplementedError(msg)
        self.log.info('name=%r matrix_num=%s form=%s mrows=%s ncols=%s tout=%s nvalues=%s g=%s' % (
            table_name, matrix_num, form, mrows, ncols, tout, nvalues, g))

        #self.show_data(data)
        #print('------------')
        self.read_markers([-2, 1, 0])
        data = self._read_record()

        if len(data) == 20:
            # TODO: why does this work?
            name, a, b = unpack(self._endian + '8s 2i', data)
            assert a == 170, a
            assert b == 170, b
        elif len(data) == 16:
            name, a, b = unpack(self._endian + '8s 2i', data)
            assert a == 170, a
            assert b == 170, b
        else:
            self.log.warning('unexpected matrix length=%s' % len(data))
            self.log.warning(self.show_data(data, types='if'))

        itable = -3
        j = None

        niter = 0
        niter_max = 100000000

        GCi = []
        GCj = []
        reals = []
        jj = 1
        while niter < niter_max:
            #nvalues, = self.get_nmarkers(1, rewind=True)
            #print('nvalues4a =', nvalues)
            self.read_markers([itable, 1])
            one, = self.get_nmarkers(1, rewind=False)

            if one:  # if keep going
                nvalues, = self.get_nmarkers(1, rewind=True)
                #print('nvalues =', nvalues)
                while nvalues >= 0:
                    nvalues, = self.get_nmarkers(1, rewind=False)
                    GCj += [jj] * nvalues
                    data = self.read_block()
                    #self.show_data(data)

                    #print(type(self._endian), self._endian)
                    fmt = self._endian + 'i %if' % nvalues
                    #print('***itable=%s nvalues=%s fmt=%r' % (itable, nvalues, fmt))

                    #print(len(data))
                    out = unpack(fmt, data)
                    ii = out[0]
                    values = out[1:]

                    GCi += list(range(ii, ii + nvalues))
                    reals += values
                    if 0:
                        self.log.debug('II=%s; j=%s i0=%s %s' % (abs(itable+2), jj, ii, values))
                    if 0:
                        if matrix_num in [101, 102, 103, 104, 105]:
                            self.log.debug('II=%s; j=%s i0=%s %s' % (abs(itable+2), jj, ii, values))
                            #print(i, values)
                            #assert i == 4, i
                            #assert values[0] == 8, values
                        else:
                            raise NotImplementedError(matrix_num)
                    nvalues, = self.get_nmarkers(1, rewind=True)
                assert len(GCi) == len(GCj), 'nGCi=%s nGCj=%s' % (len(GCi), len(GCj))
                assert len(GCi) == len(reals), 'nGCi=%s nReals=%s' % (len(GCi), len(reals))
                jj += 1
            else:
                nvalues, = self.get_nmarkers(1, rewind=False)
                assert nvalues == 0, nvalues
                # print('nvalues =', nvalues)
                # print('returning...')

                #assert max(GCi) <= mrows, 'GCi=%s GCj=%s mrows=%s' % (GCi, GCj, mrows)
                #assert max(GCj) <= ncols, 'GCi=%s GCj=%s ncols=%s' % (GCi, GCj, ncols)
                GCi = array(GCi, dtype='int32') - 1
                GCj = array(GCj, dtype='int32') - 1
                #print('Gci', GCi)
                #print('GCj', GCj)
                #print('reals', reals)
                try:
                    # we subtract 1 to account for Fortran
                    if dtype == '????':
                        matrix = None
                        self.log.warning('what is the dtype?')
                    else:
                        matrix = coo_matrix((reals, (GCi, GCj)),
                                            shape=(mrows, ncols), dtype=dtype)
                        matrix = matrix.todense()
                        self.log.info('created %s' % self.table_name)
                except ValueError:
                    self.log.warning('cant make a coo/sparse matrix...trying dense')

                    if dtype == '????':
                        matrix = None
                        self.log.warning('what is the dtype?')
                    else:
                        matrix = array(reals, dtype=dtype)
                        self.log.debug('shape=%s mrows=%s ncols=%s' % (str(matrix.shape), mrows, ncols))
                        if len(reals) == mrows * ncols:
                            self.log.info('created %s' % self.table_name)
                        else:
                            self.log.warning('cant reshape because invalid sizes : created %s' % self.table_name)

                        #matrix.reshape(mrows, ncols)
                    #print('m =', matrix)

                m.data = matrix
                if matrix is not None:
                    self.matrices[table_name.decode('utf-8')] = m
                #nvalues, = self.get_nmarkers(1, rewind=True)
                #self.show(100)
                return
            itable -= 1
            niter += 1
        raise RuntimeError('this should never happen; n=%s' % niter_max)
        #print('------------')
        #self.show(100)
        #asdf

    def _skip_table(self, table_name):
        """bypasses the next table as quickly as possible"""
        if table_name in ['DIT']:  # tables
            self._read_dit()
        elif table_name in ['PCOMPTS']:
            self._read_pcompts()
        else:
            self._skip_table_helper()

    def _read_dit(self):
        """
        Reads the DIT table (poorly).
        The DIT table stores information about table cards
        (e.g. TABLED1, TABLEM1).
        """
        table_name = self.read_table_name(rewind=False)
        self.read_markers([-1])
        data = self._read_record()

        self.read_markers([-2, 1, 0])
        data = self._read_record()
        table_name, = self.struct_8s.unpack(data)

        self.read_markers([-3, 1, 0])
        data = self._read_record()

        self.read_markers([-4, 1, 0])
        data = self._read_record()

        self.read_markers([-5, 1, 0])

        markers = self.get_nmarkers(1, rewind=True)
        if markers != [0]:
            data = self._read_record()
            self.read_markers([-6, 1, 0])

        markers = self.get_nmarkers(1, rewind=True)
        if markers != [0]:
            data = self._read_record()
            self.read_markers([-7, 1, 0])

        markers = self.get_nmarkers(1, rewind=True)
        if markers != [0]:
            data = self._read_record()
            self.read_markers([-8, 1, 0])

        markers = self.get_nmarkers(1, rewind=True)
        if markers != [0]:
            data = self._read_record()
            self.read_markers([-9, 1, 0])

        #self.show(100)
        self.read_markers([0])

    def _read_kelm(self):
        """
        .. todo:: this table follows a totally different pattern...
        The KELM table stores information about the K matrix???
        """
        self.log.debug("table_name = %r" % self.table_name)
        table_name = self.read_table_name(rewind=False)
        self.read_markers([-1])
        data = self._read_record()

        self.read_markers([-2, 1, 0])
        data = self._read_record()
        if len(data) == 16:  # KELM
            table_name, dummy_a, dummy_b = unpack(b(self._endian + '8sii'), data)
            assert dummy_a == 170, dummy_a
            assert dummy_b == 170, dummy_b
        else:
            raise NotImplementedError(self.show_data(data))

        self.read_markers([-3, 1, 1])

        # data = read_record()
        for i in range(170//10):
            self.read_markers([2])
            data = self.read_block()
            #print "i=%s n=%s" % (i, self.n)

        self.read_markers([4])
        data = self.read_block()

        for i in range(7):
            self.read_markers([2])
            data = self.read_block()
            #print "i=%s n=%s" % (i, self.n)


        self.read_markers([-4, 1, 1])
        for i in range(170//10):
            self.read_markers([2])
            data = self.read_block()
            #print "i=%s n=%s" % (i, self.n)

        self.read_markers([4])
        data = self.read_block()

        for i in range(7):
            self.read_markers([2])
            data = self.read_block()
            #print "i=%s n=%s" % (i, self.n)

        self.read_markers([-5, 1, 1])
        self.read_markers([600])
        data = self.read_block()  # 604

        self.read_markers([-6, 1, 1])
        self.read_markers([188])
        data = self.read_block()

        self.read_markers([14])
        data = self.read_block()
        self.read_markers([16])
        data = self.read_block()
        self.read_markers([18])
        data = self.read_block()
        self.read_markers([84])
        data = self.read_block()
        self.read_markers([6])
        data = self.read_block()

        self.read_markers([-7, 1, 1])
        self.read_markers([342])
        data = self.read_block()

        self.read_markers([-8, 1, 1])
        data = self.read_block()
        data = self.read_block()
        while 1:
            n = self.get_nmarkers(1, rewind=True)[0]
            if n not in [2, 4, 6, 8]:
                #print "n =", n
                break
            n = self.get_nmarkers(1, rewind=False)[0]
            #print n
            data = self.read_block()


        i = -9
        while i != -13:
            n = self.get_nmarkers(1, rewind=True)[0]

            self.read_markers([i, 1, 1])
            while 1:
                n = self.get_nmarkers(1, rewind=True)[0]
                if n not in [2, 4, 6, 8]:
                    #print "n =", n
                    break
                n = self.get_nmarkers(1, rewind=False)[0]
                #print n
                data = self.read_block()
            i -= 1

        #print "n=%s" % (self.n)
        #strings, ints, floats = self.show(100)

    def _skip_pcompts(self):
        """
        Reads the PCOMPTS table (poorly).
        The PCOMPTS table stores information about the PCOMP cards???
        """
        self.log.debug("table_name = %r" % self.table_name)
        table_name = self.read_table_name(rewind=False)

        self.read_markers([-1])
        data = self._skip_record()

        self.read_markers([-2, 1, 0])
        data = self._skip_record()
        #table_name, = self.struct_8s.unpack(data)

        self.read_markers([-3, 1, 0])
        markers = self.get_nmarkers(1, rewind=True)
        if markers != [-4]:
            data = self._skip_record()

        self.read_markers([-4, 1, 0])
        markers = self.get_nmarkers(1, rewind=True)
        if markers != [0]:
            data = self._skip_record()
        else:
            self.read_markers([0])
            return

        self.read_markers([-5, 1, 0])
        data = self._skip_record()

        self.read_markers([-6, 1, 0])
        self.read_markers([0])

    def _read_pcompts(self):
        """
        Reads the PCOMPTS table (poorly).
        The PCOMPTS table stores information about the PCOMP cards???
        """
        self._skip_pcompts()
        return
        #if self.read_mode == 1:
            #return
        #self.log.debug("table_name = %r" % self.table_name)
        #table_name = self.read_table_name(rewind=False)

        #self.read_markers([-1])
        #data = self._read_record()

        #self.read_markers([-2, 1, 0])
        #data = self._read_record()
        #table_name, = self.struct_8s.unpack(data)
        ##print "table_name = %r" % table_name

        #self.read_markers([-3, 1, 0])
        #markers = self.get_nmarkers(1, rewind=True)
        #if markers != [-4]:
            #data = self._read_record()

        #self.read_markers([-4, 1, 0])
        #markers = self.get_nmarkers(1, rewind=True)
        #if markers != [0]:
            #data = self._read_record()
        #else:
            #self.read_markers([0])
            #return

        #self.read_markers([-5, 1, 0])
        #data = self._read_record()

        #self.read_markers([-6, 1, 0])
        #self.read_markers([0])

    def read_table_name(self, rewind=False, stop_on_failure=True):
        """Reads the next OP2 table name (e.g. OUG1, OES1X1)"""
        table_name = None
        data = None
        if self.is_debug_file:
            self.binary_debug.write('read_table_name - rewind=%s\n' % rewind)
        ni = self.n
        s = self.struct_8s
        if stop_on_failure:
            data = self._read_record(debug=False, macro_rewind=rewind)
            table_name, = s.unpack(data)
            if self.is_debug_file and not rewind:
                self.binary_debug.write('marker = [4, 2, 4]\n')
                self.binary_debug.write('table_header = [8, %r, 8]\n\n' % table_name)
            table_name = table_name.strip()
        else:
            try:
                data = self._read_record(macro_rewind=rewind)
                table_name, = s.unpack(data)
                table_name = table_name.strip()
            except:
                # we're done reading
                self.n = ni
                self.f.seek(self.n)

                try:
                    # we have a trailing 0 marker
                    self.read_markers([0], macro_rewind=rewind)
                except:
                    # if we hit this block, we have a FATAL error
                    raise FatalError('There was a Nastran FATAL Error.  Check the F06.\nlast table=%r' % self.table_name)
                table_name = None

                # we're done reading, so we're going to ignore the rewind
                rewind = False

        if rewind:
            self.n = ni
            self.f.seek(self.n)
        return table_name

    def set_additional_matrices_to_read(self, matrices):
        """
        Parameters
        ----------
        self : OP2
            the OP2 object pointer
        matrices : Dict[str] = bool
            a dictionary of key=name, value=True/False,
            where True/False indicates the matrix should be read

        .. note:: If you use an already defined table (e.g. OUGV1), it will be ignored.
                  If the table you requested doesn't exist, there will be no effect.
        """
        self.additional_matrices = matrices
        if PY2:
            self.additional_matrices = matrices
        else:
            self.additional_matrices = {}
            for matrix_name, value in iteritems(matrices):
                self.additional_matrices[b(matrix_name)] = value

    def _skip_table_helper(self):
        """
        Skips the majority of geometry/result tables as they follow a very standard format.
        Other tables don't follow this format.
        """
        self.table_name = self.read_table_name(rewind=False)
        if self.is_debug_file:
            self.binary_debug.write('skipping table...%r\n' % self.table_name)
        self.read_markers([-1])
        data = self._skip_record()
        self.read_markers([-2, 1, 0])
        data = self._skip_record()
        self._skip_subtables()

    def _read_omm2(self):
        """
        Parameters
        ----------
        self : OP2
            the OP2 object pointer
        """
        self.log.debug("table_name = %r" % self.table_name)
        self.table_name = self.read_table_name(rewind=False)
        self.read_markers([-1])
        data = self._read_record()

        self.read_markers([-2, 1, 0])
        data = self._read_record()
        if len(data) == 28:
            subtable_name, month, day, year, zero, one = unpack(b(self._endian + '8s5i'), data)
            if self.is_debug_file:
                self.binary_debug.write('  recordi = [%r, %i, %i, %i, %i, %i]\n'  % (subtable_name, month, day, year, zero, one))
                self.binary_debug.write('  subtable_name=%r\n' % subtable_name)
            self._print_month(month, day, year, zero, one)
        else:
            raise NotImplementedError(self.show_data(data))
        self._read_subtables()

    def _read_fol(self):
        """
        Parameters
        ----------
        self : OP2
            the OP2 object pointer
        """
        self.log.debug("table_name = %r" % self.table_name)
        self.table_name = self.read_table_name(rewind=False)
        self.read_markers([-1])
        data = self._read_record()

        self.read_markers([-2, 1, 0])
        data = self._read_record()
        if len(data) == 12:
            subtable_name, double = unpack(b(self._endian + '8sf'), data)
            if self.is_debug_file:
                self.binary_debug.write('  recordi = [%r, %f]\n'  % (subtable_name, double))
                self.binary_debug.write('  subtable_name=%r\n' % subtable_name)
        else:
            strings, ints, floats = self.show_data(data)
            msg = 'len(data) = %i\n' % len(data)
            msg += 'strings  = %r\n' % strings
            msg += 'ints     = %r\n' % str(ints)
            msg += 'floats   = %r' % str(floats)
            raise NotImplementedError(msg)
        self._read_subtables()

    def _read_gpl(self):
        """
        Parameters
        ----------
        self : OP2
            the OP2 object pointer
        """
        self.table_name = self.read_table_name(rewind=False)
        self.log.debug('table_name = %r' % self.table_name)
        if self.is_debug_file:
            self.binary_debug.write('_read_geom_table - %s\n' % self.table_name)
        self.read_markers([-1])
        if self.is_debug_file:
            self.binary_debug.write('---markers = [-1]---\n')
        data = self._read_record()

        markers = self.get_nmarkers(1, rewind=True)
        if self.is_debug_file:
            self.binary_debug.write('---marker0 = %s---\n' % markers)
        n = -2
        while markers[0] != 0:
            self.read_markers([n, 1, 0])
            if self.is_debug_file:
                self.binary_debug.write('---markers = [%i, 1, 0]---\n' % n)

            markers = self.get_nmarkers(1, rewind=True)
            if markers[0] == 0:
                markers = self.get_nmarkers(1, rewind=False)
                break
            data = self._read_record()
            #self.show_data(data, 'i')
            n -= 1
            markers = self.get_nmarkers(1, rewind=True)

    def _read_extdb(self):
        """
        Parameters
        ----------
        self : OP2
            the OP2 object pointer
        """
        self.table_name = self.read_table_name(rewind=False)
        self.log.debug('table_name = %r' % self.table_name)
        if self.is_debug_file:
            self.binary_debug.write('_read_geom_table - %s\n' % self.table_name)
        self.read_markers([-1])
        if self.is_debug_file:
            self.binary_debug.write('---markers = [-1]---\n')
        data = self._read_record()

        markers = self.get_nmarkers(1, rewind=True)
        if self.is_debug_file:
            self.binary_debug.write('---marker0 = %s---\n' % markers)
        self.read_markers([-2, 1, 0])
        data = self._read_record()

        #markers = self.get_nmarkers(3, rewind=False)
        #print('markers =', markers)

        self.read_markers([-3, 1, 0])
        data = self._read_record()

        self.read_markers([-4, 1, 0])
        data = self._read_record()

        self.read_markers([-5, 1, 0])
        data = self._read_record()

        self.read_markers([-6, 1, 0])
        data = self._read_record()

        self.read_markers([-7, 1, 0, 0])
    #self.read_markers([-1])

        #data = self._read_record()

        #markers = self.get_nmarkers(3, rewind=False)
        #print('markers =', markers)

        #self.show_ndata(100)
        #import sys
        #sys.exit()

    def _read_bhh(self):
        """
        Parameters
        ----------
        self : OP2
            the OP2 object pointer
        """
        self.table_name = self.read_table_name(rewind=False)
        self.log.debug('table_name = %r' % self.table_name)
        if self.is_debug_file:
            self.binary_debug.write('_read_geom_table - %s\n' % self.table_name)
        self.read_markers([-1])
        if self.is_debug_file:
            self.binary_debug.write('---markers = [-1]---\n')
        data = self._read_record()

        markers = self.get_nmarkers(1, rewind=True)
        if self.is_debug_file:
            self.binary_debug.write('---marker0 = %s---\n' % markers)
        self.read_markers([-2, 1, 0])
        data = self._read_record()

        n = -3
        markers = self.get_nmarkers(3, rewind=True)
        nmin = -1000
        while nmin < n:
        #for n in [-3, -4, -5, -6, -7, -8, -9, -10, -11]:
            markers = self.get_nmarkers(3, rewind=False)
            if markers[-1] == 0:
                break
            if markers[-1] != 1:
                msg = 'expected marker=1; marker=%s; table_name=%r' % (markers[-1], self.table_name)
                raise FortranMarkerError(msg)
            #self.read_markers([n, 1, 1])
            markers = self.get_nmarkers(1, rewind=False)
            #print('markers =', markers)
            nbytes = markers[0] * 4 + 12
            data = self.f.read(nbytes)
            self.n += nbytes
            n -= 1
        assert n > nmin, 'infinite loop in BHH/KHH reader'
        self.read_markers([0])

    def _read_khh(self):
        """
        Parameters
        ----------
        self : OP2
            the OP2 object pointer
        """
        return self._read_bhh()
        self.table_name = self.read_table_name(rewind=False)
        self.log.debug('table_name = %r' % self.table_name)
        if self.is_debug_file:
            self.binary_debug.write('_read_geom_table - %s\n' % self.table_name)
        self.read_markers([-1])
        if self.is_debug_file:
            self.binary_debug.write('---markers = [-1]---\n')
        data = self._read_record()

        markers = self.get_nmarkers(1, rewind=True)
        if self.is_debug_file:
            self.binary_debug.write('---marker0 = %s---\n' % markers)
        self.read_markers([-2, 1, 0])
        data = self._read_record()

        n = -3
        markers = self.get_nmarkers(3, rewind=True)
        nmin = -1000
        while nmin < n:
        #for n in [-3, -4, -5, -6, -7, -8, -9, -10, -11]:
            print('---------------------------')
            self.show_ndata(200, types='ifs')
            data = self._read_record()
            if 0:
                markers = self.get_nmarkers(3, rewind=False)
                if markers[-1] == 0:
                    break
                if markers[-1] != 1:
                    msg = 'expected marker=1; marker=%s; table_name=%r' % (markers[-1], self.table_name)
                    raise FortranMarkerError(msg)
                #self.read_markers([n, 1, 1])
                markers = self.get_nmarkers(1, rewind=False)
                #print('markers =', markers)
                nbytes = markers[0]*4 + 12
                data = self.f.read(nbytes)
                self.n += nbytes
            n -= 1
        assert n > nmin, 'infinite loop in BHH/KHH reader'
        self.read_markers([0])

    def _read_meff(self):
        """
        Parameters
        ----------
        self : OP2
            the OP2 object pointer
        """
        self.table_name = self.read_table_name(rewind=False)
        self.log.debug('table_name = %r' % self.table_name)
        if self.is_debug_file:
            self.binary_debug.write('_read_geom_table - %s\n' % self.table_name)
        self.read_markers([-1])
        if self.is_debug_file:
            self.binary_debug.write('---markers = [-1]---\n')
        data = self._read_record()

        markers = self.get_nmarkers(1, rewind=True)
        if self.is_debug_file:
            self.binary_debug.write('---marker0 = %s---\n' % markers)
        self.read_markers([-2, 1, 0])
        data = self._read_record()

        for n in [-3, -4, -5, -6, -7, -8]:
            self.read_markers([n, 1, 1])
            markers = self.get_nmarkers(1, rewind=False)
            #print('markers =', markers)
            nbytes = markers[0]*4 + 12
            data = self.f.read(nbytes)
            self.n += nbytes
        n = -9
        self.read_markers([n, 1, 0, 0])

    def _read_intmod(self):
        """reads the INTMOD table"""
        self.table_name = self.read_table_name(rewind=False)
        #self.log.debug('table_name = %r' % self.table_name)
        if self.is_debug_file:
            self.binary_debug.write('_read_geom_table - %s\n' % self.table_name)
        self.read_markers([-1])
        if self.is_debug_file:
            self.binary_debug.write('---markers = [-1]---\n')
        data = self._read_record()
        #print('intmod data1')
        #self.show_data(data)

        markers = self.get_nmarkers(1, rewind=True)
        if self.is_debug_file:
            self.binary_debug.write('---marker0 = %s---\n' % markers)
        self.read_markers([-2, 1, 0])
        data = self._read_record()
        #print('intmod data2')
        #self.show_data(data)

        for n in [-3, -4, -5, -6, -7, -8,]:
            self.read_markers([n, 1, 1])
            markers = self.get_nmarkers(1, rewind=False)
            #print('markers =', markers)
            nbytes = markers[0]*4 + 12
            data = self.f.read(nbytes)
            #print('intmod data%i' % n)
            #self.show_data(data)
            self.n += nbytes

        n = -9
        self.read_markers([n, 1, 0, 0])
        #self.show(50)
        #raise NotImplementedError(self.table_name)


    def _read_hisadd(self):
        """preliminary reader for the HISADD table"""
        self.table_name = self.read_table_name(rewind=False)
        #self.log.debug('table_name = %r' % self.table_name)
        if self.is_debug_file:
            self.binary_debug.write('_read_geom_table - %s\n' % self.table_name)
        self.read_markers([-1])
        if self.is_debug_file:
            self.binary_debug.write('---markers = [-1]---\n')
        data = self._read_record()
        #print('hisadd data1')
        self.show_data(data)

        markers = self.get_nmarkers(1, rewind=True)
        if self.is_debug_file:
            self.binary_debug.write('---marker0 = %s---\n' % markers)
        self.read_markers([-2, 1, 0])
        data = self._read_record()
        print('hisadd data2')
        self.show_data(data)

        self.read_markers([-3, 1, 0])
        markers = self.get_nmarkers(1, rewind=False)
        print('markers =', markers)
        nbytes = markers[0]*4 + 12
        data = self.f.read(nbytes)
        self.n += nbytes
        self.show_data(data[4:-4])
        #self.show(100)
        datai = data[:-4]

        irec = data[:32]
        (design_iter, iconvergence, conv_result, obj_intial, obj_final,
         constraint_max, row_constraint_max, desvar_value) = unpack(b(self._endian + '3i3fif'), irec)
        if iconvergence == 1:
            iconvergence = 'soft'
        elif iconvergence == 2:
            iconvergence = 'hard'

        if conv_result == 0:
            conv_result = 'no'
        elif conv_result == 1:
            conv_result = 'soft'
        elif conv_result == 2:
            conv_result = 'hard'

        print('design_iter=%s iconvergence=%s conv_result=%s obj_intial=%s obj_final=%s constraint_max=%s row_constraint_max=%s desvar_value=%s' % (
            design_iter, iconvergence, conv_result, obj_intial, obj_final, constraint_max, row_constraint_max, desvar_value))
        self.show_data(datai[32:])
        raise NotImplementedError()
        #for n in [-3, -4, -5, -6, -7, -8,]:
            #self.read_markers([n, 1, 1])
            #markers = self.get_nmarkers(1, rewind=False)
            ##print('markers =', markers)
            #nbytes = markers[0]*4 + 12
            #data = self.f.read(nbytes)
            ##print('intmod data%i' % n)
            ##self.show_data(data)
            #self.n += nbytes

        #n = -9
        #self.read_markers([n, 1, 0, 0])

    def get_marker_n(self, nmarkers):
        """
        Gets N markers

        A marker is a flag that is used.  It's a series of 3 ints (4, n, 4)
        where n changes from marker to marker.

        Parameters
        ----------
        self : OP2
            the OP2 object pointer
        nmarkers : int
            the number of markers to read

        Returns
        -------
        markers : List[int, int, int]
            a list of nmarker integers
        """
        markers = []
        s = Struct('3i')
        for i in range(nmarkers):
            block = self.f.read(12)
            marker = s.unpack(block)
            markers.append(marker)
        return markers

    def _read_geom_table(self):
        """
        Reads a geometry table

        Parameters
        ----------
        self : OP2
            the OP2 object pointer
        """
        self.table_name = self.read_table_name(rewind=False)
        if self.is_debug_file:
            self.binary_debug.write('_read_geom_table - %s\n' % self.table_name)
        self.read_markers([-1])
        data = self._read_record()

        self.read_markers([-2, 1, 0])
        data = self._read_record()
        if len(data) == 8:
            subtable_name, = self.struct_8s.unpack(data)
        else:
            strings, ints, floats = self.show_data(data)
            msg = 'Unhandled table length error\n'
            msg += 'table_name = %s\n' % self.table_name
            msg += 'len(data) = %i\n' % len(data)
            msg += 'strings  = %r\n' % strings
            msg += 'ints     = %r\n' % str(ints)
            msg += 'floats   = %r' % str(floats)
            raise NotImplementedError(msg)

        self.subtable_name = subtable_name.rstrip()
        self._read_subtables()

    def _read_frl(self):
        #self.log.debug("table_name = %r" % self.table_name)
        #self.table_name = self.read_table_name(rewind=False)
        #self.read_markers([-1])
        #data = self._read_record()

        #self.read_markers([-2, 1, 0])
        #data = self._read_record()
        self._skip_table(self.table_name)


    def _read_sdf(self):
        """
        Parameters
        ----------
        self : OP2
            the OP2 object pointer
        """
        self.log.debug("table_name = %r" % self.table_name)
        self.table_name = self.read_table_name(rewind=False)
        self.read_markers([-1])
        data = self._read_record()

        self.read_markers([-2, 1, 0])
        data, ndata = self._read_record_ndata()
        if ndata == 16:
            subtable_name, dummy_a, dummy_b = unpack(b(self._endian + '8sii'), data)
            if self.is_debug_file:
                self.binary_debug.write('  recordi = [%r, %i, %i]\n'  % (subtable_name, dummy_a, dummy_b))
                self.binary_debug.write('  subtable_name=%r\n' % subtable_name)
                assert dummy_a == 170, dummy_a
                assert dummy_b == 170, dummy_b
        else:
            strings, ints, floats = self.show_data(data)
            msg = 'len(data) = %i\n' % ndata
            msg += 'strings  = %r\n' % strings
            msg += 'ints     = %r\n' % str(ints)
            msg += 'floats   = %r' % str(floats)
            raise NotImplementedError(msg)

        self.read_markers([-3, 1, 1])

        markers0 = self.get_nmarkers(1, rewind=False)
        record = self.read_block()

        #data = self._read_record()
        self.read_markers([-4, 1, 0, 0])
        #self._read_subtables()

    def _read_results_table(self):
        """
        Reads a results table

        Parameters
        ----------
        self : OP2
            the OP2 object pointer
        """
        if self.is_debug_file:
            self.binary_debug.write('read_results_table - %s\n' % self.table_name)
        self.table_name = self.read_table_name(rewind=False)
        self.read_markers([-1])
        if self.is_debug_file:
            self.binary_debug.write('---markers = [-1]---\n')
            #self.binary_debug.write('marker = [4, -1, 4]\n')
        data = self._read_record()

        self.read_markers([-2, 1, 0])
        if self.is_debug_file:
            self.binary_debug.write('---markers = [-2, 1, 0]---\n')
        data, ndata = self._read_record_ndata()
        if ndata == 8:
            subtable_name = self.struct_8s.unpack(data)
            if self.is_debug_file:
                self.binary_debug.write('  recordi = [%r]\n'  % subtable_name)
                self.binary_debug.write('  subtable_name=%r\n' % subtable_name)
        elif ndata == 28:
            subtable_name, month, day, year, zero, one = unpack(b(self._endian + '8s5i'), data)
            if self.is_debug_file:
                self.binary_debug.write('  recordi = [%r, %i, %i, %i, %i, %i]\n'  % (subtable_name, month, day, year, zero, one))
                self.binary_debug.write('  subtable_name=%r\n' % subtable_name)
            self._print_month(month, day, year, zero, one)
        elif ndata == 612: # ???
            strings, ints, floats = self.show_data(data)
            msg = 'len(data) = %i\n' % ndata
            #msg += 'strings  = %r\n' % strings
            #msg += 'ints     = %r\n' % str(ints)
            #msg += 'floats   = %r' % str(floats)
            print(msg)
            subtable_name, = unpack(b(self._endian) + '8s', data[:8])
            print('subtable_name = %r' % subtable_name.strip())
        else:
            strings, ints, floats = self.show_data(data)
            msg = 'len(data) = %i\n' % ndata
            msg += 'strings  = %r\n' % strings
            msg += 'ints     = %r\n' % str(ints)
            msg += 'floats   = %r' % str(floats)
            raise NotImplementedError(msg)
        if hasattr(self, 'subtable_name'):
            raise RuntimeError('the file hasnt been cleaned up; subtable_name_old=%s new=%s' % (self.subtable_name, subtable_name))
        self.subtable_name = subtable_name
        self._read_subtables()

    def _print_month(self, month, day, year, zero, one):
        """
        Creates the self.date attribute from the 2-digit year.

        Parameters
        ----------
        self : OP2
            the OP2 object pointer
        month : int
            the month (integer <= 12)
        day :  int
            the day (integer <= 31)
        year : int
            the day (integer <= 99)
        zero : int
            a dummy integer (???)
        one : int
            a dummy integer (???)
        """
        month, day, year = self._set_op2_date(month, day, year)

        #self.log.debug("%s/%s/%4i zero=%s one=%s" % (month, day, year, zero, one))
        #if self.is_debug_file:
        if self.is_debug_file:
            self.binary_debug.write('  [subtable_name, month=%i, day=%i, year=%i, zero=%i, one=%i]\n\n' % (month, day, year, zero, one))
        #assert zero == 0, zero  # is this the RTABLE indicator???
        assert one in [0, 1], one  # 0, 50

    def finish(self):
        """
        Clears out the data members contained within the self.words variable.
        This prevents mixups when working on the next table, but otherwise
        has no effect.
        """
        for word in self.words:
            if word != '???' and hasattr(self, word):
                if word not in ['Title', 'reference_point']:
                    delattr(self, word)
        self.obj = None
        if hasattr(self, 'subtable_name'):
            del self.subtable_name


class Matrix(object):
    def __init__(self, name):
        self.name = name
        self.data = None


def main():
    """testing pickling"""
    from pickle import dumps, dump, load, loads
    txt_filename = 'solid_shell_bar.txt'
    pickle_file = open(txt_filename, 'wb')
    op2_filename = 'solid_shell_bar.op2'
    op2 = OP2_Scalar()
    op2.read_op2(op2_filename)
    print(op2.displacements[1])
    dump(op2, pickle_file)
    pickle_file.close()

    pickle_file = open(txt_filename, 'r')
    op2 = load(pickle_file)
    pickle_file.close()
    print(op2.displacements[1])


    #import sys
    #op2_filename = sys.argv[1]

    #o = OP2_Scalar()
    #o.read_op2(op2_filename)
    #(model, ext) = os.path.splitext(op2_filename)
    #f06_outname = model + '.test_op2.f06'
    #o.write_f06(f06_outname)


if __name__ == '__main__':  # pragma: no conver
    main()
