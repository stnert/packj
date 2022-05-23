#
# Based on MalOSS:  https://github.com/osssanitizer/maloss
#

import os
import ast
import logging
from collections import Counter
from os.path import basename

import asttokens

import proto.python.ast_pb2 as ast_pb2
from util.job_util import read_proto_from_file, write_proto_to_file, exec_command
from util.job_util import write_dict_to_file
from util.enum_util import LanguageEnum
from .static_base import StaticAnalyzer
from proto.python.ast_pb2 import PkgAstResults, AstLookupConfig

logging.getLogger().setLevel(logging.ERROR)

from static_proxy.astgen_py3 import py3_astgen
from static_proxy.astgen_py import py_astgen

class PyAnalyzer(StaticAnalyzer):
    def __init__(self):
        super(PyAnalyzer, self).__init__()
        self.language = LanguageEnum.python

    def astgen(self, inpath, outfile, root=None, configpath=None, pkg_name=None, pkg_version=None, evaluate_smt=False):
        analyze_path, is_decompress_path, outfile, root, configpath = self._sanitize_astgen_args(
            inpath=inpath, outfile=outfile, root=root, configpath=configpath, language=self.language)

        # try python2
        try:
            # load the config proto
            configpb = AstLookupConfig()
            read_proto_from_file(configpb, configpath, binary=False)

            logging.debug("loaded lookup config from %s:\n%s", configpath, configpb)

            # invoke the language specific ast generators to call functions
            py3_astgen(inpath=analyze_path, outfile=outfile, configpb=configpb, root=root, pkg_name=pkg_name, pkg_version=pkg_version)

        # try python2
        except SyntaxError as se:
            logging.warning("Syntax error %s, now trying to parse %s again in python2!", se, analyze_path)
            astgen_py2_cmd = ['python', 'astgen_py.py', analyze_path, outfile, '-c', configpath]
            if root is not None:
                astgen_py2_cmd.extend(['-b', root])
            if pkg_name is not None:
                astgen_py2_cmd.extend(['-n', pkg_name])
            if pkg_version is not None:
                astgen_py2_cmd.extend(['-v', pkg_version])
            exec_command("python2 astgen", astgen_py2_cmd, cwd="static_proxy")
        except Exception as e:
            logging.error("Fatal error %s running astgen for %s!" % (str(e), analyze_path))

        # optionally evaluate smt formula
        if evaluate_smt:
            resultpb = PkgAstResults()
            read_proto_from_file(resultpb, filename=outfile, binary=False)
            satisfied = self._check_smt(astgen_results=[resultpb], configpath=configpath)
            resultpb.pkgs[0].config.smt_satisfied = satisfied
            write_proto_to_file(resultpb, filename=outfile, binary=False)

        # clean up residues
        self._cleanup_astgen(analyze_path=analyze_path, is_decompress_path=is_decompress_path)
