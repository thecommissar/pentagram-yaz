/*
 *	FuncNodes.cpp -
 *
 *  Copyright (C) 2002-2003 The Pentagram Team
 *
 *  This program is free software; you can redistribute it and/or modify
 *  it under the terms of the GNU General Public License as published by
 *  the Free Software Foundation; either version 2 of the License, or
 *  (at your option) any later version.
 *
 *  This program is distributed in the hope that it will be useful,
 *  but WITHOUT ANY WARRANTY; without even the implied warranty of
 *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *  GNU General Public License for more details.
 *
 *  You should have received a copy of the GNU General Public License
 *  along with this program; if not, write to the Free Software
 *  Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
 */

#include "pent_include.h"

#include "FuncNodes.h"
#include "Folder.h"
#include "IfNode.h"
#include "OperatorNodes.h"
#include "VarNodes.h"

#include <deque>
using	std::deque;
#include <cstdio>

/****************************************************************************
	FuncMutatorNode
 ****************************************************************************/

void FuncMutatorNode::print_unk(Console &o, const uint32 isize, const bool comment) const
{
	/* if we're in a comment, then we're actually going to output, else we silently
		do nothing. This is to handle the cases where we don't want this data
		such as in non-debugging situations */
	if(!comment && mtype!=SUSPEND) return;
	
	assert(rtype().type()==Type::T_INVALID);
	switch(mtype)
	{
		case RET:	CANT_HAPPEN(); break;
		case INIT:	CANT_HAPPEN(); break;
		case LINE_NUMBER:
			Node::print_linenum_unk(o, isize);
			#if 0
			o.Printf(" /* Line No: %d */ ", _linenum);
			#else
			o.Printf("/*%d*/", _linenum);
			#endif
			break;
		case SYMBOL_INFO:
			Node::print_linenum_unk(o, isize);
			o.Printf("symbol_info_NOPRINT(0x%04X, \"%s\")", _symboloffset, _classname.c_str());
			break;
		case SUSPEND:
			o.Printf("suspend");
			break;
		case END:	CANT_HAPPEN(); break;
		default: assert(print_assert(this)); // can't happen
	}
}

void FuncMutatorNode::print_asm(Console &o) const
{
	assert(rtype().type()==Type::T_INVALID);

	Node::print_linenum_asm(o);
	Node::print_asm(o);
	
	switch(mtype)
	{
		case RET:         print_assert(this); CANT_HAPPEN(); break;
		case INIT:        print_assert(this); CANT_HAPPEN(); break;
		case LINE_NUMBER: o.Printf("line number\t%i (%04Xh)", _linenum, _linenum); break;
		case SYMBOL_INFO: o.Printf("symbol info\toffset %04Xh = \"%s\"", _symboloffset, _classname.c_str()); break;
		case SUSPEND:     o.Printf("suspend"); break;
		case END:         CANT_HAPPEN(); break;
		default: assert(print_assert(this)); // can't happen
	}
}

void FuncMutatorNode::print_bin(ODequeDataSource &o) const
{
	assert(rtype().type()==Type::T_INVALID);
	Node::print_linenum_bin(o);
	switch(mtype)
	{
		case RET:			CANT_HAPPEN(); break;
		case INIT:			CANT_HAPPEN(); break;
		case LINE_NUMBER: o.write1(0x5B); o.write2(_linenum); break;
		case SYMBOL_INFO: o.write1(0x5C); o.write2(_symboloffset - _offset - 3); o.write(_classname.c_str(), _classname.size(), 9); break;
		case SUSPEND:     o.write1(0x53); break;
		case END:			CANT_HAPPEN(); break;
		default: assert(print_assert(this)); // can't happen
	}
}

bool FuncMutatorNode::fold(DCUnit *unit, std::deque<Node *> &nodes)
{
	fold_linenum(nodes);
	
	if(mtype==SYMBOL_INFO)
	{
		unit->setDebugOffset(_symboloffset);
		unit->setClassName(_classname);
	}
	else if(mtype==END)
	{
		// got to do a bit of juggling...
		// ... remove ourselves from the back...
		//assert((nodes.size()>0 && nodes.back()->opcode()==0x7A) || print_assert(this, unit));
		//Node *n = nodes.back();
		//nodes.pop_back();
		//assert(n==this);
		// ... grab the function node...
		assert((nodes.size()>0 && nodes.back()->opcode()==0xFFFF) || print_assert(this, unit));
		DCFuncNode *funcnode=static_cast<DCFuncNode *>(nodes.back());
		funcnode->addEnd(this);
		// ... add ourselves...
		//nodes.push_back(this);
		// ... call the func node's fold with the appriprate parameters...
		//funcnode->fold(unit, nodes);
		return false;
	}
	
	return true;
}

/****************************************************************************
	StartupNode
 ****************************************************************************/

void StartupNode::print_unk(Console &o, const uint32 isize) const
{
	indent(o, isize);
	o.Print("startup");
}

void StartupNode::print_asm(Console &o) const
{
	Node::print_asm(o);
	o.Printf("startup");
}

void StartupNode::print_bin(ODequeDataSource &o) const
{
	(void)o;
}

/****************************************************************************
	DCFuncNode
 ****************************************************************************/
#define DEBUG_COMMENTS

static std::string format_process_type(uint32 process_type)
{
	switch(process_type)
	{
		case 0x0000: return "PT_DEFAULT";
		case 0x00F0: return "PT_ANIM";
		default:
			{
				char buf[16];
				snprintf(buf, sizeof(buf), "PT_%04X", process_type);
				return buf;
			}
	}
}

static std::string format_function_name(const std::string &className, const uint32 classId, const uint32 offset)
{
	char buf[16];
	snprintf(buf, sizeof(buf), "%04X", offset);
	if(!className.empty())
		return className + "::" + buf;
	snprintf(buf, sizeof(buf), "class_%04X_function_%04X", classId, offset);
	return buf;
}

void DCFuncNode::print_unk_funcheader(Console &o, const uint32 isize, const std::string &className, const uint32 classId) const
{
	// do the obvious and spit out 'process'
	// for obvious reason's we're just assuming if a function has a 'process exclude'
	// op at the beginning, it's... a process!
	indent(o, isize);
	if(is_startup)
	{
		if(startupnode!=0)
			startupnode->print_unk(o, isize);
		else
			o.Print("startup");
	}
	else if(has_procexclude)
	{
		o.Printf("process [[%s, referent]] %s()", format_process_type(process_type).c_str(),
			format_function_name(className, classId, func_start_offset).c_str());
	}
	else
	{
		o.Printf("%s()", format_function_name(className, classId, func_start_offset).c_str());
	}
	o.Putchar('\n');
}

void DCFuncNode::print_unk(Console &o, const uint32 isize) const
{
	#ifdef DEBUG_COMMENTS
	indent(o, isize); o.Print("/*"); // prelude

	// 'init'
	indent(o, 1);
	o.Printf("Function Start Offset:\t0x%04X\n", func_start_offset);
	indent(o, isize+1);
	o.Printf("Locals Datasize:\t0x%02X\n", locals_datasize);
	// 'set info'
	indent(o, isize+1);
	o.Printf("Process Type:\t\t0x%04X", process_type);

	assert(debug_thisp==true);	
	//indent(o, isize+1);
	//setinfonode->print_unk(o, isize+1, true);
	
	indent(o, 1); o.Print("*/\n"); // postfix
	#endif
	
	//indent(o, isize);
	//procexcludenode->print_unk(o, isize);
	//o.Putchar('\n');

	for(std::deque<Node *>::const_iterator i=funcnodes.begin(); i!=funcnodes.end(); ++i)
	{
		indent(o, isize);
		(*i)->print_unk(o, isize);
		o.Putchar('\n');
	}

	assert(debug_ret_offset!=0); // 'ret'
	assert(debug_end_offset!=0); // 'end'

	#if 0 // not much use until we've got something to stuff at the end of the function
	//#ifdef DEBUG_COMMENTS
	indent(o, isize); o.Print("/*"); // prelude

	//indent(o, 1);
	//retnode->print_unk(o, isize+1, true);
	//o.Putchar('\n');
	
	//indent(o, isize+1);
	//endnode->print_unk(o, isize+1, true);
	
	indent(o, 1); o.Print("*/\n"); // postfix
	#endif
}

void DCFuncNode::print_asm(Console &o) const
{
	// 'init'
	print_asm_header(o, func_start_offset, 0x5A);
	o.Printf("init\t\t%02X\n", locals_datasize);
	
	setinfonode->print_asm(o);
	o.Putchar('\n');
	
	// 'process exclude'
	print_asm_header(o, debug_procexclude_offset, 0x78);
	o.Printf("process exclude\n");
	//procexcludenode->print_asm(o);
	//o.Putchar('\n');
	
	for(std::deque<Node *>::const_iterator i=funcnodes.begin(); i!=funcnodes.end(); ++i)
	{
		(*i)->print_asm(o);
		o.Putchar('\n');
	}
	
	// 'ret'
	print_asm_header(o, debug_ret_offset, 0x50);
	o.Printf("ret\n");
	
	// 'end'
	print_asm_header(o, debug_end_offset, 0x7A);
	o.Printf("end\n");
}

void DCFuncNode::print_bin(ODequeDataSource &o) const
{
	// 'init'
	print_mac_header(con, func_start_offset, 0x5A);
	o.write1(0x5A);
	o.write1(locals_datasize);
	
	assert(setinfonode!=0);
	setinfonode->print_mac(con);
	setinfonode->print_bin(o);
	
	// 'process exclude'
	print_mac_header(con, debug_procexclude_offset, 0x78);
	o.write1(0x78);
	//assert(procexcludenode!=0);
	//procexcludenode->print_mac(con);
	//procexcludenode->print_bin(o);
	
	for(std::deque<Node *>::const_iterator i=funcnodes.begin(); i!=funcnodes.end(); ++i)
	{
		o.clear();
		(*i)->print_mac(con);
		(*i)->print_bin(o);
		// FIXME: The following is a bit of a hack, just so we get some 'real' output
		for(std::deque<char>::const_iterator i=o.buf().begin(); i!=o.buf().end(); ++i)
			con.Printf("%02X ", static_cast<uint8>(*i));
		con.Putchar('\n');
	}
	
	// 'ret'
	print_mac_header(con, debug_ret_offset, 0x50);
	o.write1(0x50);

	// 'end'
	print_mac_header(con, debug_ret_offset, 0x7A);
	o.write1(0x7A);
}

bool DCFuncNode::fold(DCUnit *unit, std::deque<Node *> &nodes)
{
	assert(nodes.size()>0);
	
	// we get our 'end' later...
	
	// ... get our 'ret'
	fold_ret(unit, nodes);

	// while we haven't gotten init
	while(nodes.size() && !acceptOp(nodes.back()->opcode(), 0x78))
	{
		/*switch(nodes.back()->opcode())
		{
			case 0x5A:
				assert(initnode==0);
				initnode = nodes.back();
				read_last=true;
				break;
			default:*/
				funcnodes.push_front(nodes.back());
		//}
		nodes.pop_back();
	}

	// ... and our 'process exclude'
	fold_procexclude(unit, nodes);

	// ... and our 'set info'
	fold_setinfo(unit, nodes);

	// ... and our 'init'
	fold_init(unit, nodes);

	is_startup = (func_start_offset == 0);
	if(is_startup && startupnode==0)
		startupnode = new StartupNode(func_start_offset);

	// collapse if/else chains into switch/case blocks where possible
	for(std::deque<Node *>::iterator it=funcnodes.begin(); it!=funcnodes.end(); ++it)
	{
		if((*it)->opcode()!=0x51)
			continue;

		IfNode *ifnode = static_cast<IfNode *>(*it);
		const Node *cond = ifnode->a_node();
		if(cond==0 || !acceptOp(cond->opcode(), 0x24))
			continue;

		const BinOperatorNode *cmp = static_cast<const BinOperatorNode *>(cond);
		const Node *baseExpr = cmp->a_lnode();
		if(baseExpr==0)
			continue;

		std::deque<IfNode *> chain;
		std::deque<Node *>::iterator jt = it;
		while(jt!=funcnodes.end() && (*jt)->opcode()==0x51)
		{
			IfNode *caseNode = static_cast<IfNode *>(*jt);
			if(caseNode->itype==IfNode::I_ELSE)
				break;
			const Node *caseCond = caseNode->a_node();
			if(caseCond==0 || !acceptOp(caseCond->opcode(), 0x24))
				break;
			const BinOperatorNode *caseCmp = static_cast<const BinOperatorNode *>(caseCond);
			const PushVarNode *lhs = dynamic_cast<const PushVarNode *>(caseCmp->a_lnode());
			const PushVarNode *rhs = dynamic_cast<const PushVarNode *>(baseExpr);
			if(lhs==0 || rhs==0)
				break;
			if(lhs->dtype().dtype()!=rhs->dtype().dtype() || lhs->dtype().value()!=rhs->dtype().value())
				break;
			chain.push_back(caseNode);
			++jt;
		}

		if(chain.size()<2)
			continue;

		SwitchNode *sw = new SwitchNode(ifnode->offset(), const_cast<Node *>(baseExpr));
		for(std::deque<IfNode *>::const_iterator c=chain.begin(); c!=chain.end(); ++c)
		{
			const BinOperatorNode *caseCmp = static_cast<const BinOperatorNode *>((*c)->a_node());
			CaseNode *caseNode = new CaseNode((*c)->offset(), const_cast<Node *>(caseCmp->a_rnode()));
			caseNode->nodes().insert(caseNode->nodes().end(), (*c)->nodes().begin(), (*c)->nodes().end());
			sw->addCase(caseNode);
			sw->addOriginalNode(*c);
		}

		if(jt!=funcnodes.end() && (*jt)->opcode()==0x51)
		{
			IfNode *elseNode = static_cast<IfNode *>(*jt);
			if(elseNode->itype==IfNode::I_ELSE)
			{
				CaseNode *caseNode = new CaseNode(elseNode->offset(), 0);
				caseNode->nodes().insert(caseNode->nodes().end(), elseNode->nodes().begin(), elseNode->nodes().end());
				sw->addCase(caseNode);
				sw->addOriginalNode(elseNode);
				++jt;
			}
		}

		std::deque<Node *>::iterator eraseStart = it;
		std::deque<Node *>::iterator eraseEnd = jt;
		it = funcnodes.erase(eraseStart, eraseEnd);
		it = funcnodes.insert(it, sw);
	}
	
	// FIXME: This will obviously be false when we're finally implementing
	// inline functions.
	assert((nodes.size()==0) || print_assert(0, unit));
	
	return true;
}

void DCFuncNode::fold_init(DCUnit * /*unit*/, std::deque<Node *> &nodes)
{
	assert(nodes.size() && nodes.back()->opcode()==0x5A);
	FuncMutatorNode *initnode = static_cast<FuncMutatorNode *>(nodes.back());
	nodes.pop_back();
	
	locals_datasize = initnode->a_initsize();
	func_start_offset = initnode->offset();
	
	FORGET_OBJECT(initnode);
}

void DCFuncNode::fold_ret(DCUnit * /*unit*/, std::deque<Node *> &nodes)
{
	assert(nodes.size() && nodes.back()->opcode()==0x50);
	FuncMutatorNode *retnode = static_cast<FuncMutatorNode *>(nodes.back());
	nodes.pop_back();

	debug_ret_offset = retnode->offset();

	FORGET_OBJECT(retnode);
}

void DCFuncNode::fold_setinfo(DCUnit * /*unit*/, std::deque<Node *> &nodes)
{
	assert(nodes.size() && nodes.back()->opcode()==0x77);
	/*DCCallMutatorNode **/setinfonode = static_cast<DCCallMutatorNode *>(nodes.back());
	nodes.pop_back();
	
	// chain of assertions...
	assert(setinfonode->a_lnode()->opcode()==0x0B); // 'push word'
	process_type = static_cast<const PushVarNode *>(setinfonode->a_lnode())->dtype().value();
	debug_processtype_offset= static_cast<const PushVarNode *>(setinfonode->a_lnode())->dtype().value();
	
	assert(setinfonode->a_rnode()->opcode()==0x4C);
	const DCCallMutatorNode *temp_push_indirect = static_cast<const DCCallMutatorNode *>(setinfonode->a_rnode());
	// make sure we're a '*this'
	assert(temp_push_indirect->a_lnode()->rtype()==Type::T_DWORD);
	assert(static_cast<const PushVarNode *>(temp_push_indirect->a_lnode())->dtype().value()==0x06);
	debug_thisp=true;

	//FORGET_OBJECT(setinfonode); 
}

void DCFuncNode::fold_procexclude(DCUnit * /*unit*/, std::deque<Node *> &nodes)
{
	assert(nodes.size() && nodes.back()->opcode()==0x78);
	DCCallMutatorNode *procexcludenode = static_cast<DCCallMutatorNode *>(nodes.back());
	nodes.pop_back();

	// nice and simple!
	has_procexclude=true;
	debug_procexclude_offset = procexcludenode->offset();

	FORGET_OBJECT(procexcludenode);
}
