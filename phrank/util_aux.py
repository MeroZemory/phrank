import idaapi
import idautils
import idc

ptr_size = None
get_data = None


def str2strucid(s):
	if s.startswith("struct "):
		s = s[7:]

	rv = idaapi.get_struc_id(s)
	if rv != idaapi.BADADDR:
		return rv

	rv = idaapi.import_type(idaapi.get_idati(), -1, s)
	if rv == idaapi.BADNODE:
		return idaapi.BADADDR
	return rv


def tif2strucid(tif):
	if tif.is_ptr():
		tif = tif.get_pointed_object()

	if tif.is_struct():
		return str2strucid(str(tif))

	if tif.is_int() or tif.is_void():
		return idaapi.BADADDR

	print("ERROR:", "unknown tinfo2strucid", tif)
	raise NotImplementedError


def str2tif(type_str):
	if type_str[-1] != ';': type_str = type_str + ';'

	tinfo = idaapi.tinfo_t()
	idaapi.parse_decl(tinfo, idaapi.get_idati(), type_str, 0)
	if not tinfo.is_correct():
		print("[*] WARNING: Failed to parse type: {}".format(type_str))
		return None
	return tinfo

def get_int_tinfo(size=1):
	char_tinfo = idaapi.tinfo_t()
	if size == 2:
		idaapi.parse_decl(char_tinfo, idaapi.get_idati(), "unsigned short;", 0)
	elif size == 4:
		idaapi.parse_decl(char_tinfo, idaapi.get_idati(), "unsigned int;", 0)
	else:
		idaapi.parse_decl(char_tinfo, idaapi.get_idati(), "unsigned char;", 0)
	assert char_tinfo.is_correct()
	return char_tinfo

def get_voidptr_tinfo():
	voidptr_tinfo = idaapi.tinfo_t()
	idaapi.parse_decl(voidptr_tinfo, idaapi.get_idati(), "void*;", 0)
	assert voidptr_tinfo.is_correct()
	return voidptr_tinfo

def get_voidfunc_tinfo():
	void_func = idaapi.tinfo_t()
	idaapi.parse_decl(void_func, idaapi.get_idati(), "__int64 (*)();", 0)
	assert void_func.is_correct()
	return void_func

def iterate_all_functions():
	for segea in idautils.Segments():
		for funcea in idautils.Functions(segea, idc.get_segm_end(segea)):
			yield funcea


def split_list(l, cond):
	on_true = []
	on_false = []
	for i in l:
		if cond(i):
			on_true.append(i)
		else:
			on_false.append(i)
	return on_true, on_false

def is_func_import(func_ea):
	for segea in idautils.Segments():
		if idc.get_segm_name(segea) != ".idata":
			continue

		segstart, segend = idc.get_segm_start(segea), idc.get_segm_end(segea)
		if func_ea >= segstart and func_ea < segend:
			return True

	return False

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

def is_func_start(addr):
	if addr == idaapi.BADADDR: return False
	return addr == get_func_start(addr)

def get_func_start(addr):
	func = idaapi.get_func(addr)
	if func is None:
		return idaapi.BADADDR
	return func.start_ea

def get_func_calls_to(fea):
	rv = filter(None, [get_func_start(x.frm) for x in idautils.XrefsTo(fea)])
	rv = filter(lambda x: x != idaapi.BADADDR, rv)
	return list(rv)

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

def iterate_segments():
	for segea in idautils.Segments():
		yield idc.get_segm_start(segea), idc.get_segm_end(segea)