"""Point queries use real layout and keep document/shadow ownership intact."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context


POINT_CASES = r'''(() => {
 const d=frames[0].document,w=frames[0],rows=[];
 const label=e=>e?.id||e?.localName||null;
 const read=(name,x,y)=>rows.push({name,first:label(d.elementFromPoint(x,y)),
   all:[...d.elementsFromPoint(x,y)].map(label)});
 const html=markup=>{d.documentElement.style.cssText='margin:0';
   d.body.style.cssText='margin:0';d.body.innerHTML=markup;};
 html('<div id="a" style="position:absolute;left:20px;top:20px;width:120px;height:100px">'+
      '<div id="child" style="width:60px;height:50px"></div></div>'+
      '<div id="b" style="position:absolute;left:40px;top:30px;width:90px;height:80px"></div>');
 read('origin',0,0);read('overlap',50,40);read('ancestor',25,25);
 d.getElementById('a').style.zIndex='2';read('z-index',50,40);
 d.getElementById('child').style.pointerEvents='none';read('pointer-events',50,40);
 d.getElementById('a').style.display='none';read('display',50,40);
 d.getElementById('b').style.visibility='hidden';read('visibility',50,40);
 for(const [name,x,y] of [['negative',-1,0],['right',400,0],['bottom',0,300]])read(name,x,y);
 html('<div id="low" style="position:absolute;left:0;top:0;width:100px;height:100px;z-index:1">'+
      '<div id="nested" style="width:100px;height:100px;position:relative;z-index:100"></div></div>'+
      '<div id="high" style="position:absolute;left:0;top:0;width:100px;height:100px;z-index:2"></div>');
 read('stacking-context',10,10);
 html('<div id="clip" style="position:absolute;left:20px;top:20px;width:50px;height:50px;overflow:hidden">'+
      '<div id="wide" style="width:150px;height:40px"></div></div>');
 read('clipped-inside',30,30);read('clipped-outside',90,30);
 d.getElementById('clip').scrollLeft=40;read('scrolled',30,30);
 html('<div id="move" style="position:absolute;left:20px;top:20px;width:50px;height:50px;transform:translate(80px,30px)"></div>');
 read('translated',110,60);read('translated-old',30,30);
 d.getElementById('move').style.cssText='position:absolute;left:100px;top:100px;width:80px;height:80px;transform:rotate(45deg)';
 read('rotated-center',140,140);read('rotated-corner',85,85);
 d.getElementById('move').style.transform='scale(0)';read('zero-scale',140,140);
 html('<div id="host" style="position:absolute;left:20px;top:20px;width:100px;height:80px"></div>');
 const host=d.getElementById('host'),root=host.attachShadow({mode:'closed'});
 root.innerHTML='<div id="secret" style="width:100px;height:80px"></div>';
 read('closed-shadow',30,30);
 rows.push({name:'foreign-receiver',first:label(Document.prototype.elementFromPoint.call(d,30,30)),
   all:[...Document.prototype.elementsFromPoint.call(d,30,30)].map(label)});
 const detached=d.implementation.createHTMLDocument('detached');
 rows.push({name:'detached',first:label(detached.elementFromPoint(0,0)),all:[...detached.elementsFromPoint(0,0)].map(label)});
 document.querySelector('iframe').style.display='none';read('hidden-frame',0,0);
 document.querySelector('iframe').style.display='block';read('revealed-frame',30,30);
 return rows;
})()'''


@unittest.skipUnless((ROOT / "dist/js").is_file(), "build the native runtime first")
class PointQueryTests(unittest.TestCase):
    def test_layout_mutations_clipping_and_ownership(self):
        expected = [
            ('origin', 'html', ['html']),
            ('overlap', 'b', ['b', 'child', 'a', 'html']),
            ('ancestor', 'child', ['child', 'a', 'html']),
            ('z-index', 'child', ['child', 'a', 'b', 'html']),
            ('pointer-events', 'a', ['a', 'b', 'html']),
            ('display', 'b', ['b', 'html']),
            ('visibility', 'html', ['html']),
            ('negative', None, []), ('right', None, []), ('bottom', None, []),
            ('stacking-context', 'high', ['high', 'nested', 'low', 'html']),
            ('clipped-inside', 'wide', ['wide', 'clip', 'html']),
            ('clipped-outside', 'html', ['html']),
            ('scrolled', 'wide', ['wide', 'clip', 'html']),
            ('translated', 'move', ['move', 'html']),
            ('translated-old', 'html', ['html']),
            ('rotated-center', 'move', ['move', 'html']),
            ('rotated-corner', 'html', ['html']),
            ('zero-scale', 'html', ['html']),
            ('closed-shadow', 'host', ['host', 'html']),
            ('foreign-receiver', 'host', ['host', 'html']),
            ('detached', None, []), ('hidden-frame', None, []),
            ('revealed-frame', 'host', ['host', 'html']),
        ]
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://points.test/", '<iframe srcdoc="<!doctype html>" style="width:400px;height:300px;border:0"></iframe>')
            actual=context.eval(POINT_CASES)
            self.assertEqual(actual,[{'name':n,'first':f,'all':a} for n,f,a in expected])

    def test_argument_conversion_and_result_realm(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://points.test/", '<iframe srcdoc="<!doctype html>" style="width:400px;height:300px;border:0"></iframe>')
            self.assertEqual(context.eval("""(() => {
                const d=frames[0].document,order=[];
                const x={valueOf(){order.push('x');return 0}},y={valueOf(){order.push('y');return 0}};
                const result=Document.prototype.elementsFromPoint.call(d,x,y);
                let missing=false,symbol=false,nonfinite=0;
                try{d.elementFromPoint(0)}catch(e){missing=e.name==='TypeError'}
                try{d.elementFromPoint(Symbol(),0)}catch(e){symbol=e.name==='TypeError'}
                for(const fn of [d.elementFromPoint,d.elementsFromPoint])
                    for(const point of [[NaN,0],[0,Infinity]])
                        try{fn.call(d,...point)}catch(e){if(e.name==='TypeError')nonfinite++}
                return {order,missing,symbol,nonfinite,realm:Object.getPrototypeOf(result)===Array.prototype,
                    identity:result[0]===d.documentElement,length:Document.prototype.elementFromPoint.length};
            })()"""), {'order':['x','y'],'missing':True,'symbol':True,'nonfinite':4,'realm':True,'identity':True,'length':2})


if __name__ == "__main__":
    unittest.main()
