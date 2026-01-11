#ifndef GLOBALNAMES_H
#define GLOBALNAMES_H

#include <map>
#include <string>

#include "common_types.h"

class GlobalName
{
	public:
		GlobalName(const uint32 _offset=0, const uint32 _size=0,
			const std::string _name=std::string())
		: offset(_offset), size(_size), name(_name) {};

		uint32	offset; //the offset into the char[]
		uint32	size; //the number of bytes stored in the global
		std::string	name; //the name of the global
};

extern std::map<uint32, GlobalName> GlobalNames;

inline const GlobalName * const findGlobalName(const uint32 offset)
{
	std::map<uint32, GlobalName>::const_iterator it = GlobalNames.find(offset);
	if (it == GlobalNames.end())
		return 0;
	return &it->second;
}

#endif
