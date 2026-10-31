// Grid layout (CSS Grid 1): explicit tracks from grid-template-columns/rows
// (lengths, percentages, fr, auto, min-/max-content, minmax(), repeat() with a
// count, auto-fill or auto-fit), implicit rows from grid-auto-rows, row-major
// auto-placement with line numbers and spans, the track sizing algorithm
// (§12: base sizes, growth limits, maximize, flexible tracks, stretch auto),
// gaps, implicit columns, and item alignment. Named lines/areas and column-
// major auto-placement are not resolved by this box model.
#include "domain/styling/box_layout_internal.h"
#include "domain/styling/css_numeric_value.h"
#include "domain/styling/css_components.h"
#include <cstdlib>

namespace ruyijs::domain::styling {
namespace {
constexpr size_t kMaxTracks = 1000;
struct Track { double min = 0, max = 0, fr = 0; bool min_auto = false, max_auto = false; double base = 0, limit = 0; };
std::vector<std::string> Words(const std::string& text) {
  std::vector<std::string> out;
  int depth = 0;
  std::string word;
  for (char c : text) {
    if (c == '(') ++depth;
    if (c == ')') --depth;
    if ((c == ' ' || c == '\t' || c == '\n') && depth == 0) { if (!word.empty()) out.push_back(word); word.clear(); }
    else word.push_back(c);
  }
  if (!word.empty()) out.push_back(word);
  return out;
}
bool Length(const BoxStyle& style, const std::string& text, double percent, double* out) {
  if (text.find('%') != text.npos && !std::isfinite(percent)) return false;
  const auto value = CssNumericResolve(text, style.font_size, style.root_font_size, std::isfinite(percent) ? percent : 0);
  if (!value.kind || (value.kind != CssLength && value.number != 0)) return false;
  *out = std::max(0.0, value.number);
  return true;
}
// One <track-size>: a breadth or minmax(min, max).
Track Size(const BoxStyle& style, const std::string& text, double percent) {
  Track track;
  auto side = [&](const std::string& part, bool maximum) {
    double value = 0;
    if (part.size() > 2 && part.compare(part.size() - 2, 2, "fr") == 0) {
      if (maximum) track.fr = std::max(0.0, std::strtod(part.c_str(), nullptr));
      else track.min_auto = true;  // An fr minimum behaves as auto.
      return;
    }
    if (Length(style, part, percent, &value)) { (maximum ? track.max : track.min) = value; return; }
    (maximum ? track.max_auto : track.min_auto) = true;  // auto, min-content, max-content, fit-content
  };
  if (text.rfind("minmax(", 0) == 0 && text.back() == ')') {
    const auto inner = text.substr(7, text.size() - 8);
    const auto comma = inner.find(',');
    side(CssTrim(inner.substr(0, comma)), false);
    side(CssTrim(comma == inner.npos ? std::string() : inner.substr(comma + 1)), true);
  } else {
    side(text, true);
    if (track.fr > 0) track.min_auto = true;
    else { track.min = track.max; track.min_auto = track.max_auto; }
  }
  return track;
}
std::vector<Track> Tracks(const BoxStyle& style, const std::string& text, double room, double gap) {
  std::vector<Track> out;
  if (text.empty() || text == "none") return out;
  for (const auto& word : Words(text)) {
    if (word.front() == '[') continue;  // line names
    if (word.rfind("repeat(", 0) != 0 || word.back() != ')') { out.push_back(Size(style, word, room)); continue; }
    const auto inner = word.substr(7, word.size() - 8);
    const auto comma = inner.find(',');
    if (comma == inner.npos) continue;
    const auto how = CssTrim(inner.substr(0, comma));
    std::vector<Track> list;
    for (const auto& part : Words(CssTrim(inner.substr(comma + 1))))
      if (part.front() != '[') list.push_back(Size(style, part, room));
    if (list.empty()) continue;
    size_t count = std::strtoul(how.c_str(), nullptr, 10);
    if (how == "auto-fill" || how == "auto-fit") {
      double each = 0;
      for (const auto& t : list) each += (t.max_auto || t.fr > 0 ? t.min : std::max(t.min, t.max)) + gap;
      count = each > 0 && std::isfinite(room) ? std::max<size_t>(1, size_t((room + gap) / each)) : 1;
    }
    for (size_t i = 0; i < count && out.size() < kMaxTracks; ++i) out.insert(out.end(), list.begin(), list.end());
  }
  if (out.size() > kMaxTracks) out.resize(kMaxTracks);
  return out;
}
// A line placement: start line (1-based, 0 = auto) and span.
void Line(const BoxStyle& style, const char* axis, size_t* start, size_t* span) {
  auto start_text = style.Get((std::string("grid-") + axis + "-start").c_str());
  auto end_text = style.Get((std::string("grid-") + axis + "-end").c_str());
  const auto shorthand = style.Get((std::string("grid-") + axis).c_str());
  if (!shorthand.empty() && (start_text.empty() || start_text == "auto")) {
    const auto slash = shorthand.find('/');
    start_text = CssTrim(shorthand.substr(0, slash));
    if (slash != shorthand.npos) end_text = CssTrim(shorthand.substr(slash + 1));
  }
  const auto area = CssSplit(style.Get("grid-area"), '/');
  const size_t first = std::string(axis) == "row" ? 0 : 1;
  if (start_text.empty() && first < area.size()) start_text = CssTrim(area[first]);
  if (end_text.empty() && first + 2 < area.size()) end_text = CssTrim(area[first + 2]);
  *start = 0; *span = 1;
  const auto parse_span = [](const std::string& t) { return t.rfind("span", 0) == 0 ? std::max(1L, std::strtol(t.c_str() + 4, nullptr, 10)) : 0L; };
  if (const long s = parse_span(start_text)) *span = size_t(s);
  else if (const long n = std::strtol(start_text.c_str(), nullptr, 10); n > 0) *start = size_t(n);
  if (const long s = parse_span(end_text)) *span = size_t(s);
  else if (const long n = std::strtol(end_text.c_str(), nullptr, 10); n > 0 && *start && size_t(n) > *start) *span = size_t(n) - *start;
}
struct Item { size_t node, column = 0, row = 0, column_span = 1, row_span = 1; long order = 0; };
// Resolve positive numeric line placement and the implicit grid before either
// intrinsic sizing or layout. Explicitly positioned items can overlap; they
// reserve cells before auto-positioned items look for unoccupied space.
std::vector<Item> Items(const std::vector<BoxNode>& nodes, size_t index,
                        std::vector<Track>& columns, std::vector<Track>& rows) {
  const auto& style = nodes[index].style;
  auto auto_columns = Tracks(style, style.Get("grid-auto-columns"), BoxAuto(), 0);
  auto auto_rows = Tracks(style, style.Get("grid-auto-rows"), BoxAuto(), 0);
  if (auto_columns.empty()) auto_columns.push_back(Size(style,"auto",BoxAuto()));
  if (auto_rows.empty()) auto_rows.push_back(Size(style,"auto",BoxAuto()));
  const size_t explicit_columns=columns.size(),explicit_rows=rows.size();
  const auto grow_columns=[&](size_t count) {
    while(columns.size()<std::min(kMaxTracks,count))
      columns.push_back(auto_columns[(columns.size()-explicit_columns)%auto_columns.size()]);
  };
  std::vector<Item> items;
  size_t count=std::max(size_t(1),columns.size());
  for(auto child:nodes[index].children) {
    const auto& node=nodes[child];
    if(BoxAbsolute(node)||node.style.Get("display")=="none"||(node.text&&node.text_width<=0)) continue;
    Item item{child};
    if(!node.text) {
      Line(node.style,"column",&item.column,&item.column_span);
      Line(node.style,"row",&item.row,&item.row_span);
      item.order=std::strtol(node.style.Get("order").c_str(),nullptr,10);
    }
    item.column=std::min(item.column,kMaxTracks);item.row=std::min(item.row,kMaxTracks);
    item.column_span=std::min(item.column_span,kMaxTracks-(item.column?item.column-1:0));
    item.row_span=std::min(item.row_span,kMaxTracks-(item.row?item.row-1:0));
    count=std::max(count,(item.column?item.column-1:0)+item.column_span);
    items.push_back(item);
  }
  grow_columns(count);
  std::stable_sort(items.begin(),items.end(),[](const auto& a,const auto& b){return a.order<b.order;});
  std::vector<std::vector<bool>> taken;
  const auto free_at=[&](size_t row,size_t column,const Item& item) {
    if(column+item.column_span>columns.size()||row+item.row_span>kMaxTracks) return false;
    for(size_t r=row;r<row+item.row_span;++r)
      for(size_t c=column;c<column+item.column_span;++c)
        if(r<taken.size()&&c<taken[r].size()&&taken[r][c]) return false;
    return true;
  };
  const auto occupy=[&](Item& item,size_t row,size_t column) {
    item.row=row;item.column=column;
    if(taken.size()<row+item.row_span) taken.resize(row+item.row_span);
    for(size_t r=row;r<row+item.row_span;++r) {
      if(taken[r].size()<columns.size()) taken[r].resize(columns.size());
      for(size_t c=column;c<column+item.column_span;++c) taken[r][c]=true;
    }
  };
  std::vector<bool> placed(items.size());
  for(size_t i=0;i<items.size();++i) if(items[i].row&&items[i].column) {
    occupy(items[i],items[i].row-1,items[i].column-1);placed[i]=true;
  }
  for(size_t i=0;i<items.size();++i) if(!placed[i]&&items[i].row) {
    auto& item=items[i];size_t r=item.row-1,c=0;
    while(c+item.column_span<=kMaxTracks) {
      grow_columns(c+item.column_span);
      if(free_at(r,c,item)) break;
      ++c;
    }
    c=std::min(c,columns.size()-item.column_span);
    occupy(item,r,c);placed[i]=true;
  }
  size_t cursor_row=0,cursor_column=0;
  const bool dense=style.Get("grid-auto-flow").find("dense")!=std::string::npos;
  for(size_t i=0;i<items.size();++i) if(!placed[i]) {
    auto& item=items[i];size_t r=dense?0:cursor_row,c=dense?0:cursor_column;
    if(item.column) {size_t target=item.column-1;if(target<c)++r;c=target;}
    while(!free_at(r,c,item)&&r+item.row_span<=kMaxTracks) {
      if(item.column) ++r;
      else if(++c+item.column_span>columns.size()) {c=0;++r;}
    }
    r=std::min(r,kMaxTracks-item.row_span);c=std::min(c,columns.size()-item.column_span);
    occupy(item,r,c);cursor_row=r;cursor_column=c+item.column_span;
  }
  while(rows.size()<taken.size()) rows.push_back(auto_rows[(rows.size()-explicit_rows)%auto_rows.size()]);
  return items;
}
// §12.4-12.7 for one axis: base sizes from fixed minimums or item minimum
// contributions, growth limits, then free space to non-flexible and fr tracks.
void Size(std::vector<Track>& tracks, double room, double gap, bool stretch) {
  double used = gap * (tracks.empty() ? 0 : tracks.size() - 1), fr = 0;
  for (auto& t : tracks) { t.limit = std::max(t.base, t.limit); used += t.base; fr += t.fr; }
  if (!std::isfinite(room)) {
    for (auto& t : tracks) if (!t.fr) t.base = t.limit;
    return;
  }
  double free = room - used;
  double growable = 0;
  for (auto& t : tracks) if (!t.fr && std::isfinite(t.limit)) growable += t.limit - t.base;
  if (free > 0 && growable > 0) {
    const double share = std::min(1.0, free / growable);
    for (auto& t : tracks) if (!t.fr && std::isfinite(t.limit)) { const double add = (t.limit - t.base) * share; t.base += add; free -= add; }
  }
  if (fr > 0) {
    // §12.7.1: a track whose base exceeds its fr share is inflexible.
    std::vector<bool> flexible(tracks.size());
    for (size_t i = 0; i < tracks.size(); ++i) flexible[i] = tracks[i].fr > 0;
    for (size_t round = 0; round <= tracks.size(); ++round) {
      double leftover = room - gap * (tracks.size() - 1), factors = 0;
      for (size_t i = 0; i < tracks.size(); ++i) if (flexible[i]) factors += tracks[i].fr; else leftover -= tracks[i].base;
      const double unit = std::max(0.0, leftover) / std::max(1.0, factors);
      bool changed = false;
      for (size_t i = 0; i < tracks.size(); ++i)
        if (flexible[i] && tracks[i].base > unit * tracks[i].fr) { flexible[i] = false; changed = true; }
      if (changed) continue;
      for (size_t i = 0; i < tracks.size(); ++i) if (flexible[i]) tracks[i].base = unit * tracks[i].fr;
      break;
    }
  } else if (stretch && free > 0) {
    size_t autos = 0;
    for (const auto& t : tracks) autos += t.max_auto;
    for (auto& t : tracks) if (t.max_auto) t.base += free / autos;
  }
}
double Sum(const std::vector<Track>& t, size_t from, size_t count, double gap) {
  double total = gap * (count ? count - 1 : 0);
  for (size_t i = from; i < from + count && i < t.size(); ++i) total += t[i].base;
  return total;
}
}  // namespace

double BoxFlow::GridIntrinsic(size_t index, bool minimum, unsigned depth) {
  const auto& style=nodes[index].style;
  double gap=0;Length(style,style.Get("column-gap"),BoxAuto(),&gap);
  auto columns=Tracks(style,style.Get("grid-template-columns"),BoxAuto(),gap);
  auto rows=Tracks(style,style.Get("grid-template-rows"),BoxAuto(),0);
  auto items=Items(nodes,index,columns,rows);
  for(auto& track:columns) track.base=track.min_auto?0:track.min;
  std::stable_sort(items.begin(),items.end(),[](const auto& a,const auto& b){return a.column_span<b.column_span;});
  for(const auto& item:items) {
    const double contribution=IntrinsicOuter(item.node,minimum,depth+1);
    const double free=contribution-Sum(columns,item.column,item.column_span,gap);
    size_t flexible=0;
    for(size_t i=item.column;i<item.column+item.column_span;++i)
      flexible+=columns[i].min_auto||columns[i].max_auto||columns[i].fr>0;
    if(free>0&&flexible) for(size_t i=item.column;i<item.column+item.column_span;++i)
      if(columns[i].min_auto||columns[i].max_auto||columns[i].fr>0) columns[i].base+=free/flexible;
  }
  return Sum(columns,0,columns.size(),gap);
}

bool BoxFlow::GridChildren(size_t index, size_t positioned, unsigned depth, double* height, double* width) {
  const auto& style = nodes[index].style;
  const BoxRect content = boxes[index].content;
  const bool definite = boxes[index].definite_height;
  const auto gap = [&](const char* name, double basis) {
    const auto text = style.Get(name);
    double value = 0;
    return text.empty() || text == "normal" || !Length(style, text, basis, &value) ? 0.0 : value;
  };
  const double column_gap = gap("column-gap", content[2]);
  const double row_gap = gap("row-gap", definite ? content[3] : BoxAuto());
  auto columns = Tracks(style, style.Get("grid-template-columns"), content[2], column_gap);
  auto rows = Tracks(style, style.Get("grid-template-rows"), definite ? content[3] : BoxAuto(), row_gap);
  const auto items=Items(nodes,index,columns,rows);
  const auto normal = [](const std::string& v) { return v.empty() || v == "normal" || v == "stretch"; };
  // Columns: content contributions of single-span items set auto minimums/maximums.
  for (auto& t : columns) { t.base = t.min_auto ? 0 : t.min; t.limit = t.max_auto ? 0 : (t.fr ? INFINITY : std::max(t.max, t.base)); }
  for (const auto& item : items) {
    if (item.column_span != 1) continue;
    auto& t = columns[item.column];
    if (t.min_auto) t.base = std::max(t.base, IntrinsicOuter(item.node, true, depth + 1));
    if (t.max_auto) t.limit = std::max(t.limit, IntrinsicOuter(item.node, false, depth + 1));
  }
  for (auto& t : columns) if (t.max_auto && !t.fr) t.limit = std::max(t.limit, t.base);
  Size(columns, content[2], column_gap, normal(style.Get("justify-content")));
  // Lay each item out at its column area's width; rows from their heights.
  std::vector<double> outer(items.size());
  for (size_t n = 0; n < items.size(); ++n) {
    const auto& item = items[n];
    auto& box = boxes[item.node];
    const double area = Sum(columns, item.column, item.column_span, column_gap);
    if (!nodes[item.node].text) {
      BoxEdges(nodes[item.node], area, &box);
      const double extra = box.padding[1] + box.padding[3] + box.edge[1] + box.edge[3];
      const auto& cs = nodes[item.node].style;
      double specified = BoxLength(cs, "width", area, BoxAuto());
      if (std::isfinite(specified) && cs.Get("box-sizing") == "border-box") specified -= extra;
      auto justify=cs.Get("justify-self");
      if(justify.empty()||justify=="auto") justify=style.Get("justify-items");
      const double room=std::max(0.0,area-box.margin[1]-box.margin[3]-extra);
      forced_width[item.node] = std::isfinite(specified) ? specified
          : normal(justify) ? room : std::min(room,Intrinsic(item.node,false,depth+1));
      forced_height[item.node] = BoxAuto();
    }
    const BoxRect cell{content[0], content[1], area, BoxAuto()};
    if (!Place(item.node, cell, false, content[0], content[1], positioned, depth + 1)) return false;
    outer[n] = box.border[3] + box.margin[0] + box.margin[2];
  }
  for (auto& t : rows) { t.base = t.min_auto ? 0 : t.min; t.limit = t.max_auto || t.fr ? 0 : std::max(t.max, t.base); }
  for (size_t n = 0; n < items.size(); ++n)
    if (items[n].row_span == 1) {
      auto& t = rows[items[n].row];
      if (t.min_auto || t.fr) t.base = std::max(t.base, outer[n]);
      if (t.max_auto || t.fr) t.limit = std::max(t.limit, outer[n]);
    }
  for (auto& t : rows) if (t.fr && !definite) { t.fr = 0; t.max_auto = true; }
  Size(rows, definite ? content[3] : BoxAuto(), row_gap, definite && normal(style.Get("align-content")));
  std::vector<double> column_at(columns.size()), row_at(rows.size());
  for (size_t i = 0; i < columns.size(); ++i) column_at[i] = Sum(columns, 0, i, column_gap) + (i ? column_gap : 0);
  for (size_t i = 0; i < rows.size(); ++i) row_at[i] = Sum(rows, 0, i, row_gap) + (i ? row_gap : 0);
  const auto align_items = style.Get("align-items");
  for (size_t n = 0; n < items.size(); ++n) {
    const auto& item = items[n];
    auto& box = boxes[item.node];
    const double area_height = Sum(rows, item.row, item.row_span, row_gap);
    auto align = nodes[item.node].text ? std::string("start") : nodes[item.node].style.Get("align-self");
    if (align.empty() || align == "auto") align = align_items;
    double offset = 0;
    const auto specified_height = nodes[item.node].text ? std::string() : nodes[item.node].style.Get("height");
    if (!nodes[item.node].text && normal(align) && (specified_height.empty() || specified_height == "auto")) {
      const double extra = box.padding[0] + box.padding[2] + box.edge[0] + box.edge[2];
      const double target = BoxLimit(nodes[item.node].style, false, area_height,
                                     std::max(0.0, area_height - box.margin[0] - box.margin[2] - extra), extra);
      if (std::abs(target - box.content[3]) > 1e-6) {
        if (Relayout(item.node, true)) {
          forced_height[item.node] = target;
          const BoxRect cell{content[0], content[1], Sum(columns, item.column, item.column_span, column_gap), area_height};
          if (!Place(item.node, cell, true, content[0], content[1], positioned, depth + 1)) return false;
        } else {
          Resize(item.node, true, target);
        }
      }
    } else if (align == "center") offset = (area_height - outer[n]) / 2;
    else if (align == "end" || align == "flex-end" || align == "self-end") offset = area_height - outer[n];
    auto justify=nodes[item.node].style.Get("justify-self");
    if(justify.empty()||justify=="auto") justify=style.Get("justify-items");
    const double free=Sum(columns,item.column,item.column_span,column_gap)-box.border[2]-box.margin[1]-box.margin[3];
    const double horizontal=justify=="center"?free/2 : justify=="end"||justify=="self-end"||justify=="flex-end"?free:0;
    const double x = content[0] + column_at[item.column] + box.margin[3] + horizontal;
    const double y = content[1] + row_at[item.row] + box.margin[0] + std::max(0.0, offset);
    ShiftBoxes(item.node, BoxRound(x) - box.border[0], BoxRound(y) - box.border[1]);
  }
  *height = BoxRound(rows.empty() ? 0 : Sum(rows, 0, rows.size(), row_gap));
  *width = BoxRound(Sum(columns, 0, columns.size(), column_gap));
  return true;
}
}  // namespace ruyijs::domain::styling
