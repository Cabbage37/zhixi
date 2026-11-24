async function renderDatabase() {
  const view = $('feature-view'), token = generation;
  view.innerHTML = '<section class="panel"><h2>互动数据库</h2><p role="status">正在打开数据库…</p></section>';
  const panel = view.firstElementChild;
  try {
    let state = await api('/api/interactive-database/open', {method:'POST'});
    const started = Date.now();
    while (state.starting) {
      if (!panel.isConnected || generation !== token) return;
      if (Date.now() - started > 180000) throw Error('数据库启动时间较长，请稍后重新打开。');
      panel.querySelector('p').textContent = '正在启动原版数据库工作区，首次打开需要一些时间…';
      await new Promise(resolve => setTimeout(resolve, 1500));
      if (!panel.isConnected || generation !== token) return;
      state = await api('/api/interactive-database/status', {method:'POST'});
    }
    const {url} = state;
    if (generation !== token || !panel.isConnected) return;
    panel.innerHTML = '<h2>互动数据库</h2><a target="_blank" rel="noopener">在新窗口打开完整工作区 ↗</a>';
    panel.querySelector('a').href = url;
    const frame = document.createElement('iframe');
    frame.title = '互动数据库工作区';
    frame.src = url;
    frame.style.cssText = 'width:100%;height:80vh;border:0;display:block;margin-top:1rem';
    panel.append(frame);
  } catch (error) {
    if (!panel.isConnected) return;
    panel.querySelector('p').textContent = error.message;
    const retry = text('button', '重新打开');
    retry.className = 'secondary';
    retry.onclick = renderDatabase;
    panel.append(retry);
  }
}
