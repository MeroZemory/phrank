from __future__ import annotations

import idaapi

import phrank.utils as utils
from phrank.ast_analysis import *


class ASTAnalyzer(idaapi.ctree_visitor_t):
	def __init__(self):
		idaapi.ctree_visitor_t.__init__(self, idaapi.CV_FAST)
		self.current_ast_analysis: ASTAnalysis = None # type:ignore

	def analyze_cfunc(self, cfunc: idaapi.cfunc_t) -> ASTAnalysis:
		actx = ASTCtx.from_cfunc(cfunc)
		self.current_ast_analysis = ASTAnalysis(actx)
		self.apply_to(cfunc.body, None)

		rv, self.current_ast_analysis = self.current_ast_analysis, None # type:ignore
		return rv

	def visit_insn(self, insn: idaapi.cinsn_t) -> int:
		if insn.op == idaapi.cit_return and self.handle_return(insn):
			self.prune_now()
		return 0

	def visit_expr(self, expr: idaapi.cexpr_t) -> int:
		if expr.op == idaapi.cot_asg:
			should_prune = self.handle_assignment(expr)
		elif expr.op == idaapi.cot_call:
			should_prune = self.handle_call(expr)
		else:
			should_prune = self.handle_expr(expr)

		if should_prune:
			self.prune_now()

		return 0

	def handle_return(self, insn:idaapi.cinsn_t) -> bool:
		actx = self.current_ast_analysis.actx
		retval = utils.strip_casts(insn.creturn.expr)

		# FIXME
		if retval.op == idaapi.cot_num:
			return True

		if len(extract_vars(retval, actx)) > 1:
			print("WARNING:", "found multiple variables in return value", utils.expr2str(retval))
			return True

		vuc = get_var_use_chain(retval, actx)
		if vuc is None:
			print("WARNING:", "failed to calculate return value use chain", utils.expr2str(retval))
			return True

		var, uses = vuc.var, vuc.uses
		rw = ReturnWrapper(var, retval, *uses)
		self.current_ast_analysis.returns.append(rw)
		return True

	def handle_call(self, expr:idaapi.cexpr_t) -> bool:
		actx = self.current_ast_analysis.actx

		fc = FuncCall(expr)
		self.current_ast_analysis.calls.append(fc)
		if fc.is_implicit():
			if len(extract_vars(expr.x, actx)) > 1:
				print("WARNING:", "found multiple variables in call argument", utils.expr2str(expr.x))
			else:
				fc.implicit_var_use_chain = get_var_use_chain(expr.x, actx)
				if fc.implicit_var_use_chain is None:
					print("WARNING:", "failed to get var use chain of implicit call for", utils.expr2str(expr.x))

		for arg_id, arg in enumerate(expr.a):
			self.apply_to_exprs(arg, None)
			arg = utils.strip_casts(arg)
			if arg.op in [idaapi.cot_num, idaapi.cot_sizeof, idaapi.cot_call]:
				continue

			if len(extract_vars(arg, actx)) > 1:
				print("WARNING:", "found multiple variables in call argument", utils.expr2str(arg))
				continue

			vuc = get_var_use_chain(arg, actx)
			if vuc is None:
				print("WARNING:", "failed to calculate call argument chain", utils.expr2str(arg))
				continue

			var, uses = vuc.var, vuc.uses
			cast = CallCast(var, arg_id, fc, *uses)
			self.current_ast_analysis.call_casts.append(cast)
		return True

	def handle_assignment(self, expr: idaapi.cexpr_t) -> bool:
		actx = self.current_ast_analysis.actx

		self.apply_to(expr.y, None)

		if len(extract_vars(expr.x, actx)) > 1:
			print("WARNING:", "found multiple variables in write target", utils.expr2str(expr.x))
			return True

		vuc = get_var_use_chain(expr.x, actx)
		if vuc is None:
			print("WARNING:", "failed to calculate write target chain", utils.expr2str(expr.x))
			return True

		var, uses = vuc.var, vuc.uses
		w = VarWrite(var, expr.y, *uses)
		self.current_ast_analysis.var_writes.append(w)
		return True

	def handle_expr(self, expr:idaapi.cexpr_t) -> bool:
		actx = self.current_ast_analysis.actx

		# FIXME
		if expr.op == idaapi.cot_num:
			return True

		if len(extract_vars(expr, actx)) > 1:
			print("WARNING:", "found multiple variables in read", utils.expr2str(expr))
			return True

		vuc = get_var_use_chain(expr, actx)
		if vuc is None:
			print("WARNING:", "failed to calculate read chain", utils.expr2str(expr))
			return True

		var, uses = vuc.var, vuc.uses
		r = VarRead(var, *uses)
		self.current_ast_analysis.var_reads.append(r)
		return True