window.SB_VIEWS = window.SB_VIEWS || {};
window.SB_VIEWS["screens-view"] = {
  template: `
  <div class="panel">
    <h2>屏幕台账</h2>
    <p class="lead">物理终端绑定分区、分辨率与在线状态；维保屏禁止正式上屏。</p>
    <table>
      <thead><tr><th>编码</th><th>标题</th><th>分区</th><th>分辨率</th><th>状态</th><th>风险</th><th>发布态</th></tr></thead>
      <tbody>
        <tr v-for="s in items" :key="s.id">
          <td>{{ s.code }}</td><td>{{ s.title }}</td><td>{{ s.zone_title }}</td>
          <td>{{ s.resolution }}</td>
          <td><span class="badge" :class="s.status==='online'?'':(s.status==='maintenance'?'bad':'warn')">{{ s.status_label }}</span></td>
          <td>{{ s.risk_level }}</td>
          <td>
            <span class="badge bad" v-if="s.status==='maintenance'">禁止发布</span>
            <span class="badge warn" v-else-if="s.official_suspended">正式挂起</span>
            <span class="badge" v-else-if="s.on_air">已上屏</span>
            <span class="badge warn" v-else>未上屏</span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>`,
  data() { return { items: [] }; },
  async mounted() { this.items = (await SB.api("/api/screens")).items; }
};
