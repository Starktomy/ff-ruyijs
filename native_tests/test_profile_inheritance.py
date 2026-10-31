"""Configured owner profiles survive new frame and document realms."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context


PROFILE = {
    "webgl": {"unmaskedVendor": "Profile Vendor", "unmaskedRenderer": "Profile Renderer",
              "limits": {"34930": 31}, "extensions": ["WEBGL_debug_renderer_info"]},
    "webgpu": {"enabled": True},
    "permissions": {"geolocation": "granted"},
    "geolocation": {"latitude": 37, "longitude": 13, "accuracy": 4},
    "speech": {"voices": ["Profile Voice"], "langs": ["en-US"], "default": "Profile Voice"},
    "media": {"devices": ["audioinput|Profile Microphone|profile-device|profile-group"]},
    "audio": {"sampleRate": 48000, "baseLatency": 0.012, "maxChannelCount": 4},
    "mediaFeatures": {"prefersColorScheme": "dark", "pointer": "coarse"},
    "rtc": {"audioCodecs": ["audio/profile-test|48000|2|"]},
}

PROBE = """(()=>{globalThis.profileResult=null;
    const canvas=document.createElement('canvas'),gl=canvas.getContext('webgl');
    const debug=gl.getExtension('WEBGL_debug_renderer_info'),audio=new AudioContext();
    Promise.all([
        navigator.permissions.query({name:'geolocation'}).then(p=>p.state),
        navigator.mediaDevices.enumerateDevices().then(devices=>devices.map(d=>
            [d.kind,d.label,d.deviceId,d.groupId])),
        new Promise(resolve=>navigator.geolocation.getCurrentPosition(p=>
            resolve([p.coords.latitude,p.coords.longitude,p.coords.accuracy]),
            e=>resolve(e.code))),
        new Promise(resolve=>{
            const names=()=>speechSynthesis.getVoices().map(v=>v.name),initial=names();
            if(initial.length) resolve(initial);
            else speechSynthesis.onvoiceschanged=()=>resolve(names());
        })
    ]).then(values=>{
        profileResult={renderer:gl.getParameter(debug.UNMASKED_RENDERER_WEBGL),
            vendor:gl.getParameter(debug.UNMASKED_VENDOR_WEBGL),units:gl.getParameter(34930),
            extensions:gl.getSupportedExtensions(),gpu:typeof navigator.gpu,
            audio:[audio.sampleRate,audio.baseLatency,audio.destination.maxChannelCount],
            dark:matchMedia('(prefers-color-scheme:dark)').matches,
            coarse:matchMedia('(pointer:coarse)').matches,
            codecs:RTCRtpSender.getCapabilities('audio').codecs.map(c=>c.mimeType),
            voices:values[3],
            permission:values[0],devices:values[1],position:values[2]};
        audio.close();
    });})();void 0;"""

EXPECTED = {"renderer": "Profile Renderer", "vendor": "Profile Vendor", "units": 31,
            "extensions": ["WEBGL_debug_renderer_info"], "gpu": "object",
            "audio": [48000, 0.012, 4], "dark": True, "coarse": True,
            "codecs": ["audio/profile-test"], "voices": ["Profile Voice"],
            "permission": "granted",
            "devices": [["audioinput", "Profile Microphone", "profile-device", "profile-group"]],
            "position": [37, 13, 4]}


@unittest.skipUnless((ROOT / "dist/js").is_file(), "build the native runtime first")
class ProfileInheritanceTests(unittest.TestCase):
    def probe(self, context, window="window"):
        context.set("profileProbe", PROBE)
        context.eval(f"{window}.eval(profileProbe)")
        result = None
        for _ in range(100):
            context.advance(10)
            result = context.eval(f"{window}.profileResult")
            if result is not None:
                break
        self.assertEqual(result, EXPECTED)

    def test_initial_and_nested_about_blank_frames_use_the_configured_owners(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.configure_fingerprint(PROFILE)
            context.load_page("https://profile.test/", "<!doctype html><iframe></iframe>")
            self.probe(context)
            self.probe(context, "frames[0]")
            context.eval("frames[0].document.body.appendChild(frames[0].document.createElement('iframe'))")
            context.collect_garbage()
            self.probe(context, "frames[0].frames[0]")
            self.assertEqual(context.eval("""[frames[0].navigator!==navigator,
                frames[0].WebGLRenderingContext!==WebGLRenderingContext,
                Object.getPrototypeOf(frames[0].navigator)===frames[0].Navigator.prototype,
                Object.hasOwn(frames[0],'webglGroup')]"""), [True, True, True, False])

    def test_cross_origin_frame_navigation_and_srcdoc_keep_the_profile(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.configure_fingerprint(PROFILE)
            context.put_resource("https://other.test/child", "<!doctype html><iframe></iframe>",
                                 headers=[["Content-Type", "text/html"]])
            context.load_page("https://profile.test/", '<!doctype html><iframe src="https://other.test/child"></iframe>')
            for _ in range(100):
                context.advance(10)
                if context.eval("frames[0].document.querySelectorAll('iframe').length"):
                    break
            self.probe(context, "frames[0]")
            self.probe(context, "frames[0].frames[0]")
            context.eval("document.querySelector('iframe').src='https://other.test/child#replacement'")
            context.advance(10)
            context.collect_garbage()
            self.probe(context, "frames[0]")
            context.eval("document.querySelector('iframe').srcdoc='<!doctype html><p>replacement</p>'")
            context.advance(10)
            self.assertEqual(context.eval("""frames[0].eval(`(()=>{
                const gl=document.createElement('canvas').getContext('webgl');
                return gl.getParameter(gl.getExtension('WEBGL_debug_renderer_info').UNMASKED_RENDERER_WEBGL);
            })()`)"""), "Profile Renderer")

    def test_top_level_successor_documents_keep_the_profile(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.configure_fingerprint(PROFILE)
            for url in ["https://profile.test/first", "https://other.test/next", "https://profile.test/final"]:
                context.load_page(url, "<!doctype html><iframe></iframe>")
                context.collect_garbage()
                self.probe(context)
                self.probe(context, "frames[0]")


if __name__ == "__main__":
    unittest.main()
