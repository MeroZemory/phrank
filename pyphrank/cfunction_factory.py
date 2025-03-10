from __future__ import annotations

import idaapi

import pyphrank.settings as settings
import pyphrank.utils as utils

def should_skip_decompiling(func_ea:int) -> bool:
	fname = idaapi.get_name(func_ea)
	if fname is None:
		print("emtpy name %s" % hex(func_ea))
		return True

	if settings.should_skip_by_prefix(fname):
		return True

	# global constructors
	if fname.startswith("_GLOBAL__sub_I_"):
		return True

	dfname = idaapi.demangle_name(fname, idaapi.MNG_NODEFINIT | idaapi.MNG_NORETTYPE)
	if dfname is not None and settings.should_skip_by_prefix(dfname):
		return True

	return False


class CFunctionFactory:
	def __init__(self) -> None:
		self.cached_cfuncs:dict[int, idaapi.cfunc_t] = {}

	def get_cfunc(self, func_ea:int) -> idaapi.cfunc_t|None:
		cfunc = self.cached_cfuncs.get(func_ea)
		if isinstance(cfunc, idaapi.cfunc_t):
			return cfunc
		# Check if it's our sentinel value (-1) indicating a failed decompilation
		if isinstance(cfunc, int) and cfunc == -1:
			return None

		if not settings.DECOMPILE_RECURSIVELY:
			cfunc = utils.decompile_function(func_ea)
			# -1 (instead of None) to cache failed decompilation
			if cfunc is None:
				self.cached_cfuncs[func_ea] = -1
				return None
			self.cached_cfuncs[func_ea] = cfunc
			return cfunc

		decompilation_queue = [func_ea]
		while len(decompilation_queue) != 0:
			func_ea = decompilation_queue[-1]
			new_functions_to_decompile = set()
			for subcall in utils.get_func_calls_from(func_ea):
				if subcall in self.cached_cfuncs:
					continue
				if subcall in decompilation_queue:
					continue
				new_functions_to_decompile.add(subcall)

			if len(new_functions_to_decompile) == 0:
				cfunc = utils.decompile_function(func_ea)
				if cfunc is None: 
					self.cached_cfuncs[func_ea] = -1
				else:
					self.cached_cfuncs[func_ea] = cfunc
				decompilation_queue.pop()
			else:
				decompilation_queue += list(new_functions_to_decompile)

		cfunc = self.cached_cfuncs.get(func_ea)
		# Check if it's our sentinel value (-1) indicating a failed decompilation
		if isinstance(cfunc, int) and cfunc == -1:
			return None
		return cfunc

	def clear_cfunc(self, func_ea:int) -> None:
		self.cached_cfuncs.pop(func_ea, None)

	def set_cfunc(self, cfunc:idaapi.cfunc_t):
		self.cached_cfuncs[cfunc.entry_ea] = cfunc

	def decompile_all(self):
		saved_decomp = settings.DECOMPILE_RECURSIVELY
		settings.DECOMPILE_RECURSIVELY = True
		for func_ea in utils.iterate_all_functions():
			self.get_cfunc(func_ea)
		settings.DECOMPILE_RECURSIVELY = saved_decomp