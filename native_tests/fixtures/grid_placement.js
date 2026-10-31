(() => {
  document.body.style.margin='0';
  const out={};
  const rect=e=>{const r=e.getBoundingClientRect();return [r.x,r.y,r.width,r.height]};
  const run=(name,style,children,outer='')=>{
    document.body.innerHTML=`<div style="${outer}"><div id="grid" style="display:grid;${style}">${children}</div></div>`;
    out[name]=[rect(grid),...[...grid.children].map(rect)];
  };
  run('implicitIntrinsic','position:relative;place-items:center',
    '<input style="position:absolute;inset:0;width:100%;height:100%;margin:0;padding:0;border:0"><span style="grid-area:1/1;width:24px;height:24px"></span><span style="grid-column:2;width:98px;height:16px;margin-left:8px"></span>',
    'display:flex;align-items:center;width:300px;height:65px');
  run('implicitColumns','width:120px;grid-auto-columns:20px 30px;grid-auto-rows:10px',
    '<div style="grid-column:4"></div><div style="grid-column:2"></div>');
  run('overlap','width:100px;grid-template-columns:50px 50px;grid-auto-rows:20px',
    '<div style="grid-area:1/1"></div><div style="grid-area:1/1"></div><div></div>');
  run('explicitBeforeAuto','width:100px;grid-template-columns:50px 50px;grid-auto-rows:20px',
    '<div></div><div style="grid-area:1/1"></div><div></div>');
  run('lockedRow','width:100px;grid-auto-columns:20px;grid-auto-rows:10px',
    '<div style="grid-row:1"></div><div style="grid-row:1"></div><div style="grid-row:1"></div>');
  run('spanningIntrinsic','column-gap:4px',
    '<div style="grid-column:1/span 2;width:100px;height:10px"></div><div style="grid-column:1;width:30px;height:10px"></div><div style="grid-column:2;width:20px;height:10px"></div>', 'display:flex');
  run('alignment','width:100px;height:40px;place-items:center','<div style="width:20px;height:10px"></div>');
  return out;
})()
