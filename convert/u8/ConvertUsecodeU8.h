/*
 *  Copyright (C) 2002-2005 The Pentagram Team
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

#ifndef CONVERTUSECODEU8_H
#define CONVERTUSECODEU8_H

#ifndef INCLUDE_CONVERTUSECODEU8_WITHOUT_BRINGING_IN_FOLD
#include "Convert.h"
#else

class ConvertUsecode
{
public:
		virtual ~ConvertUsecode() { }	
		class TempOp;
		class Node;
		typedef int DebugSymbol;
		struct UsecodeHeader
		{
			uint32 maxOffset;
		};
		uint32 read4(IDataSource *) { return 0; }
		uint32 curOffset;

		virtual const char* const *intrinsics()=0;
		virtual const char* const *event_names()=0;
		virtual void readheader(IDataSource *ucfile, UsecodeHeader &uch, uint32 &curOffset)=0;
		virtual void readevents(IDataSource *ucfile, const UsecodeHeader &uch)=0;
		virtual void readOp(TempOp &op, IDataSource *ucfile, uint32 &dbg_symbol_offset, std::vector<DebugSymbol> &debugSymbols, bool &done)=0;
		virtual Node *readOp(IDataSource *ucfile, uint32 &dbg_symbol_offset, std::vector<DebugSymbol> &debugSymbols, bool &done)=0;
		void readOpGeneric(TempOp &, IDataSource *, uint32 &, std::vector<DebugSymbol> &,
			bool &, const bool ) { }
		Node *readOpGeneric(IDataSource *, uint32 &, std::vector<DebugSymbol> &,
			bool &, const bool ) { return 0; }
};

#endif

class ConvertUsecodeU8 : public ConvertUsecode
{
	public:
		const char* const *intrinsics()  { return _intrinsics;  };
		const char* const *event_names() { return _event_names; };
		void readheader(IDataSource *ucfile, UsecodeHeader &uch, uint32 &curOffset);
		void readevents(IDataSource *ucfile, const UsecodeHeader &/*uch*/)
		{
#ifndef INCLUDE_CONVERTUSECODEU8_WITHOUT_BRINGING_IN_FOLD
			EventMap.clear();
			for (uint32 i=0; i<32; ++i)
			{
				uint32 offset = read4(ucfile);
				EventMap[offset] = i;
#ifdef DISASM_DEBUG
				pout << "Event " << i << ": " << std::hex << std::setw(4) << offset << std::dec << endl;
#endif
			}
#endif
		}

		void readOp(TempOp &op, IDataSource *ucfile, uint32 &dbg_symbol_offset, std::vector<DebugSymbol> &debugSymbols, bool &done)
		{ readOpGeneric(op, ucfile, dbg_symbol_offset, debugSymbols, done, false); };
		Node *readOp(IDataSource *ucfile, uint32 &dbg_symbol_offset, std::vector<DebugSymbol> &debugSymbols, bool &done)
		{ return readOpGeneric(ucfile, dbg_symbol_offset, debugSymbols, done, false); };

	
	private:
		static const char* const _intrinsics[];
		static const char* const _event_names[];
};

const char* const ConvertUsecodeU8::_intrinsics[] = {
	// 0000
	"Item::touch()",
	"word Item::getX()",
	"word Item::getY()",
	"word Item::getZ()",
	"word Item::getCX()",
	"word Item::getCY()",
	"word Item::getCZ()",
	"Item::getPoint(WorldPoint*)",
	"uword Item::getShape()",
	"void Item::setShape(uword type)",
	"uword Item::getFrame()",
	"void Item::setFrame(uword frame)",
	"uword Item::getQuality()",
	"uword Item::getUnkEggType()",
	"uword Item::getQuantity()",
	"void Item::setQuantity(word value)",
	// 0010
	"Item::getContainer()",
	"Item::getRootContainer()",
	"Item::destroyContents()",
	"Item::destroy()",
	"uword Item::getQ()",
	"void Item::setQ(uword)",
	"void Item::setQuality(word value)",
	"Item::getContents()",
	"word Item::getFamily()",
	"bool Item::getTypeFlag(word bit)",
	"word Item::getStatus()",
	"void Item::orStatus(word mask)",
	"void Item::andStatus(word mask)",
	"Item::ascend(word)",
	"Item::getWeight()",
	"Item::getWeightIncludingContents()",
	// 0020
	"Item::getVolume()",
	"Item::getHeight()",
	"Item::getFamilyOfType()",
	"Item::legalCreateAtPoint()",
	"Item::legalCreateAtCoords()",
	"Item::legalCreateInCont()",
	"Item::create(uword, uword)",
	"Item::pop(uword, uword, ubyte)",
	"Item::popToCoords()",
	"Item::popToContainer()",
	"Item::popToEnd(uword)",
	"Item::move(uword, uword, ubyte)",
	"Item::legalMoveToPoint()",
	"Item::legalMoveToContainer()",
	"Item::legalMoveToParent()",
	"Item::getEtherealTop()",
	// 0030
	"Item::doFormatCollision()",
	"Item::moveToEtherealVoid()",
	"Item::moveToFromEtherealVoid()",
	"Item::isOnScreen()",
	"Item::getZTop()",
	"Item::hasFlags()",
	"Item::getFlags()",
	"Item::setFlag()",
	"Item::clearFlag()",
	"Item::getMapArray()",
	"Item::receiveHit(uword, byte, word, uword)",
	"Item::explode()",
	"Item::canReach(uword, word)",
	"Item::getRange(uword)",
	"Item::getRange2(uword, uword, uword)",
	"Item::getDirToCoords(uword, uword)",
	// 0040
	"Item::getDirFromCoords(uword, uword)",
	"Item::getDirToItem(uword)",
	"Item::getDirFromItem(uword)",
	"Item::getDirFromTo()",
	"Item::setFrameRotateClockwise()",
	"Item::setFrameRotateAntiClockwise()",
	"Item::isMouseDownEvent()",
	"word Item::getSliderInput(word min, word max, word step)",
	"Item::openGump(word)",
	"Item::closeGump()",
	"Item::getSliderValue()",
	"Item::setSliderValue()",
	"Item::setSliderShape()",
	"Item::sliderSetGumpShape()",
	"Item::getNpcNum()",
	"Item::getOwner()",
	// 0050
	"Item::getOwnerObjId()",
	"Item::getMapNum()",
	"Item::isOnMap()",
	"Item::getAttrFlags()",
	"Item::getTalkRange()",
	"Item::setNpcNum()",
	"Item::addTargetObjectId()",
	"Item::removeTargetObjectId()",
	"Item::clearTargetObjectIds()",
	"Item::addTargetMapId()",
	"Item::removeTargetMapId()",
	"Item::clearTargetMapIds()",
	"Item::resetRangedTargetTimer()",
	"Item::setMapNum()",
	"Item::setAttrFlags()",
	"Item::setTalkRange()",
	// 0060
	"Item::getTalkRangeTimer()",
	"Item::isObjIdTarget()",
	"Item::isMapIdTarget()",
	"Actor::isDead()",
	"Actor::getMap()",
	"Actor::getNpcNum()",
	"Actor::getLastActivityNo()",
	"Actor::getAlignment()",
	"Actor::setLastActivityNo()",
	"Actor::setAlignment()",
	"Actor::setTarget()",
	"Actor::setMap()",
	"Actor::getTarget()",
	"Actor::getMapNum()",
	"Actor::createActor()",
	"Actor::setStats()",
	// 0070
	"Actor::getHp()",
	"Actor::setHp()",
	"Actor::getMana()",
	"Actor::setMana()",
	"Actor::getStr()",
	"Actor::setStr()",
	"Actor::getDex()",
	"Actor::setDex()",
	"Actor::getInt()",
	"Actor::setInt()",
	"Actor::getMaxHp()",
	"Actor::getMaxMana()",
	"Actor::getArmorClass()",
	"Actor::isOnScreen()",
	"Actor::createActorFast()",
	"Actor::schedule()",
	// 0080
	"Actor::clownAttack()",
	"MusicProcess::playMusic()",
	"MusicProcess::queueMusic()",
	"MusicProcess::unqueueMusic()",
	"MusicProcess::restoreMusic()",
	"MusicProcess::getNextEggMusicTrack()",
	"MusicProcess::playCombatMusic()",
	"MusicProcess::isPlayingCombatMusic()",
	"MusicProcess::setEggMusic()",
	"Egg::reset()",
	"Egg::getEggId()",
	"Egg::setEggId(uword)",
	"Egg::getEggXRange()",
	"Egg::getEggYRange()",
	"Egg::setEggXRange(uword)",
	"Egg::setEggYRange(uword)",
	// 0090
	"CameraProcess::getCameraX()",
	"CameraProcess::getCameraY()",
	"CameraProcess::getCameraZ()",
	"CameraProcess::setCameraY()",
	"CameraProcess::setEarthquake()",
	"CameraProcess::getEarthquake()",
	"CameraProcess::setCenterOn()",
	"CameraProcess::move_to()",
	"CameraProcess::scrollTo()",
	"CameraProcess::bark()",
	"TeleportEgg::teleport()",
	"Actor::getLastAnimFrame()",
	"Actor::doAnim()",
	"Actor::getDir()",
	"Actor::getLastAnim()",
	"Actor::setDead()",
	// 00A0
	"Actor::getMaxEnergy()",
	"Actor::setMaxEnergy()",
	"Actor::getEnergy()",
	"Actor::setEnergy()",
	"Actor::getMaxStr()",
	"Actor::setMaxStr()",
	"Actor::getImmortal()",
	"Actor::setImmortal()",
	"Actor::getName()",
	"Actor::setName()",
	"Actor::getFlag()",
	"Actor::setFlag()",
	"Actor::clearFlag()",
	"Actor::getInventoryShape()",
	"Actor::setInventoryShape()",
	"Actor::getShield()",
	// 00B0
	"Actor::setShield()",
	"Actor::getMaxDex()",
	"Actor::setMaxDex()",
	"Actor::getMaxInt()",
	"Actor::setMaxInt()",
	"Actor::getImmortal()",
	"Actor::setImmortal()",
	"Actor::getActiveWeapon()",
	"Actor::setActiveWeapon()",
	"Actor::createTimer()",
	"Actor::getXRange()",
	"Actor::getYRange()",
	"Actor::setXRange()",
	"Actor::setYRange()",
	"Actor::getDir()",
	"Actor::getMap()",
	// 00C0
	"Actor::getAlignment()",
	"Actor::setAlignment()",
	"Actor::getEnemyAlignment()",
	"Actor::setEnemyAlignment()",
	"Actor::isEnemyAligned()",
	"Actor::isInParty()",
	"Actor::getLastActivity()",
	"Actor::setLastActivity()",
	"Actor::setInAction()",
	"Actor::setAirWalkEnabled()",
	"Actor::schedule()",
	"Actor::doAnimNo()",
	"Actor::getDirFacing()",
	"Actor::getEquip()",
	"Actor::setEquip()",
	"Actor::getDefaultActivity()",
	// 00D0
	"Actor::setDefaultActivity()",
	"Actor::setHomePosition()",
	"Actor::isKneeling()",
	"Actor::doAnim()",
	"Actor::isDead()",
	"Actor::setActivity()",
	"Actor::getLastAnimFrame()",
	"Actor::getAlignment()",
	"Actor::setAlignment()",
	"Actor::getNpcNum()",
	"Actor::setNpcNum()",
	"Actor::setAirWalkEnabled()",
	"Actor::getMaxEnergy()",
	"Actor::getEnergy()",
	"Actor::setEnergy()",
	"Actor::getMana()",
	// 00E0
	"Actor::setMana()",
	"Actor::getStr()",
	"Actor::setStr()",
	"Actor::getDex()",
	"Actor::setDex()",
	"Actor::getInt()",
	"Actor::setInt()",
	"Actor::getMaxHp()",
	"Actor::getHp()",
	"Actor::setHp()",
	"Actor::getName()",
	"Actor::setName()",
	"Actor::getFlag()",
	"Actor::setFlag()",
	"Actor::clearFlag()",
	"Actor::teleport()",
	// 00F0
	"Actor::getMaxDex()",
	"Actor::setMaxDex()",
	"Actor::getMaxInt()",
	"Actor::setMaxInt()",
	"Actor::getMaxStr()",
	"Actor::setMaxStr()",
	"Actor::setTarget()",
	"Actor::getTarget()",
	"Actor::isInCombat()",
	"Actor::setInCombat()",
	"Actor::terminateCombat()",
	"Actor::isEnemy()",
	"Actor::setEnemy()",
	"Actor::clearEnemy()",
	"Actor::setInAction()",
	"Actor::setLastActivity()",
	// 0100
	"Actor::setImmortal()",
	0
};

const char * const ConvertUsecodeU8::_event_names[] = {
	"look()",						// 0x00
	"use()",						// 0x01
	"anim()",						// 0x02
	"setActivity()",				// 0x03
	"cachein()",					// 0x04
	"hit(uword, word)",				// 0x05
	"gotHit(uword, word)",			// 0x06
	"hatch()",						// 0x07
	"schedule()",					// 0x08
	"release()",					// 0x09
	"equip()",						// 0x0A
	"unequip()",					// 0x0B
	"combine()",					// 0x0C
	"func0D",						// 0x0D
	"calledFromAnim()",				// 0x0E
	"enterFastArea()",				// 0x0F

	"leaveFastArea()",				// 0x10
	"cast(uword)",					// 0x11
	"justMoved()",					// 0x12
	"AvatarStoleSomething(uword)",	// 0x13
	"animGetHit()",					// 0x14
	"guardianBark(word)",			// 0x15
	"func16",						// 0x16
	"func17",						// 0x17
	"func18",						// 0x18
	"func19",						// 0x19
	"func1A",						// 0x1A
	"func1B",						// 0x1B
	"func1C",						// 0x1C
	"func1D",						// 0x1D
	"func1E",						// 0x1E
	"func1F",						// 0x1F
	0
};

void ConvertUsecodeU8::readheader(IDataSource *ucfile, UsecodeHeader &uch, uint32 &curOffset)
{
	#ifdef DISASM_DEBUG
	perr << std::setfill('0') << std::hex;
	perr << "unknown1: " << std::setw(4) << read4(ucfile) << endl; // unknown
	uch.maxOffset = read4(ucfile) - 0x0C; // file size
	perr << "maxoffset: " << std::setw(4) << maxOffset << endl;
	perr << "unknown2: " << std::setw(4) << read4(ucfile) << endl; // unknown
	curOffset = 0;
	#else
	read4(ucfile); // unknown
	uch.maxOffset = read4(ucfile) - 0x0C; // file size
	read4(ucfile); // unknown
	curOffset = 0;
	#endif
};

#endif
