window.SB_VIEWS = window.SB_VIEWS || {};
window.SB_VIEWS["evaluate-view"] = {
  template: `
  <div class="panel">
    <h2>在线求值</h2>
    <p class="lead">给定屏幕与时刻，计算应播内容（覆盖优先）；维保屏不返回任何可播内容。</p>
    <div class="row-form">
      <input v-model.number="screen_id" type="number" placeholder="屏幕ID" />
      <input v-model="now_hm" placeholder="HH:MM" />
      <input v-model="weekday" placeholder="星期1-7" />
      <button class="primary" @click="run">求值</button>
    </div>
    <div class="notice warn" v-if="maintNotice">
      <b>维保中</b><span>{{ maintReason || "屏幕维保中，禁止上屏" }}</span>
    </div>
    <pre style="white-space:pre-wrap;background:#0d1828;padding:12px;border-radius:10px;">{{ resultText }}</pre>
    <p class="err" v-if="error">{{ error }}</p>
  </div>`,
  data() {
    return {
      screen_id: 1, now_hm: "10:30", weekday: "1",
      result: null, resultText: "", error: "", maintNotice: false, maintReason: ""
    };
  },
  methods: {
    async run() {
      this.error = ""; this.result = null; this.maintNotice = false; this.maintReason = "";
      try {
        const r = await SB.api("/api/evaluate/screen", {
          method: "POST",
          body: JSON.stringify({ screen_id: this.screen_id, now_hm: this.now_hm, weekday: this.weekday })
        });
        this.result = r;
        this.resultText = JSON.stringify(r, null, 2);
        this.maintNotice = r.source === "maintenance";
        this.maintReason = r.reason || "";
      } catch (e) { this.error = e.message; }
    }
  }
};
