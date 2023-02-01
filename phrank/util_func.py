from __future__ import annotations

import idaapi
import idc
import idautils
import re

def is_func_start(addr:int) -> bool:
	if addr == idaapi.BADADDR: return False
	return addr == get_func_start(addr)

def get_func_start(addr:int) -> int:
	func = idaapi.get_func(addr)
	if func is None:
		return idaapi.BADADDR
	return func.start_ea

def get_func_calls_to(fea:int) -> list[int]:
	rv = filter(None, [get_func_start(x.frm) for x in idautils.XrefsTo(fea)])
	rv = filter(lambda x: x != idaapi.BADADDR, rv)
	return list(rv)

def get_func_calls_from(fea:int) -> list[int]:
	return [x.to for r in idautils.FuncItems(fea) for x in idautils.XrefsFrom(r, 0) if x.type == idaapi.fl_CN or x.type == idaapi.fl_CF]

# finds connection in call-graph for selected functions
def got_path(fea:int, funcs) -> bool:
	if isinstance(funcs, set):
		_funcs = funcs
	else:
		_funcs = set(funcs)

	calls_from_to = set()
	calls_from_to.update(get_func_calls_to(fea))
	calls_from_to.update(get_func_calls_from(fea))
	return len(_funcs & calls_from_to) != 0

def get_single_block_func_instructions(func_ea:int) -> list[int]:
	block_count = 0
	for b in idautils.Chunks(func_ea):
		block_count += 1
	if block_count > 1:
		return []

	rv = []
	for b in idautils.Chunks(func_ea):
		for h in idautils.Heads(b[0], b[1]):
			rv.append(h)
	return rv

def is_func_import(func_ea:int) -> bool:
	for segea in idautils.Segments():
		if idc.get_segm_name(segea) != ".idata":
			continue

		segstart, segend = idc.get_segm_start(segea), idc.get_segm_end(segea)
		if func_ea >= segstart and func_ea < segend:
			return True

	return False

def iterate_all_functions():
	for segea in idautils.Segments():
		for funcea in idautils.Functions(segea, idc.get_segm_end(segea)):
			yield funcea

def is_movrax_ret(func_ea:int) -> bool:
	instrs = get_single_block_func_instructions(func_ea)
	if len(instrs) != 2:
		return False

	# first is xor rax|eax
	disasm = idc.GetDisasm(instrs[0])
	p1 = re.compile("xor[ ]*(eax|rax), (eax|rax).*")  # mov rax, 0
	p2 = re.compile("mov[ ]*(eax|rax), \d+.*")        # mov rax, !0
	if re.fullmatch(p1, disasm) is None and re.fullmatch(p2, disasm) is None:
		return False

	# second is retn
	disasm = idc.GetDisasm(instrs[1])
	if not disasm.startswith("retn"):
		return False
	return True

def decompile_function(func_ea:int) -> idaapi.cfunc_t|None:
	try:
		cfunc = idaapi.decompile(func_ea)
		str(cfunc)
		return cfunc
	except idaapi.DecompilationFailure:
		print("failed to decompile", hex(func_ea), idaapi.get_name(func_ea))
		return None