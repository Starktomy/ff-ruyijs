#pragma once
#ifdef _WIN32
struct IDWriteFontFace;
#else
class SkTypeface;
using IDWriteFontFace = SkTypeface;
#endif
