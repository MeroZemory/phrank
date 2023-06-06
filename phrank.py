
# forward imports
from pyphrank.analyzers.cpp_class_analyzer import CppClassAnalyzer
from pyphrank.analyzers.type_analyzer import TypeAnalyzer
from pyphrank.ast_analyzer import CTreeAnalyzer, get_var, get_var_use_chain, extract_vars
from pyphrank.cfunction_factory import CFunctionFactory
from pyphrank.containers.structure import Structure
from pyphrank.containers.union import Union
from pyphrank.containers.ida_struc_wrapper import IdaStrucWrapper
from pyphrank.containers.vtable import Vtable
from pyphrank.ast_analysis import ASTAnalysis
import pyphrank.settings as settings

from pyphrank.utils import *
from pyphrank.ast_parts import *


def propagate_var(var:Var):
	struct_analyzer = TypeAnalyzer()
	var_type = struct_analyzer.get_db_var_type(var)
	struct_analyzer.set_var_type(var, var_type)
	strucid = tif2strucid(var_type)
	struct_analyzer.new_types.add(strucid)
	struct_analyzer.propagate_var(var)
	struct_analyzer.apply_analysis()