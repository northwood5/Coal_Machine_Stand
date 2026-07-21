<script setup lang="ts">
import type { ModuleInfo } from '../api'

defineProps<{
  modules: ModuleInfo[]
  selected: string | null
}>()
const emit = defineEmits<{ select: [id: string] }>()

function statusIcon(m: ModuleInfo): string {
  if (m.missing_inputs && m.missing_inputs.length > 0) return '○' // 缺参
  if (m.dirty === false) return '✓' // 结果有效
  if (m.dirty === true) return '!' // 已过期/未计算
  return '·'
}
</script>

<template>
  <div class="module-tree">
    <h3>计算模块</h3>
    <ul>
      <li
        v-for="m in modules"
        :key="m.id"
        :class="{ active: m.id === selected }"
        @click="emit('select', m.id)"
      >
        <span class="icon" :data-state="statusIcon(m)">{{ statusIcon(m) }}</span>
        <span class="order">{{ m.order }}.</span>
        {{ m.name }}
      </li>
    </ul>
    <div class="legend">
      <span>✓ 结果有效</span><span>! 待计算/已过期</span><span>○ 缺少参数</span>
    </div>
  </div>
</template>

<style scoped>
.module-tree { padding: 12px; }
h3 { margin: 0 0 8px; font-size: 14px; color: #555; }
ul { list-style: none; margin: 0; padding: 0; }
li {
  padding: 8px 10px; cursor: pointer; border-radius: 6px;
  display: flex; align-items: center; gap: 6px; font-size: 14px;
}
li:hover { background: #f0f4f8; }
li.active { background: #e3edf7; font-weight: 600; }
.icon { width: 16px; text-align: center; }
.icon[data-state='✓'] { color: #27ae60; }
.icon[data-state='!'] { color: #e67e22; }
.icon[data-state='○'] { color: #999; }
.order { color: #999; }
.legend { margin-top: 16px; font-size: 11px; color: #999; display: flex; flex-direction: column; gap: 2px; }
</style>
