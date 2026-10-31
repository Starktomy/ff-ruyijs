#pragma once
#include "web_audio/internal.h"
#include <vector>

namespace ruyijs::web_audio {

// Buffer sources use the otherwise unused waveform slot for their private
// scheduling record. The existing fields own buffer, loop and AudioParams.
bool InitBufferSource(State&, JS::HandleObject);
bool BufferSourceAction(State&, const JS::CallArgs&, JS::HandleObject, bool stop);

struct BufferVoice {
  std::vector<std::vector<float>> channels;
  bool started = false, loop = false;
  double start = 0, stop = 0, duration = 0;
  double position = 0, played = 0, step = 1, sourceRate = 44100;
  double loopStart = 0, loopEnd = 0;
  void Compute(float* output, size_t frames, double outputTime, double outputRate);
};

bool ConfigureBufferVoice(State&, JS::HandleObject node, double outputRate, BufferVoice*);

}  // namespace ruyijs::web_audio
