from __future__ import annotations
import idaapi
import idaapi
import time

import pyphrank.utils as utils
import pyphrank.settings as settings

from pyphrank.type_flow_graph_parts import Var, ASTCtx
from pyphrank.ast_analyzer import extract_vars
from pyphrank.type_analyzer import TypeAnalyzer



def get_lvar_id(cfunc, lvar_arg):
	for lvar_id, lvar in enumerate(cfunc.lvars):
		if lvar_arg.name == lvar.name:
			return lvar_id
	return -1


class PluginActionHandler(idaapi.action_handler_t):
	def __init__(self, action_name, label, plugin:IDAPlugin, hotkey=None):
		idaapi.action_handler_t.__init__(self)
		self.action_name = action_name
		self.hotkey = hotkey
		self.label = label
		self.plugin = plugin

	def _get_analyzer(self):
		if self.plugin is None:
			raise ValueError("Plugin is not set in its action")
		return self.plugin.type_analyzer
	
	def can_activate(self, ctx):
		if ctx.widget_type != idaapi.BWN_PSEUDOCODE:
			return False
		return True

	def activate(self, ctx):
		if not self.can_activate(ctx):
			return 0

		hx_view = idaapi.get_widget_vdui(ctx.widget)
		cfunc = hx_view.cfunc
		func_ea = cfunc.entry_ea
		if utils.is_cfunc_bugged(cfunc):
			idaapi.mark_cfunc_dirty(func_ea)
			hx_view.refresh_view(1)
			nargs = cfunc.type.get_nargs()
			utils.log_critical(
				f"{idaapi.get_name(func_ea)} is bugged: "\
				f"signature_args={[str(cfunc.type.get_nth_arg(i)) for i in range(nargs)]} but "\
				f"args={[str(a.type()) for a in cfunc.arguments]}. "\
				f"Pseudocode refreshed, repeat action."
			)
			return 1

		# updating caches
		self.plugin.type_analyzer.func_manager.func_factory.set_cfunc(cfunc)
		self.plugin.type_analyzer.get_tfg(func_ea, nocache=True)

		citem = hx_view.item

		should_refresh = 0
		if citem.citype == idaapi.VDI_EXPR:
			citem = citem.it.to_specific_type
			should_refresh = self.activate_item(cfunc, citem)
		elif citem.citype == idaapi.VDI_LVAR:
			lvar_id = get_lvar_id(cfunc, citem.l)
			if lvar_id == -1:
				utils.log_err(f"failed to get local variable id for {citem.l}")
				should_refresh = 0
			else:
				var = Var(func_ea, lvar_id)
				should_refresh = self.activate_var(var)
		elif citem.citype == idaapi.VDI_FUNC:
			should_refresh = self.activate_function(func_ea)

		if should_refresh == 1:
			hx_view.refresh_view(1)
		return should_refresh

	def activate_item(self, cfunc, citem) -> int:
		raise NotImplementedError()

	def activate_var(self, var:Var) -> int:
		raise NotImplementedError()

	def activate_function(self, func_ea:int) -> int:
		raise NotImplementedError()

	def update(self, ctx):
		return idaapi.AST_ENABLE_ALWAYS

	def register(self):
		current_state = idaapi.get_action_state(self.action_name)
		if current_state[0]:
			idaapi.unregister_action(self.action_name)
		idaapi.register_action(
			idaapi.action_desc_t(self.action_name, self.label, self, self.hotkey)
		)
		idaapi.update_action_state(self.action_name, idaapi.AST_ENABLE_ALWAYS)


class TFGPrinter(PluginActionHandler):
	def print_var_tfg(self, var:Var):
		tfg = self._get_analyzer().get_all_var_uses(var, nocache=True)
		tfg.print(f"TypeFlowGraph for {var}")

	def activate_function(self, func_ea:int):
		tfg = self._get_analyzer().get_tfg(func_ea, nocache=True)
		tfg.print(f"TypeFlowGraph for {idaapi.get_name(func_ea)}")
		return 0

	def activate_var(self, var:Var) -> int:
		self.print_var_tfg(var)
		return 0

	def activate_item(self, cfunc, citem) -> int:
		citem = utils.strip_casts(citem)
		if citem.op == idaapi.cot_obj and not utils.is_func_start(citem.obj_ea):
			var = Var(citem.obj_ea)
			self.print_var_tfg(var)

		elif citem.op == idaapi.cot_var:
			var = Var(cfunc.entry_ea, citem.v.idx)
			self.print_var_tfg(var)

		else:
			self.activate_function(cfunc.entry_ea)

		return 0


class ItemAnalyzer(PluginActionHandler):
	def handle_var(self, var:Var):
		analyzer = self._get_analyzer()
		start = time.time()
		analyzer.analyze_var(var)
		if self.plugin.should_apply_analysis:
			analyzer.apply_analysis()
		utils.log_info(f"Analysis completed in {time.time() - start}")

	def handle_function(self, func_ea:int):
		"""
		Will analyze retval and all arguments
		"""
		analyzer = self._get_analyzer()
		start = time.time()
		for i in range(analyzer.func_manager.get_args_count(func_ea)):
			analyzer.analyze_var(Var(func_ea, i))

		analyzer.analyze_retval(func_ea)
		if self.plugin.should_apply_analysis:
			analyzer.apply_analysis()
		utils.log_info(f"Analysis completed in {time.time() - start}")

	def activate_function(self, func_ea:int):
		"""
		Will analyze retval and all local variables
		"""
		analyzer = self._get_analyzer()
		start = time.time()
		for i in range(analyzer.func_manager.get_lvars_counter(func_ea)):
			analyzer.analyze_var(Var(func_ea, i))

		analyzer.analyze_retval(func_ea)
		if self.plugin.should_apply_analysis:
			analyzer.apply_analysis()
		utils.log_info(f"Analysis completed in {time.time() - start}")
		return 1

	def activate_var(self, var:Var) -> int:
		self.handle_var(var)
		return 1

	def activate_item(self, cfunc, citem) -> int:
		if not citem.is_expr():
			return 0

		citem = utils.strip_casts(citem)

		if citem.op == idaapi.cot_obj:
			if utils.is_func_start(citem.obj_ea):
				self.handle_function(citem.obj_ea)
				return 1

			var = Var(citem.obj_ea)
			return self.activate_var(var)

		if citem.op == idaapi.cot_call:
			if citem.x.op == idaapi.cot_obj and utils.is_func_start(citem.x.obj_ea):
				self.handle_function(citem.obj_ea)
				return 1

		if citem.op == idaapi.cot_var:
			var = Var(cfunc.entry_ea, citem.v.idx)
			return self.activate_var(var)

		actx = ASTCtx.from_cfunc(cfunc)
		vars = extract_vars(citem, actx)
		if len(vars) == 1:
			var = vars.pop()
			return self.activate_var(var)

		utils.log_info(f"unknown citem under cursor {citem.opname}")
		return 0


class IDAPlugin(idaapi.plugin_t):
	instance = None

	flags = 0
	wanted_name = "phrank"
	comment = ""
	help = ""
	wanted_hotkey = ""

	def __init__(self) -> None:
		super().__init__()
		# will calculate size of the pointer in variable at cursor
		# then will create struct structure with that size or adjust size of existing one
		# then will set variable to new type, if created
		self.actions: list[PluginActionHandler] = []
		self.type_analyzer = TypeAnalyzer()
		self.should_apply_analysis = True

	@classmethod
	def get_instance(cls):
		if cls.instance is None:
			cls.instance = cls()
		return cls.instance

	def init(self):
		if not idaapi.init_hexrays_plugin():
			return idaapi.PLUGIN_SKIP

		utils.create_logger()
		settings.PTRSIZE = utils.get_pointer_size()

		self.actions.append(
			ItemAnalyzer("phrank::item_analyzer", "analyze item under cursor and its dependencies", self, "Shift-A")
		)
		self.actions.append(
			TFGPrinter("phrank::tfg_printer", "print TypeFlowGraph for variable/function under cursor", self, "Alt-T")
		)
		for action in self.actions:
			action.register()

		return idaapi.PLUGIN_KEEP

	def run(self, arg):
		return

	def term(self):
		for action in self.actions:
			idaapi.unregister_action(action.action_name)
		self.actions = []
		return