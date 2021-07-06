import idaapi
import idautils

ptr_size = None
get_data = None


def is_func_import(func_ea):
	return

def get_next_available_strucname(strucname):
	while idaapi.get_struc_id(strucname) != idaapi.BADADDR:
		prefix, ctr = strucname.rsplit('_', 1)
		strucname = prefix + '_' + str(int(ctr) + 1)
	return strucname

# inner *__shifted(outer, offset)
def make_shifted_ptr(outer, inner, offset):
	shifted_tif = idaapi.tinfo_t()
	pi = idaapi.ptr_type_data_t()
	pi.taptr_bits = idaapi.TAPTR_SHIFTED
	pi.delta = offset
	pi.parent = outer
	pi.obj_type = inner
	shifted_tif.create_ptr(pi)
	return shifted_tif

# finds connection in call-graph for selected functions
def got_path(fea, funcs):
	if isinstance(funcs, set):
		_funcs = funcs
	else:
		_funcs = set(funcs)

	calls_from_to = set()
	calls_from_to.update(get_func_calls_to(fea))
	calls_from_to.update(get_func_calls_from(fea))
	return len(_funcs & calls_from_to) != 0

def get_func_start(addr):
	func = idaapi.get_func(addr)
	if func is None:
		return idaapi.BADADDR
	return func.start_ea

def get_func_calls_to(fea):
	return list(filter(None, [get_func_start(x.frm) for x in idautils.XrefsTo(fea)]))

def get_func_calls_from(fea):
	return [x.to for r in idautils.FuncItems(fea) for x in idautils.XrefsFrom(r, 0) if x.type == idaapi.fl_CN or x.type == idaapi.fl_CF]

def get_ptr_size():
	global ptr_size
	global get_data

	if ptr_size is None:
		info = idaapi.get_inf_structure()
		if info.is_64bit():
			ptr_size = 8
			get_data = idaapi.get_qword
		elif info.is_32bit():
			ptr_size = 4
			get_data = idaapi.get_dword
		else:
			ptr_size = 2
			get_data = idaapi.get_word

	return ptr_size

def read_ptr(addr):
	global get_data
	global ptr_size

	if get_data is None:
		info = idaapi.get_inf_structure()
		if info.is_64bit():
			ptr_size = 8
			get_data = idaapi.get_qword
		elif info.is_32bit():
			ptr_size = 4
			get_data = idaapi.get_dword
		else:
			ptr_size = 2
			get_data = idaapi.get_word

	return get_data(addr)

def size2dataflags(sz):
	df = {8: idaapi.FF_QWORD, 4: idaapi.FF_DWORD, 2: idaapi.FF_WORD, 1: idaapi.FF_BYTE}[sz]
	return df | idaapi.FF_DATA