// Native Skia image codecs return the same premultiplied BGRA frame contract.
#include "web_media/image_codec.h"
#include "include/codec/SkCodec.h"
#include "include/codec/SkEncodedImageFormat.h"
#include "include/core/SkColorSpace.h"
#include "include/core/SkData.h"
#include "include/core/SkImageInfo.h"
#include "include/core/SkPixmap.h"
#include "include/core/SkSamplingOptions.h"
#include <limits>
#include <new>

namespace ruyijs::web_media {
namespace {
bool Matches(const std::string& type, SkEncodedImageFormat format) {
  switch (format) {
    case SkEncodedImageFormat::kPNG: return type == "image/png" || type == "image/x-png";
    case SkEncodedImageFormat::kJPEG: return type == "image/jpeg" || type == "image/jpg" || type == "image/pjpeg";
    case SkEncodedImageFormat::kGIF: return type == "image/gif";
    case SkEncodedImageFormat::kWEBP: return type == "image/webp";
    case SkEncodedImageFormat::kBMP: return type == "image/bmp" || type == "image/x-ms-bmp";
    case SkEncodedImageFormat::kICO: return type == "image/x-icon" || type == "image/vnd.microsoft.icon";
    default: return false;
  }
}
}
bool ImageCodecSupports(const std::string& type) {
  return type == "image/avif" || type == "image/png" || type == "image/x-png" || type == "image/jpeg" ||
      type == "image/jpg" || type == "image/pjpeg" || type == "image/gif" || type == "image/webp" ||
      type == "image/bmp" || type == "image/x-ms-bmp" || type == "image/x-icon" || type == "image/vnd.microsoft.icon";
}
void ImageColorTransform(domain::web_media::ImageFrame*) {
  // There is no display ICC profile in the headless Linux runtime; decoding
  // chooses an explicit sRGB destination rather than borrowing a desktop DC.
}
domain::web_media::ImageDecodeStatus DecodeImageBytes(const std::string& type, const std::vector<uint8_t>& bytes,
    uint32_t width, uint32_t height, bool noColor, domain::web_media::ImageData* output) {
  using Status = domain::web_media::ImageDecodeStatus;
  if (type == "image/avif") return DecodeAvifBytes(bytes, width, height, output);
  if (!ImageCodecSupports(type)) return Status::Unsupported;
  if (bytes.empty() || bytes.size() > domain::web_media::kEncodedImageLimit) return Status::InvalidData;
  try {
    auto codec = SkCodec::MakeFromData(SkData::MakeWithCopy(bytes.data(), bytes.size()));
    if (!codec || !Matches(type, codec->getEncodedFormat())) return Status::InvalidData;
    const auto native = codec->getInfo();
    if (native.width() <= 0 || native.height() <= 0 || uint64_t(native.width()) * native.height() > domain::web_media::kImagePixelLimit) return Status::InvalidData;
    const auto info = SkImageInfo::Make(native.width(), native.height(), kBGRA_8888_SkColorType,
        kPremul_SkAlphaType, noColor ? nullptr : SkColorSpace::MakeSRGB());
    const int count = codec->getFrameCount();
    if (count < 1 || count > 10000) return Status::InvalidData;
    const uint32_t targetWidth = width && height ? width : uint32_t(info.width());
    const uint32_t targetHeight = width && height ? height : uint32_t(info.height());
    if (uint64_t(targetWidth) * targetHeight * count > domain::web_media::kImagePixelLimit) return Status::InvalidData;
    domain::web_media::ImageData result;
    result.animated = count > 1;
    const int repetitions = codec->getRepetitionCount();
    result.repetitions = repetitions < 0 ? std::numeric_limits<double>::infinity() : repetitions;
    std::vector<uint8_t> pixels(info.computeMinByteSize());
    uint64_t timestamp = 0;
    for (int i = 0; i < count; ++i) {
      SkCodec::Options options;
      options.fFrameIndex = i;
      options.fPriorFrame = i ? i - 1 : SkCodec::kNoFrame;
      if (codec->getPixels(info, pixels.data(), info.minRowBytes(), &options) != SkCodec::kSuccess) return Status::InvalidData;
      domain::web_media::ImageFrame frame;
      frame.width = targetWidth;
      frame.height = targetHeight;
      frame.animated = result.animated;
      frame.timestamp = timestamp;
      SkCodec::FrameInfo metadata;
      if (codec->getFrameInfo(i, &metadata)) frame.duration = uint64_t(metadata.fDuration) * 1000;
      timestamp += frame.duration;
      if (frame.width == uint32_t(info.width()) && frame.height == uint32_t(info.height())) frame.pixels = pixels;
      else {
        const auto resized = info.makeWH(int(frame.width), int(frame.height));
        frame.pixels.resize(resized.computeMinByteSize());
        if (!SkPixmap(info, pixels.data(), info.minRowBytes()).scalePixels(
            SkPixmap(resized, frame.pixels.data(), resized.minRowBytes()), SkSamplingOptions(SkFilterMode::kLinear))) return Status::InvalidData;
      }
      frame.opaque = true;
      for (size_t j = 3; j < frame.pixels.size(); j += 4) if (frame.pixels[j] != 255) { frame.opaque = false; break; }
      result.frames.push_back(std::move(frame));
    }
    *output = std::move(result);
    return Status::Ok;
  } catch (const std::bad_alloc&) { return Status::OutOfMemory; }
}
}
