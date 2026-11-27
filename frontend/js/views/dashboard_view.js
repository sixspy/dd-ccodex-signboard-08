window.SB_VIEWS = window.SB_VIEWS || {};
window.SB_VIEWS["dashboard-view"] = {
  template: `
  <div>
    <div class="panel">
      <h2>总览</h2>
      <p class="lead">{{ meta.skeleton || "加载中…" }}</p>
      <div class="notice" :class="meta.healthy ? 'ok' : 'warn'" v-if="meta.healthy !== undefined">
        <b>{{ meta.healthy ? "发布健康" : "存在维保挂起" }}</b>
        <span v-if="meta.healthy">维保屏均已从正式发布册撤下，正式上屏账实一致。</span>
        <span v-else>检测到维保屏仍挂正式发布（{{ meta.suspended_publications }} 条），不得视为在线齐套。</span>
      </div>
      <div class="stats">
        <div class="stat" v-for="s in cards" :key="s.k" :class="s.tone || ''">
          <b>{{ s.v }}</b><span>{{ s.l }}</span>
        </div>
      </div>
    </div>
    <div class="panel" v-if="maintRows.length">
      <h3>维保屏</h3>
      <p class="lead">维保期间禁止正式上屏；复机后才可重新发布。</p>
      <table>
        <thead><tr><th>屏幕</th><th>状态</th><th>正式发布</th></tr></thead>
        <tbody>
          <tr v-for="s in maintRows" :key="s.id">
            <td>{{ s.code }} · {{ s.title }}</td>
            <td><span class="badge bad">{{ s.status_label }}</span></td>
            <td>
              <span v-if="s.official_count" class="badge bad">挂起 {{ s.official_count }} 条</span>
              <span v-else class="badge warn">已撤下</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>`,
  data() { return { meta: {}, cards: [], maintRows: [] }; },
  async mounted() {
    const d = await SB.api("/api/dashboard");
    this.meta = d;
    this.cards = [
      { k: "screens", l: "屏幕总数", v: d.screens },
      { k: "online", l: "在线屏幕", v: d.online_screens },
      { k: "maint", l: "维保屏幕", v: d.maintenance_screens, tone: d.maintenance_screens ? "warn" : "" },
      { k: "assets", l: "可播素材", v: d.ready_assets },
      { k: "pubs", l: "正式发布", v: d.official_publications },
      { k: "susp", l: "维保挂起正式", v: d.suspended_publications, tone: d.suspended_publications ? "bad" : "" },
      { k: "shadows", l: "待升正影子", v: d.open_shadows },
      { k: "ov", l: "生效覆盖", v: d.active_overrides },
    ];
    const screens = (await SB.api("/api/screens")).items;
    this.maintRows = screens.filter(s => s.status === "maintenance");
  }
};
