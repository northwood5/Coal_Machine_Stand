<script setup lang="ts">
import { computed } from 'vue'
import type { ModuleRunResult } from '../api'

const props = defineProps<{
  result: ModuleRunResult | null
  running: boolean
}>()

// 双纽线轨迹 → SVG polyline (x 放大展示摆动)
const traj = computed(() => {
  const t = props.result?.results?.trajectory as [number, number][] | undefined
  if (!t || t.length < 2) return null
  const xs = t.map((p) => p[0])
  const ys = t.map((p) => p[1])
  const xMin = Math.min(...xs), xMax = Math.max(...xs)
  const yMin = Math.min(...ys), yMax = Math.max(...ys)
  const W = 260, H = 220, pad = 14
  const sx = (xMax - xMin) > 1 ? (W - 2 * pad) / (xMax - xMin) : 1
  const sy = (H - 2 * pad) / (yMax - yMin)
  const pts = t.map(([x, y]) =>
    `${(pad + (x - xMin) * sx).toFixed(1)},${(H - pad - (y - yMin) * sy).toFixed(1)}`,
  ).join(' ')
  return { pts, W, H, width: (xMax - xMin).toFixed(1), hRange: `${yMin.toFixed(0)}~${yMax.toFixed(0)}` }
})
</script>

<template>
  <div class="result-view">
    <h3>计算结果</h3>
    <p v-if="running" class="hint">计算中…</p>
    <template v-else-if="result">
      <div v-if="result.passed !== null" class="verdict" :class="result.passed ? 'pass' : 'fail'">
        {{ result.passed ? '✓ 校核通过' : '✗ 校核不通过' }}
      </div>

      <section v-if="traj">
        <h4>顶梁铰点轨迹 (双纽线, 横向已放大)</h4>
        <svg :width="traj.W" :height="traj.H" class="traj">
          <polyline :points="traj.pts" fill="none" stroke="#2c7be5" stroke-width="2" />
        </svg>
        <p class="traj-note">横向摆动 {{ traj.width }} mm · E点高度 {{ traj.hRange }} mm</p>
      </section>

      <section v-if="Object.keys(result.margins).length">
        <h4>安全裕度</h4>
        <table>
          <tr v-for="(v, k) in result.margins" :key="k">
            <td>{{ k }}</td><td>{{ v }}</td>
          </tr>
        </table>
      </section>

      <section v-if="result.standard_refs.length">
        <h4>对标条款</h4>
        <ul><li v-for="r in result.standard_refs" :key="r">{{ r }}</li></ul>
      </section>

      <section v-if="result.suggestions.length">
        <h4>建议</h4>
        <ul><li v-for="s in result.suggestions" :key="s">{{ s }}</li></ul>
      </section>

      <section>
        <h4>原始输出</h4>
        <pre>{{ JSON.stringify(result.results, null, 2) }}</pre>
      </section>

      <p class="snap">已自动创建计算前快照 #{{ result.snapshot_id }}</p>
    </template>
    <p v-else class="hint">运行模块后在此查看结果</p>
  </div>
</template>

<style scoped>
.result-view { padding: 16px; overflow-y: auto; font-size: 13px; }
h3 { margin: 0 0 12px; font-size: 14px; color: #555; }
h4 { margin: 14px 0 6px; font-size: 13px; color: #666; }
.verdict { padding: 10px; border-radius: 6px; font-weight: 600; text-align: center; }
.verdict.pass { background: #e8f8ef; color: #27ae60; }
.verdict.fail { background: #fdeeee; color: #e74c3c; }
table { width: 100%; border-collapse: collapse; }
td { border: 1px solid #eee; padding: 4px 8px; }
ul { margin: 0; padding-left: 18px; }
pre {
  background: #f7f9fb; border: 1px solid #e0e6ed; border-radius: 6px;
  padding: 10px; font-size: 12px; overflow-x: auto;
}
.snap { color: #999; font-size: 11px; margin-top: 10px; }
.traj { background: #f7f9fb; border: 1px solid #e0e6ed; border-radius: 6px; }
.traj-note { color: #777; font-size: 11px; margin: 4px 0 0; }
.hint { color: #999; text-align: center; margin-top: 60px; }
</style>
